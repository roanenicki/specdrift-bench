"""Run one multi-turn SpecDrift session with mini-SWE-agent and score it.

Example (from the repository root):

    python -m specdrift.runner --task tasks/t01_invlite \
        --model groq/llama-3.3-70b-versatile --condition continuous \
        --order-row 0 --seed 0 --out runs/

Conditions
    continuous  one conversation; the rules are given at turn 1 only (plus AGENTS.md in the repo)
    recall      one conversation; the rules are repeated in every request
    fresh       a new conversation at every turn (rules + current repo + request, no history)

The agent's bash commands are executed directly in a copy of the task repository.
Run it inside a disposable machine (Kaggle, Colab, a container), never on your own PC.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from importlib import resources
from pathlib import Path
from typing import Callable, Dict, List, Optional

import yaml

from specdrift.metrics import load_task, score_session

CONDITIONS = ("continuous", "recall", "fresh")
IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".git")

INSTANCE_TEMPLATE = """You are working in the repository at {{cwd}} (Python project `{{package}}`).
You will receive a sequence of change requests from the maintainers, one at a time.

## Project rules (from AGENTS.md — they apply to every change, for the whole session)

{{rules}}

## Current request

{{task}}

## How to work

1. Read the relevant files, make the change, and check it (for example with `python -m pytest -q tests`).
2. When the request is done, submit with exactly this command, on its own:
   `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`
3. Every response must contain exactly ONE command in a ```mswea_bash_command block.
   Each command runs in a new subshell, so use `cd {{cwd}} && ...` when needed.

<system_information>
{{system}} {{release}} {{machine}}
</system_information>
"""

NEXT_TURN_TEMPLATE = """## New request

{task}
{reminder}
When this request is done, submit again with `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` (on its own)."""

RECALL_REMINDER = "\n## Reminder: project rules (AGENTS.md)\n\n{rules}\n"


# --------------------------------------------------------------------- ordering
def williams_order(n: int, row: int) -> List[int]:
    """Row `row` of a Williams (balanced Latin square) design for n items.
    Over n rows (n even) every item appears once at every position and every
    item immediately follows every other item exactly once."""
    first = [0]
    lo, hi = 1, n - 1
    for k in range(1, n):
        if k % 2:
            first.append(lo)
            lo += 1
        else:
            first.append(hi)
            hi -= 1
    return [(x + row) % n for x in first]


# ------------------------------------------------------------------------ agent
def _base_agent_config() -> dict:
    cfg_path = resources.files("minisweagent.config") / "mini_textbased.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    return cfg


def make_agent(model, workdir: Path, step_limit: int, cmd_timeout: int):
    """Build a mini-SWE-agent DefaultAgent subclass that supports several turns."""
    from minisweagent.agents.default import DefaultAgent
    from minisweagent.environments.local import LocalEnvironment

    class MultiTurnAgent(DefaultAgent):
        def _loop(self) -> dict:
            from minisweagent.exceptions import FormatError, InterruptAgentFlow

            while True:
                try:
                    self.step()
                    self.n_consecutive_format_errors = 0
                except FormatError as e:
                    self.n_consecutive_format_errors += 1
                    if 0 < self.config.max_consecutive_format_errors <= self.n_consecutive_format_errors:
                        self.add_messages(*e.messages, {"role": "exit", "content": "RepeatedFormatError",
                                                        "extra": {"exit_status": "RepeatedFormatError"}})
                    else:
                        self.add_messages(*e.messages)
                except InterruptAgentFlow as e:
                    self.add_messages(*e.messages)
                if self.messages[-1].get("role") == "exit":
                    return self.messages[-1].get("extra", {})

        def start(self, task: str, **template_vars) -> dict:
            self.extra_template_vars |= {"task": task, **template_vars}
            self.messages = []
            self.add_messages(
                self.model.format_message(role="system", content=self._render_template(self.config.system_template)),
                self.model.format_message(role="user", content=self._render_template(self.config.instance_template)),
            )
            self.config.step_limit = self.n_calls + step_limit
            return self._loop()

        def continue_with(self, text: str) -> dict:
            # 'exit' messages are bookkeeping only and must not be sent to the API.
            self.messages = [m for m in self.messages if m.get("role") != "exit"]
            self.add_messages(self.model.format_message(role="user", content=text))
            self.config.step_limit = self.n_calls + step_limit
            return self._loop()

    cfg = _base_agent_config()["agent"]
    env_cfg = _base_agent_config().get("environment", {})
    env = LocalEnvironment(cwd=str(workdir), timeout=cmd_timeout, env=env_cfg.get("env", {}))
    return MultiTurnAgent(
        model, env,
        system_template=cfg["system_template"],
        instance_template=INSTANCE_TEMPLATE,
        step_limit=step_limit,
        cost_limit=0,
        max_consecutive_format_errors=3,
    )


def make_model(model_name: str, temperature: float, api_base: str = "", max_tokens: int = 2048,
               model_class: str = "litellm_textbased"):
    """`api_base` points LiteLLM to a local OpenAI-compatible server (e.g. vLLM on Kaggle):
    use model names like `hosted_vllm/Qwen/Qwen2.5-Coder-14B-Instruct-AWQ`."""
    from minisweagent.models import get_model

    obs = _base_agent_config()["model"]
    kwargs = {"temperature": temperature, "drop_params": True, "max_tokens": max_tokens}
    if api_base:
        kwargs["api_base"] = api_base
    return get_model(model_name, {
        "model_class": model_class,
        "model_kwargs": kwargs,
        "cost_tracking": "ignore_errors",
        "observation_template": obs["observation_template"],
        "format_error_template": obs["format_error_template"],
    })


# ---------------------------------------------------------------------- helpers
def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-c", "user.name=specdrift-runner", "-c", "user.email=runner@specdrift.invalid", *args],
        cwd=repo, capture_output=True, text=True,
    )
    return r.stdout.strip()


def run_hidden_tests(task_dir: Path, snapshot: Path, test_files: List[str], timeout: int = 300) -> Dict[str, bool]:
    results = {}
    for tf in test_files:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", str(task_dir / tf)],
                env={**os.environ, "PYTHONPATH": f"{snapshot}{os.pathsep}{task_dir / 'hidden_tests'}"},
                cwd=snapshot, capture_output=True, text=True, timeout=timeout,
            )
            results[tf] = r.returncode == 0
        except subprocess.TimeoutExpired:
            results[tf] = False
    return results


# ----------------------------------------------------------------------- session
def run_session(
    task_dir: Path,
    out_dir: Path,
    model_factory: Callable[[], object],
    condition: str,
    order: List[str],
    step_limit: int = 30,
    cmd_timeout: int = 60,
    log: Callable[[str], None] = print,
) -> dict:
    assert condition in CONDITIONS, condition
    task = load_task(task_dir)
    rules = (task_dir / task["repo"] / "AGENTS.md").read_text(encoding="utf-8").strip()
    out_dir.mkdir(parents=True, exist_ok=True)
    workdir = (out_dir / "work").resolve()
    if workdir.exists():
        shutil.rmtree(workdir)
    shutil.copytree(task_dir / task["repo"], workdir, ignore=IGNORE)
    _git(workdir, "init", "-q", "-b", "main")
    _git(workdir, "add", "-A")
    _git(workdir, "commit", "-qm", "baseline")

    snapshots: List[Path] = []
    turns_meta = []
    agent = None
    tmpl_vars = {"rules": rules, "package": task.get("package", ""), "cwd": str(workdir)}
    for t, rid in enumerate(order, start=1):
        req = task["_requests"][rid]
        text = req["text"].strip()
        t0 = time.time()
        if condition == "fresh" or agent is None:
            if agent is not None:
                agent.save(out_dir / "trajectories" / f"turn_{t - 1:02d}.json")
            agent = make_agent(model_factory(), workdir, step_limit, cmd_timeout)
            calls_before = 0
            try:
                info = agent.start(text, **tmpl_vars)
            except Exception as e:  # API failure etc.: record and stop the session
                info = {"exit_status": f"Error:{type(e).__name__}", "error": str(e)[:500]}
        else:
            reminder = RECALL_REMINDER.format(rules=rules) if condition == "recall" else ""
            calls_before = agent.n_calls
            try:
                info = agent.continue_with(NEXT_TURN_TEMPLATE.format(task=text, reminder=reminder))
            except Exception as e:
                info = {"exit_status": f"Error:{type(e).__name__}", "error": str(e)[:500]}

        _git(workdir, "add", "-A")
        _git(workdir, "commit", "-qm", f"turn {t}: {rid}", "--allow-empty")
        snap = out_dir / "snapshots" / f"turn_{t:02d}"
        if snap.exists():
            shutil.rmtree(snap)
        shutil.copytree(workdir, snap, ignore=IGNORE)
        snapshots.append(snap)
        if condition == "fresh":
            agent.save(out_dir / "trajectories" / f"turn_{t:02d}.json")

        own = run_hidden_tests(task_dir, snap, [req["hidden_test"]])
        turns_meta.append({
            "turn": t, "request": rid,
            "exit_status": info.get("exit_status", ""),
            "error": info.get("error"),
            "model_calls": agent.n_calls - calls_before,
            "seconds": round(time.time() - t0, 1),
            "functional_pass": own[req["hidden_test"]],
        })
        log(f"  turn {t:2d} {rid:20s} exit={turns_meta[-1]['exit_status']:18s} "
            f"calls={turns_meta[-1]['model_calls']:3d} functional={'pass' if own[req['hidden_test']] else 'FAIL'}")
        if str(info.get("exit_status", "")).startswith("Error:"):
            log("  session aborted after an API error; partial results are kept")
            break

    if condition != "fresh" and agent is not None:
        agent.save(out_dir / "trajectories" / "session.json")

    # Regression: every request done so far, checked on the final state.
    done = [task["_requests"][m["request"]]["hidden_test"] for m in turns_meta]
    final = run_hidden_tests(task_dir, snapshots[-1], done) if snapshots else {}

    scored = score_session(task_dir, [m["request"] for m in turns_meta], snapshots)
    for rec, meta in zip(scored["turns"], turns_meta):
        rec.update({k: v for k, v in meta.items() if k not in ("turn", "request")})
    scored["condition"] = condition
    scored["final_regression"] = final
    scored["summary"]["functional_success_rate"] = (
        round(sum(m["functional_pass"] for m in turns_meta) / len(turns_meta), 4) if turns_meta else None
    )
    (out_dir / "results.json").write_text(json.dumps(scored, indent=2), encoding="utf-8")
    shutil.rmtree(workdir, ignore_errors=True)
    return scored


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", type=Path, required=True)
    ap.add_argument("--model", required=True, help="LiteLLM model name, e.g. groq/llama-3.3-70b-versatile")
    ap.add_argument("--condition", choices=CONDITIONS, required=True)
    ap.add_argument("--order-row", type=int, default=0, help="row of the Williams design (0..n-1)")
    ap.add_argument("--seed", type=int, default=0, help="repetition index, only used in the output path")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--api-base", default="", help="URL of a local OpenAI-compatible server, e.g. http://localhost:8000/v1")
    ap.add_argument("--step-limit", type=int, default=30, help="max model calls per turn")
    ap.add_argument("--n-turns", type=int, default=0, help="run only the first N requests (0 = all)")
    ap.add_argument("--out", type=Path, default=Path("runs"))
    a = ap.parse_args(argv)

    task = load_task(a.task)
    ids = [r["id"] for r in task["requests"]]
    order = [ids[i] for i in williams_order(len(ids), a.order_row)]
    if a.n_turns:
        order = order[: a.n_turns]
    safe_model = a.model.replace("/", "__")
    out = a.out / task["id"] / safe_model / a.condition / f"row{a.order_row:02d}_seed{a.seed}"
    print(f"session -> {out}\norder: {', '.join(order)}")
    res = run_session(a.task, out, lambda: make_model(a.model, a.temperature, a.api_base), a.condition, order, a.step_limit)
    print(json.dumps(res["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
