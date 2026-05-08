"""Write run artifacts to disk."""
from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock

from src.orchestration.run_paths import RUNS_DIR
from src.app.use_cases import (
    DISCOVERY_READY_RUN_STATUS,
    SUCCESS_RUN_STATUS,
    sanitize_success_unresolved,
)

logger = logging.getLogger(__name__)


def _ensure_within_runs_dir(path: str | Path) -> Path:
    """Resolve and enforce that ``path`` is contained in the trusted runs root."""
    root = Path(RUNS_DIR).resolve()
    candidate = Path(path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Refusing to write outside runs directory.") from exc
    return candidate


def atomic_write_json(path: str | Path, payload: Any) -> None:
    """Write JSON atomically via a same-directory tempfile and replace."""
    target = _ensure_within_runs_dir(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, ensure_ascii=False)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(encoded)
        handle.flush()
        temp_name = handle.name
    Path(temp_name).replace(target)


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
    path = Path(run_dir)
    path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()

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

    atomic_write_json(path / "run_meta.json", run_meta)
    atomic_write_json(path / "chat_history.json", chat_history)
    sanitized_pipeline_data = _sanitize_pipeline_data_for_status(
        status=status,
        pipeline_data=pipeline_data,
        run_context=run_context,
    )
    atomic_write_json(path / "pipeline_data.json", sanitized_pipeline_data)
    atomic_write_json(path / "run_context.json", run_context)
    atomic_write_json(path / "memory_snapshot.json", run_context.get("short_term_memory", {}))
    if sanitized_pipeline_data:
        try:
            from src.exporters.pdf_report import generate_pdf

            for lang in ("de", "en"):
                file_name = f"liquisto_briefing_{run_id}_{lang.upper()}.pdf"
                pdf_payload = dict(sanitized_pipeline_data)
                pdf_payload.setdefault("run_id", run_id)
                export_binary_artifact(
                    run_dir=path,
                    relative_path=f"reports/{file_name}",
                    content=generate_pdf(pdf_payload, lang=lang),
                )
        except Exception as exc:  # pragma: no cover - non-fatal export hardening
            logger.warning("pdf export failed for run %s: %s", run_id, exc)


def export_follow_up(run_dir: str | Path, follow_up_answer: dict[str, Any]) -> None:
    path = _ensure_within_runs_dir(run_dir)
    path.mkdir(parents=True, exist_ok=True)
    target = _ensure_within_runs_dir(path / "follow_up_history.json")
    lock = FileLock(str(target) + ".lock")
    with lock:
        history: list[dict[str, Any]] = []
        if target.exists():
            history = json.loads(target.read_text(encoding="utf-8"))
        history.append(follow_up_answer)
        atomic_write_json(target, history)


def export_binary_artifact(
    *,
    run_dir: str | Path,
    relative_path: str,
    content: bytes,
) -> Path:
    """Persist a generated binary export under the run artifact directory."""
    path = _ensure_within_runs_dir(run_dir)
    target = _ensure_within_runs_dir(path / relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target
