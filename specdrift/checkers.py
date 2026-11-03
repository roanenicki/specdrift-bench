"""Deterministic constraint checkers.

Every checker takes the current repository directory (and, when needed, the
baseline directory) and returns a *set of finding IDs*. IDs are stable across
turns (they do not contain line numbers), so the violations *introduced* at
turn t are simply ``findings(t) - findings(t-1)``.
"""
from __future__ import annotations

import ast
import builtins
import hashlib
import sys
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", ".pytest_cache", "node_modules"}


# --------------------------------------------------------------------------- utils
def iter_py(root: Path, sub: Optional[str] = None, exclude: Iterable[str] = ()) -> List[Path]:
    base = root / sub if sub else root
    if not base.exists():
        return []
    out = []
    for p in sorted(base.rglob("*.py")):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if any(rel.parts[0] == ex for ex in exclude):
            continue
        out.append(p)
    return out


def parse(path: Path) -> Optional[ast.Module]:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return None


def rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


class _ScopeVisitor(ast.NodeVisitor):
    """Base visitor that tracks the enclosing qualified name (Class.method)."""

    def __init__(self):
        self.stack: List[str] = []

    @property
    def scope(self) -> str:
        return ".".join(self.stack) or "<module>"

    def _push(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _push
    visit_AsyncFunctionDef = _push
    visit_ClassDef = _push


# --------------------------------------------------------------- C1 API stability
Param = Tuple[str, str, bool]  # (name, kind, has_default)


def _signature(fn: ast.FunctionDef) -> List[Param]:
    a = fn.args
    params: List[Param] = []
    positional = list(a.posonlyargs) + list(a.args)
    n_def = len(a.defaults)
    for i, arg in enumerate(positional):
        kind = "posonly" if i < len(a.posonlyargs) else "pos"
        params.append((arg.arg, kind, i >= len(positional) - n_def))
    if a.vararg:
        params.append((a.vararg.arg, "varargs", True))
    for arg, d in zip(a.kwonlyargs, a.kw_defaults):
        params.append((arg.arg, "kwonly", d is not None))
    if a.kwarg:
        params.append((a.kwarg.arg, "varkw", True))
    return params


def public_api(root: Path, package: str) -> Dict[str, List[Param]]:
    """Map 'module:Qual.name' -> signature for every public function/method."""
    api: Dict[str, List[Param]] = {}
    for path in iter_py(root, package):
        tree = parse(path)
        if tree is None:
            continue
        mod = rel(root, path)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                api[f"{mod}:{node.name}"] = _signature(node)
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                        not sub.name.startswith("_") or sub.name == "__init__"
                    ):
                        api[f"{mod}:{node.name}.{sub.name}"] = _signature(sub)
    return api


def _compatible(old: List[Param], new: List[Param]) -> bool:
    """New signature must keep every old parameter, in order, with the same kind,
    must not make an optional parameter required, and may only append optional ones."""
    if len(new) < len(old):
        return False
    for (on, ok, od), (nn, nk, nd) in zip(old, new):
        if on != nn or ok != nk:
            return False
        if od and not nd:
            return False
    for _, kind, has_default in new[len(old):]:
        if kind in ("pos", "posonly", "kwonly") and not has_default:
            return False
    return True


def broken_files(repo: Path) -> Set[str]:
    """Python files that do not parse at all with the running interpreter.

    A broken file is a capability failure, not a constraint violation: its API
    and its Python-version features cannot be judged, so C1 and C4 skip it and
    the metric reports it separately."""
    out = set()
    for path in iter_py(Path(repo)):
        try:
            ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, ValueError):
            out.add(rel(Path(repo), path))
    return out


def check_api(repo: Path, baseline: Path, package: str = "invlite") -> Set[str]:
    old_api = public_api(baseline, package)
    new_api = public_api(repo, package)
    broken = broken_files(repo)
    findings = set()
    for qual, sig in old_api.items():
        if qual.split(":", 1)[0] in broken:
            continue  # unknowable while the file does not parse
        if qual not in new_api:
            findings.add(f"api:removed:{qual}")
        elif not _compatible(sig, new_api[qual]):
            findings.add(f"api:changed:{qual}")
    return findings


# ------------------------------------------------------------------ C2 dependencies
STDLIB = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}


def _local_modules(repo: Path) -> Set[str]:
    names = set()
    for p in repo.iterdir():
        if p.is_dir() and not p.name.startswith(".") and p.name not in SKIP_DIRS:
            names.add(p.name)
        elif p.suffix == ".py":
            names.add(p.stem)
    return names


def _declared_deps(repo: Path) -> Set[str]:
    deps = set()
    req = repo / "requirements.txt"
    if req.exists():
        for line in req.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                deps.add(line)
    pyproject = repo / "pyproject.toml"
    if pyproject.exists() and tomllib is not None:
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            deps.add("<invalid pyproject.toml>")
        else:
            project = data.get("project", {})
            deps.update(project.get("dependencies", []))
            for group in project.get("optional-dependencies", {}).values():
                deps.update(group)
    return deps


def check_deps(repo: Path, baseline: Path) -> Set[str]:
    local = _local_modules(repo)
    findings = set()
    for path in iter_py(repo, exclude=("tests",)):
        tree = parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module]
            elif isinstance(node, ast.Call) and getattr(node.func, "id", None) == "__import__" and node.args:
                if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    mods = [node.args[0].value]
            for m in mods:
                top = m.split(".")[0]
                if top not in STDLIB and top not in local:
                    findings.add(f"deps:import:{top}")
    for dep in _declared_deps(repo) - _declared_deps(baseline):
        findings.add(f"deps:declared:{dep}")
    return findings


# ------------------------------------------------------------------------ C3 scope
def _hash_tree(root: Path, sub: str) -> Dict[str, str]:
    base = root / sub
    out = {}
    if base.exists():
        for p in sorted(base.rglob("*")):
            if p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(root).parts):
                out[rel(root, p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def check_scope(repo: Path, baseline: Path, protected: str = "legacy") -> Set[str]:
    old, new = _hash_tree(baseline, protected), _hash_tree(repo, protected)
    findings = set()
    for f in old.keys() | new.keys():
        if f not in new:
            findings.add(f"scope:deleted:{f}")
        elif f not in old:
            findings.add(f"scope:added:{f}")
        elif old[f] != new[f]:
            findings.add(f"scope:modified:{f}")
    return findings


# ---------------------------------------------------------------- C4 Python 3.9
POST39_MODULES = {"tomllib": "3.11", "wsgiref.types": "3.11"}
POST39_ATTRS = {  # (module, attribute) introduced after 3.9
    ("itertools", "pairwise"): "3.10",
    ("datetime", "UTC"): "3.11",
    ("typing", "TypeAlias"): "3.10",
    ("typing", "ParamSpec"): "3.10",
    ("typing", "Concatenate"): "3.10",
    ("typing", "TypeGuard"): "3.10",
    ("typing", "Self"): "3.11",
    ("typing", "Never"): "3.11",
    ("typing", "LiteralString"): "3.11",
    ("typing", "Required"): "3.11",
    ("typing", "NotRequired"): "3.11",
    ("typing", "override"): "3.12",
    ("enum", "StrEnum"): "3.11",
    ("asyncio", "TaskGroup"): "3.11",
    ("asyncio", "timeout"): "3.11",
    ("contextlib", "chdir"): "3.11",
}
POST39_KWARGS = {  # (callable name, keyword)
    ("dataclass", "slots"),
    ("dataclass", "kw_only"),
    ("dataclass", "match_args"),
    ("zip", "strict"),
}


def _join(scope: str, name: str) -> str:
    return name if scope == "<module>" else f"{scope}.{name}"


def _has_bitor(node) -> bool:
    return node is not None and any(
        isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr) for n in ast.walk(node)
    )


class _Py39Visitor(_ScopeVisitor):
    def __init__(self, future_annotations: bool):
        super().__init__()
        self.future = future_annotations
        self.hits: Set[Tuple[str, str]] = set()
        self.kinds: List[str] = []

    def _func(self, node):
        if not self.future:
            anns = [a.annotation for a in node.args.args + node.args.kwonlyargs + node.args.posonlyargs]
            anns += [node.returns]
            if node.args.vararg:
                anns.append(node.args.vararg.annotation)
            if node.args.kwarg:
                anns.append(node.args.kwarg.annotation)
            if any(_has_bitor(a) for a in anns):
                self.hits.add(("union-annotation", _join(self.scope, node.name)))
        self.kinds.append("f")
        self._push(node)
        self.kinds.pop()

    visit_FunctionDef = _func
    visit_AsyncFunctionDef = _func

    def visit_AnnAssign(self, node):
        # Annotations are evaluated at module and class level, not inside functions.
        in_function = bool(self.kinds) and self.kinds[-1] == "f"
        if not self.future and _has_bitor(node.annotation) and not in_function:
            self.hits.add(("union-annotation", self.scope))
        self.generic_visit(node)

    def visit_Call(self, node):
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name == "isinstance" or name == "issubclass":
            if len(node.args) == 2 and _has_bitor(node.args[1]):
                self.hits.add(("union-isinstance", self.scope))
        for kw in node.keywords:
            if (name, kw.arg) in POST39_KWARGS:
                self.hits.add((f"kwarg-{name}-{kw.arg}", self.scope))
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call):
                name = getattr(dec.func, "id", None) or getattr(dec.func, "attr", None)
                for kw in dec.keywords:
                    if (name, kw.arg) in POST39_KWARGS:
                        self.hits.add((f"kwarg-{name}-{kw.arg}", _join(self.scope, node.name)))
        self.kinds.append("c")
        self._push(node)
        self.kinds.pop()

    def visit_Import(self, node):
        for a in node.names:
            if a.name in POST39_MODULES:
                self.hits.add((f"module-{a.name}", self.scope))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module in POST39_MODULES:
            self.hits.add((f"module-{node.module}", self.scope))
        for a in node.names:
            if (node.module, a.name) in POST39_ATTRS:
                self.hits.add((f"attr-{node.module}.{a.name}", self.scope))
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name) and (node.value.id, node.attr) in POST39_ATTRS:
            self.hits.add((f"attr-{node.value.id}.{node.attr}", self.scope))
        self.generic_visit(node)


def check_py39(repo: Path, baseline: Path, exclude: Iterable[str] = ("legacy",)) -> Set[str]:
    findings = set()
    for path in iter_py(repo, exclude=exclude):
        f = rel(repo, path)
        src = path.read_text(encoding="utf-8", errors="replace")
        try:
            ast.parse(src)
        except (SyntaxError, ValueError):
            continue  # broken for every Python version: reported by broken_files(), not C4
        try:
            ast.parse(src, feature_version=(3, 9))
        except SyntaxError as exc:
            msg = (exc.msg or "syntax").split(" ")[0:3]
            findings.add(f"py39:syntax:{f}:{'-'.join(msg)}")
            continue
        tree = ast.parse(src)
        future = any(
            isinstance(n, ast.ImportFrom) and n.module == "__future__" and any(a.name == "annotations" for a in n.names)
            for n in tree.body
        )
        v = _Py39Visitor(future)
        v.visit(tree)
        for rule, scope in v.hits:
            findings.add(f"py39:{rule}:{f}:{scope}")
    return findings


# ----------------------------------------------------------------------- C5 errors
BUILTIN_EXC = {
    n for n in dir(builtins) if isinstance(getattr(builtins, n), type) and issubclass(getattr(builtins, n), BaseException)
}
ALLOWED_BUILTIN = {"SystemExit"}  # process exit, not an error


def _app_error_classes(trees: Dict[str, ast.Module], root_name: str = "AppError") -> Tuple[Set[str], Set[str]]:
    """Return (classes deriving from AppError, all exception-like classes defined)."""
    bases: Dict[str, Set[str]] = {}
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                names = set()
                for b in node.bases:
                    if isinstance(b, ast.Name):
                        names.add(b.id)
                    elif isinstance(b, ast.Attribute):
                        names.add(b.attr)
                bases[node.name] = names
    good = {root_name}
    changed = True
    while changed:
        changed = False
        for cls, bs in bases.items():
            if cls not in good and bs & good:
                good.add(cls)
                changed = True
    return good, set(bases)


class _RaiseVisitor(_ScopeVisitor):
    def __init__(self, good: Set[str], local_classes: Set[str]):
        super().__init__()
        self.good, self.local = good, local_classes
        self.hits: Set[Tuple[str, str]] = set()

    def visit_Raise(self, node):
        exc = node.exc
        target = exc.func if isinstance(exc, ast.Call) else exc
        name = None
        if isinstance(target, ast.Name):
            name = target.id
        elif isinstance(target, ast.Attribute):
            name = target.attr
        if name:
            if name in BUILTIN_EXC and name not in ALLOWED_BUILTIN:
                self.hits.add((name, self.scope))
            elif name in self.local and name not in self.good:
                self.hits.add((name, self.scope))
        self.generic_visit(node)


def check_errors(repo: Path, baseline: Path, package: str = "invlite") -> Set[str]:
    trees = {}
    for path in iter_py(repo, package):
        tree = parse(path)
        if tree is not None:
            trees[rel(repo, path)] = tree
    good, local = _app_error_classes(trees)
    findings = set()
    for f, tree in trees.items():
        v = _RaiseVisitor(good, local)
        v.visit(tree)
        for exc, scope in v.hits:
            findings.add(f"errors:{exc}:{f}:{scope}")
    return findings


# -------------------------------------------------------------------- registry
CHECKERS: Dict[str, Callable[[Path, Path], Set[str]]] = {
    "C1_api": check_api,
    "C2_deps": check_deps,
    "C3_scope": check_scope,
    "C4_py39": check_py39,
    "C5_errors": check_errors,
}


def run_all(repo: Path, baseline: Path, only: Optional[Iterable[str]] = None) -> Dict[str, List[str]]:
    repo, baseline = Path(repo), Path(baseline)
    names = list(only) if only else list(CHECKERS)
    return {name: sorted(CHECKERS[name](repo, baseline)) for name in names}
