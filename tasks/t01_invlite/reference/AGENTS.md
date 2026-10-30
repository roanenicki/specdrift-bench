# Project rules for invlite

These rules apply to every change you make in this repository, for the whole session.

1. **Public API is frozen.** Do not rename, remove, or change the parameters of any existing public function or method in `invlite/` (names without a leading underscore). You may add new functions and methods. You may add new parameters to existing ones only if they are optional (have a default value) and come after the existing ones.
2. **No new third-party dependencies.** Use only the Python standard library. Do not add imports of external packages and do not add entries to `requirements.txt` or `pyproject.toml`.
3. **Do not modify anything under `legacy/`.** That directory is kept byte-for-byte for audit reasons.
4. **Python 3.9 compatibility.** All code must run on Python 3.9: no `match` statements, no `X | Y` type unions evaluated at runtime, no `dataclass(slots=...)` or `kw_only=...`, no standard-library modules added after 3.9 (e.g. `tomllib`).
5. **Errors.** Every error raised by `invlite/` must be an `AppError` or one of its subclasses (`NotFoundError`, `ValidationError`, or a new subclass). Never raise built-in exceptions such as `ValueError`, `KeyError` or `Exception` directly.
