"""Write run artifacts to disk."""
from __future__ import annotations

import json
import logging
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from filelock import FileLock

from src.app.use_cases import (
    DISCOVERY_READY_RUN_STATUS,
    SUCCESS_RUN_STATUS,
    sanitize_success_unresolved,
)
from src.orchestration.run_paths import (
    RUNS_DIR,
    InvalidRunIdError,
    resolve_path_within_runs_root,
    resolve_run_dir,
    validate_run_id,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SafeRunPath:
    """Resolved path constrained to RUNS_DIR."""

    path: Path


def _ensure_within_runs_dir(path: str | Path, runs_root: Path | None = None) -> SafeRunPath:
    """Resolve and enforce that ``path`` is contained in the trusted runs root."""
    effective_root = (runs_root if runs_root is not None else RUNS_DIR).resolve(strict=False)
    candidate = Path(path)
    if candidate.is_absolute():
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(effective_root)
        except ValueError as exc:
            raise ValueError("Refusing to write outside runs directory.") from exc
        return SafeRunPath(path=resolved)
    try:
        resolved = resolve_path_within_runs_root(path, runs_root=effective_root)
    except InvalidRunIdError as exc:
        raise ValueError("Invalid relative artifact path.") from exc
    return SafeRunPath(path=resolved)


def atomic_write_json(target: SafeRunPath, payload: Any, runs_root: Path | None = None) -> None:
    """Write JSON atomically via a same-directory tempfile and replace; expects sanitized path only."""
    safe_parent = target.path.parent
    safe_parent.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", target.path.name).strip("._-") or "artifact"
    encoded = json.dumps(payload, indent=2, ensure_ascii=False)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        prefix=f".{safe_name}.",
        suffix=".tmp",
        delete=False,
        dir=str(safe_parent),
    ) as handle:
        handle.write(encoded)
        handle.flush()
        temp_name = handle.name
        # Path-injection hardening and static-analysis clarity for temp file containment.
        temp_path = Path(temp_name).resolve(strict=False)
        if temp_path.parent != safe_parent.resolve(strict=False):
            raise ValueError("Temporary file escaped the target directory.")
    safe_target = _ensure_within_runs_dir(target.path, runs_root).path
    # Explicit containment assertions before replace for hardening/static-analysis clarity.
    safe_temp = _ensure_within_runs_dir(temp_path, runs_root).path
    safe_temp.replace(safe_target)


def _sanitize_pipeline_data_for_status(
    *,
    status: str,
    pipeline_data: dict[str, Any],
    run_context: dict[str, Any],
) -> dict[str, Any]:
    data = dict(pipeline_data)
    if isinstance(run_context, dict):
        report_package = run_context.get("report_package")
        if isinstance(report_package, dict) and report_package:
            data["report_package"] = report_package
        meeting_readiness = run_context.get("meeting_readiness_assessment")
        if isinstance(meeting_readiness, dict) and meeting_readiness:
            data["meeting_readiness_assessment"] = meeting_readiness
        final_briefing = run_context.get("final_briefing")
        if isinstance(final_briefing, dict) and final_briefing:
            data["final_briefing"] = final_briefing
    if status != SUCCESS_RUN_STATUS:
        return data
    synthesis = dict(data.get("synthesis", {}) or {})
    synthesis.pop("open_questions", None)
    data["synthesis"] = synthesis
    return data


def _extract_export_unresolved(*, status: str, run_context: dict[str, Any]) -> dict[str, list[str]]:
    resolution_plan = (
        (run_context or {}).get("resolution_state", {}).get("resolution_plan", {})
        if isinstance(run_context, dict)
        else {}
    )
    unresolved = resolution_plan.get("unresolved", {}) if isinstance(resolution_plan, dict) else {}
    if status == SUCCESS_RUN_STATUS:
        return sanitize_success_unresolved(unresolved)
    if status == DISCOVERY_READY_RUN_STATUS:
        cleaned: dict[str, list[str]] = {}
        for key, value in (unresolved or {}).items():
            if isinstance(value, list):
                cleaned[key] = [str(item).strip() for item in value if str(item).strip()]
        return cleaned
    return {}


def export_run(
    *,
    run_dir: str | Path,
    run_id: str,
    company_name: str,
    web_domain: str,
    status: str,
    messages: list[dict[str, Any]],
    pipeline_data: dict[str, Any],
    run_context: dict[str, Any],
    usage: dict[str, Any] | None = None,
    budget: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    safe_run_dir = _ensure_within_runs_dir(run_dir)
    safe_run_dir.path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).isoformat()

    run_meta = {
        "run_id": run_id,
        "timestamp": timestamp,
        "company_name": company_name,
        "web_domain": web_domain,
        "status": status,
        "usage": usage or {},
        "budget": budget or {},
        "error": error,
        "unresolved": _extract_export_unresolved(status=status, run_context=run_context),
        "meeting_readiness": (run_context or {}).get("meeting_readiness_assessment", {}),
    }

    chat_history = [{"name": item.get("agent", "Agent"), "content": item.get("content", "")} for item in messages]

    atomic_write_json(_ensure_within_runs_dir(safe_run_dir.path / "run_meta.json"), run_meta)
    atomic_write_json(_ensure_within_runs_dir(safe_run_dir.path / "chat_history.json"), chat_history)
    sanitized_pipeline_data = _sanitize_pipeline_data_for_status(
        status=status,
        pipeline_data=pipeline_data,
        run_context=run_context,
    )
    atomic_write_json(_ensure_within_runs_dir(safe_run_dir.path / "pipeline_data.json"), sanitized_pipeline_data)
    atomic_write_json(_ensure_within_runs_dir(safe_run_dir.path / "run_context.json"), run_context)
    atomic_write_json(
        _ensure_within_runs_dir(safe_run_dir.path / "memory_snapshot.json"),
        run_context.get("short_term_memory", {}),
    )
    if sanitized_pipeline_data:
        try:
            from src.exporters.pdf_report import generate_pdf

            for lang in ("de", "en"):
                file_name = f"liquisto_briefing_{run_id}_{lang.upper()}.pdf"
                pdf_payload = dict(sanitized_pipeline_data)
                pdf_payload.setdefault("run_id", run_id)
                export_binary_artifact(
                    run_dir=safe_run_dir,
                    relative_path=f"reports/{file_name}",
                    content=generate_pdf(pdf_payload, lang=lang),
                )
        except Exception as exc:  # pragma: no cover - non-fatal export hardening
            logger.warning("pdf export failed for run %s: %s", run_id, exc)


def export_follow_up(run_id: str, follow_up_answer: dict[str, Any], *, runs_root: Path | None = None) -> None:
    """Append follow-up answer history; expects sanitized path only."""
    effective_root: Path = (runs_root if runs_root is not None else RUNS_DIR).resolve(strict=False)
    safe_run_id = validate_run_id(run_id)
    resolved_run_dir = resolve_run_dir(safe_run_id, runs_root=effective_root, must_exist=False)
    safe_run_dir = _ensure_within_runs_dir(resolved_run_dir, effective_root)
    safe_run_dir.path.mkdir(parents=True, exist_ok=True)
    safe_target = _ensure_within_runs_dir(safe_run_dir.path / "follow_up_history.json", effective_root)
    lock_path = safe_target.path.with_name(safe_target.path.name + ".lock")
    safe_lock_path = _ensure_within_runs_dir(lock_path, effective_root)
    lock = FileLock(str(safe_lock_path.path))
    with lock:
        history: list[dict[str, Any]] = []
        if safe_target.path.exists():
            history = json.loads(safe_target.path.read_text(encoding="utf-8"))
        history.append(follow_up_answer)
        atomic_write_json(safe_target, history, effective_root)


def _sanitize_relative_artifact_path(relative_path: str) -> Path:
    """Return a safe relative artifact path made of basename-like segments only."""
    parts: list[str] = []
    for raw_part in Path(str(relative_path or "")).parts:
        part = str(raw_part).strip()
        if not part or part in {".", ".."}:
            continue
        if part in {"/", "\\"}:
            continue
        safe_part = re.sub(r"[^A-Za-z0-9._-]", "_", part).strip("._-")
        if safe_part:
            parts.append(safe_part)
    if not parts:
        raise ValueError("Invalid artifact relative path.")
    return Path(*parts)


def export_binary_artifact(
    *,
    run_dir: str | Path | SafeRunPath,
    relative_path: str,
    content: bytes,
) -> Path:
    """Persist a generated binary export under the run artifact directory; expects sanitized path only."""
    base_dir = run_dir.path if isinstance(run_dir, SafeRunPath) else Path(run_dir).resolve(strict=False)
    safe_relative_path = _sanitize_relative_artifact_path(relative_path)
    target_path = (base_dir / safe_relative_path).resolve(strict=False)
    try:
        target_path.relative_to(base_dir)
    except ValueError as exc:
        raise ValueError("Artifact path escapes run directory.") from exc
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(content)
    return target_path
