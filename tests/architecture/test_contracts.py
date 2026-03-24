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
    DepartmentRunState,
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
            "decision": "accept",
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
        result = {"task_status": "rejected", "open_questions": ["No evidence found"]}
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
