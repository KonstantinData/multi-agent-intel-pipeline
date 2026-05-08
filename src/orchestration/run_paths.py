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


def _find_existing_run_dir(root: Path, safe_run_id: str) -> Path | None:
    """Return the resolved run directory matching ``safe_run_id`` under ``root``."""
    if not root.exists():
        return None
    for child in root.iterdir():
        if child.is_dir() and child.name == safe_run_id:
            return child.resolve()
    return None


def _resolve_within_root(root: Path, leaf_name: str) -> Path:
    """Resolve ``leaf_name`` under ``root`` and enforce containment."""
    safe_leaf_name = validate_run_id(leaf_name)
    leaf_path = Path(safe_leaf_name)
    if leaf_path.is_absolute() or leaf_path.name != safe_leaf_name or any(
        part in ("", ".", "..") for part in leaf_path.parts
    ):
        raise InvalidRunIdError("Invalid run_id.")
    candidate = (root / safe_leaf_name).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise InvalidRunIdError("Invalid run_id.") from exc
    return candidate


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

    candidate = _find_existing_run_dir(root, safe_run_id)

    if candidate is None:
        if must_exist:
            raise FileNotFoundError("Run was not found.")
        # Defense in depth: enforce basename semantics before constructing path.
        basename = Path(safe_run_id).name
        if basename != safe_run_id:
            raise InvalidRunIdError("Invalid run_id.")
        candidate = _resolve_within_root(root, basename)

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise InvalidRunIdError("Invalid run_id.") from exc
    return candidate

