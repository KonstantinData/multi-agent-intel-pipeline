"""Safe run artifact path resolution.

Run IDs are identifiers, not filesystem paths.  All runtime code that reads or
writes a persisted run should resolve the identifier through this module.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "artifacts" / "runs"

_TIMESTAMP_RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z$")
_FIXTURE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")


class InvalidRunIdError(ValueError):
    """Raised when a run_id is not a safe run identifier."""


def validate_run_id(run_id: str) -> str:
    """Return a normalized safe run_id or raise ``InvalidRunIdError``.

    Production run IDs use ``YYYYMMDDTHHMMSSZ``.  Dependency-light tests and
    golden fixtures also use explicit basename-only fixture IDs, so safe
    alphanumeric identifiers with ``_`` and ``-`` are accepted.  Path
    separators, dots, drive letters, and absolute paths are rejected by design.
    """
    normalized = str(run_id or "").strip()
    if _TIMESTAMP_RUN_ID_RE.fullmatch(normalized):
        return normalized
    if _FIXTURE_RUN_ID_RE.fullmatch(normalized):
        return normalized
    raise InvalidRunIdError("Invalid run_id.")


def resolve_run_dir(
    run_id: str,
    *,
    runs_root: str | Path = RUNS_DIR,
    must_exist: bool = False,
) -> Path:
    """Resolve ``run_id`` to a directory under ``runs_root``.

    The returned path is resolved and proven to be inside the resolved run root.
    Error messages deliberately avoid echoing filesystem paths.
    """
    safe_run_id = validate_run_id(run_id)
    root = Path(runs_root).resolve()

    candidate: Path | None = None
    if root.exists():
        for child in root.iterdir():
            if child.is_dir() and child.name == safe_run_id:
                candidate = child.resolve()
                break

    if candidate is None:
        if must_exist:
            raise FileNotFoundError("Run was not found.")
        candidate = (root / safe_run_id).resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise InvalidRunIdError("Invalid run_id.") from exc
    return candidate

