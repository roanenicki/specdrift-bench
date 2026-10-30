"""End-to-end test of the runner with a scripted (deterministic) model: no API needed."""
from pathlib import Path

import pytest

pytest.importorskip("minisweagent")

from minisweagent.models.test_models import DeterministicModel, make_output  # noqa: E402

from specdrift.runner import run_session, williams_order  # noqa: E402

TASK = Path(__file__).resolve().parents[1] / "tasks" / "t01_invlite"
SUBMIT = {"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"}


def test_williams_is_balanced_latin_square():
    n = 10
    rows = [williams_order(n, r) for r in range(n)]
    for row in rows:
        assert sorted(row) == list(range(n))
    for pos in range(n):
        assert sorted(r[pos] for r in rows) == list(range(n))
    pairs = {(r[i], r[i + 1]) for r in rows for i in range(n - 1)}
    assert len(pairs) == n * (n - 1)  # every ordered pair appears exactly once


def scripted_turns():
    # turn 1 (r09_delete_item): naive rename -> C1 violation, functional test passes
    t1 = [
        make_output("look", [{"command": "ls invlite"}]),
        make_output("rename", [{"command": "sed -i 's/def remove_item(self, sku):/def delete_item(self, sku):/' invlite/store.py"}]),
        make_output("done", [SUBMIT]),
    ]
    # turn 2 (r05_report_empty): patches legacy -> C3 violation, functional test passes
    t2 = [
        make_output("fix", [{"command": "sed -i 's|avg = total / len(items)|avg = total / len(items) if items else 0.0|' legacy/old_report.py"}]),
        make_output("done", [SUBMIT]),
    ]
    return t1, t2


def test_continuous_session(tmp_path):
    t1, t2 = scripted_turns()
    model = DeterministicModel(outputs=t1 + t2)
    res = run_session(TASK, tmp_path / "s", lambda: model, "continuous", ["r09_delete_item", "r05_report_empty"],
                      log=lambda *_: None)
    turns = res["turns"]
    assert [t["F"] for t in turns] == [0.0, 0.0]
    assert turns[0]["introduced"] == {"C1_api": ["api:removed:invlite/store.py:InventoryStore.remove_item"]}
    assert turns[1]["introduced"] == {"C3_scope": ["scope:modified:legacy/old_report.py"]}
    assert [t["functional_pass"] for t in turns] == [True, True]
    assert [t["model_calls"] for t in turns] == [3, 2]
    assert res["summary"]["functional_success_rate"] == 1.0
    assert (tmp_path / "s" / "trajectories" / "session.json").exists()
    # the conversation must never contain an 'exit' message in the middle
    import json

    msgs = json.loads((tmp_path / "s" / "trajectories" / "session.json").read_text())["messages"]
    assert [m["role"] for m in msgs[:-1]].count("exit") == 0
    requests = [m["content"] for m in msgs if m["role"] == "user" and "## New request" in m["content"]]
    assert len(requests) == 1 and "Reminder" not in requests[0]


def test_recall_adds_reminder(tmp_path):
    t1, t2 = scripted_turns()
    model = DeterministicModel(outputs=t1 + t2)
    run_session(TASK, tmp_path / "s", lambda: model, "recall", ["r09_delete_item", "r05_report_empty"],
                log=lambda *_: None)
    import json

    msgs = json.loads((tmp_path / "s" / "trajectories" / "session.json").read_text())["messages"]
    last_user = [m["content"] for m in msgs if m["role"] == "user" and "## New request" in m["content"]][-1]
    assert "Reminder: project rules" in last_user and "Public API is frozen" in last_user


def test_fresh_uses_new_conversation_each_turn(tmp_path):
    t1, t2 = scripted_turns()
    scripts = iter([t1, t2])
    res = run_session(TASK, tmp_path / "s", lambda: DeterministicModel(outputs=next(scripts)), "fresh",
                      ["r09_delete_item", "r05_report_empty"], log=lambda *_: None)
    assert [t["F"] for t in res["turns"]] == [0.0, 0.0]
    assert (tmp_path / "s" / "trajectories" / "turn_01.json").exists()
    assert (tmp_path / "s" / "trajectories" / "turn_02.json").exists()


def test_step_limit_per_turn(tmp_path):
    # the agent never submits: the turn must stop at the step limit and the session go on
    looping = [make_output("loop", [{"command": "true"}])] * 3
    t2 = [make_output("done", [SUBMIT])]
    model = DeterministicModel(outputs=looping + t2)
    res = run_session(TASK, tmp_path / "s", lambda: model, "continuous", ["r01_search", "r02_get_default"],
                      step_limit=3, log=lambda *_: None)
    assert [t["exit_status"] for t in res["turns"]] == ["LimitsExceeded", "Submitted"]
    assert [t["functional_pass"] for t in res["turns"]] == [False, False]
