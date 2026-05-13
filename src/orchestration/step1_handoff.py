"""Step-1 handoff contract and validation gate."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from src.domain.briefing import validate_supervisor_brief_message
from src.orchestration.meeting_questions import TASK_TO_QUESTION_IDS

STEP1_HANDOFF_SCHEMA_VERSION = "2026-05-12.1"
RUNTIME_EVENT_SCHEMA_VERSION = "2026-05-12.1"

STEP1_READY = "ready_for_department_routing"
STEP1_READY_WITH_GAPS = "ready_with_gaps"
STEP1_BLOCKED = "blocked_step1_handoff"


class Step1HandoffErrorCode(StrEnum):
    STEP1_HANDOFF_INVALID = "step1_handoff_invalid"
    QUESTION_REGISTRY_INVALID = "question_registry_invalid"
    ANSWER_MATRIX_INVALID = "answer_matrix_invalid"
    SUPERVISOR_MESSAGE_INVALID = "supervisor_message_invalid"
    CHECKPOINT_WRITE_FAILED = "checkpoint_write_failed"
    EVENT_EMIT_FAILED = "event_emit_failed"


@dataclass(frozen=True, slots=True)
class Step1ValidationError:
    code: str
    message: str
    field: str = ""
    severity: str = "blocking"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    event_id: str
    run_id: str
    sequence: int
    timestamp: str
    agent: str
    type: str
    schema_version: str
    content: str
    content_type: str
    phase: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CheckpointInfo:
    checkpoint_id: str
    phase: str
    path: str = ""
    content_hash: str = ""
    schema_version: str = STEP1_HANDOFF_SCHEMA_VERSION
    written: bool = False
    error_code: str = ""
    error_message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Step1Handoff:
    schema_version: str
    run_id: str
    intake: dict[str, Any]
    supervisor_brief: dict[str, Any]
    supervisor_message: dict[str, Any]
    question_registry: dict[str, dict[str, Any]]
    answer_matrix: dict[str, dict[str, Any]]
    retrieved_strategies: list[dict[str, Any]]
    retrieved_role_strategies: dict[str, list[dict[str, Any]]]
    runtime_agents_snapshot: dict[str, Any]
    storage_snapshot: dict[str, Any]
    budget_snapshot: dict[str, Any]
    first_event: dict[str, Any]
    checkpoint: dict[str, Any]
    readiness: str
    validation_errors: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def stable_json_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_question_contracts(
    question_registry: dict[str, dict[str, Any]],
    answer_matrix: dict[str, dict[str, Any]],
) -> tuple[Step1ValidationError, ...]:
    errors: list[Step1ValidationError] = []
    if not question_registry:
        errors.append(Step1ValidationError(
            code=Step1HandoffErrorCode.QUESTION_REGISTRY_INVALID,
            field="question_registry",
            message="question registry is empty",
        ))
    if not answer_matrix:
        errors.append(Step1ValidationError(
            code=Step1HandoffErrorCode.ANSWER_MATRIX_INVALID,
            field="answer_matrix",
            message="answer matrix is empty",
        ))

    registry_keys = tuple(question_registry.keys())
    matrix_keys = tuple(answer_matrix.keys())
    if set(registry_keys) != set(matrix_keys):
        errors.append(Step1ValidationError(
            code=Step1HandoffErrorCode.ANSWER_MATRIX_INVALID,
            field="answer_matrix",
            message="answer matrix keys differ from question registry keys",
        ))

    for question_id, meta in question_registry.items():
        if not question_id.startswith("q_"):
            errors.append(Step1ValidationError(
                code=Step1HandoffErrorCode.QUESTION_REGISTRY_INVALID,
                field=question_id,
                message="question_id must be stable and start with 'q_'",
            ))
        for required in ("question", "focus_area"):
            if not str(meta.get(required, "")).strip():
                errors.append(Step1ValidationError(
                    code=Step1HandoffErrorCode.QUESTION_REGISTRY_INVALID,
                    field=f"{question_id}.{required}",
                    message=f"question registry entry missing {required}",
                ))
        if meta.get("question_id") not in (None, "", question_id):
            errors.append(Step1ValidationError(
                code=Step1HandoffErrorCode.QUESTION_REGISTRY_INVALID,
                field=f"{question_id}.question_id",
                message="embedded question_id must match registry key when present",
            ))

    for question_id, entry in answer_matrix.items():
        expected_section = question_registry.get(question_id, {}).get("focus_area", "n/v")
        expected_defaults = {
            "status": "pending",
            "answer": "",
            "notes": "",
        }
        for key, expected in expected_defaults.items():
            if entry.get(key) != expected:
                errors.append(Step1ValidationError(
                    code=Step1HandoffErrorCode.ANSWER_MATRIX_INVALID,
                    field=f"{question_id}.{key}",
                    message=f"initial answer matrix field {key} must be {expected!r}",
                ))
        if entry.get("source_tasks") != []:
            errors.append(Step1ValidationError(
                code=Step1HandoffErrorCode.ANSWER_MATRIX_INVALID,
                field=f"{question_id}.source_tasks",
                message="initial answer matrix source_tasks must be empty",
            ))
        if entry.get("target_section") != expected_section:
            errors.append(Step1ValidationError(
                code=Step1HandoffErrorCode.ANSWER_MATRIX_INVALID,
                field=f"{question_id}.target_section",
                message="answer matrix target_section must match question focus_area",
            ))

    missing_refs = sorted({
        qid
        for question_ids in TASK_TO_QUESTION_IDS.values()
        for qid in question_ids
        if qid not in question_registry
    })
    for qid in missing_refs:
        errors.append(Step1ValidationError(
            code=Step1HandoffErrorCode.QUESTION_REGISTRY_INVALID,
            field="TASK_TO_QUESTION_IDS",
            message=f"task-to-question mapping references missing question {qid}",
        ))
    return tuple(errors)


def validate_runtime_event(event: dict[str, Any]) -> tuple[Step1ValidationError, ...]:
    errors: list[Step1ValidationError] = []
    required = {
        "event_id", "run_id", "sequence", "timestamp", "agent", "type",
        "schema_version", "content", "content_type", "phase",
    }
    for key in sorted(required - set(event)):
        errors.append(Step1ValidationError(
            code=Step1HandoffErrorCode.EVENT_EMIT_FAILED,
            field=key,
            message=f"runtime event missing {key}",
        ))
    if event.get("schema_version") != RUNTIME_EVENT_SCHEMA_VERSION:
        errors.append(Step1ValidationError(
            code=Step1HandoffErrorCode.EVENT_EMIT_FAILED,
            field="schema_version",
            message="runtime event schema version mismatch",
        ))
    return tuple(errors)


def build_step1_handoff(
    *,
    run_context,
    supervisor_message: dict[str, Any],
    first_event: dict[str, Any],
    checkpoint: dict[str, Any],
    runtime_agents_snapshot: dict[str, Any],
    budget_snapshot: dict[str, Any],
) -> Step1Handoff:
    validation_errors: list[Step1ValidationError] = []
    is_valid_message, message_errors = validate_supervisor_brief_message(supervisor_message)
    if not is_valid_message:
        validation_errors.extend(
            Step1ValidationError(
                code=Step1HandoffErrorCode.SUPERVISOR_MESSAGE_INVALID,
                field="supervisor_message",
                message=message_error,
            )
            for message_error in message_errors
        )
    if not isinstance(supervisor_message.get("payload"), dict):
        validation_errors.append(Step1ValidationError(
            code=Step1HandoffErrorCode.SUPERVISOR_MESSAGE_INVALID,
            field="supervisor_message.payload",
            message="supervisor message payload must be a dict",
        ))
    if not isinstance(run_context.supervisor_brief, dict) or not run_context.supervisor_brief:
        validation_errors.append(Step1ValidationError(
            code=Step1HandoffErrorCode.SUPERVISOR_MESSAGE_INVALID,
            field="run_context.supervisor_brief",
            message="run context supervisor_brief is missing",
        ))
    validation_errors.extend(validate_question_contracts(
        run_context.question_registry,
        run_context.answer_matrix,
    ))
    validation_errors.extend(validate_runtime_event(first_event))
    if not checkpoint.get("written"):
        validation_errors.append(Step1ValidationError(
            code=Step1HandoffErrorCode.CHECKPOINT_WRITE_FAILED,
            field="checkpoint",
            message=checkpoint.get("error_message") or "after_supervisor_brief checkpoint was not written",
        ))

    message_status = str(supervisor_message.get("status", ""))
    if validation_errors:
        readiness = STEP1_BLOCKED
    elif message_status == STEP1_READY:
        readiness = STEP1_READY
    else:
        readiness = STEP1_READY_WITH_GAPS

    return Step1Handoff(
        schema_version=STEP1_HANDOFF_SCHEMA_VERSION,
        run_id=run_context.run_id,
        intake=dict(run_context.intake),
        supervisor_brief=dict(run_context.supervisor_brief),
        supervisor_message=dict(supervisor_message),
        question_registry=dict(run_context.question_registry),
        answer_matrix=dict(run_context.answer_matrix),
        retrieved_strategies=list(run_context.retrieved_strategies),
        retrieved_role_strategies=dict(run_context.retrieved_role_strategies),
        runtime_agents_snapshot=dict(runtime_agents_snapshot),
        storage_snapshot=dict(run_context.resolution_state.get("storage", {})),
        budget_snapshot=dict(budget_snapshot),
        first_event=dict(first_event),
        checkpoint=dict(checkpoint),
        readiness=readiness,
        validation_errors=[error.as_dict() for error in validation_errors],
    )


def handoff_allows_department_routing(handoff: Step1Handoff | dict[str, Any]) -> bool:
    readiness = handoff.readiness if isinstance(handoff, Step1Handoff) else handoff.get("readiness")
    return readiness in {STEP1_READY, STEP1_READY_WITH_GAPS}
