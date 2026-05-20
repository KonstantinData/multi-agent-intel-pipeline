"""OpenTelemetry-oriented RuntimeStep consumer.

The module is intentionally dependency-light at import time. The official
OpenTelemetry API is loaded only when telemetry is enabled and no explicit sink
is injected, so architecture tests and local runs do not need OTel installed.
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)

OTEL_ENABLED_ENV = "LIQUISTO_OTEL_ENABLED"
OTEL_SERVICE_NAME_ENV = "LIQUISTO_OTEL_SERVICE_NAME"
OTEL_TRACER_NAME = "liquisto.runtime"

_TRUTHY = {"1", "true", "yes", "on"}
_MAX_ATTRIBUTE_TEXT_LENGTH = 120
_AG2_NOOP_THRESHOLD = 100
_TRACE_BYTES_THRESHOLD = 500_000

_PHASE_SPAN_NAMES = {
    "initialized": "runtime.initialized",
    "storage_init": "runtime.storage_init",
    "memory_retrieval": "runtime.memory_retrieval",
    "supervisor_brief": "runtime.supervisor_brief",
    "step1_handoff": "runtime.step1_handoff",
    "first_pass": "runtime.first_pass",
    "auto_close": "runtime.auto_close",
    "synthesis": "runtime.synthesis",
    "finalization": "runtime.finalization",
    "report_and_export": "runtime.report_and_export",
    "follow_up": "runtime.follow_up",
}


class TelemetrySink(Protocol):
    """Sink abstraction used by tests and by the optional OTel SDK bridge."""

    def emit_span(
        self,
        name: str,
        attributes: dict[str, Any],
        events: list[dict[str, Any]] | None = None,
    ) -> None:
        """Emit one span-like telemetry record."""

    def emit_event(self, scope_name: str, name: str, attributes: dict[str, Any]) -> None:
        """Emit an event on a logical parent span."""

    def emit_metric(self, name: str, value: int | float, attributes: dict[str, Any]) -> None:
        """Emit one counter metric."""


@dataclass(slots=True)
class InMemoryTelemetrySink:
    """Test sink that records the OTel mapping without importing OTel."""

    spans: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)

    def emit_span(
        self,
        name: str,
        attributes: dict[str, Any],
        events: list[dict[str, Any]] | None = None,
    ) -> None:
        self.spans.append(
            {
                "name": name,
                "attributes": dict(attributes),
                "events": list(events or []),
            }
        )

    def emit_event(self, scope_name: str, name: str, attributes: dict[str, Any]) -> None:
        self.events.append(
            {
                "scope_name": scope_name,
                "name": name,
                "attributes": dict(attributes),
            }
        )

    def emit_metric(self, name: str, value: int | float, attributes: dict[str, Any]) -> None:
        self.metrics.append(
            {
                "name": name,
                "value": value,
                "attributes": dict(attributes),
            }
        )


class OpenTelemetrySdkSink:
    """Thin bridge to the official OpenTelemetry API when installed."""

    def __init__(self, *, tracer_name: str = OTEL_TRACER_NAME) -> None:
        try:
            from opentelemetry import metrics, trace
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "OpenTelemetry is enabled but the opentelemetry API is not installed"
            ) from exc
        self._tracer = trace.get_tracer(tracer_name)
        self._meter = metrics.get_meter(tracer_name)
        self._counters: dict[str, Any] = {}

    def emit_span(
        self,
        name: str,
        attributes: dict[str, Any],
        events: list[dict[str, Any]] | None = None,
    ) -> None:
        with self._tracer.start_as_current_span(name) as span:
            for key, value in attributes.items():
                span.set_attribute(key, value)
            for event in events or []:
                span.add_event(
                    str(event.get("name", "runtime.step.event")),
                    attributes=dict(event.get("attributes", {})),
                )

    def emit_event(self, scope_name: str, name: str, attributes: dict[str, Any]) -> None:
        with self._tracer.start_as_current_span(scope_name) as span:
            span.add_event(name, attributes=attributes)

    def emit_metric(self, name: str, value: int | float, attributes: dict[str, Any]) -> None:
        counter = self._counters.get(name)
        if counter is None:
            counter = self._meter.create_counter(name)
            self._counters[name] = counter
        counter.add(value, attributes=attributes)


def otel_steps_enabled() -> bool:
    """Return whether RuntimeStep OTel export is enabled."""

    return os.getenv(OTEL_ENABLED_ENV, "0").strip().lower() in _TRUTHY


def build_otel_step_consumer_from_env() -> OpenTelemetryStepConsumer | None:
    """Build the optional OTel consumer from environment configuration."""

    if not otel_steps_enabled():
        return None
    try:
        return OpenTelemetryStepConsumer()
    except Exception as exc:
        logger.warning("OpenTelemetry RuntimeStep consumer disabled: %s", exc)
        return None


class OpenTelemetryStepConsumer:
    """Map validated RuntimeSteps to OTel-compatible spans, events, and metrics."""

    def __init__(self, sink: TelemetrySink | None = None) -> None:
        self.sink = sink or OpenTelemetrySdkSink()
        self._seen_runs: set[str] = set()

    def consume(self, step: dict[str, Any]) -> None:
        if not _schema_version_supported(step):
            return

        self._emit_root_once(step)
        metric_attributes = _metric_attributes(step)
        self._emit_step_metrics(step, metric_attributes)

        if _is_ag2_noop_step(step):
            self.sink.emit_event(
                _department_span_name(step),
                "department_groupchat.no_op",
                _event_attributes(step),
            )
            return

        self.sink.emit_span(
            _span_name(step),
            _span_attributes(step),
            _step_events(step),
        )

    def _emit_root_once(self, step: dict[str, Any]) -> None:
        run_id = _identity(step).get("run_id", "")
        if not run_id or run_id in self._seen_runs:
            return
        self._seen_runs.add(run_id)
        attrs = {
            "run.id": str(run_id),
            "runtime.mode": str(_scope(step).get("mode", "")),
            "runtime.status": str(_execution(step).get("status", "")),
            "step.schema_version": str(_identity(step).get("schema_version", "")),
            "service.name": _bounded(os.getenv(OTEL_SERVICE_NAME_ENV, "liquisto-runtime")),
        }
        self.sink.emit_span("runtime.run", attrs)
        self.sink.emit_metric("runtime.run.count", 1, {"runtime.status": attrs["runtime.status"]})

    def _emit_step_metrics(self, step: dict[str, Any], attributes: dict[str, Any]) -> None:
        self.sink.emit_metric("runtime.step.count", 1, attributes)
        self.sink.emit_metric("runtime.step.bytes", _json_size(step), attributes)

        action_kind = str(_planned_action(step).get("kind", ""))
        if action_kind == "capability_call":
            self.sink.emit_metric("runtime.capability.call.count", 1, attributes)
        if action_kind == "state_transition":
            self.sink.emit_metric("runtime.state_transition.count", 1, attributes)

        errors = _execution(step).get("errors", [])
        if isinstance(errors, list) and errors:
            self.sink.emit_metric("runtime.error.count", len(errors), attributes)
            if action_kind == "capability_call":
                self.sink.emit_metric("runtime.capability.error.count", len(errors), attributes)

        usage = _usage(step)
        for source_key, metric_name in (
            ("total_tokens", "runtime.tokens.total"),
            ("prompt_tokens", "runtime.tokens.prompt"),
            ("completion_tokens", "runtime.tokens.completion"),
            ("thinking_tokens", "runtime.tokens.thinking"),
            ("estimated_cost_usd", "runtime.cost.estimated_usd"),
            ("retry_count", "runtime.retry.count"),
        ):
            value = _number(usage.get(source_key))
            if value > 0:
                self.sink.emit_metric(metric_name, value, attributes)


def summarize_compactable_ag2_noops(
    steps: list[dict[str, Any]],
    *,
    noop_threshold: int = _AG2_NOOP_THRESHOLD,
    trace_bytes_threshold: int = _TRACE_BYTES_THRESHOLD,
) -> list[dict[str, Any]]:
    """Return compaction summaries for AG2 no-op runs that exceed ADR-002 limits."""

    trace_bytes = _json_size(steps)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for step in steps:
        if _is_ag2_noop_step(step):
            key = (
                str(_identity(step).get("run_id", "")),
                str(_scope(step).get("department", "")),
            )
            grouped[key].append(step)

    summaries: list[dict[str, Any]] = []
    for (run_id, department), group in grouped.items():
        if len(group) <= 2:
            continue
        if len(group) <= noop_threshold and trace_bytes <= trace_bytes_threshold:
            continue
        sequences = [int(_identity(item).get("sequence", 0) or 0) for item in group]
        actor_counts: dict[str, int] = defaultdict(int)
        task_counts: dict[str, int] = defaultdict(int)
        error_count = 0
        for item in group:
            actor_counts[str(_scope(item).get("actor_role", "") or "unknown")] += 1
            task_key = str(_scope(item).get("task_key", "") or "")
            if task_key:
                task_counts[task_key] += 1
            errors = _execution(item).get("errors", [])
            if isinstance(errors, list):
                error_count += len(errors)
        summaries.append(
            {
                "kind": "department_groupchat_noop_compaction",
                "run_id": run_id,
                "department": department,
                "count": len(group),
                "first_sequence": min(sequences),
                "last_sequence": max(sequences),
                "actor_role_counts": dict(sorted(actor_counts.items())),
                "task_key_counts": dict(sorted(task_counts.items())),
                "error_count": error_count,
            }
        )
    return summaries


def _schema_version_supported(step: dict[str, Any]) -> bool:
    return str(_identity(step).get("schema_version", "")).startswith("2026-05-20")


def _span_name(step: dict[str, Any]) -> str:
    action = _planned_action(step)
    action_kind = str(action.get("kind", ""))
    action_target = _normalize_target(str(action.get("target", "step")))
    scope = _scope(step)
    phase = str(scope.get("phase", ""))
    department = str(scope.get("department", "") or "")

    if action_kind == "capability_call":
        return f"capability.{action_target}"
    if department and action_target.startswith("department"):
        return _department_span_name(step)
    if action_kind == "state_transition":
        return _PHASE_SPAN_NAMES.get(phase, f"state.{action_target}")
    return f"runtime.step.{action_kind or 'unknown'}"


def _department_span_name(step: dict[str, Any]) -> str:
    department = str(_scope(step).get("department", "") or "unknown_department")
    return f"department.{_normalize_target(department)}"


def _span_attributes(step: dict[str, Any]) -> dict[str, Any]:
    identity = _identity(step)
    scope = _scope(step)
    execution = _execution(step)
    outcome = _outcome(step)
    action = _planned_action(step)
    usage = _usage(step)
    reasoning_policy = _reasoning_policy(step)
    reasoning_realized = _reasoning_realized(step)

    attrs: dict[str, Any] = {
        "step.id": _bounded(identity.get("step_id", "")),
        "step.sequence": int(identity.get("sequence", 0) or 0),
        "step.schema_version": _bounded(identity.get("schema_version", "")),
        "step.mode": _bounded(scope.get("mode", "")),
        "step.status": _bounded(execution.get("status", "")),
        "phase": _bounded(scope.get("phase", "")),
        "actor.role": _bounded(scope.get("actor_role", "")),
        "action.kind": _bounded(action.get("kind", "")),
        "action.target": _normalize_target(str(action.get("target", ""))),
        "decision": _bounded(outcome.get("decision", "")),
        "stop.reason": _bounded(outcome.get("stop_reason", "")),
    }
    if scope.get("department"):
        attrs["department"] = _bounded(scope.get("department", ""))
    if scope.get("task_key"):
        attrs["task.key"] = _bounded(scope.get("task_key", ""))
    if scope.get("attempt") is not None:
        attrs["task.attempt"] = int(scope.get("attempt") or 0)
    if usage.get("provider"):
        attrs["model.provider"] = _bounded(usage.get("provider", ""))
    if usage.get("model"):
        attrs["model.name"] = _bounded(usage.get("model", ""))
    if reasoning_policy.get("effort"):
        attrs["reasoning.effort_planned"] = _bounded(reasoning_policy.get("effort", ""))
    if reasoning_realized.get("effort_used"):
        attrs["reasoning.effort_used"] = _bounded(reasoning_realized.get("effort_used", ""))
    error_class = _error_class(step)
    if error_class:
        attrs["error.class"] = error_class
    return {key: value for key, value in attrs.items() if value not in {"", None}}


def _metric_attributes(step: dict[str, Any]) -> dict[str, Any]:
    attrs = _span_attributes(step)
    metric_attrs: dict[str, Any] = {}
    for key in (
        "phase",
        "department",
        "actor.role",
        "action.kind",
        "action.target",
        "step.status",
        "error.class",
        "model.provider",
    ):
        if key in attrs:
            metric_attrs[key] = attrs[key]
    model = str(attrs.get("model.name", ""))
    if model:
        metric_attrs["model.family"] = _model_family(model)
    return metric_attrs


def _event_attributes(step: dict[str, Any]) -> dict[str, Any]:
    attrs = _span_attributes(step)
    return {
        key: attrs[key]
        for key in (
            "step.id",
            "step.sequence",
            "step.status",
            "phase",
            "department",
            "actor.role",
            "action.kind",
            "action.target",
            "task.key",
        )
        if key in attrs
    }


def _step_events(step: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    execution = _execution(step)
    for call in execution.get("capability_calls", []):
        if not isinstance(call, dict):
            continue
        events.append(
            {
                "name": "capability.call",
                "attributes": {
                    "capability.kind": _bounded(call.get("kind", "")),
                    "capability.target": _normalize_target(str(call.get("target", call.get("kind", "")))),
                },
            }
        )
    for transition in execution.get("state_transitions", []):
        if not isinstance(transition, dict):
            continue
        attrs = {
            "state.kind": _bounded(transition.get("kind", "")),
        }
        if transition.get("checkpoint_id"):
            attrs["checkpoint_id"] = _bounded(transition.get("checkpoint_id", ""))
        if transition.get("phase"):
            attrs["phase"] = _bounded(transition.get("phase", ""))
        if transition.get("sequence") is not None:
            attrs["sequence"] = int(transition.get("sequence") or 0)
        if transition.get("content_hash"):
            attrs["content_hash"] = _bounded(transition.get("content_hash", ""))
        events.append({"name": "state.transition", "attributes": attrs})
    for error in execution.get("errors", []):
        if isinstance(error, dict):
            events.append(
                {
                    "name": "runtime.step.error",
                    "attributes": {"error.class": _bounded(error.get("class", error.get("type", "error")))},
                }
            )
    return events


def _is_ag2_noop_step(step: dict[str, Any]) -> bool:
    action = _planned_action(step)
    return (
        str(_scope(step).get("phase", "")) == "department_groupchat"
        and action.get("kind") == "no_op"
        and str(action.get("target", "")) == "ag2.turn"
    )


def _identity(step: dict[str, Any]) -> dict[str, Any]:
    value = step.get("identity", {})
    return value if isinstance(value, dict) else {}


def _scope(step: dict[str, Any]) -> dict[str, Any]:
    value = step.get("scope", {})
    return value if isinstance(value, dict) else {}


def _intent(step: dict[str, Any]) -> dict[str, Any]:
    value = step.get("intent", {})
    return value if isinstance(value, dict) else {}


def _execution(step: dict[str, Any]) -> dict[str, Any]:
    value = step.get("execution", {})
    return value if isinstance(value, dict) else {}


def _outcome(step: dict[str, Any]) -> dict[str, Any]:
    value = step.get("outcome", {})
    return value if isinstance(value, dict) else {}


def _planned_action(step: dict[str, Any]) -> dict[str, Any]:
    value = _intent(step).get("planned_action", {})
    return value if isinstance(value, dict) else {}


def _reasoning_policy(step: dict[str, Any]) -> dict[str, Any]:
    value = _intent(step).get("reasoning_policy", {})
    return value if isinstance(value, dict) else {}


def _reasoning_realized(step: dict[str, Any]) -> dict[str, Any]:
    value = _execution(step).get("reasoning_realized", {})
    return value if isinstance(value, dict) else {}


def _usage(step: dict[str, Any]) -> dict[str, Any]:
    value = _execution(step).get("usage", {})
    return value if isinstance(value, dict) else {}


def _error_class(step: dict[str, Any]) -> str:
    errors = _execution(step).get("errors", [])
    if not isinstance(errors, list) or not errors:
        return ""
    first = errors[0]
    if not isinstance(first, dict):
        return "error"
    return _bounded(first.get("class", first.get("type", "error")))


def _bounded(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) <= _MAX_ATTRIBUTE_TEXT_LENGTH:
        return text
    return f"{text[:_MAX_ATTRIBUTE_TEXT_LENGTH]}..."


def _normalize_target(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "").strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_.-")
    return _bounded(normalized or "unknown")


def _model_family(model: str) -> str:
    text = str(model or "").strip().lower()
    for prefix in ("gpt-5", "gpt-4.1", "gpt-4o", "o3", "o4", "claude", "gemini"):
        if text.startswith(prefix):
            return prefix
    return text.split("-", 1)[0] if text else "unknown"


def _number(value: Any) -> int | float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0
    if number <= 0:
        return 0
    if number.is_integer():
        return int(number)
    return number


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
