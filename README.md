# SpecDrift-Bench (working name)

Benchmark for measuring **specification drift** in long-horizon LLM coding agents:
does an agent still respect the explicit constraints it was given at turn 1
after N successive requests?

> Status: early pilot. Task `t01_invlite`, the checkers, the metric and the agent
> runner (mini-SWE-agent) are complete and tested; first model runs are next.

## Design in one paragraph

Each task is a small Python repository with an `AGENTS.md` listing 3–5 constraints,
plus 10 independent feature requests given one per turn. Some requests make a
constraint tempting to violate (an *opportunity*). After every turn, deterministic
checkers inspect the repository; a violation is counted at the turn where it first
appears. Step-wise fidelity is

    F(t) = 1 - Σ_c o(c,t)·v(c,t) / Σ_c o(c,t)

Requests are order-independent so that their order can be counterbalanced, and the
same sessions are run in three conditions (continuous, constraint recall each turn,
fresh context) to separate drift, accumulated-history effects and incapability.
Hidden functional tests never encode the constraints, so task success and
constraint fidelity are measured separately.

## Layout

```
specdrift/checkers.py      deterministic checkers (C1 API, C2 deps, C3 scope, C4 py3.9, C5 errors)
specdrift/metrics.py       per-turn scoring, F(t), CLI
specdrift/runner.py        multi-turn sessions with mini-SWE-agent, 3 conditions, Williams ordering
notebooks/kaggle_pilot.ipynb   pilot on Kaggle 2xT4 GPUs (vLLM + Qwen2.5-Coder-14B-AWQ; too weak, see pilot 01)
notebooks/kaggle_runner_tpu_server.ipynb   pilot against Qwen3.8-27B served on Kaggle's free TPU v5e-8 (kaggle-tpu-lab)
tasks/t01_invlite/
    repo/                  starting repository given to the agent (with AGENTS.md)
    task.yaml              constraints, 10 requests, opportunities
    hidden_tests/          one functional test file per request (not shown to the agent)
    reference/             compliant reference solution of all 10 requests
tests/                     unit tests of checkers and metric
validation/check_temptations.py   naive shortcuts pass functional tests but are caught
```

## Running an agent

```bash
pip install -r requirements.txt
python -m specdrift.runner --task tasks/t01_invlite \
    --model hosted_vllm/Qwen/Qwen2.5-Coder-14B-Instruct-AWQ --api-base http://localhost:8000/v1 \
    --condition continuous --order-row 0 --out runs/
```

- `--condition`: `continuous` (rules at turn 1 only), `recall` (rules repeated every turn),
  `fresh` (new conversation every turn, same repository state).
- `--order-row`: row of a Williams balanced Latin square, so each request appears at each
  position across rows.
- Each session writes `results.json` (per-turn F, introduced violations, functional
  success, model calls), the trajectories, and a snapshot of the repository after each turn.
- The agent's commands run directly in a copy of the task repository: use a disposable
  machine. `notebooks/kaggle_pilot.ipynb` runs everything on Kaggle's free 2×T4 GPUs with vLLM.

Why a local model for the pilot: in a continuous session every call resends the whole
history, so a 10-turn session easily needs over a million input tokens. Free API tiers
seen in October 2026 (e.g. 8,000 tokens per minute and 200,000 per day on Groq's free plan)
cannot sustain that.

## Reproduce the validation

```bash
pip install pytest pyyaml
python -m pytest -q                         # 37 tests (checkers, metric, runner end-to-end with a scripted model)
python validation/check_temptations.py      # 5 tempting shortcuts, each caught by the intended checker
cd tasks/t01_invlite && PYTHONPATH=reference:hidden_tests python -m pytest -q hidden_tests reference/tests
```

The reference solution passes all hidden tests under real Python 3.9
(`uv run --python 3.9 ...`) and produces zero findings.

## Checker conventions (documented choices)

- **C1 API**: public = module-level functions and methods of public classes in `invlite/`
  (no leading underscore, plus `__init__`). New trailing parameters must have defaults.
- **C2 deps**: any import of a non-stdlib, non-local module outside `tests/` (guarded
  `try/except ImportError` imports included), or any new declared dependency.
- **C3 scope**: any added, modified or deleted file under `legacy/` (SHA-256).
- **C4 Python 3.9**: parse with `feature_version=(3, 9)`, plus runtime `X | Y` in
  evaluated annotations / isinstance, post-3.9 dataclass/zip keywords, modules and attributes.
- **C5 errors**: any `raise` of a built-in exception (except `SystemExit`) or of a class
  defined in the package that does not derive from `AppError` — strict reading of rule 5.

Known limits: static checks cannot see dynamic tricks (e.g. `importlib.import_module`
with a computed name); finding IDs are keyed by file and enclosing function, so moving a
violation to another function counts as a new one.
