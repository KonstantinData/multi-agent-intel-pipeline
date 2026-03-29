from __future__ import annotations

from src.orchestration.resolution_controller import ResolutionController
from src.orchestration.follow_up import run_bounded_follow_up


def test_resolution_controller_auto_close_required_for_public_gaps():
    controller = ResolutionController()
    result = controller.classify(
        sections={"company_profile": {}},
        department_packages={
            "CompanyDepartment": {"admission": {"decision": "accepted"}, "raw_package": {"open_questions": ["Public revenue signal?"]}},
            "ContactDepartment": {"admission": {"decision": "accepted"}, "raw_package": {"open_questions": []}},
        },
        answer_matrix={"q_company_fundamentals": {"status": "answered"}},
        task_statuses={"company_fundamentals": "accepted"},
    )
    assert result["bucket"] == "AUTO_CLOSE_REQUIRED"
    assert result["meeting_critical_public_gaps"] == ["Public revenue signal?"]


def test_resolution_controller_uses_typed_gap_candidates_as_primary():
    controller = ResolutionController()
    result = controller.classify(
        sections={"company_profile": {}},
        department_packages={
            "CompanyDepartment": {
                "admission": {"decision": "accepted"},
                "raw_package": {
                    "open_questions": [],
                    "gap_candidates": [{"question": "Revenue trend unclear", "severity": "high"}],
                },
            },
        },
        answer_matrix={},
        task_statuses={},
    )
    assert result["bucket"] == "AUTO_CLOSE_REQUIRED"
    assert "Revenue trend unclear" in result["meeting_critical_public_gaps"]


def test_resolution_controller_blocking_failure_on_rejected_department():
    controller = ResolutionController()
    result = controller.classify(
        sections={},
        department_packages={
            "MarketDepartment": {"admission": {"decision": "rejected"}, "raw_package": {"open_questions": []}},
        },
        answer_matrix={},
        task_statuses={},
    )
    assert result["bucket"] == "BLOCKING_FAILURE"


def test_run_bounded_follow_up_limits_questions():
    run_context = {"short_term_memory": {"department_packages": {}, "department_run_states": {}}}
    pipeline_data = {
        "company_profile": {"company_name": "ACME", "description": "maker", "product_asset_scope": [], "economic_situation": {"assessment": "stable"}},
        "industry_analysis": {},
        "market_network": {},
        "contact_intelligence": {},
        "synthesis": {},
    }
    result = run_bounded_follow_up(
        run_id="r1",
        run_context=run_context,
        pipeline_data=pipeline_data,
        public_gap_questions=["one", "two", "three"],
        max_questions=2,
    )
    assert result["attempted_questions"] == 2
    assert result["max_questions"] == 2
    assert result["closure_pass"] == 1
    assert result["max_closure_passes"] == 1
    assert "stop_reason" in result


def test_finalization_blocked_when_public_gaps_remain_after_closure():
    """RA-04: Finalization must be blocked when public meeting-critical gaps remain."""
    from src.app.use_cases import BLOCKED_RUN_STATUS, SUCCESS_RUN_STATUS, determine_final_status

    # Gaps remain after closure → must block
    status = determine_final_status(
        readiness_usable=True,
        first_round_resolution={"bucket": "AUTO_CLOSE_REQUIRED"},
        remaining_public_gaps=["Revenue trend unclear"],
    )
    assert status == BLOCKED_RUN_STATUS

    # No gaps remain → success
    status_ok = determine_final_status(
        readiness_usable=True,
        first_round_resolution={"bucket": "NOT_MEETING_CRITICAL"},
        remaining_public_gaps=[],
    )
    assert status_ok == SUCCESS_RUN_STATUS

    # readiness_usable=False → blocked even without gaps
    status_not_ready = determine_final_status(
        readiness_usable=False,
        first_round_resolution={"bucket": "NOT_MEETING_CRITICAL"},
        remaining_public_gaps=[],
    )
    assert status_not_ready == BLOCKED_RUN_STATUS


def test_meeting_readiness_gate_blocks_on_low_evidence():
    """RA-06: Gate blocks when evidence quality is low AND coverage is thin."""
    from src.orchestration.meeting_readiness import MeetingReadinessGate

    gate = MeetingReadinessGate()
    # Only 1 answered question + low evidence = blocked
    result = gate.evaluate(
        answer_matrix={"q_company_fundamentals": {"status": "answered"}},
        resolution_state={"auto_close": {"remaining_public_gaps": []}, "dashboard_state": {}},
        evidence_health="low",
        readiness_usable=False,
    )
    assert not result.meeting_ready


def test_meeting_readiness_gate_passes_when_ready():
    """RA-06: Gate passes when all conditions met."""
    from src.orchestration.meeting_readiness import MeetingReadinessGate

    gate = MeetingReadinessGate()
    result = gate.evaluate(
        answer_matrix={
            "q_company_fundamentals": {"status": "answered"},
            "q_market_situation": {"status": "answered"},
            "q_peer_companies": {"status": "answered"},
            "q_monetization_redeployment": {"status": "answered"},
            "q_contact_intelligence": {"status": "partially_answered"},
        },
        resolution_state={"auto_close": {"remaining_public_gaps": []}, "dashboard_state": {}},
        evidence_health="medium",
        readiness_usable=True,
    )
    assert result.meeting_ready
    assert result.blocked_reasons == []


def test_final_briefing_composer_produces_meeting_actions():
    """RA-06: Composer produces concrete meeting_actions."""
    from src.orchestration.meeting_readiness import FinalBriefingComposer

    composer = FinalBriefingComposer()
    actions = composer.compose(
        synthesis={
            "recommended_engagement_paths": ["excess_inventory"],
            "opportunity_assessment_summary": "Strong excess inventory signal.",
        },
        answer_matrix={
            "q_company_fundamentals": {"status": "answered"},
            "q_contact_intelligence": {"status": "partially_answered"},
        },
        quality_review={"open_gaps": ["Revenue trend unclear"]},
        resolution_state={"resolution_plan": {"unresolved": {"customer_confirmation_items": ["Confirm ownership"]}}},
        company_name="TestCo",
    )
    assert len(actions) >= 2
    types = [a.action_type for a in actions]
    assert "prepare_meeting" in types
    assert any(a.title for a in actions)


def test_runtime_guardrails_structured_validation():
    """RA-08: Structured-output validation for runtime artifacts."""
    from src.orchestration.runtime_guardrails import validate_structured_artifact

    valid = validate_structured_artifact("EvidencePacket", {"packet_id": "p1", "claim": "test"})
    assert valid["valid"] is True

    invalid = validate_structured_artifact("EvidencePacket", {"confidence": "INVALID"})
    assert invalid["valid"] is False

    unknown = validate_structured_artifact("UnknownType", {})
    assert unknown["valid"] is True  # no schema = passthrough


def test_runtime_guardrails_phase_budget_tracker():
    """RA-08: Phase-aware budget tracking with stop reasons."""
    from src.orchestration.runtime_guardrails import PhaseBudgetTracker

    tracker = PhaseBudgetTracker(first_pass_budget=100, closure_budget=50)
    assert tracker.check_budget("first_pass") is True

    tracker.record_phase_tokens("first_pass", 120)
    assert tracker.check_budget("first_pass") is False
    tracker.record_stop("first_pass", "token_budget_exceeded")

    snap = tracker.snapshot()
    assert snap["budgets"]["first_pass"]["used"] == 120
    assert len(snap["stop_reasons"]) == 1
    assert snap["stop_reasons"][0]["reason"] == "token_budget_exceeded"


def test_runtime_guardrails_deterministic_ordering():
    """RA-08: Deterministic ordering for answer matrix and meeting actions."""
    from src.orchestration.runtime_guardrails import sort_answer_matrix, sort_meeting_actions

    matrix = {
        "q_contact_intelligence": {"status": "pending"},
        "q_company_fundamentals": {"status": "answered"},
        "q_market_situation": {"status": "answered"},
    }
    sorted_items = sort_answer_matrix(matrix)
    assert sorted_items[0][0] == "q_company_fundamentals"
    assert sorted_items[1][0] == "q_market_situation"
    assert sorted_items[2][0] == "q_contact_intelligence"

    actions = [
        {"action_type": "hold", "title": "wait"},
        {"action_type": "prepare_meeting", "title": "lead"},
        {"action_type": "collect_missing_evidence", "title": "validate"},
    ]
    sorted_actions = sort_meeting_actions(actions)
    assert sorted_actions[0]["action_type"] == "prepare_meeting"
    assert sorted_actions[1]["action_type"] == "collect_missing_evidence"
    assert sorted_actions[2]["action_type"] == "hold"
