"""Write run artifacts to disk."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.app.use_cases import SUCCESS_RUN_STATUS, sanitize_success_unresolved


def _sanitize_pipeline_data_for_status(*, status: str, pipeline_data: dict[str, Any]) -> dict[str, Any]:
    data = dict(pipeline_data)
    if status != SUCCESS_RUN_STATUS:
        return data
    synthesis = dict(data.get("synthesis", {}) or {})
    synthesis.pop("open_questions", None)
    data["synthesis"] = synthesis
    return data


def _extract_export_unresolved(*, status: str, run_context: dict[str, Any]) -> dict[str, list[str]]:
    if status != SUCCESS_RUN_STATUS:
        return {}
    resolution_plan = (
        (run_context or {}).get("resolution_state", {}).get("resolution_plan", {})
        if isinstance(run_context, dict)
        else {}
    )
    unresolved = resolution_plan.get("unresolved", {}) if isinstance(resolution_plan, dict) else {}
    return sanitize_success_unresolved(unresolved)


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

    (path / "run_meta.json").write_text(json.dumps(run_meta, indent=2, ensure_ascii=False), encoding="utf-8")
    (path / "chat_history.json").write_text(json.dumps(chat_history, indent=2, ensure_ascii=False), encoding="utf-8")
    sanitized_pipeline_data = _sanitize_pipeline_data_for_status(status=status, pipeline_data=pipeline_data)
    (path / "pipeline_data.json").write_text(
        json.dumps(sanitized_pipeline_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (path / "run_context.json").write_text(json.dumps(run_context, indent=2, ensure_ascii=False), encoding="utf-8")
    (path / "memory_snapshot.json").write_text(
        json.dumps(run_context.get("short_term_memory", {}), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def export_follow_up(run_dir: str | Path, follow_up_answer: dict[str, Any]) -> None:
    path = Path(run_dir)
    path.mkdir(parents=True, exist_ok=True)
    target = path / "follow_up_history.json"
    history: list[dict[str, Any]] = []
    if target.exists():
        history = json.loads(target.read_text(encoding="utf-8"))
    history.append(follow_up_answer)
    target.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
