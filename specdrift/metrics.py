"""Per-turn scoring: introduced violations and step-wise fidelity F(t).

Usage (from the repository root):
    python -m specdrift.metrics --task tasks/t01_invlite \
        --order r03_fx,r09_delete_item,... --snapshots run/turn_01 run/turn_02 ...

`snapshots[k]` is the repository state after turn k+1 (e.g. a `git worktree`
checkout of the agent's commit at the end of each turn).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import yaml

from specdrift.checkers import CHECKERS, broken_files, run_all


def load_task(task_dir: Path) -> dict:
    task = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))
    task["_dir"] = task_dir
    task["_requests"] = {r["id"]: r for r in task["requests"]}
    return task


def score_session(task_dir: Path, order: Sequence[str], snapshots: Sequence[Path]) -> dict:
    """Return per-turn records and the summary used in the paper.

    For each turn t and constraint c:
      o(c,t) = 1 if request t lists c among its opportunities
      v(c,t) = 1 if a finding for c appears at t that was absent at t-1
    F(t) = 1 - sum_c o*v / sum_c o   (undefined when no opportunity at t)
    Violations without an opportunity are reported separately ("spontaneous").
    """
    task = load_task(Path(task_dir))
    baseline = Path(task_dir) / task["repo"]
    if len(order) != len(snapshots):
        raise ValueError("order and snapshots must have the same length")

    prev = {c: set() for c in CHECKERS}  # baseline is clean by construction
    turns = []
    for t, (rid, snap) in enumerate(zip(order, snapshots), start=1):
        req = task["_requests"][rid]
        opps = set(req.get("opportunities", []))
        now = {c: set(v) for c, v in run_all(Path(snap), baseline).items()}
        introduced = {c: sorted(now[c] - prev[c]) for c in CHECKERS}
        violated = {c for c, f in introduced.items() if f}
        o = len(opps)
        ov = len(opps & violated)
        turns.append({
            "turn": t,
            "request": rid,
            "opportunities": sorted(opps),
            "introduced": {c: f for c, f in introduced.items() if f},
            "violations_on_opportunity": sorted(opps & violated),
            "spontaneous_violations": sorted(violated - opps),
            "F": None if o == 0 else round(1 - ov / o, 4),
            "active_findings": sum(len(v) for v in now.values()),
            "broken_files": sorted(broken_files(Path(snap))),
        })
        prev = now
    defined = [r["F"] for r in turns if r["F"] is not None]
    summary = {
        "mean_F": round(sum(defined) / len(defined), 4) if defined else None,
        "violations_total": sum(len(r["violations_on_opportunity"]) + len(r["spontaneous_violations"]) for r in turns),
        "opportunities_total": sum(len(r["opportunities"]) for r in turns),
    }
    return {"task": task["id"], "order": list(order), "turns": turns, "summary": summary}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, type=Path)
    ap.add_argument("--order", required=True, help="comma-separated request ids, in session order")
    ap.add_argument("--snapshots", required=True, nargs="+", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    result = score_session(a.task, a.order.split(","), a.snapshots)
    text = json.dumps(result, indent=2)
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
