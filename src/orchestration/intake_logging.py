"""Structured JSON logging for intake-validation events.

Implements the unified Observability fields defined in TODO 0.4:
`run_id, phase, status, error_code, duration_ms, component, schema_version`.

Events are emitted via the standard `logging` module under the
`liquisto.intake` logger. In tests or local runs without an explicit
handler, a JSON-formatted stderr handler is attached at import time so
events are visible without further configuration.

Phase-2 wiring (OpenTelemetry Collector, Prometheus counters) can attach
additional handlers to the same logger without touching call sites.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

_LOG_SCHEMA_VERSION = "1"
_COMPONENT = "intake"
_LOGGER_NAME = "liquisto.intake"


class _JsonFormatter(logging.Formatter):
    """Render the LogRecord's `payload` extra as a single-line JSON object."""

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


def log_intake_event(
    *,
    run_id: str,
    status: str,
    duration_ms: int | None = None,
    error_code: str = "",
    rejection_reason: str = "",
    canonical_domain: str = "",
    registrable_domain: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit a single structured intake event.

    `status` ∈ {"ok", "failed", "degraded"}. `error_code` carries the
    machine-readable IntakeErrorCode on failure. Domain values are included
    only when validation succeeded; on failure we keep them empty to avoid
    leaking ill-formed user input into logs.
    """
    payload: dict[str, Any] = {
        "schema_version": _LOG_SCHEMA_VERSION,
        "component": _COMPONENT,
        "phase": "intake_validation",
        "run_id": run_id,
        "status": status,
        "error_code": error_code,
    }
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if canonical_domain:
        payload["canonical_domain"] = canonical_domain
    if registrable_domain:
        payload["registrable_domain"] = registrable_domain
    if rejection_reason:
        payload["rejection_reason"] = rejection_reason
    if extra:
        # Only propagate non-sensitive caller-supplied keys.
        for key, value in extra.items():
            if key in payload:
                continue
            payload[key] = value

    level = logging.INFO if status == "ok" else logging.WARNING
    _LOGGER.log(level, "intake_event", extra={"payload": payload})


__all__ = ["log_intake_event"]
