"""Structured JSON logging for the Supervisor Briefing phase (TODO 5.11).

Emits one event per Step-1 supervisor-brief call (success or degraded). Schema
mirrors `intake_logging` and `factory_logging`:
`schema_version`, `component`, `phase`, `run_id`, `status`, `error_code`,
`duration_ms`. Briefing-specific: `briefing_readiness`, `identity_confidence`,
`industry_confidence`, `fetch_status`, `evidence_item_count`, `routing_gaps`.

No prompts, no homepage raw text, no secrets.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

_LOG_SCHEMA_VERSION = "1"
_COMPONENT = "supervisor_brief"
_LOGGER_NAME = "liquisto.supervisor_brief"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "payload", None)
        if isinstance(payload, dict):
            return json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return json.dumps(
            {"message": record.getMessage(), "level": record.levelname},
            ensure_ascii=False,
        )


def _configure_default_handler() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


_LOGGER = _configure_default_handler()


def log_supervisor_brief_event(
    *,
    run_id: str,
    status: str,
    duration_ms: int | None = None,
    briefing_readiness: str = "",
    identity_confidence: str = "",
    industry_confidence: str = "",
    fetch_status: str = "",
    evidence_item_count: int | None = None,
    routing_gaps: tuple[str, ...] | list[str] | None = None,
    error_code: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit one structured supervisor-brief event.

    `status` ∈ {"ok", "degraded", "blocked", "failed"}. Routing-blocking
    cases (`BLOCKED_*` readiness) log as `blocked` with `WARNING`; ready
    cases log as `ok` with `INFO`.
    """
    payload: dict[str, Any] = {
        "schema_version": _LOG_SCHEMA_VERSION,
        "component": _COMPONENT,
        "phase": "supervisor_brief",
        "run_id": run_id,
        "status": status,
        "error_code": error_code,
    }
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if briefing_readiness:
        payload["briefing_readiness"] = briefing_readiness
    if identity_confidence:
        payload["identity_confidence"] = identity_confidence
    if industry_confidence:
        payload["industry_confidence"] = industry_confidence
    if fetch_status:
        payload["fetch_status"] = fetch_status
    if evidence_item_count is not None:
        payload["evidence_item_count"] = evidence_item_count
    if routing_gaps:
        payload["routing_gaps"] = list(routing_gaps)
    if extra:
        for key, value in extra.items():
            if key not in payload:
                payload[key] = value

    level = logging.INFO if status == "ok" else logging.WARNING
    _LOGGER.log(level, "supervisor_brief_event", extra={"payload": payload})


__all__ = ["log_supervisor_brief_event"]
