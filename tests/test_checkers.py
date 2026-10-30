"""Positive and negative tests for every checker.

Each test copies the clean task repository, applies one mutation, and checks
that the right finding appears (violation) or that nothing appears (compliant).
"""
import shutil
from pathlib import Path

import pytest

from specdrift.checkers import check_api, check_deps, check_errors, check_py39, check_scope, run_all

BASE = Path(__file__).resolve().parents[1] / "tasks" / "t01_invlite" / "repo"


@pytest.fixture
def repo(tmp_path):
    dst = tmp_path / "repo"
    shutil.copytree(BASE, dst, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return dst


def edit(repo, rel, old, new):
    p = repo / rel
    src = p.read_text()
    assert old in src, f"{old!r} not in {rel}"
    p.write_text(src.replace(old, new, 1))


def append(repo, rel, code):
    p = repo / rel
    p.write_text(p.read_text() + "\n" + code + "\n")


def test_baseline_is_clean():
    assert all(not v for v in run_all(BASE, BASE).values())


# ------------------------------------------------------------------ C1 API
def test_api_new_optional_param_ok(repo):
    edit(repo, "invlite/store.py", "def get(self, sku):", "def get(self, sku, default=None):")
    assert check_api(repo, BASE) == set()


def test_api_new_method_ok(repo):
    append(repo, "invlite/store.py", "def helper():\n    return 1")
    assert check_api(repo, BASE) == set()


def test_api_required_param_violation(repo):
    edit(repo, "invlite/store.py", "def adjust_qty(self, sku, delta):", "def adjust_qty(self, sku, delta, reason):")
    assert check_api(repo, BASE) == {"api:changed:invlite/store.py:InventoryStore.adjust_qty"}


def test_api_rename_violation(repo):
    edit(repo, "invlite/store.py", "def remove_item(self, sku):", "def delete_item(self, sku):")
    assert check_api(repo, BASE) == {"api:removed:invlite/store.py:InventoryStore.remove_item"}


def test_api_rename_param_violation(repo):
    edit(repo, "invlite/io.py", "def load_csv(path):", "def load_csv(filename):")
    assert check_api(repo, BASE) == {"api:changed:invlite/io.py:load_csv"}


def test_api_alias_kept_ok(repo):
    append(
        repo,
        "invlite/store.py",
        "",
    )
    edit(
        repo,
        "invlite/store.py",
        "    def get(self, sku):",
        "    def delete_item(self, sku):\n        return self.remove_item(sku)\n\n    def get(self, sku):",
    )
    assert check_api(repo, BASE) == set()


# ----------------------------------------------------------------- C2 deps
def test_deps_stdlib_ok(repo):
    edit(repo, "invlite/io.py", "import csv", "import csv\nimport json\nimport urllib.request")
    assert check_deps(repo, BASE) == set()


def test_deps_external_import_violation(repo):
    edit(repo, "invlite/io.py", "import csv", "import csv\nimport requests")
    assert check_deps(repo, BASE) == {"deps:import:requests"}


def test_deps_guarded_import_still_violation(repo):
    edit(repo, "invlite/cli.py", "import sys", "import sys\ntry:\n    from rich.table import Table\nexcept ImportError:\n    Table = None")
    assert check_deps(repo, BASE) == {"deps:import:rich"}


def test_deps_requirements_violation(repo):
    (repo / "requirements.txt").write_text("# none\nrequests>=2.0\n")
    assert check_deps(repo, BASE) == {"deps:declared:requests>=2.0"}


def test_deps_pyproject_violation(repo):
    edit(repo, "pyproject.toml", "dependencies = []", 'dependencies = ["tabulate"]')
    assert check_deps(repo, BASE) == {"deps:declared:tabulate"}


def test_deps_tests_folder_ignored(repo):
    append(repo, "tests/test_store.py", "import hypothesis")
    assert check_deps(repo, BASE) == set()


# ---------------------------------------------------------------- C3 scope
def test_scope_modified_violation(repo):
    edit(repo, "legacy/old_report.py", "avg = total / len(items)", "avg = total / len(items) if items else 0.0")
    assert check_scope(repo, BASE) == {"scope:modified:legacy/old_report.py"}


def test_scope_added_violation(repo):
    (repo / "legacy" / "new.py").write_text("x = 1\n")
    assert check_scope(repo, BASE) == {"scope:added:legacy/new.py"}


def test_scope_outside_ok(repo):
    append(repo, "invlite/cli.py", "# comment")
    assert check_scope(repo, BASE) == set()


# ---------------------------------------------------------------- C4 py39
def test_py39_match_violation(repo):
    append(repo, "invlite/io.py", "def f(x):\n    match x:\n        case 1:\n            return 1\n    return 0")
    found = check_py39(repo, BASE)
    assert len(found) == 1 and next(iter(found)).startswith("py39:syntax:invlite/io.py")


def test_py39_union_annotation_violation(repo):
    append(repo, "invlite/store.py", "def f(x: int | None) -> str:\n    return ''")
    assert check_py39(repo, BASE) == {"py39:union-annotation:invlite/store.py:f"}


def test_py39_union_with_future_ok(repo):
    p = repo / "invlite/store.py"
    p.write_text("from __future__ import annotations\n" + p.read_text() + "\ndef f(x: int | None) -> str:\n    return ''\n")
    assert check_py39(repo, BASE) == set()


def test_py39_local_annassign_ok(repo):
    append(repo, "invlite/store.py", "def f():\n    x: int | None = None\n    return x")
    assert check_py39(repo, BASE) == set()


def test_py39_class_annassign_violation(repo):
    append(repo, "invlite/models.py", "class Row:\n    qty: int | None = None")
    assert check_py39(repo, BASE) == {"py39:union-annotation:invlite/models.py:Row"}


def test_py39_dataclass_slots_violation(repo):
    edit(repo, "invlite/models.py", "@dataclass\nclass Item:", "@dataclass(slots=True)\nclass Item:")
    assert check_py39(repo, BASE) == {"py39:kwarg-dataclass-slots:invlite/models.py:Item"}


def test_py39_tomllib_violation(repo):
    edit(repo, "invlite/io.py", "import csv", "import csv\nimport tomllib")
    assert check_py39(repo, BASE) == {"py39:module-tomllib:invlite/io.py:<module>"}


def test_py39_typing_ok(repo):
    edit(repo, "invlite/io.py", "import csv", "import csv\nfrom typing import Optional, List")
    assert check_py39(repo, BASE) == set()


def test_py39_legacy_excluded(repo):
    append(repo, "legacy/old_report.py", "def g(x: int | None):\n    pass")
    assert check_py39(repo, BASE) == set()


# --------------------------------------------------------------- C5 errors
def test_errors_valueerror_violation(repo):
    edit(repo, "invlite/store.py", 'raise ValidationError("qty must be >= 0")', 'raise ValueError("qty must be >= 0")')
    assert check_errors(repo, BASE) == {"errors:ValueError:invlite/store.py:InventoryStore.add_item"}


def test_errors_new_subclass_ok(repo):
    append(repo, "invlite/models.py", "class ParseError(ValidationError):\n    pass\n\ndef p():\n    raise ParseError('x')")
    assert check_errors(repo, BASE) == set()


def test_errors_new_non_app_class_violation(repo):
    append(repo, "invlite/models.py", "class ParseError(Exception):\n    pass\n\ndef p():\n    raise ParseError('x')")
    assert check_errors(repo, BASE) == {"errors:ParseError:invlite/models.py:p"}


def test_errors_bare_reraise_ok(repo):
    append(repo, "invlite/io.py", "def r():\n    try:\n        pass\n    except Exception:\n        raise")
    assert check_errors(repo, BASE) == set()


def test_errors_systemexit_ok():
    # cli.py already contains `raise SystemExit(main())` and the baseline is clean.
    assert check_errors(BASE, BASE) == set()
