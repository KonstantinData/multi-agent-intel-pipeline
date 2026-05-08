"""Safe run artifact path resolution.

Run IDs are identifiers, not filesystem paths.  All runtime code that reads or
writes a persisted run should resolve the identifier through this module.
"""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath

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


def _safe_run_id_to_dir(root: Path, safe_run_id: str) -> Path:
    """Single sanctioned constructor for user-originated run directory paths."""
    if Path(safe_run_id).name != safe_run_id:
        raise InvalidRunIdError("Invalid run_id.")
    if PurePosixPath(safe_run_id).is_absolute():
        raise InvalidRunIdError("Invalid run_id.")
    if PureWindowsPath(safe_run_id).is_absolute() or re.match(r"^[A-Za-z]:", safe_run_id):
        raise InvalidRunIdError("Invalid run_id.")

    return resolve_path_within_runs_root(safe_run_id, runs_root=root)


def _validate_relative_artifact_path_text(path_text: str) -> str:
    """Normalize and validate a relative artifact path text value."""
    normalized = str(path_text or "").strip()
    if not normalized:
        raise InvalidRunIdError("Invalid run_id.")

    # Reject lexical absolute path forms for both POSIX and Windows semantics.
    if normalized.startswith(("/", "\\")):
        raise InvalidRunIdError("Invalid run_id.")
    if re.match(r"^[A-Za-z]:", normalized):
        raise InvalidRunIdError("Invalid run_id.")
    if PurePosixPath(normalized).is_absolute():
        raise InvalidRunIdError("Invalid run_id.")
    if PureWindowsPath(normalized).is_absolute():
        raise InvalidRunIdError("Invalid run_id.")

    parts = [part for part in re.split(r"[\\/]+", normalized) if part]
    if any(part in (".", "..") for part in parts):
        raise InvalidRunIdError("Invalid run_id.")
    return normalized


def resolve_path_within_runs_root(
    candidate_path: str | Path,
    *,
    runs_root: str | Path = RUNS_DIR,
) -> Path:
    """Resolve ``candidate_path`` and enforce containment under ``runs_root``.

    Absolute inputs are accepted only when already under ``runs_root``.
    Relative inputs are resolved from ``runs_root`` and must not contain
    traversal-like segments.
    """
    root = Path(runs_root).resolve(strict=False)
    candidate_text = str(candidate_path)
    candidate_input = Path(candidate_text)

    if candidate_input.is_absolute():
        candidate_resolved = candidate_input.resolve(strict=False)
        try:
            rel = candidate_resolved.relative_to(root)
        except ValueError as exc:
            raise InvalidRunIdError("Invalid run_id.") from exc
        safe_relative_text = _validate_relative_artifact_path_text(str(rel))
    else:
        safe_relative_text = _validate_relative_artifact_path_text(candidate_text)

    candidate = (root / safe_relative_text).resolve(strict=False)
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
    root = Path(runs_root).resolve(strict=False)

    candidate = _find_existing_run_dir(root, safe_run_id)

    if candidate is None:
        if must_exist:
            raise FileNotFoundError("Run was not found.")
        candidate = _safe_run_id_to_dir(root, safe_run_id)

    return _safe_run_id_to_dir(root, candidate.name)
