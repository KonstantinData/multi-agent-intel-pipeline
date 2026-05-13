"""Structured logging for runtime-agent factory events.

Emits one JSON-line event per Step-1 agent-factory call (success or failure)
on the `liquisto.runtime_factory` logger. Schema mirrors `intake_logging`:
`schema_version`, `component`, `phase`, `run_id`, `status`, `error_code`,
`duration_ms`. Optional fields: `factory_version`, `role_count`, `errors`.

No prompts, no secrets, no model parameters are recorded.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

_LOG_SCHEMA_VERSION = "1"
_COMPONENT = "runtime_factory"
_LOGGER_NAME = "liquisto.runtime_factory"


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


def log_factory_event(
    *,
    run_id: str,
    status: str,
    duration_ms: int | None = None,
    error_code: str = "",
    factory_version: str = "",
    role_count: int | None = None,
    errors: tuple[str, ...] | list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit one structured factory event.

    `status` ∈ {"ok", "failed"}. `errors` is included only on failure.
    """
    payload: dict[str, Any] = {
        "schema_version": _LOG_SCHEMA_VERSION,
        "component": _COMPONENT,
        "phase": "runtime_agent_factory",
        "run_id": run_id,
        "status": status,
        "error_code": error_code,
    }
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if factory_version:
        payload["factory_version"] = factory_version
    if role_count is not None:
        payload["role_count"] = role_count
    if errors:
        payload["errors"] = list(errors)
    if extra:
        for key, value in extra.items():
            if key not in payload:
                payload[key] = value

    level = logging.INFO if status == "ok" else logging.WARNING
    _LOGGER.log(level, "factory_event", extra={"payload": payload})


__all__ = ["log_factory_event"]
