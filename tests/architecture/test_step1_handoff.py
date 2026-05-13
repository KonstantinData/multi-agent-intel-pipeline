from __future__ import annotations

from src.orchestration.meeting_questions import (
    MEETING_QUESTION_REGISTRY,
    TASK_TO_QUESTION_IDS,
    build_initial_answer_matrix,
    build_question_registry,
)
from src.orchestration.run_context import RunContext
from src.orchestration.step1_handoff import (
    RUNTIME_EVENT_SCHEMA_VERSION,
    STEP1_BLOCKED,
    STEP1_HANDOFF_SCHEMA_VERSION,
    STEP1_READY,
    build_step1_handoff,
    handoff_allows_department_routing,
    validate_question_contracts,
)
from src.orchestration.supervisor_loop import emit_message


def _supervisor_message() -> dict:
    return {
        "schema_version": "2026-05-12.1",
        "section": "supervisor_brief",
        "status": "ready_for_department_routing",
        "briefing_readiness": "ready",
        "identity_confidence": "high",
        "industry_confidence": "high",
        "routing_gaps": [],
        "evidence_summary": {
            "item_count": 1,
            "source_types": ["owned_website"],
            "missing_fields": [],
        },
        "payload": {"normalized_domain": "example.com"},
    }


def _event() -> dict:
    return emit_message(
        None,
        agent="Supervisor",
        content="{}",
        run_id="20260512T120000Z",
        sequence=1,
        phase="supervisor_brief",
    )


def test_meeting_question_registry_contract_has_twelve_questions() -> None:
    registry = build_question_registry()

    assert len(registry) == 12
    assert len(MEETING_QUESTION_REGISTRY) == 12
    assert tuple(registry.keys()) == tuple(MEETING_QUESTION_REGISTRY.keys())


def test_question_registry_answer_matrix_and_task_mapping_validate() -> None:
    registry = build_question_registry()
    matrix = build_initial_answer_matrix()

    assert set(registry) == set(matrix)
    assert validate_question_contracts(registry, matrix) == ()
    for question_id, entry in matrix.items():
        assert entry["status"] == "pending"
        assert entry["answer"] == ""
        assert entry["notes"] == ""
        assert entry["source_tasks"] == []
        assert entry["target_section"] == registry[question_id]["focus_area"]
    missing_refs = {
        qid
        for question_ids in TASK_TO_QUESTION_IDS.values()
        for qid in question_ids
        if qid not in registry
    }
    assert missing_refs == set()


def test_runtime_event_contract_has_id_sequence_phase_and_schema() -> None:
    event = _event()

    assert event["event_id"] == "20260512T120000Z:000001:supervisor_brief"
    assert event["sequence"] == 1
    assert event["phase"] == "supervisor_brief"
    assert event["schema_version"] == RUNTIME_EVENT_SCHEMA_VERSION
    assert event["content_type"] == "application/json"


def test_step1_handoff_contract_validates_ready_state() -> None:
    ctx = RunContext(
        run_id="20260512T120000Z",
        intake={"company_name": "Example AG", "normalized_domain": "example.com"},
    )
    ctx.supervisor_brief = {"normalized_domain": "example.com"}
    ctx.question_registry = build_question_registry()
    ctx.answer_matrix = build_initial_answer_matrix()
    ctx.retrieved_strategies = [{"name": "general"}]
    ctx.retrieved_role_strategies = {"CompanyResearcher": [{"name": "role"}]}
    ctx.resolution_state["storage"] = {"profile": "local_dev"}

    handoff = build_step1_handoff(
        run_context=ctx,
        supervisor_message=_supervisor_message(),
        first_event=_event(),
        checkpoint={
            "checkpoint_id": "after_supervisor_brief",
            "phase": "after_supervisor_brief",
            "written": True,
            "content_hash": "abc",
        },
        runtime_agents_snapshot={"factory_version": "test"},
        budget_snapshot={"phase_durations_ms": {"supervisor_brief": 1}},
    )

    assert handoff.schema_version == STEP1_HANDOFF_SCHEMA_VERSION
    assert handoff.readiness == STEP1_READY
    assert handoff.validation_errors == []
    assert handoff_allows_department_routing(handoff) is True


def test_step1_handoff_blocks_missing_supervisor_brief_and_matrix_mismatch() -> None:
    ctx = RunContext(
        run_id="20260512T120000Z",
        intake={"company_name": "Example AG", "normalized_domain": "example.com"},
    )
    ctx.question_registry = build_question_registry()
    ctx.answer_matrix = build_initial_answer_matrix()
    ctx.answer_matrix.pop("q_market_situation")

    handoff = build_step1_handoff(
        run_context=ctx,
        supervisor_message={"section": "supervisor_brief", "payload": {}},
        first_event={},
        checkpoint={"written": False, "error_message": "disk full"},
        runtime_agents_snapshot={},
        budget_snapshot={},
    )

    assert handoff.readiness == STEP1_BLOCKED
    assert handoff_allows_department_routing(handoff) is False
    codes = {error["code"] for error in handoff.validation_errors}
    assert "supervisor_message_invalid" in codes
    assert "answer_matrix_invalid" in codes
    assert "checkpoint_write_failed" in codes
