"""RA-09: Negative-path tests for the meeting-ready runtime model.

These tests verify that the system correctly BLOCKS finalization when
meeting-readiness conditions are not met.
"""
from __future__ import annotations

from src.app.use_cases import (
    BLOCKED_RUN_STATUS,
    SELECTION_REQUIRED_RUN_STATUS,
    SUCCESS_RUN_STATUS,
    determine_final_status,
)
from src.orchestration.meeting_readiness import FinalBriefingComposer, MeetingReadinessGate
from src.orchestration.runtime_guardrails import validate_structured_artifact


# ---------------------------------------------------------------------------
# Negative path: unresolved public gaps block finalization
# ---------------------------------------------------------------------------

def test_unresolved_public_gaps_block_finalization():
    status = determine_final_status(
        readiness_usable=True,
        first_round_resolution={"bucket": "AUTO_CLOSE_REQUIRED"},
        remaining_public_gaps=["Revenue trend unclear", "Market size unknown"],
    )
    assert status == BLOCKED_RUN_STATUS


def test_gate_blocks_when_public_gaps_remain_in_resolution_state():
    gate = MeetingReadinessGate()
    result = gate.evaluate(
        answer_matrix={"q_company_fundamentals": {"status": "answered"}},
        resolution_state={
            "auto_close": {"remaining_public_gaps": ["Unresolved gap"]},
            "dashboard_state": {},
        },
        evidence_health="medium",
        readiness_usable=True,
    )
    assert not result.meeting_ready
    assert any("gap" in r.lower() for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Negative path: missing dashboard decisions block finalization
# ---------------------------------------------------------------------------

def test_missing_dashboard_decisions_block_finalization():
    gate = MeetingReadinessGate()
    result = gate.evaluate(
        answer_matrix={"q_company_fundamentals": {"status": "answered"}},
        resolution_state={
            "auto_close": {"remaining_public_gaps": []},
            "dashboard_state": {"pending_user_selection": True},
        },
        evidence_health="medium",
        readiness_usable=True,
    )
    assert not result.meeting_ready
    assert any("user" in r.lower() or "selection" in r.lower() for r in result.blocked_reasons)


def test_user_decision_required_bucket_produces_selection_status():
    status = determine_final_status(
        readiness_usable=True,
        first_round_resolution={"bucket": "USER_DECISION_REQUIRED"},
        remaining_public_gaps=[],
    )
    assert status == SELECTION_REQUIRED_RUN_STATUS


# ---------------------------------------------------------------------------
# Negative path: schema parse failure blocks success
# ---------------------------------------------------------------------------

def test_invalid_evidence_packet_schema_detected():
    result = validate_structured_artifact("EvidencePacket", {"confidence": "INVALID_VALUE"})
    assert result["valid"] is False
    assert "error" in result


def test_invalid_gap_candidate_schema_detected():
    result = validate_structured_artifact("GapCandidate", {"severity": "CATASTROPHIC"})
    assert result["valid"] is False


def test_invalid_meeting_action_schema_detected():
    result = validate_structured_artifact("MeetingAction", {"action_type": "NONEXISTENT"})
    assert result["valid"] is False


# ---------------------------------------------------------------------------
# Negative path: low evidence blocks gate
# ---------------------------------------------------------------------------

def test_low_evidence_health_blocks_gate():
    gate = MeetingReadinessGate()
    # Low evidence + thin coverage (< 4 answered) = blocked
    result = gate.evaluate(
        answer_matrix={"q_company_fundamentals": {"status": "answered"}},
        resolution_state={"auto_close": {"remaining_public_gaps": []}, "dashboard_state": {}},
        evidence_health="low",
        readiness_usable=False,
    )
    assert not result.meeting_ready


def test_readiness_not_usable_blocks_gate():
    gate = MeetingReadinessGate()
    # Not usable + thin coverage = blocked
    result = gate.evaluate(
        answer_matrix={"q_company_fundamentals": {"status": "answered"}},
        resolution_state={"auto_close": {"remaining_public_gaps": []}, "dashboard_state": {}},
        evidence_health="high",
        readiness_usable=False,
    )
    assert not result.meeting_ready


# ---------------------------------------------------------------------------
# Negative path: pending non-contact questions block gate
# ---------------------------------------------------------------------------

def test_pending_non_contact_questions_block_gate():
    gate = MeetingReadinessGate()
    result = gate.evaluate(
        answer_matrix={
            "q_company_fundamentals": {"status": "answered"},
            "q_market_situation": {"status": "pending"},  # non-contact, still pending
        },
        resolution_state={"auto_close": {"remaining_public_gaps": []}, "dashboard_state": {}},
        evidence_health="medium",
        readiness_usable=True,
    )
    assert not result.meeting_ready
    assert any("pending" in r.lower() or "blocked" in r.lower() for r in result.blocked_reasons)


def test_pending_contact_question_does_not_block_gate():
    """Contact gaps are customer-confirmation items, not blockers."""
    gate = MeetingReadinessGate()
    result = gate.evaluate(
        answer_matrix={
            "q_company_fundamentals": {"status": "answered"},
            "q_market_situation": {"status": "answered"},
            "q_peer_companies": {"status": "answered"},
            "q_monetization_redeployment": {"status": "answered"},
            "q_contact_intelligence": {"status": "pending"},  # contact = not blocking
        },
        resolution_state={"auto_close": {"remaining_public_gaps": []}, "dashboard_state": {}},
        evidence_health="medium",
        readiness_usable=True,
    )
    assert result.meeting_ready


def test_low_evidence_does_not_block_when_coverage_is_strong():
    """Low evidence_health should not block when many questions are answered."""
    gate = MeetingReadinessGate()
    result = gate.evaluate(
        answer_matrix={
            "q_company_fundamentals": {"status": "answered"},
            "q_economic_commercial_situation": {"status": "partially_answered"},
            "q_market_situation": {"status": "partially_answered"},
            "q_peer_companies": {"status": "answered"},
            "q_monetization_redeployment": {"status": "answered"},
            "q_contact_intelligence": {"status": "partially_answered"},
        },
        resolution_state={"auto_close": {"remaining_public_gaps": []}, "dashboard_state": {}},
        evidence_health="low",
        readiness_usable=True,
    )
    # Strong answered/partial coverage should NOT be blocked by low evidence alone
    assert result.meeting_ready


# ---------------------------------------------------------------------------
# Positive path: composer fallback when no paths
# ---------------------------------------------------------------------------

def test_composer_produces_hold_action_when_no_evidence():
    composer = FinalBriefingComposer()
    actions = composer.compose(
        synthesis={"recommended_engagement_paths": ["further_validation_required"]},
        answer_matrix={},
        quality_review={"open_gaps": []},
        resolution_state={"resolution_plan": {"unresolved": {}}},
        company_name="EmptyCo",
    )
    assert len(actions) >= 1
    assert actions[0].action_type == "hold"
