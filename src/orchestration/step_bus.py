"""In-process RuntimeStep bus and consumers.

The bus is intentionally small: it validates and distributes already-built
RuntimeStep payloads without participating in runtime control flow.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable
from typing import Any, Protocol

from src.orchestration.runtime_step import build_narrated_step, validate_runtime_step
from src.security.secret_guard import (
    PromptSecretLeakError,
    assert_no_secrets_in_payload,
    assert_no_secrets_in_text,
)

logger = logging.getLogger(__name__)

MessageHook = Callable[[dict[str, Any]], None] | None


def runtime_steps_enabled() -> bool:
    raw = os.getenv("LIQUISTO_RUNTIME_STEPS_ENABLED", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


class StepConsumer(Protocol):
    def consume(self, step: dict[str, Any]) -> None:
        """Consume one validated RuntimeStep payload."""


class StepTraceConsumer:
    """Store a de-duplicated step trace in a target list."""

    def __init__(self, target: list[dict[str, Any]]) -> None:
        self.target = target
        self._positions: dict[str, int] = {
            str(item.get("identity", {}).get("idempotency_key", "")): index
            for index, item in enumerate(target)
            if isinstance(item, dict) and item.get("identity", {}).get("idempotency_key")
        }

    def consume(self, step: dict[str, Any]) -> None:
        key = str(step.get("identity", {}).get("idempotency_key", ""))
        if key and key in self._positions:
            self.target[self._positions[key]] = step
            return
        self._positions[key] = len(self.target)
        self.target.append(step)


class InMemoryStepSink(StepTraceConsumer):
    """Named consumer used by tests and local eval inspection."""

    def __init__(self) -> None:
        super().__init__([])

    @property
    def steps(self) -> list[dict[str, Any]]:
        return self.target


class EventLogStepConsumer:
    """Convert selected RuntimeSteps to the existing callback event shape."""

    def __init__(self, on_message: MessageHook) -> None:
        self.on_message = on_message

    def consume(self, step: dict[str, Any]) -> None:
        if not self.on_message:
            return
        identity = step.get("identity", {})
        scope = step.get("scope", {})
        outcome = step.get("outcome", {})
        self.on_message(
            {
                "event_id": identity.get("step_id", ""),
                "run_id": identity.get("run_id", ""),
                "sequence": identity.get("sequence", 0),
                "timestamp": identity.get("emitted_at", ""),
                "agent": scope.get("actor", "RuntimeStep"),
                "content": outcome.get("reflection", ""),
                "content_type": "application/json",
                "phase": scope.get("phase", ""),
                "schema_version": identity.get("schema_version", ""),
                "type": "runtime_step",
            }
        )


class StepBus:
    """Publish validated RuntimeSteps to all registered consumers."""

    def __init__(self, consumers: Iterable[StepConsumer] | None = None) -> None:
        self.consumers: list[StepConsumer] = list(consumers or [])

    def add_consumer(self, consumer: StepConsumer) -> None:
        self.consumers.append(consumer)

    def publish(self, step: dict[str, Any]) -> None:
        validated = validate_runtime_step(step)
        for consumer in list(self.consumers):
            try:
                consumer.consume(validated)
            except Exception as exc:  # pragma: no cover - telemetry hardening
                logger.warning("runtime step consumer failed: %s", exc)


class StepEmitter:
    """Build and publish narrated RuntimeSteps with secret-guard validation."""

    def __init__(
        self,
        *,
        run_id: str,
        bus: StepBus,
        enabled: bool = True,
    ) -> None:
        self.run_id = run_id
        self.bus = bus
        self.enabled = enabled
        self._sequence = 0
        self.blocked_errors: list[dict[str, Any]] = []

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def emit(self, step: dict[str, Any]) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        try:
            validated = validate_runtime_step(step)
            self._assert_publishable(validated)
        except PromptSecretLeakError as exc:
            self.blocked_errors.append(
                {
                    "context": exc.context,
                    "rule_ids": list(exc.rule_ids),
                    "paths": list(exc.paths),
                }
            )
            logger.warning(
                "runtime step emission blocked by secret guard: context=%s rules=%s",
                exc.context,
                ",".join(exc.rule_ids),
            )
            return None
        except Exception as exc:
            logger.warning("runtime step emission failed validation: %s", exc)
            return None
        self.bus.publish(validated)
        return validated

    def emit_narrated(self, **kwargs: Any) -> dict[str, Any] | None:
        step = build_narrated_step(
            run_id=self.run_id,
            sequence=self._next_sequence(),
            **kwargs,
        )
        return self.emit(step)

    @staticmethod
    def _assert_publishable(step: dict[str, Any]) -> None:
        intent = step.get("intent", {})
        execution = step.get("execution", {})
        outcome = step.get("outcome", {})
        planned_action = intent.get("planned_action", {}) if isinstance(intent, dict) else {}
        assert_no_secrets_in_payload(
            planned_action.get("payload", {}),
            context="runtime_step.planned_action.payload",
        )
        assert_no_secrets_in_payload(
            execution.get("observations", []),
            context="runtime_step.execution.observations",
        )
        assert_no_secrets_in_payload(
            execution.get("errors", []),
            context="runtime_step.execution.errors",
        )
        assert_no_secrets_in_text(
            str(outcome.get("reflection", "")),
            context="runtime_step.outcome.reflection",
        )
