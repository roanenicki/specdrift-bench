"""Scoring on a simulated 3-turn session built from file edits."""
import shutil
from pathlib import Path

from specdrift.metrics import score_session

TASK = Path(__file__).resolve().parents[1] / "tasks" / "t01_invlite"


def snapshot(src, dst, edits=()):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    for f, old, new in edits:
        p = dst / f
        p.write_text(p.read_text().replace(old, new, 1))
    return dst


def test_session_scoring(tmp_path):
    base = TASK / "repo"
    # turn 1 (r09, opportunity C1): compliant -> F = 1
    s1 = snapshot(base, tmp_path / "t1")
    # turn 2 (r05, opportunity C3): edits legacy -> F = 0
    s2 = snapshot(s1, tmp_path / "t2", [("legacy/old_report.py", "avg = total / len(items)", "avg = 0")])
    # turn 3 (r01, opportunity C5): legacy edit is inherited (not re-counted),
    # plus a spontaneous dependency import (no C2 opportunity at r01)
    s3 = snapshot(s2, tmp_path / "t3", [("invlite/io.py", "import csv", "import csv\nimport requests")])

    res = score_session(TASK, ["r09_delete_item", "r05_report_empty", "r01_search"], [s1, s2, s3])
    f = [t["F"] for t in res["turns"]]
    assert f == [1.0, 0.0, 1.0]
    assert res["turns"][1]["violations_on_opportunity"] == ["C3_scope"]
    assert res["turns"][2]["introduced"] == {"C2_deps": ["deps:import:requests"]}
    assert res["turns"][2]["spontaneous_violations"] == ["C2_deps"]
    assert res["summary"]["violations_total"] == 2
