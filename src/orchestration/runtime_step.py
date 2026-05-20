"""RuntimeStep contract for narrated runtime tracing.

ADR-001 introduces a stable event envelope that is intentionally lighter than
the department contracts: nested subtype payloads are structured dicts so the
observation sprint can validate their final shape before hardening them.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Literal

RUNTIME_STEP_SCHEMA_VERSION = "2026-05-20.1"
MAX_REFLECTION_CHARS = 2000
TRUNCATION_MARKER = "... [truncated by RuntimeStep validator]"

RuntimeStepMode = Literal["narrated", "imperative"]
PlannedActionKind = Literal["capability_call", "state_transition", "sub_step_spawn", "no_op"]
RuntimeStepStatus = Literal["pending", "running", "completed", "failed", "skipped", "cancelled"]
RuntimeRefKind = Literal["artifact_id", "uri", "inline"]

NARRATED_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "failed", "skipped", "cancelled"},
)
VALID_STATUSES: frozenset[str] = frozenset(
    {"pending", "running", "completed", "failed", "skipped", "cancelled"},
)
VALID_MODES: frozenset[str] = frozenset({"narrated", "imperative"})
VALID_ACTION_KINDS: frozenset[str] = frozenset(
    {"capability_call", "state_transition", "sub_step_spawn", "no_op"},
)
VALID_REF_KINDS: frozenset[str] = frozenset({"artifact_id", "uri", "inline"})


class RuntimeStepValidationError(ValueError):
    """Raised when a RuntimeStep payload violates the ADR-001 contract."""


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def runtime_ref(
    *,
    kind: RuntimeRefKind,
    value: str,
    mime_type: str | None = None,
) -> dict[str, Any]:
    if kind not in VALID_REF_KINDS:
        raise RuntimeStepValidationError(f"invalid RuntimeRef kind: {kind}")
    return {"kind": kind, "value": str(value), "mime_type": mime_type}


def _normalize_string_for_hash(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def canonicalize_for_hash(value: Any) -> Any:
    """Return a deterministic, semantically stable representation for hashing."""
    if isinstance(value, dict):
        return {
            str(key): canonicalize_for_hash(value[key])
            for key in sorted(value.keys(), key=str)
        }
    if isinstance(value, (list, tuple)):
        return [canonicalize_for_hash(item) for item in value]
    if isinstance(value, str):
        return _normalize_string_for_hash(value)
    return value


def _stable_json(value: Any) -> str:
    return json.dumps(
        canonicalize_for_hash(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def stable_hash(value: Any, *, prefix: str = "") -> str:
    digest = hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}{digest}" if prefix else digest


def make_idempotency_key(
    *,
    run_id: str,
    parent_step_id: str | None,
    mode: str,
    planned_action: dict[str, Any],
    task_key: str | None = None,
    attempt: int | None = None,
) -> str:
    payload = {
        "run_id": str(run_id),
        "parent_step_id": parent_step_id or "",
        "mode": str(mode),
        "planned_action": planned_action,
        "task_key": task_key or "",
        "attempt": attempt,
    }
    return stable_hash(payload, prefix="rstepidem_")[:27]


def make_step_id(*, run_id: str, sequence: int, idempotency_key: str) -> str:
    suffix = stable_hash({"run_id": run_id, "sequence": sequence, "idempotency_key": idempotency_key})[:12]
    return f"{run_id}:step:{int(sequence):06d}:{suffix}"


def truncate_reflection(value: Any) -> str:
    text = str(value or "")
    if len(text) <= MAX_REFLECTION_CHARS:
        return text
    keep = max(MAX_REFLECTION_CHARS - len(TRUNCATION_MARKER), 0)
    return f"{text[:keep]}{TRUNCATION_MARKER}"


def _require_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise RuntimeStepValidationError(f"RuntimeStep.{key} must be an object")
    return value


def _require_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise RuntimeStepValidationError(f"RuntimeStep.{key} must be a list")
    return value


def _validate_refs(refs: list[Any], *, field_path: str) -> None:
    for index, ref in enumerate(refs):
        if not isinstance(ref, dict):
            raise RuntimeStepValidationError(f"{field_path}[{index}] must be an object")
        if ref.get("kind") not in VALID_REF_KINDS:
            raise RuntimeStepValidationError(f"{field_path}[{index}].kind is invalid")
        if not str(ref.get("value", "")).strip():
            raise RuntimeStepValidationError(f"{field_path}[{index}].value is required")


def validate_runtime_step(step: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one RuntimeStep dict.

    The returned payload is safe to pass to consumers. Validation is strict for
    the envelope and deliberately permissive for nested subtype payloads.
    """
    payload = deepcopy(step)
    identity = _require_mapping(payload, "identity")
    scope = _require_mapping(payload, "scope")
    intent = _require_mapping(payload, "intent")
    execution = _require_mapping(payload, "execution")
    outcome = _require_mapping(payload, "outcome")

    if not str(identity.get("schema_version", "")).strip():
        raise RuntimeStepValidationError("identity.schema_version is required")
    if not str(identity.get("run_id", "")).strip():
        raise RuntimeStepValidationError("identity.run_id is required")
    if not str(identity.get("step_id", "")).strip():
        raise RuntimeStepValidationError("identity.step_id is required")
    if not str(identity.get("idempotency_key", "")).strip():
        raise RuntimeStepValidationError("identity.idempotency_key is required")
    if int(identity.get("sequence", 0) or 0) < 1:
        raise RuntimeStepValidationError("identity.sequence must be >= 1")
    if not str(identity.get("emitted_at", "")).strip():
        raise RuntimeStepValidationError("identity.emitted_at is required")

    mode = str(scope.get("mode", ""))
    if mode not in VALID_MODES:
        raise RuntimeStepValidationError(f"scope.mode is invalid: {mode}")
    if not str(scope.get("phase", "")).strip():
        raise RuntimeStepValidationError("scope.phase is required")
    if not str(scope.get("actor", "")).strip():
        raise RuntimeStepValidationError("scope.actor is required")

    planned_action = intent.get("planned_action")
    if not isinstance(planned_action, dict):
        raise RuntimeStepValidationError("intent.planned_action must be an object")
    if planned_action.get("kind") not in VALID_ACTION_KINDS:
        raise RuntimeStepValidationError("intent.planned_action.kind is invalid")
    if not str(planned_action.get("target", "")).strip():
        raise RuntimeStepValidationError("intent.planned_action.target is required")
    if not isinstance(planned_action.get("payload", {}), dict):
        raise RuntimeStepValidationError("intent.planned_action.payload must be an object")

    _validate_refs(_require_list(intent, "input_refs"), field_path="intent.input_refs")
    _validate_refs(_require_list(outcome, "output_refs"), field_path="outcome.output_refs")

    status = str(execution.get("status", ""))
    if status not in VALID_STATUSES:
        raise RuntimeStepValidationError(f"execution.status is invalid: {status}")
    if mode == "narrated" and status not in NARRATED_TERMINAL_STATUSES:
        raise RuntimeStepValidationError("narrated steps must use a terminal execution.status")
    for key in ("capability_calls", "state_transitions", "spawned_steps", "observations", "errors"):
        _require_list(execution, key)

    outcome["reflection"] = truncate_reflection(outcome.get("reflection", ""))
    return payload


def build_narrated_step(
    *,
    run_id: str,
    sequence: int,
    phase: str,
    actor: str,
    goal: str,
    action_kind: PlannedActionKind,
    action_target: str,
    action_payload: dict[str, Any] | None = None,
    actor_role: str = "runtime",
    department: str | None = None,
    task_key: str | None = None,
    attempt: int | None = None,
    parent_step_id: str | None = None,
    idempotency_key: str | None = None,
    status: RuntimeStepStatus = "completed",
    input_refs: list[dict[str, Any]] | None = None,
    reasoning_policy: dict[str, Any] | None = None,
    approval_policy: dict[str, Any] | None = None,
    expected_observation: dict[str, Any] | None = None,
    deadline: str | None = None,
    capability_calls: list[dict[str, Any]] | None = None,
    state_transitions: list[dict[str, Any]] | None = None,
    spawned_steps: list[str] | None = None,
    observations: list[dict[str, Any]] | None = None,
    reasoning_realized: dict[str, Any] | None = None,
    usage: dict[str, Any] | None = None,
    errors: list[dict[str, Any]] | None = None,
    decision: str = "",
    reflection: str = "",
    stop_reason: str = "",
    output_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    planned_action = {
        "kind": action_kind,
        "target": action_target,
        "payload": dict(action_payload or {}),
    }
    idem = idempotency_key or make_idempotency_key(
        run_id=run_id,
        parent_step_id=parent_step_id,
        mode="narrated",
        planned_action=planned_action,
        task_key=task_key,
        attempt=attempt,
    )
    step = {
        "identity": {
            "schema_version": RUNTIME_STEP_SCHEMA_VERSION,
            "run_id": str(run_id),
            "step_id": make_step_id(run_id=str(run_id), sequence=sequence, idempotency_key=idem),
            "parent_step_id": parent_step_id,
            "idempotency_key": idem,
            "sequence": int(sequence),
            "emitted_at": utc_now_iso(),
        },
        "scope": {
            "mode": "narrated",
            "phase": str(phase),
            "department": department,
            "task_key": task_key,
            "attempt": attempt,
            "actor": str(actor),
            "actor_role": str(actor_role),
        },
        "intent": {
            "goal": str(goal),
            "input_refs": list(input_refs or []),
            "planned_action": planned_action,
            "reasoning_policy": reasoning_policy,
            "approval_policy": approval_policy,
            "expected_observation": expected_observation,
            "deadline": deadline,
        },
        "execution": {
            "status": status,
            "capability_calls": list(capability_calls or []),
            "state_transitions": list(state_transitions or []),
            "spawned_steps": list(spawned_steps or []),
            "observations": list(observations or []),
            "reasoning_realized": reasoning_realized,
            "usage": usage,
            "errors": list(errors or []),
        },
        "outcome": {
            "decision": str(decision),
            "reflection": str(reflection),
            "stop_reason": str(stop_reason),
            "output_refs": list(output_refs or []),
        },
    }
    return validate_runtime_step(step)
