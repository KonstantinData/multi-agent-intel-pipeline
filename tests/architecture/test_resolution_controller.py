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
