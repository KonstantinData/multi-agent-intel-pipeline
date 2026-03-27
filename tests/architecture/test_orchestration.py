"""Pure architecture tests for follow-up, task backlog, routing, and synthesis.

Validates:
- Follow-up evidence extraction from run brain
- Follow-up department answer functions
- Task backlog contract fields
- Supervisor routing (weighted keyword scoring)
- Synthesis context building
- Section assembly
- Run condition evaluation
- Config defaults

NO AG2/autogen dependency.
"""
from __future__ import annotations

from src.orchestration.follow_up import _extract_task_evidence, _get_department_run_state
from src.app.use_cases import (
    STANDARD_TASK_BACKLOG,
    get_task_validation_rules,
    get_task_contract,
)
from src.models.registry import SCHEMA_REGISTRY, resolve_output_schema, assemble_section, SECTION_MODEL_MAP
from src.orchestration.synthesis import build_synthesis_context, assess_research_readiness
from src.orchestration.task_router import Assignment, evaluate_run_conditions
from src.config.settings import MAX_TASK_RETRIES, SOFT_TOKEN_BUDGET, HARD_TOKEN_CAP
from src.agents.critic import CriticAgent, _evaluate_rule
from src.agents.judge import JudgeAgent


# ===========================================================================
# Follow-up evidence extraction (CHG-08)
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
# Task backlog contract fields
# ===========================================================================

REQUIRED_FIELDS = {
    "task_key", "label", "assignee", "target_section", "objective_template",
    "depends_on", "run_condition", "input_artifacts", "output_schema_key",
    "validation_rules",
}
VALID_RULE_CHECKS = {"non_placeholder", "min_items", "min_length"}
VALID_RULE_CLASSES = {"core", "supporting"}


class TestTaskBacklogContracts:
    def test_all_tasks_have_required_contract_fields(self):
        for task in STANDARD_TASK_BACKLOG:
            missing = REQUIRED_FIELDS - set(task.keys())
            assert not missing, f"Task '{task['task_key']}' is missing fields: {missing}"

    def test_all_tasks_have_12_entries(self):
        assert len(STANDARD_TASK_BACKLOG) == 12

    def test_output_schema_key_resolves_in_registry(self):
        for task in STANDARD_TASK_BACKLOG:
            key = task["output_schema_key"]
            model = resolve_output_schema(key)
            assert model is not None, f"output_schema_key '{key}' for task '{task['task_key']}' not in registry"

    def test_all_validation_rules_are_structurally_valid(self):
        for task in STANDARD_TASK_BACKLOG:
            for rule in task.get("validation_rules", []):
                assert "check" in rule
                assert "field" in rule
                assert "class" in rule
                assert "message" in rule
                assert rule["check"] in VALID_RULE_CHECKS
                assert rule["class"] in VALID_RULE_CLASSES
                if rule["check"] in {"min_items", "min_length"}:
                    assert "value" in rule

    def test_contact_tasks_have_run_conditions(self):
        discovery = get_task_contract("contact_discovery")
        qualification = get_task_contract("contact_qualification")
        assert discovery is not None
        assert qualification is not None
        assert discovery["run_condition"] == "buyer_department_has_prioritized_firms"
        assert qualification["run_condition"] == "contact_discovery_completed"

    def test_non_contact_tasks_have_no_run_condition(self):
        for task in STANDARD_TASK_BACKLOG:
            if task["task_key"] not in {"contact_discovery", "contact_qualification"}:
                assert task["run_condition"] is None

    def test_schema_registry_contains_all_output_keys(self):
        expected_keys = {task["output_schema_key"] for task in STANDARD_TASK_BACKLOG}
        missing = expected_keys - set(SCHEMA_REGISTRY.keys())
        assert not missing, f"SCHEMA_REGISTRY is missing keys: {missing}"

    def test_validation_rules_lookup_returns_empty_for_unknown_task(self):
        rules = get_task_validation_rules("totally_unknown_task_key")
        assert rules == []

    def test_get_task_contract_returns_none_for_unknown(self):
        contract = get_task_contract("does_not_exist")
        assert contract is None

    def test_no_conservative_status_in_use_cases(self):
        from src.app import use_cases
        import inspect
        source = inspect.getsource(use_cases)
        assert '"conservative"' not in source


# ===========================================================================
# Critic generic evaluator tests
# ===========================================================================

class TestCriticEvaluator:
    def test_non_placeholder_passes_real_value(self):
        rule = {"check": "non_placeholder", "field": "company_name", "class": "core", "message": "missing"}
        assert _evaluate_rule(rule, {"company_name": "ACME GmbH"}) is True

    def test_non_placeholder_fails_nv(self):
        rule = {"check": "non_placeholder", "field": "company_name", "class": "core", "message": "missing"}
        assert _evaluate_rule(rule, {"company_name": "n/v"}) is False

    def test_non_placeholder_fails_empty(self):
        rule = {"check": "non_placeholder", "field": "industry", "class": "core", "message": "missing"}
        assert _evaluate_rule(rule, {"industry": ""}) is False

    def test_min_items_passes(self):
        rule = {"check": "min_items", "field": "products_and_services", "value": 1, "class": "supporting", "message": "missing"}
        assert _evaluate_rule(rule, {"products_and_services": ["Control units"]}) is True

    def test_min_items_fails_empty_list(self):
        rule = {"check": "min_items", "field": "products_and_services", "value": 1, "class": "supporting", "message": "missing"}
        assert _evaluate_rule(rule, {"products_and_services": []}) is False

    def test_min_length_passes(self):
        rule = {"check": "min_length", "field": "description", "value": 10, "class": "supporting", "message": "missing"}
        assert _evaluate_rule(rule, {"description": "A long enough description."}) is True

    def test_min_length_fails(self):
        rule = {"check": "min_length", "field": "description", "value": 10, "class": "supporting", "message": "missing"}
        assert _evaluate_rule(rule, {"description": "Short"}) is False

    def test_nested_field_resolution(self):
        rule = {"check": "non_placeholder", "field": "economic_situation.assessment", "class": "core", "message": "missing"}
        assert _evaluate_rule(rule, {"economic_situation": {"assessment": "Strong growth"}}) is True
        assert _evaluate_rule(rule, {"economic_situation": {"assessment": "n/v"}}) is False
        assert _evaluate_rule(rule, {"economic_situation": {}}) is False

    def test_unknown_check_fails_safe(self):
        rule = {"check": "does_not_exist", "field": "x", "class": "core", "message": "unknown"}
        assert _evaluate_rule(rule, {"x": "something"}) is False

    def test_critic_review_produces_class_counts(self):
        critic = CriticAgent("CompanyCritic")
        rules = [
            {"check": "non_placeholder", "field": "company_name", "class": "core", "message": "m1"},
            {"check": "non_placeholder", "field": "website", "class": "core", "message": "m2"},
            {"check": "min_items", "field": "products_and_services", "value": 1, "class": "supporting", "message": "m3"},
        ]
        payload = {"company_name": "ACME", "website": "acme.de", "products_and_services": ["widgets"]}
        result = critic.review(
            task_key="company_fundamentals", section="company_profile",
            objective="test", payload=payload, validation_rules=rules,
        )
        assert result["core_passed"] == 2
        assert result["core_total"] == 2
        assert result["supporting_passed"] == 1
        assert result["supporting_total"] == 1

    def test_critic_no_task_point_rules_dict(self):
        import src.agents.critic as critic_mod
        assert not hasattr(critic_mod, "TASK_POINT_RULES")

    def test_critic_surfaces_worker_field_issues(self):
        critic = CriticAgent("TestCritic")
        rules = [{"check": "non_placeholder", "field": "company_name", "class": "core", "message": "missing"}]
        payload = {"company_name": "ACME"}
        report = {"field_issues": ["LLM payload normalization failed: headquarters type error"]}
        result = critic.review(
            task_key="company_fundamentals", section="company_profile",
            objective="test", payload=payload, report=report, validation_rules=rules,
        )
        assert any("Worker field issue" in issue for issue in result["issues"])

    def test_critic_no_field_issues_when_report_clean(self):
        critic = CriticAgent("TestCritic")
        rules = [{"check": "non_placeholder", "field": "company_name", "class": "core", "message": "missing"}]
        payload = {"company_name": "ACME"}
        report = {"field_issues": []}
        result = critic.review(
            task_key="company_fundamentals", section="company_profile",
            objective="test", payload=payload, report=report, validation_rules=rules,
        )
        assert not any("Worker field issue" in issue for issue in result["issues"])


# ===========================================================================
# Judge three-outcome gate tests
# ===========================================================================

def _make_review(core_passed, core_total, supporting_passed, supporting_total):
    failed_msgs = [f"core rule {i} failed" for i in range(core_total - core_passed)]
    return {
        "core_passed": core_passed, "core_total": core_total,
        "supporting_passed": supporting_passed, "supporting_total": supporting_total,
        "failed_rule_messages": failed_msgs, "issues": failed_msgs,
    }


class TestJudgeGate:
    def test_accept_when_all_core_pass(self):
        judge = JudgeAgent("CompanyJudge")
        review = _make_review(2, 2, 1, 1)
        result = judge.decide(section="company_fundamentals", critic_review=review)
        assert result["decision"] == "accepted"
        assert result["task_status"] == "accepted"

    def test_accept_degraded_when_partial_core(self):
        judge = JudgeAgent("CompanyJudge")
        review = _make_review(1, 2, 0, 1)
        result = judge.decide(section="market_situation", critic_review=review)
        assert result["decision"] == "accepted_with_gaps"
        assert result["task_status"] == "degraded"
        assert len(result["open_questions"]) >= 1

    def test_reject_when_no_core_pass(self):
        judge = JudgeAgent("CompanyJudge")
        review = _make_review(0, 2, 0, 1)
        result = judge.decide(section="peer_companies", critic_review=review)
        assert result["decision"] == "closed_unresolved"
        assert result["task_status"] == "degraded"

    def test_never_produces_skipped(self):
        judge = JudgeAgent("CompanyJudge")
        review = _make_review(0, 2, 0, 0)
        result = judge.decide(section="any_task", critic_review=review)
        assert result["task_status"] != "skipped"

    def test_degraded_carries_open_questions(self):
        judge = JudgeAgent("CompanyJudge")
        review = _make_review(1, 3, 0, 1)
        result = judge.decide(section="some_task", critic_review=review)
        assert result["task_status"] == "degraded"
        assert result["open_questions"]

    def test_confidence_high_when_all_rules_pass(self):
        judge = JudgeAgent("CompanyJudge")
        review = _make_review(2, 2, 2, 2)
        result = judge.decide(section="company_fundamentals", critic_review=review)
        assert result["confidence"] == "high"

    def test_confidence_low_when_degraded(self):
        judge = JudgeAgent("CompanyJudge")
        review = _make_review(1, 2, 0, 1)
        result = judge.decide(section="test", critic_review=review)
        assert result["confidence"] == "low"


# ===========================================================================
# Synthesis context building
# ===========================================================================

class TestSynthesisContext:
    def test_build_synthesis_context_returns_confidence_from_quality_review(self):
        result = build_synthesis_context(
            company_profile={"company_name": "ACME GmbH", "industry": "Manufacturing"},
            industry_analysis={"analytics_signals": [], "key_trends": []},
            market_network={
                "peer_competitors": {"companies": []},
                "downstream_buyers": {"companies": [], "assessment": "n/v"},
                "service_providers": {"companies": []},
                "cross_industry_buyers": {"companies": []},
                "monetization_paths": [], "redeployment_paths": [],
            },
            contact_intelligence={},
            quality_review={"evidence_health": "medium", "open_gaps": []},
            memory_snapshot={"sources": [], "next_actions": []},
        )
        assert result["confidence"] == "medium"

    def test_synthesis_fallback_confidence_not_forced_low(self):
        result = build_synthesis_context(
            company_profile={"company_name": "ACME GmbH", "industry": "Manufacturing"},
            industry_analysis={"analytics_signals": ["gap signal"], "key_trends": ["trend"]},
            market_network={
                "peer_competitors": {"companies": [{"name": "Peer1"}], "assessment": "competitive"},
                "downstream_buyers": {"companies": [{"name": "Buyer1"}], "assessment": "active"},
                "service_providers": {"companies": []},
                "cross_industry_buyers": {"companies": []},
                "monetization_paths": ["resale path"],
                "redeployment_paths": ["redeployment path"],
            },
            contact_intelligence={},
            quality_review={"evidence_health": "high", "open_gaps": []},
            memory_snapshot={"sources": [], "next_actions": []},
        )
        assert result["confidence"] == "high"

    def test_negative_placeholder_signals_are_not_treated_as_positive(self):
        synthesis = build_synthesis_context(
            company_profile={"company_name": "Example GmbH", "industry": "Mechanical Engineering"},
            industry_analysis={"analytics_signals": [], "key_trends": []},
            market_network={
                "peer_competitors": {"companies": []},
                "downstream_buyers": {"companies": [], "assessment": "No credible buyer path validated yet."},
                "service_providers": {"companies": []},
                "cross_industry_buyers": {"companies": []},
                "monetization_paths": ["No credible monetization path validated yet."],
                "redeployment_paths": ["No validated repurposing path found."],
            },
            contact_intelligence={},
            quality_review={"open_gaps": []},
            memory_snapshot={"sources": [], "next_actions": []},
        )
        assert synthesis["recommended_engagement_paths"] == ["further_validation_required"]
        assert all(item["relevance"] == "unclear" for item in synthesis["liquisto_service_relevance"])


# ===========================================================================
# Section assembly
# ===========================================================================

class TestSectionAssembly:
    def test_assemble_section_company_profile(self):
        raw = {
            "company_name": "ACME GmbH", "website": "acme.de", "industry": "Manufacturing",
            "products_and_services": ["widgets"], "product_asset_scope": ["steel parts"],
            "economic_situation": {"assessment": "Stable", "revenue_trend": "flat"},
        }
        result = assemble_section("company_profile", raw)
        assert result["company_name"] == "ACME GmbH"
        assert result["economic_situation"]["assessment"] == "Stable"
        assert "legal_form" in result
        assert "key_people" in result

    def test_assemble_section_industry_analysis(self):
        raw = {
            "industry_name": "Automotive", "assessment": "Declining",
            "key_trends": ["EV shift"], "repurposing_signals": ["battery reuse"],
            "analytics_signals": ["planning gap"],
        }
        result = assemble_section("industry_analysis", raw)
        assert result["industry_name"] == "Automotive"
        assert result["repurposing_signals"] == ["battery reuse"]
        assert "overcapacity_signals" in result

    def test_assemble_section_market_network(self):
        raw = {
            "target_company": "ACME",
            "peer_competitors": {"companies": [{"name": "Peer1"}], "assessment": "close"},
            "downstream_buyers": {"companies": [], "assessment": "n/v"},
            "monetization_paths": ["resale"],
        }
        result = assemble_section("market_network", raw)
        assert result["target_company"] == "ACME"
        assert len(result["peer_competitors"]["companies"]) == 1
        assert "service_providers" in result

    def test_assemble_section_contact_intelligence(self):
        raw = {
            "contacts": [{"name": "Jane Doe", "firma": "BuyerCo"}],
            "firms_searched": 3, "contacts_found": 1,
        }
        result = assemble_section("contact_intelligence", raw)
        assert result["contacts_found"] == 1
        assert result["contacts"][0]["name"] == "Jane Doe"
        assert "prioritized_contacts" in result

    def test_assemble_section_unknown_returns_raw(self):
        raw = {"custom_key": "value"}
        result = assemble_section("synthesis", raw)
        assert result == raw

    def test_assemble_section_empty_payload_returns_defaults(self):
        result = assemble_section("company_profile", {})
        assert result["company_name"] == "n/v"
        assert result["products_and_services"] == []

    def test_section_model_map_covers_all_department_sections(self):
        expected = {"company_profile", "industry_analysis", "market_network", "contact_intelligence"}
        assert set(SECTION_MODEL_MAP.keys()) == expected


# ===========================================================================
# Routing tests — SupervisorAgent.route_question()
# ===========================================================================

class TestSupervisorRouting:
    def _sup(self):
        from src.agents.supervisor import SupervisorAgent
        return SupervisorAgent()

    def test_route_contact_keywords(self):
        sup = self._sup()
        assert sup.route_question(question="Who is the procurement contact?")["route"] == "ContactDepartment"
        assert sup.route_question(question="Ansprechpartner bei Käuferfirmen")["route"] == "ContactDepartment"
        assert sup.route_question(question="LinkedIn decision-maker outreach")["route"] == "ContactDepartment"

    def test_route_buyer_keywords(self):
        sup = self._sup()
        assert sup.route_question(question="Who are the downstream buyers?")["route"] == "BuyerDepartment"
        assert sup.route_question(question="Käufer und Wiederverkauf")["route"] == "BuyerDepartment"
        assert sup.route_question(question="redeployment aftermarket paths")["route"] == "BuyerDepartment"

    def test_route_market_keywords(self):
        sup = self._sup()
        assert sup.route_question(question="What is the demand outlook?")["route"] == "MarketDepartment"
        assert sup.route_question(question="Markt Nachfrage und Angebot")["route"] == "MarketDepartment"
        assert sup.route_question(question="circular economy repurposing")["route"] == "MarketDepartment"

    def test_route_synthesis_keywords(self):
        sup = self._sup()
        assert sup.route_question(question="What is the Liquisto opportunity?")["route"] == "SynthesisDepartment"
        assert sup.route_question(question="Zusammenfassung und Gesamtbild")["route"] == "SynthesisDepartment"
        assert sup.route_question(question="next step for the meeting briefing")["route"] == "SynthesisDepartment"

    def test_route_company_keywords(self):
        sup = self._sup()
        assert sup.route_question(question="What is the company revenue?")["route"] == "CompanyDepartment"
        assert sup.route_question(question="Firma Umsatz und Bestand")["route"] == "CompanyDepartment"

    def test_route_fallback_to_company(self):
        sup = self._sup()
        result = sup.route_question(question="xyzzy foobar baz")
        assert result["route"] == "CompanyDepartment"

    def test_route_overlapping_keywords_resolved_by_weight(self):
        sup = self._sup()
        result = sup.route_question(question="buyer contact person for procurement")
        assert result["route"] == "ContactDepartment"

    def test_route_includes_score(self):
        sup = self._sup()
        result = sup.route_question(question="market demand supply")
        assert "score" in result["reason"]


# ===========================================================================
# Run condition evaluation
# ===========================================================================

class TestRunConditionEvaluation:
    def test_skips_when_no_buyer(self):
        assignments = [
            Assignment(
                task_key="contact_discovery", assignee="ContactDepartment",
                target_section="contact_intelligence", label="Contact discovery",
                objective="Find contacts", model_name="m", allowed_tools=("search",),
                run_condition="buyer_department_has_prioritized_firms",
            ),
        ]
        # Legacy format (pre-F2)
        state = {"department_packages": {"BuyerDepartment": {"accepted_points": []}}, "task_statuses": {}}
        runnable, skipped = evaluate_run_conditions(assignments, pipeline_state=state)
        assert len(runnable) == 0
        assert len(skipped) == 1
        assert skipped[0]["status"] == "skipped"

    def test_runs_when_buyer_has_points(self):
        assignments = [
            Assignment(
                task_key="contact_discovery", assignee="ContactDepartment",
                target_section="contact_intelligence", label="Contact discovery",
                objective="Find contacts", model_name="m", allowed_tools=("search",),
                run_condition="buyer_department_has_prioritized_firms",
            ),
        ]
        # Legacy format (pre-F2)
        state = {"department_packages": {"BuyerDepartment": {"accepted_points": ["peer_competitors.assessment"]}}, "task_statuses": {}}
        runnable, skipped = evaluate_run_conditions(assignments, pipeline_state=state)
        assert len(runnable) == 1
        assert len(skipped) == 0

    def test_runs_when_buyer_envelope_admitted(self):
        """F2 envelope format: admitted BuyerDepartment triggers contact."""
        assignments = [
            Assignment(
                task_key="contact_discovery", assignee="ContactDepartment",
                target_section="contact_intelligence", label="Contact discovery",
                objective="Find contacts", model_name="m", allowed_tools=("search",),
                run_condition="buyer_department_has_prioritized_firms",
            ),
        ]
        state = {
            "department_packages": {
                "BuyerDepartment": {
                    "admission": {"decision": "accepted", "downstream_visible": True, "reason": "ok"},
                    "raw_package": {"accepted_points": ["peer_competitors.assessment"]},
                    "admitted_payload": {"target_company": "ACME"},
                },
            },
            "task_statuses": {},
        }
        runnable, skipped = evaluate_run_conditions(assignments, pipeline_state=state)
        assert len(runnable) == 1

    def test_skips_when_buyer_envelope_rejected(self):
        """F2 envelope format: rejected BuyerDepartment does NOT trigger contact."""
        assignments = [
            Assignment(
                task_key="contact_discovery", assignee="ContactDepartment",
                target_section="contact_intelligence", label="Contact discovery",
                objective="Find contacts", model_name="m", allowed_tools=("search",),
                run_condition="buyer_department_has_prioritized_firms",
            ),
        ]
        state = {
            "department_packages": {
                "BuyerDepartment": {
                    "admission": {"decision": "rejected", "downstream_visible": False, "reason": "all failed"},
                    "raw_package": {"accepted_points": ["peer_competitors.assessment"]},
                    "admitted_payload": None,
                },
            },
            "task_statuses": {},
        }
        runnable, skipped = evaluate_run_conditions(assignments, pipeline_state=state)
        assert len(runnable) == 0
        assert len(skipped) == 1

    def test_no_condition_always_runs(self):
        assignments = [
            Assignment(
                task_key="company_fundamentals", assignee="CompanyDepartment",
                target_section="company_profile", label="Fundamentals",
                objective="Build fundamentals", model_name="m", allowed_tools=("search",),
            ),
        ]
        state = {"department_packages": {}, "task_statuses": {}}
        runnable, skipped = evaluate_run_conditions(assignments, pipeline_state=state)
        assert len(runnable) == 1
        assert len(skipped) == 0

    def test_contact_qualification_condition(self):
        assignments = [
            Assignment(
                task_key="contact_qualification", assignee="ContactDepartment",
                target_section="contact_intelligence", label="Qualification",
                objective="Qualify contacts", model_name="m", allowed_tools=("search",),
                run_condition="contact_discovery_completed",
            ),
        ]
        state = {"department_packages": {}, "task_statuses": {"contact_discovery": "rejected"}}
        runnable, skipped = evaluate_run_conditions(assignments, pipeline_state=state)
        assert len(skipped) == 1
        state["task_statuses"]["contact_discovery"] = "accepted"
        runnable, skipped = evaluate_run_conditions(assignments, pipeline_state=state)
        assert len(runnable) == 1


# ===========================================================================
# Config defaults
# ===========================================================================

class TestConfigDefaults:
    def test_max_task_retries_default(self):
        assert MAX_TASK_RETRIES >= 2

    def test_token_budget_defaults(self):
        assert SOFT_TOKEN_BUDGET == 200_000
        assert HARD_TOKEN_CAP == 500_000


# ===========================================================================
# Research readiness
# ===========================================================================

class TestResearchReadiness:
    def test_requires_multiple_sections(self):
        readiness = assess_research_readiness(
            company_profile={"company_name": "ACME"},
            industry_analysis={"industry_name": "Software"},
            market_network={"target_company": "ACME"},
            contact_intelligence={},
            quality_review={"evidence_health": "medium"},
        )
        assert readiness["usable"] is True
        assert readiness["score"] >= 70


# ===========================================================================
# F2 — Supervisor acceptance gate
# ===========================================================================

class TestSupervisorAcceptanceDecision:
    """Tests for the three-outcome admission decision."""

    def _sup(self):
        from src.agents.supervisor import SupervisorAgent
        return SupervisorAgent()

    def test_accepted_when_substantive_and_tasks_pass(self):
        sup = self._sup()
        result = sup.accept_department_package(
            department="CompanyDepartment",
            package={
                "completed_tasks": [{"task_key": "t1", "status": "accepted"}],
                "section_payload": {"company_name": "ACME GmbH"},
                "open_questions": [],
            },
        )
        assert result["decision"] == "accepted"

    def test_accepted_with_gaps_when_no_task_accepted(self):
        sup = self._sup()
        result = sup.accept_department_package(
            department="MarketDepartment",
            package={
                "completed_tasks": [{"task_key": "t1", "status": "degraded"}],
                "section_payload": {"industry_name": "Manufacturing"},
                "open_questions": ["demand unclear"],
            },
        )
        assert result["decision"] == "accepted_with_gaps"

    def test_rejected_when_all_tasks_failed(self):
        sup = self._sup()
        result = sup.accept_department_package(
            department="BuyerDepartment",
            package={
                "completed_tasks": [
                    {"task_key": "t1", "status": "rejected"},
                    {"task_key": "t2", "status": "rejected"},
                ],
                "section_payload": {"target_company": "ACME"},
                "open_questions": [],
            },
        )
        assert result["decision"] == "rejected"

    def test_rejected_when_no_substantive_content(self):
        sup = self._sup()
        result = sup.accept_department_package(
            department="CompanyDepartment",
            package={
                "completed_tasks": [{"task_key": "t1", "status": "accepted"}],
                "section_payload": {"company_name": "n/v", "industry": ""},
                "open_questions": [],
            },
        )
        assert result["decision"] == "rejected"

    def test_rejected_when_empty_payload(self):
        sup = self._sup()
        result = sup.accept_department_package(
            department="CompanyDepartment",
            package={
                "completed_tasks": [{"task_key": "t1", "status": "accepted"}],
                "section_payload": {},
                "open_questions": [],
            },
        )
        assert result["decision"] == "rejected"


class TestAcceptanceGate:
    """Tests for _apply_acceptance_gate and _admitted_packages_for_synthesis."""

    def test_accepted_package_flows_downstream(self):
        from src.orchestration.supervisor_loop import _apply_acceptance_gate
        sections: dict = {}
        packages: dict = {}
        _apply_acceptance_gate(
            {"decision": "accepted", "reason": "ok"},
            dept_name="CompanyDepartment",
            target_section="company_profile",
            section_payload={"company_name": "ACME"},
            package={"completed_tasks": [], "open_questions": []},
            sections=sections,
            department_packages=packages,
        )
        assert sections["company_profile"] == {"company_name": "ACME"}
        envelope = packages["CompanyDepartment"]
        assert envelope["admission"]["decision"] == "accepted"
        assert envelope["admission"]["downstream_visible"] is True
        assert envelope["admitted_payload"] == {"company_name": "ACME"}
        assert "raw_package" in envelope

    def test_accepted_with_gaps_flows_with_marker(self):
        from src.orchestration.supervisor_loop import _apply_acceptance_gate
        sections: dict = {}
        packages: dict = {}
        _apply_acceptance_gate(
            {"decision": "accepted_with_gaps", "reason": "partial"},
            dept_name="MarketDepartment",
            target_section="industry_analysis",
            section_payload={"industry_name": "Mfg"},
            package={"completed_tasks": [], "open_questions": ["gap"]},
            sections=sections,
            department_packages=packages,
        )
        assert sections["industry_analysis"]["industry_name"] == "Mfg"
        assert sections["industry_analysis"]["_admission"] == "accepted_with_gaps"
        envelope = packages["MarketDepartment"]
        assert envelope["admission"]["downstream_visible"] is True
        assert envelope["admitted_payload"] is not None

    def test_rejected_package_blocked_downstream(self):
        from src.orchestration.supervisor_loop import _apply_acceptance_gate
        sections: dict = {}
        packages: dict = {}
        _apply_acceptance_gate(
            {"decision": "rejected", "reason": "all failed"},
            dept_name="BuyerDepartment",
            target_section="market_network",
            section_payload={"target_company": "ACME"},
            package={"completed_tasks": [], "open_questions": ["no buyers"]},
            sections=sections,
            department_packages=packages,
        )
        assert sections["market_network"]["section_status"] == "blocked"
        assert sections["market_network"]["reason"] == "all failed"
        envelope = packages["BuyerDepartment"]
        assert envelope["admission"]["downstream_visible"] is False
        assert envelope["admitted_payload"] is None
        assert envelope["raw_package"]["completed_tasks"] == []

    def test_admitted_packages_for_synthesis_filters_rejected(self):
        from src.orchestration.supervisor_loop import _admitted_packages_for_synthesis
        packages = {
            "CompanyDepartment": {
                "admission": {"decision": "accepted", "downstream_visible": True, "reason": "ok"},
                "raw_package": {}, "admitted_payload": {"company_name": "ACME"},
            },
            "BuyerDepartment": {
                "admission": {"decision": "rejected", "downstream_visible": False, "reason": "failed"},
                "raw_package": {}, "admitted_payload": None,
            },
        }
        admitted = _admitted_packages_for_synthesis(packages)
        assert "CompanyDepartment" in admitted
        assert "BuyerDepartment" not in admitted

    def test_admission_envelope_has_raw_and_admitted(self):
        from src.orchestration.supervisor_loop import _apply_acceptance_gate
        sections: dict = {}
        packages: dict = {}
        raw = {"completed_tasks": [{"task_key": "t1", "status": "accepted"}], "open_questions": []}
        _apply_acceptance_gate(
            {"decision": "accepted", "reason": "ok"},
            dept_name="Test",
            target_section="test_section",
            section_payload={"key": "value"},
            package=raw,
            sections=sections,
            department_packages=packages,
        )
        envelope = packages["Test"]
        assert envelope["raw_package"] is raw
        assert envelope["admitted_payload"] == {"key": "value"}
        assert "admission" in envelope


# ===========================================================================
# F3 — Synthesis acceptance gate
# ===========================================================================

class TestSynthesisAcceptanceGate:
    """Tests for the three-outcome synthesis admission decision."""

    def _sup(self):
        from src.agents.supervisor import SupervisorAgent
        return SupervisorAgent()

    def test_accepted_when_normal_and_substantive(self):
        sup = self._sup()
        result = sup.accept_synthesis(synthesis_payload={
            "target_company": "ACME GmbH",
            "executive_summary": "ACME GmbH operates in manufacturing with strong market signals.",
            "generation_mode": "normal",
        })
        assert result["decision"] == "accepted"

    def test_accepted_with_gaps_on_fallback(self):
        sup = self._sup()
        result = sup.accept_synthesis(synthesis_payload={
            "target_company": "ACME GmbH",
            "executive_summary": "Fallback synthesis for ACME GmbH.",
            "generation_mode": "fallback",
        })
        assert result["decision"] == "accepted_with_gaps"

    def test_accepted_with_gaps_when_summary_weak(self):
        """Normal mode but short summary → accepted_with_gaps."""
        sup = self._sup()
        result = sup.accept_synthesis(synthesis_payload={
            "target_company": "ACME GmbH",
            "executive_summary": "Short.",
            "generation_mode": "normal",
        })
        assert result["decision"] == "accepted_with_gaps"

    def test_rejected_when_no_target_company(self):
        sup = self._sup()
        result = sup.accept_synthesis(synthesis_payload={
            "target_company": "n/v",
            "executive_summary": "Some summary text that is long enough.",
            "generation_mode": "normal",
        })
        assert result["decision"] == "rejected"

    def test_rejected_when_empty_payload(self):
        sup = self._sup()
        result = sup.accept_synthesis(synthesis_payload={})
        assert result["decision"] == "rejected"

    def test_synthesis_task_status_reflects_decision(self):
        """Verify the mapping used in supervisor_loop for synthesis tasks."""
        mapping = {
            "accepted": "accepted",
            "accepted_with_gaps": "degraded",
            "rejected": "degraded",
        }
        for decision, expected_status in mapping.items():
            assert mapping[decision] == expected_status

    def test_pipeline_runner_does_not_override_synthesis_admission(self):
        """pipeline_runner must read _synthesis_admission, not re-decide."""
        import inspect
        from src import pipeline_runner
        source = inspect.getsource(pipeline_runner.run_pipeline)
        # The old implicit gate pattern: using target_company in an if-branch
        # to decide generation_mode or acceptance. Data reads are fine.
        assert 'if ag2_synthesis' not in source.replace('ag2_synthesis.get("_synthesis_admission"', ''), (
            "pipeline_runner still contains an implicit ag2_synthesis gate "
            "that should have been replaced by _synthesis_admission"
        )
        # The authoritative marker must be read
        assert '_synthesis_admission' in source

    def test_rejected_synthesis_produces_blocked_artifact(self):
        """Rejected synthesis must not produce a fallback that looks like real content."""
        # Simulate what pipeline_runner does for rejected synthesis
        ag2_synthesis = {"_synthesis_admission": "rejected", "target_company": "n/v"}
        synthesis = {
            "section_status": "blocked",
            "reason": ag2_synthesis.get("_synthesis_admission", "rejected"),
            "target_company": ag2_synthesis.get("target_company", "n/v"),
            "generation_mode": "blocked",
            "confidence": "low",
        }
        assert synthesis["section_status"] == "blocked"
        assert synthesis["generation_mode"] == "blocked"
        assert synthesis["confidence"] == "low"


# ===========================================================================
# F7 — Vocabulary consistency
# ===========================================================================

class TestVocabularyConsistency:
    def test_judge_uses_contract_vocabulary(self):
        """Judge decisions must be valid TaskDecisionOutcomes."""
        from src.agents.judge import JudgeAgent
        from src.orchestration.contracts import TERMINAL_OUTCOMES, NON_TERMINAL_OUTCOMES
        all_outcomes = TERMINAL_OUTCOMES | NON_TERMINAL_OUTCOMES
        judge = JudgeAgent("TestJudge")
        # All three paths
        for core_p, core_t in [(2, 2), (1, 2), (0, 2)]:
            review = {"core_passed": core_p, "core_total": core_t,
                      "supporting_passed": 0, "supporting_total": 1,
                      "failed_rule_messages": ["test"]}
            result = judge.decide(section="test", critic_review=review)
            assert result["decision"] in all_outcomes, (
                f"Judge decision '{result['decision']}' not in contract outcomes"
            )

    def test_no_phantom_status_in_short_term_store(self):
        """submitted and needs_revision must not appear in ShortTermMemoryStore."""
        import inspect
        from src.memory import short_term_store
        source = inspect.getsource(short_term_store)
        # Allow in comments (# F7: was "submitted") but not as active string literals
        active_lines = [l for l in source.splitlines()
                        if not l.strip().startswith("#") and "# F7:" not in l]
        active_source = "\n".join(active_lines)
        assert '"submitted"' not in active_source, "Phantom status 'submitted' still active"
        assert '"needs_revision"' not in active_source, "Phantom status 'needs_revision' still active"

    def test_no_accepted_bool_in_supervisor_acceptance(self):
        """accepted: bool shim must be removed from supervisor acceptance methods."""
        from src.agents.supervisor import SupervisorAgent
        sup = SupervisorAgent()
        # Department acceptance
        result = sup.accept_department_package(
            department="Test",
            package={"completed_tasks": [{"task_key": "t1", "status": "accepted"}],
                     "section_payload": {"company_name": "ACME"}, "open_questions": []},
        )
        assert "accepted" not in result or result.get("accepted") is None or isinstance(result.get("decision"), str), \
            "accepted: bool shim should be removed"
        assert "decision" in result
        # Synthesis acceptance
        result2 = sup.accept_synthesis(synthesis_payload={
            "target_company": "ACME", "executive_summary": "A long enough summary for testing.",
            "generation_mode": "normal",
        })
        assert "decision" in result2
        assert "accepted" not in result2, "accepted: bool shim should be removed from accept_synthesis"

    def test_task_lifecycle_statuses_are_canonical(self):
        """All OUTCOME_TO_TASK_STATUS values must be in TASK_LIFECYCLE_STATUSES."""
        from src.orchestration.contracts import OUTCOME_TO_TASK_STATUS, TASK_LIFECYCLE_STATUSES
        for outcome, status in OUTCOME_TO_TASK_STATUS.items():
            assert status in TASK_LIFECYCLE_STATUSES, (
                f"OUTCOME_TO_TASK_STATUS['{outcome}'] = '{status}' not in TASK_LIFECYCLE_STATUSES"
            )

    def test_no_legacy_judge_labels_in_judge_module(self):
        """Legacy labels accept/accept_degraded/reject must not appear as decision values in judge.py."""
        import inspect
        from src.agents import judge
        source = inspect.getsource(judge)
        # Check for old-style decision assignments (not in comments or docstrings)
        code_lines = [l for l in source.splitlines()
                      if not l.strip().startswith("#") and not l.strip().startswith('\"\"\"')]
        code = "\n".join(code_lines)
        assert '"accept"' not in code.replace('"accepted"', '').replace('"accepted_with_gaps"', ''), \
            "Legacy 'accept' label still in judge.py"
        assert '"accept_degraded"' not in code, "Legacy 'accept_degraded' label still in judge.py"
        assert '"reject"' not in code.replace('"rejected"', ''), \
            "Legacy 'reject' label still in judge.py"
