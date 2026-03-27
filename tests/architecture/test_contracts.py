"""Pure contract tests for runtime dataclasses and state objects.

Validates:
- TaskArtifact, TaskReviewArtifact, TaskDecisionArtifact construction and serialization
- DepartmentRunState artifact lifecycle, terminal detection, serialization
- TERMINAL_OUTCOMES / NON_TERMINAL_OUTCOMES / OUTCOME_TO_TASK_STATUS mappings

NO AG2/autogen dependency.
"""
from __future__ import annotations

import json

from src.orchestration.contracts import (
    ContractViolation,
    DepartmentRunState,
    DEPENDENCY_SATISFYING_OUTCOMES,
    TaskArtifact,
    TaskDecisionArtifact,
    TaskReviewArtifact,
    TERMINAL_OUTCOMES,
    NON_TERMINAL_OUTCOMES,
    OUTCOME_TO_TASK_STATUS,
)


# ===========================================================================
# TaskArtifact
# ===========================================================================

class TestTaskArtifact:
    def test_from_worker_report(self):
        report = {
            "task_key": "company_fundamentals",
            "worker": "CompanyResearcher",
            "facts": ["ACME makes widgets", "Founded 1985"],
            "payload": {"company_name": "ACME GmbH"},
            "queries_used": ["ACME GmbH annual report"],
            "sources": [{"url": "https://acme.de", "title": "ACME"}],
            "open_questions": ["Revenue unclear"],
            "objective": "Establish company identity",
        }
        artifact = TaskArtifact.from_worker_report(report, attempt=1)
        assert artifact.task_key == "company_fundamentals"
        assert artifact.attempt == 1
        assert len(artifact.facts) == 2
        assert artifact.payload["company_name"] == "ACME GmbH"
        assert artifact.queries_used == ["ACME GmbH annual report"]

    def test_to_dict_round_trip(self):
        artifact = TaskArtifact(
            task_key="market_situation",
            attempt=2,
            facts=["Market growing"],
            payload={"key_trends": ["EV shift"]},
        )
        d = artifact.to_dict()
        assert d["task_key"] == "market_situation"
        assert d["attempt"] == 2
        assert d["facts"] == ["Market growing"]


# ===========================================================================
# TaskReviewArtifact
# ===========================================================================

class TestTaskReviewArtifact:
    def test_from_critic_review(self):
        review = {
            "approved": True,
            "core_passed": 3,
            "core_total": 3,
            "supporting_passed": 1,
            "supporting_total": 1,
            "accepted_points": ["company_name present", "industry present"],
            "rejected_points": [],
            "issues": [],
            "evidence_strength": "strong",
            "method_issue": False,
        }
        artifact = TaskReviewArtifact.from_critic_review(
            review, task_key="company_fundamentals", attempt=1, reviewer="CompanyCritic"
        )
        assert artifact.approved is True
        assert artifact.core_passed == 3
        assert artifact.core_total == 3
        assert "company_name present" in artifact.accepted_points

    def test_rejected_review_captures_issues(self):
        review = {
            "approved": False,
            "core_passed": 0,
            "core_total": 2,
            "accepted_points": [],
            "rejected_points": ["company_name missing"],
            "issues": ["company_name is n/v"],
            "evidence_strength": "weak",
            "method_issue": True,
        }
        artifact = TaskReviewArtifact.from_critic_review(
            review, task_key="company_fundamentals", attempt=1
        )
        assert artifact.approved is False
        assert artifact.method_issue is True
        assert "company_name is n/v" in artifact.issues


# ===========================================================================
# TaskDecisionArtifact
# ===========================================================================

class TestTaskDecisionArtifact:
    def test_from_judge_result_accept(self):
        result = {
            "task_status": "accepted",
            "decision": "accepted",
            "confidence": "high",
            "open_questions": [],
            "reason": "All core rules passed.",
        }
        decision = TaskDecisionArtifact.from_judge_result(
            result, task_key="company_fundamentals", attempt=1
        )
        assert decision.task_status == "accepted"
        assert decision.outcome == "accepted"
        assert decision.decided_by == "judge"
        assert decision.is_terminal is True

    def test_from_judge_result_degraded(self):
        result = {
            "task_status": "degraded",
            "decision": "accepted_with_gaps",
            "confidence": "low",
            "open_questions": ["Revenue not confirmed"],
        }
        decision = TaskDecisionArtifact.from_judge_result(
            result, task_key="economic_commercial_situation", attempt=2
        )
        assert decision.outcome == "accepted_with_gaps"
        assert decision.is_terminal is True
        assert "Revenue not confirmed" in decision.open_questions

    def test_from_judge_result_rejected(self):
        result = {"task_status": "degraded", "decision": "closed_unresolved", "open_questions": ["No evidence found"]}
        decision = TaskDecisionArtifact.from_judge_result(
            result, task_key="peer_companies", attempt=2
        )
        assert decision.outcome == "closed_unresolved"
        assert decision.is_terminal is True

    def test_lead_accepted_factory(self):
        review = TaskReviewArtifact(
            task_key="market_situation",
            attempt=1,
            approved=True,
            core_passed=2,
            core_total=2,
        )
        decision = TaskDecisionArtifact.lead_accepted(
            task_key="market_situation", attempt=1, review=review
        )
        assert decision.decided_by == "lead"
        assert decision.task_status == "accepted"
        assert decision.confidence == "high"

    def test_terminal_vs_non_terminal(self):
        for outcome in TERMINAL_OUTCOMES:
            d = TaskDecisionArtifact(
                task_key="t", attempt=1, outcome=outcome,
                task_status="accepted"
            )
            assert d.is_terminal, f"{outcome} should be terminal"
        for outcome in NON_TERMINAL_OUTCOMES:
            d = TaskDecisionArtifact(
                task_key="t", attempt=1, outcome=outcome,
                task_status="pending"
            )
            assert not d.is_terminal, f"{outcome} should be non-terminal"

    def test_outcome_to_task_status_mapping(self):
        assert OUTCOME_TO_TASK_STATUS["accepted"] == "accepted"
        assert OUTCOME_TO_TASK_STATUS["accepted_with_gaps"] == "degraded"
        assert OUTCOME_TO_TASK_STATUS["closed_unresolved"] == "degraded"


# ===========================================================================
# DepartmentRunState
# ===========================================================================

class TestDepartmentRunState:
    def _make_state(self) -> DepartmentRunState:
        return DepartmentRunState(department="CompanyDepartment")

    def test_record_and_retrieve_artifacts(self):
        state = self._make_state()
        artifact = TaskArtifact(task_key="company_fundamentals", attempt=1, facts=["fact1"])
        state.record_task_artifact(artifact)
        assert state.latest_artifact("company_fundamentals") is artifact
        assert len(state.task_artifacts["company_fundamentals"]) == 1

    def test_multiple_attempts_all_stored(self):
        state = self._make_state()
        for i in range(1, 4):
            state.record_task_artifact(
                TaskArtifact(task_key="market_situation", attempt=i, facts=[f"fact attempt {i}"])
            )
        assert len(state.task_artifacts["market_situation"]) == 3
        assert state.latest_artifact("market_situation").attempt == 3

    def test_backward_compat_flat_views_updated(self):
        state = self._make_state()
        artifact = TaskArtifact(task_key="peer_companies", attempt=1, facts=["Peer A"])
        state.record_task_artifact(artifact)
        assert "peer_companies" in state.task_results
        assert state.task_results["peer_companies"]["facts"] == ["Peer A"]

    def test_review_backward_compat(self):
        state = self._make_state()
        review = TaskReviewArtifact(
            task_key="company_fundamentals", attempt=1, approved=True,
            accepted_points=["company_name present"]
        )
        state.record_review_artifact(review)
        assert state.latest_review("company_fundamentals") is review
        assert state.last_reviews["company_fundamentals"]["approved"] is True

    def test_judge_escalation_logged(self):
        state = self._make_state()
        decision = TaskDecisionArtifact(
            task_key="peer_companies", attempt=2,
            outcome="closed_unresolved", task_status="degraded",
            decided_by="judge"
        )
        state.record_decision_artifact(decision)
        assert len(state.judge_escalations) == 1
        assert state.judge_escalations[0]["task_key"] == "peer_companies"

    def test_rework_logged_as_strategy_change(self):
        state = self._make_state()
        decision = TaskDecisionArtifact(
            task_key="market_situation", attempt=1,
            outcome="rework_required", task_status="pending",
            decided_by="lead", reason="method_issue detected"
        )
        state.record_decision_artifact(decision)
        assert len(state.strategy_changes) == 1
        assert "method_issue" in state.strategy_changes[0]["reason"]

    def test_coding_support_logged(self):
        state = self._make_state()
        state.record_coding_support("market_situation", ["query A", "query B"])
        assert len(state.coding_support_used) == 1
        assert state.coding_support_used[0]["queries_count"] == 2

    def test_is_task_terminal(self):
        state = self._make_state()
        assert not state.is_task_terminal("company_fundamentals")
        state.record_decision_artifact(TaskDecisionArtifact(
            task_key="company_fundamentals", attempt=1,
            outcome="accepted", task_status="accepted"
        ))
        assert state.is_task_terminal("company_fundamentals")

    def test_to_dict_serialisable(self):
        state = self._make_state()
        state.record_task_artifact(TaskArtifact(task_key="t", attempt=1, facts=["x"]))
        d = state.to_dict()
        json.dumps(d)  # must not raise
        assert "task_artifacts" in d
        assert "review_artifacts" in d
        assert "decision_artifacts" in d

    def test_guardrail_state_returns_shared_dict(self):
        state = self._make_state()
        gs = state.guardrail_state()
        assert isinstance(gs, dict)
        state._consecutive_text_turns["researcher"] = 2
        assert gs.get("researcher") == 2


# ===========================================================================
# Task artifact lifecycle (research → review → decision)
# ===========================================================================

class TestTaskArtifactLifecycle:
    def test_research_review_decision_sequence(self):
        state = DepartmentRunState(department="CompanyDepartment")
        artifact = TaskArtifact(task_key="company_fundamentals", attempt=1, facts=["ACME GmbH is a manufacturer"])
        state.record_task_artifact(artifact)
        assert state.latest_artifact("company_fundamentals") is artifact

        review = TaskReviewArtifact(
            task_key="company_fundamentals", attempt=1,
            approved=True, core_passed=2, core_total=2,
            accepted_points=["company_name present"],
        )
        state.record_review_artifact(review)
        assert state.latest_review("company_fundamentals") is review

        decision = TaskDecisionArtifact.lead_accepted(
            task_key="company_fundamentals", attempt=1, review=review
        )
        state.record_decision_artifact(decision)
        assert state.is_task_terminal("company_fundamentals")
        assert state.latest_decision("company_fundamentals").outcome == "accepted"

    def test_retry_stores_all_attempts(self):
        state = DepartmentRunState(department="MarketDepartment")
        for attempt in range(1, 4):
            state.record_task_artifact(
                TaskArtifact(task_key="market_situation", attempt=attempt)
            )
            state.record_review_artifact(
                TaskReviewArtifact(task_key="market_situation", attempt=attempt, approved=False)
            )
        assert len(state.task_artifacts["market_situation"]) == 3
        assert len(state.review_artifacts["market_situation"]) == 3
        assert state.latest_artifact("market_situation").attempt == 3
        assert state.latest_review("market_situation").attempt == 3


# ===========================================================================
# Package finalization from stored decisions
# ===========================================================================

class TestPackageFinalizationFromDecisions:
    def test_finalize_uses_stored_judge_decision(self):
        state = DepartmentRunState(department="CompanyDepartment")
        state.record_task_artifact(TaskArtifact(
            task_key="company_fundamentals", attempt=2,
            facts=["ACME GmbH manufactures control units"],
            payload={"company_name": "ACME GmbH"},
            sources=[],
        ))
        state.record_review_artifact(TaskReviewArtifact(
            task_key="company_fundamentals", attempt=2,
            approved=False, core_passed=1, core_total=2,
            accepted_points=["company_name present"],
        ))
        decision = TaskDecisionArtifact(
            task_key="company_fundamentals", attempt=2,
            outcome="accepted_with_gaps", task_status="degraded",
            decided_by="judge", open_questions=["Revenue unclear"]
        )
        state.record_decision_artifact(decision)
        assert state.latest_decision("company_fundamentals") is decision
        assert state.latest_decision("company_fundamentals").decided_by == "judge"

    def test_finalize_creates_implicit_decision_for_approved_task(self):
        state = DepartmentRunState(department="CompanyDepartment")
        state.record_task_artifact(TaskArtifact(
            task_key="company_fundamentals", attempt=1,
            facts=["ACME is a manufacturer"],
            payload={"company_name": "ACME GmbH"},
        ))
        state.record_review_artifact(TaskReviewArtifact(
            task_key="company_fundamentals", attempt=1,
            approved=True, core_passed=3, core_total=3,
            accepted_points=["company_name present", "industry confirmed"],
        ))
        assert state.latest_decision("company_fundamentals") is None

        review = state.latest_review("company_fundamentals")
        if review and review.approved:
            implicit = TaskDecisionArtifact.lead_accepted(
                task_key="company_fundamentals", attempt=1, review=review
            )
            state.record_decision_artifact(implicit)

        assert state.latest_decision("company_fundamentals").decided_by == "lead"
        assert state.latest_decision("company_fundamentals").task_status == "accepted"


# ===========================================================================
# F4 — Dependency satisfaction vs. terminality
# ===========================================================================

class TestDependencySatisfaction:
    def test_accepted_is_dependency_satisfying(self):
        state = DepartmentRunState(department="Test")
        state.record_decision_artifact(TaskDecisionArtifact(
            task_key="t1", attempt=1, outcome="accepted", task_status="accepted",
        ))
        assert state.is_dependency_satisfied("t1") is True
        assert state.is_task_terminal("t1") is True

    def test_accepted_with_gaps_is_dependency_satisfying(self):
        state = DepartmentRunState(department="Test")
        state.record_decision_artifact(TaskDecisionArtifact(
            task_key="t1", attempt=1, outcome="accepted_with_gaps", task_status="degraded",
        ))
        assert state.is_dependency_satisfied("t1") is True
        assert state.is_task_terminal("t1") is True

    def test_closed_unresolved_is_terminal_but_not_dependency_satisfying(self):
        state = DepartmentRunState(department="Test")
        state.record_decision_artifact(TaskDecisionArtifact(
            task_key="t1", attempt=2, outcome="closed_unresolved", task_status="degraded",
        ))
        assert state.is_task_terminal("t1") is True
        assert state.is_dependency_satisfied("t1") is False

    def test_blocked_by_dependency_is_terminal_but_not_dependency_satisfying(self):
        state = DepartmentRunState(department="Test")
        state.record_decision_artifact(TaskDecisionArtifact(
            task_key="t1", attempt=1, outcome="blocked_by_dependency",
            task_status="blocked", decided_by="runtime",
        ))
        assert state.is_task_terminal("t1") is True
        assert state.is_dependency_satisfied("t1") is False

    def test_no_decision_is_not_satisfied(self):
        state = DepartmentRunState(department="Test")
        assert state.is_dependency_satisfied("t1") is False

    def test_dependency_satisfying_outcomes_is_subset_of_terminal(self):
        assert DEPENDENCY_SATISFYING_OUTCOMES <= TERMINAL_OUTCOMES


# ===========================================================================
# F4 — ContractViolation
# ===========================================================================

class TestContractViolation:
    def test_to_dict(self):
        cv = ContractViolation(
            field_path="company_name",
            violation_type="missing_required_field",
            severity="high",
            message="Field is required",
        )
        d = cv.to_dict()
        assert d["field_path"] == "company_name"
        assert d["severity"] == "high"

    def test_task_artifact_carries_violations(self):
        cv = ContractViolation(
            field_path="industry", violation_type="type_mismatch",
            severity="medium", message="Expected str",
        )
        artifact = TaskArtifact(
            task_key="t1", attempt=1,
            contract_violations=[cv],
            needs_contract_review=False,
        )
        d = artifact.to_dict()
        assert len(d["contract_violations"]) == 1
        assert d["contract_violations"][0]["field_path"] == "industry"
        assert d["needs_contract_review"] is False

    def test_task_artifact_needs_contract_review_flag(self):
        cv = ContractViolation(
            field_path="*", violation_type="type_mismatch",
            severity="high", message="Total failure",
        )
        artifact = TaskArtifact(
            task_key="t1", attempt=1,
            contract_violations=[cv],
            needs_contract_review=True,
        )
        assert artifact.needs_contract_review is True


# ===========================================================================
# F4 — Schema validation helper
# ===========================================================================

class TestSchemaValidationHelper:
    def test_valid_payload_produces_no_violations(self):
        from src.agents.lead import _validate_payload_against_task_schema
        violations = _validate_payload_against_task_schema(
            "CompanyFundamentals",
            {"company_name": "ACME", "website": "acme.de", "industry": "Mfg"},
        )
        assert violations == []

    def test_empty_schema_key_produces_no_violations(self):
        from src.agents.lead import _validate_payload_against_task_schema
        violations = _validate_payload_against_task_schema("", {"anything": "ok"})
        assert violations == []

    def test_unknown_schema_key_produces_no_violations(self):
        from src.agents.lead import _validate_payload_against_task_schema
        violations = _validate_payload_against_task_schema("NonExistent", {"x": 1})
        assert violations == []

    def test_empty_payload_against_schema_with_defaults_passes(self):
        """Pydantic models with all-default fields accept empty dicts."""
        from src.agents.lead import _validate_payload_against_task_schema
        violations = _validate_payload_against_task_schema("CompanyFundamentals", {})
        # CompanyFundamentals has all defaults, so empty dict validates fine
        assert violations == []

    def test_approved_review_without_decision_is_dependency_satisfying(self):
        """Fix: during GroupChat, approved review satisfies dependency before finalize_package."""
        state = DepartmentRunState(department="Test")
        # Record artifact + approved review, but NO decision yet
        state.record_task_artifact(TaskArtifact(task_key="t1", attempt=1, facts=["fact"]))
        state.record_review_artifact(TaskReviewArtifact(
            task_key="t1", attempt=1, approved=True, core_passed=2, core_total=2,
        ))
        # No decision recorded — simulates mid-GroupChat state
        assert state.latest_decision("t1") is None
        assert state.is_dependency_satisfied("t1") is True

    def test_rejected_review_without_decision_is_still_satisfied_if_artifact_has_facts(self):
        """Rejected review but artifact has facts — dependency satisfied (Level 3).
        Dependency semantics = 'upstream produced data', not 'upstream passed review'."""
        state = DepartmentRunState(department="Test")
        state.record_task_artifact(TaskArtifact(task_key="t1", attempt=1, facts=["fact"]))
        state.record_review_artifact(TaskReviewArtifact(
            task_key="t1", attempt=1, approved=False, core_passed=0, core_total=2,
        ))
        assert state.is_dependency_satisfied("t1") is True

    def test_artifact_without_review_is_dependency_satisfying(self):
        """Research completed but not yet reviewed — dependency satisfied (Level 3)."""
        state = DepartmentRunState(department="Test")
        state.record_task_artifact(TaskArtifact(
            task_key="t1", attempt=1, facts=["some evidence found"],
        ))
        # No review, no decision — just a research artifact with facts
        assert state.latest_review("t1") is None
        assert state.latest_decision("t1") is None
        assert state.is_dependency_satisfied("t1") is True

    def test_empty_artifact_without_facts_is_not_dependency_satisfying(self):
        """Research ran but produced no facts — dependency NOT satisfied."""
        state = DepartmentRunState(department="Test")
        state.record_task_artifact(TaskArtifact(
            task_key="t1", attempt=1, facts=[],
        ))
        assert state.is_dependency_satisfied("t1") is False

    def test_explicit_closed_unresolved_overrides_artifact(self):
        """Explicit non-satisfying decision takes precedence over artifact."""
        state = DepartmentRunState(department="Test")
        state.record_task_artifact(TaskArtifact(
            task_key="t1", attempt=1, facts=["some evidence"],
        ))
        state.record_decision_artifact(TaskDecisionArtifact(
            task_key="t1", attempt=1, outcome="closed_unresolved",
            task_status="degraded",
        ))
        assert state.is_dependency_satisfied("t1") is False
