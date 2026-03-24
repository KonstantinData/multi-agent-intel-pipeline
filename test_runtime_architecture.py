"""DEPRECATED — migrated to tests/architecture/ and tests/integration/.

This file is kept for reference only. Run `pytest tests/` instead.
See TESTING.md for the new test structure.
"""
from __future__ import annotations

import pytest
pytest.skip("Migrated to tests/. Run pytest tests/ instead.", allow_module_level=True)

# Original content below (unreachable due to skip above)
"""
Tests for the CHG-00..CHG-10 runtime architecture refactor.

Covers:
1. CHG-01: Runtime contract objects (TaskArtifact, DepartmentRunState, ...)
2. CHG-02: Run brain — ShortTermMemoryStore carries department_run_states
3. CHG-03: No supervisor revision callback during department run
4. CHG-04: Selector acts as guardrail, not workflow choreographer
5. CHG-05: Artifact lifecycle (task → review → decision)
6. CHG-07: Package finalization from stored decisions
7. CHG-08: Follow-up rehydration uses run brain artifacts
8. CHG-09: Consolidation emits only process-safe patterns (no company facts)
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.orchestration.contracts import (
    DepartmentRunState,
    TaskArtifact,
    TaskDecisionArtifact,
    TaskReviewArtifact,
    TERMINAL_OUTCOMES,
    NON_TERMINAL_OUTCOMES,
    OUTCOME_TO_TASK_STATUS,
)
from src.memory.short_term_store import ShortTermMemoryStore
from src.memory.consolidation import (
    consolidate_role_patterns,
    _scrub_company_from_query,
    _is_process_safe_query,
    _to_structural_patterns,
)
from src.orchestration.follow_up import _extract_task_evidence, _get_department_run_state


# ===========================================================================
# 1. CHG-01: Runtime contract objects
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
        # task_results flat view must be updated
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
        # last_reviews flat view must be updated
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
        import json
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
        # Same object — mutations by selector are reflected in state
        state._consecutive_text_turns["researcher"] = 2
        assert gs.get("researcher") == 2


# ===========================================================================
# 2. CHG-02: Run brain — ShortTermMemoryStore
# ===========================================================================

class TestShortTermMemoryStoreRunBrain:
    def test_record_department_run_state(self):
        store = ShortTermMemoryStore()
        run_state_dict = {
            "department": "CompanyDepartment",
            "task_artifacts": {"company_fundamentals": [{"task_key": "company_fundamentals", "attempt": 1}]},
        }
        store.record_department_run_state("CompanyDepartment", run_state_dict)
        assert "CompanyDepartment" in store.department_run_states
        assert store.department_run_states["CompanyDepartment"]["department"] == "CompanyDepartment"

    def test_snapshot_includes_department_run_states(self):
        store = ShortTermMemoryStore()
        store.record_department_run_state("MarketDepartment", {"department": "MarketDepartment"})
        snap = store.snapshot()
        assert "department_run_states" in snap
        assert "MarketDepartment" in snap["department_run_states"]

    def test_department_run_states_are_run_specific(self):
        """Verify that department_run_states exist in the run brain snapshot."""
        store = ShortTermMemoryStore()
        store.record_department_run_state("BuyerDepartment", {"judge_escalations": [{"task_key": "peer_companies"}]})
        snap = store.snapshot()
        escalations = snap["department_run_states"]["BuyerDepartment"].get("judge_escalations", [])
        assert len(escalations) == 1


# ===========================================================================
# 3. CHG-03: No supervisor in department loop
# ===========================================================================

class TestNoSupervisorInDepartmentLoop:
    def test_department_lead_run_has_no_supervisor_param(self):
        """DepartmentLeadAgent.run() must not accept a supervisor parameter."""
        from src.agents.lead import DepartmentLeadAgent
        lead = DepartmentLeadAgent("CompanyDepartment")
        import inspect
        sig = inspect.signature(lead.run)
        params = sig.parameters
        assert "supervisor" not in params, (
            "supervisor parameter still present in DepartmentLeadAgent.run() — "
            "P1-1 requires full removal"
        )

    def test_department_runtime_run_has_no_supervisor_param(self):
        from src.orchestration.department_runtime import DepartmentRuntime
        import inspect
        rt = DepartmentRuntime.__new__(DepartmentRuntime)
        sig = inspect.signature(rt.run)
        params = sig.parameters
        assert "supervisor" not in params, (
            "supervisor parameter still present in DepartmentRuntime.run() — "
            "P1-1 requires full removal"
        )

    def test_lead_has_no_request_supervisor_revision_tool(self):
        """request_supervisor_revision must not be used as a function/tool in lead.py."""
        import src.agents.lead as lead_mod
        import inspect, re
        source = inspect.getsource(lead_mod)
        # Strip comments and docstrings before checking; only flag actual code usage
        # (def, assignment, or call — not documentation references)
        code_lines = [
            ln for ln in source.split("\n")
            if not ln.strip().startswith("#") and not ln.strip().startswith('"""') and not ln.strip().startswith("'''")
        ]
        for line in code_lines:
            # Skip lines that are part of a docstring (inside triple quotes) by
            # looking for actual Python usage: def/=/(
            if re.search(r"\brequest_supervisor_revision\s*[=(]", line):
                raise AssertionError(
                    f"request_supervisor_revision used as code in lead.py: {line!r}\n"
                    "CHG-03 requires it to be removed"
                )

    def test_supervisor_decide_revision_not_called_in_lead(self):
        """supervisor.decide_revision() must not be called inside lead.py."""
        import src.agents.lead as lead_mod
        import inspect
        source = inspect.getsource(lead_mod)
        assert "decide_revision" not in source, (
            "supervisor.decide_revision() still called in lead.py — "
            "CHG-03 requires department autonomy"
        )


# ===========================================================================
# 4. CHG-04: Selector is guardrail-only
# ===========================================================================

class TestSelectorGuardrails:
    def _make_selector(self):
        from src.orchestration.speaker_selector import build_department_selector
        guardrail_state: dict = {}
        agents = {name: MagicMock(name=name) for name in
                  ["Lead", "Researcher", "Critic", "Judge", "Coding", "Executor"]}
        for name, agent in agents.items():
            agent.name = name
        selector = build_department_selector(
            guardrail_state=guardrail_state,
            agent_map=agents,
            lead_name="Lead",
            researcher_name="Researcher",
            critic_name="Critic",
            judge_name="Judge",
            coding_name="Coding",
            executor_name="Executor",
        )
        return selector, agents, guardrail_state

    def _fake_gc(self, messages):
        gc = MagicMock()
        gc.messages = messages
        return gc

    def test_tool_call_routes_to_executor(self):
        selector, agents, _ = self._make_selector()
        gc = self._fake_gc([{"name": "Researcher", "tool_calls": [{"function": "run_research"}]}])
        result = selector(agents["Researcher"], gc)
        assert result.name == "Executor"

    def test_executor_done_routes_to_lead(self):
        selector, agents, _ = self._make_selector()
        gc = self._fake_gc([{"name": "Executor", "content": "tool result"}])
        result = selector(agents["Executor"], gc)
        assert result.name == "Lead"

    def test_loop_prevention_forces_lead(self):
        selector, agents, _ = self._make_selector()
        gc = self._fake_gc([{"name": "Researcher", "content": "I will search"}])
        # Trigger 3 consecutive text turns from Researcher
        for _ in range(3):
            result = selector(agents["Researcher"], gc)
        # After 3 text turns, selector should return Lead
        assert result.name == "Lead"

    def test_lead_addressing_researcher_routes_to_researcher(self):
        selector, agents, _ = self._make_selector()
        gc = self._fake_gc([{"name": "Lead", "content": "Researcher, please call run_research(task_key=company_fundamentals)"}])
        result = selector(agents["Lead"], gc)
        assert result.name == "Researcher"

    def test_lead_addressing_critic_routes_to_critic(self):
        selector, agents, _ = self._make_selector()
        gc = self._fake_gc([{"name": "Lead", "content": "Critic, please review_research(task_key=company_fundamentals)"}])
        result = selector(agents["Lead"], gc)
        assert result.name == "Critic"

    def test_lead_addressing_judge_routes_to_judge(self):
        selector, agents, _ = self._make_selector()
        gc = self._fake_gc([{"name": "Lead", "content": "Judge, please call judge_decision(task_key=peer_companies)"}])
        result = selector(agents["Lead"], gc)
        assert result.name == "Judge"

    def test_lead_addressing_coding_routes_to_coding(self):
        selector, agents, _ = self._make_selector()
        gc = self._fake_gc([{"name": "Lead", "content": "Coding, please suggest_refined_queries(task_key=market_situation)"}])
        result = selector(agents["Lead"], gc)
        assert result.name == "Coding"

    def test_selector_has_no_workflow_step(self):
        """Selector must not reference workflow_step anywhere."""
        import src.orchestration.speaker_selector as sel_mod
        import inspect
        source = inspect.getsource(sel_mod)
        # workflow_step should only appear in the synthesis selector (legacy comment allowed)
        # but should NOT appear in build_department_selector
        lines = source.split("\n")
        in_dept_selector = False
        in_docstring = False
        for line in lines:
            stripped = line.strip()
            if '"""' in line or "'''" in line:
                # Toggle docstring state on triple-quote boundaries
                in_docstring = not in_docstring
            if "def build_department_selector" in line:
                in_dept_selector = True
                in_docstring = False
            if in_dept_selector and "def build_synthesis_selector" in line:
                in_dept_selector = False
            if (
                in_dept_selector
                and not in_docstring
                and "workflow_step" in line
                and not stripped.startswith("#")
                and not stripped.startswith('"""')
                and not stripped.startswith("'''")
            ):
                raise AssertionError(
                    f"workflow_step still used as code in build_department_selector: {line!r}"
                    "\n — the Lead owns the workflow."
                )

    def test_non_lead_text_turn_routes_back_to_lead(self):
        selector, agents, _ = self._make_selector()
        gc = self._fake_gc([{"name": "Critic", "content": "The research looks weak."}])
        result = selector(agents["Critic"], gc)
        assert result.name == "Lead"


# ===========================================================================
# 5. CHG-05: Task artifact lifecycle
# ===========================================================================

class TestTaskArtifactLifecycle:
    def test_research_review_decision_sequence(self):
        state = DepartmentRunState(department="CompanyDepartment")

        # Step 1: research produces artifact
        artifact = TaskArtifact(task_key="company_fundamentals", attempt=1, facts=["ACME GmbH is a manufacturer"])
        state.record_task_artifact(artifact)
        assert state.latest_artifact("company_fundamentals") is artifact

        # Step 2: review produces review artifact
        review = TaskReviewArtifact(
            task_key="company_fundamentals", attempt=1,
            approved=True, core_passed=2, core_total=2,
            accepted_points=["company_name present"],
        )
        state.record_review_artifact(review)
        assert state.latest_review("company_fundamentals") is review

        # Step 3: decision closes the task
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
        # Latest is attempt 3
        assert state.latest_artifact("market_situation").attempt == 3
        assert state.latest_review("market_situation").attempt == 3


# ===========================================================================
# 7. CHG-07: Package finalization from stored decisions
# ===========================================================================

class TestPackageFinalizationFromDecisions:
    def _make_assignment(self, task_key: str):
        from src.orchestration.task_router import Assignment
        return Assignment(
            task_key=task_key,
            assignee="CompanyResearcher",
            target_section="company_profile",
            label=task_key.replace("_", " ").title(),
            objective=f"Investigate {task_key}",
            model_name="gpt-4.1-mini",
            allowed_tools=("web_search",),
        )

    def test_finalize_uses_stored_judge_decision(self):
        """finalize_package must not re-judge tasks that already have a decision artifact."""
        from src.agents.lead import DepartmentLeadAgent
        lead = DepartmentLeadAgent("CompanyDepartment")

        state = DepartmentRunState(department="CompanyDepartment")
        # Pre-populate: research + review + judge decision
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

        # Verify that latest_decision returns the pre-stored decision
        assert state.latest_decision("company_fundamentals") is decision
        assert state.latest_decision("company_fundamentals").decided_by == "judge"

    def test_finalize_creates_implicit_decision_for_approved_task(self):
        """An approved critic review with no explicit decision → lead_accepted created at finalize."""
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
        # No decision artifact yet
        assert state.latest_decision("company_fundamentals") is None

        # Simulate the implicit decision creation from finalize_package logic
        review = state.latest_review("company_fundamentals")
        if review and review.approved:
            implicit = TaskDecisionArtifact.lead_accepted(
                task_key="company_fundamentals", attempt=1, review=review
            )
            state.record_decision_artifact(implicit)

        assert state.latest_decision("company_fundamentals").decided_by == "lead"
        assert state.latest_decision("company_fundamentals").task_status == "accepted"


# ===========================================================================
# 8. CHG-08: Follow-up rehydration
# ===========================================================================

class TestFollowUpRehydration:
    def _make_run_context_with_artifacts(self) -> dict:
        run_state_dict = {
            "department": "CompanyDepartment",
            "task_artifacts": {
                "company_fundamentals": [
                    {"task_key": "company_fundamentals", "attempt": 1,
                     "facts": ["ACME GmbH is a manufacturer of control units"],
                     "open_questions": ["Revenue not confirmed"]}
                ]
            },
            "review_artifacts": {
                "company_fundamentals": [
                    {"task_key": "company_fundamentals", "attempt": 1,
                     "approved": True,
                     "accepted_points": ["company_name present", "industry confirmed"],
                     "core_passed": 2, "core_total": 2}
                ]
            },
            "decision_artifacts": {
                "company_fundamentals": [
                    {"task_key": "company_fundamentals", "attempt": 1,
                     "outcome": "accepted", "task_status": "accepted",
                     "open_questions": []}
                ]
            },
        }
        return {
            "short_term_memory": {
                "department_packages": {
                    "CompanyDepartment": {"open_questions": ["What is the revenue?"]}
                },
                "department_run_states": {"CompanyDepartment": run_state_dict},
            }
        }

    def test_extract_task_evidence_from_run_state(self):
        run_context = self._make_run_context_with_artifacts()
        run_state = _get_department_run_state(run_context, "CompanyDepartment")
        evidence, unresolved = _extract_task_evidence(run_state)
        # Evidence should include facts from artifacts
        assert any("ACME GmbH" in e for e in evidence), f"Expected ACME in evidence: {evidence}"

    def test_get_department_run_state_returns_empty_for_missing(self):
        result = _get_department_run_state({}, "NonExistentDepartment")
        assert result == {}

    def test_get_department_run_state_returns_stored_dict(self):
        run_context = self._make_run_context_with_artifacts()
        run_state = _get_department_run_state(run_context, "CompanyDepartment")
        assert run_state["department"] == "CompanyDepartment"
        assert "task_artifacts" in run_state

    def test_run_brain_enriches_company_answer(self):
        from src.orchestration.follow_up import _company_answer
        pipeline_data = {
            "company_profile": {
                "company_name": "ACME GmbH",
                "description": "A manufacturer of control units",
                "product_asset_scope": ["control units", "sensors"],
                "economic_situation": {"assessment": "Stable"},
            }
        }
        run_context = self._make_run_context_with_artifacts()
        answer, evidence, unresolved = _company_answer(
            "What products does ACME make?", pipeline_data, run_context
        )
        assert len(evidence) > 0
        assert "ACME GmbH" in answer


# ===========================================================================
# 9. CHG-09: Consolidation emits only process-safe patterns
# ===========================================================================

class TestConsolidationProcessSafety:
    def test_scrub_removes_domain(self):
        q = "ACME GmbH annual report site:acme.de"
        scrubbed = _scrub_company_from_query(q)
        assert "acme.de" not in scrubbed.lower()
        assert "{domain}" in scrubbed

    def test_scrub_removes_quoted_company(self):
        q = '"ACME GmbH" inventory surplus 2024'
        scrubbed = _scrub_company_from_query(q)
        assert '"ACME GmbH"' not in scrubbed

    def test_scrub_removes_gmbh_form(self):
        q = "Mustermann GmbH financial distress signals"
        scrubbed = _scrub_company_from_query(q)
        assert "Mustermann GmbH" not in scrubbed

    def test_process_safe_query_accepted(self):
        assert _is_process_safe_query("manufacturing company inventory surplus signals")
        assert _is_process_safe_query("procurement director site:linkedin.com")

    def test_process_safe_query_rejects_short(self):
        assert not _is_process_safe_query("ACME")
        assert not _is_process_safe_query("  ")

    def test_structural_patterns_strip_company_names(self):
        raw = [
            "ACME GmbH annual report",
            "manufacturer inventory surplus signals",
            '"Mustermann AG" financial distress',
        ]
        patterns = _to_structural_patterns(raw)
        for p in patterns:
            assert "ACME" not in p, f"Company name leaked into pattern: {p}"
            assert "Mustermann" not in p, f"Company name leaked into pattern: {p}"

    def test_consolidation_no_domain_in_pattern_names(self):
        """Consolidated patterns must not store domain or company names."""
        run_context = {
            "short_term_memory": {
                "worker_reports": [
                    {
                        "worker": "CompanyResearcher",
                        "queries_used": [
                            "manufacturer inventory surplus signals",
                            "company financial distress restructuring",
                        ],
                        "task_key": "company_fundamentals",
                    }
                ],
                "sources": [{"source_type": "registry"}],
                "critic_reviews": {},
                "department_run_states": {},
            },
        }
        pipeline_data = {
            "company_profile": {"industry": "Manufacturing"}
        }
        patterns = consolidate_role_patterns(
            run_context=run_context,
            pipeline_data=pipeline_data,
            status="completed",
            usable=True,
        )
        for p in patterns:
            # Pattern name must not contain a domain or company name
            assert "acme" not in p.get("name", "").lower()
            assert "mustermann" not in p.get("name", "").lower()
            # domain field must be empty (CHG-09 policy)
            assert p.get("domain", "") == "", (
                f"Pattern '{p['name']}' has non-empty domain: {p['domain']!r}"
            )

    def test_consolidation_empty_for_failed_run(self):
        patterns = consolidate_role_patterns(
            run_context={}, pipeline_data={}, status="failed", usable=False
        )
        assert patterns == []

    def test_consolidation_empty_for_not_usable(self):
        patterns = consolidate_role_patterns(
            run_context={}, pipeline_data={}, status="completed", usable=False
        )
        assert patterns == []

    def test_consolidation_extracts_critic_heuristics(self):
        run_context = {
            "short_term_memory": {
                "worker_reports": [],
                "sources": [],
                "critic_reviews": {
                    "company_fundamentals": {
                        "core_passed": 2,
                        "core_total": 3,
                        "failed_rule_messages": ["company description too short"],
                    }
                },
                "department_run_states": {},
            }
        }
        pipeline_data = {"company_profile": {"industry": "Automotive"}}
        patterns = consolidate_role_patterns(
            run_context=run_context, pipeline_data=pipeline_data,
            status="completed", usable=True,
        )
        critic_patterns = [p for p in patterns if p.get("pattern_scope") == "critic_heuristics"]
        assert len(critic_patterns) >= 1
        p = critic_patterns[0]
        assert "avg_core_pass_rate" in p
        assert p.get("domain", "") == ""  # no domain stored

    def test_consolidation_judge_patterns_from_run_state(self):
        run_context = {
            "short_term_memory": {
                "worker_reports": [],
                "sources": [],
                "critic_reviews": {},
                "department_run_states": {
                    "CompanyDepartment": {
                        "judge_escalations": [
                            {"task_key": "peer_companies", "attempt": 2,
                             "outcome": "closed_unresolved", "confidence": "low"},
                        ],
                        "coding_support_used": [],
                        "strategy_changes": [],
                    }
                },
            }
        }
        pipeline_data = {"company_profile": {"industry": "Manufacturing"}}
        patterns = consolidate_role_patterns(
            run_context=run_context, pipeline_data=pipeline_data,
            status="completed", usable=True,
        )
        judge_patterns = [p for p in patterns if p.get("pattern_scope") == "judge_principles"]
        assert len(judge_patterns) >= 1
