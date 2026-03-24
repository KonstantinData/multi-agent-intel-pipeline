"""DEPRECATED — migrated to tests/architecture/ and tests/integration/.

This file is kept for reference only. Run `pytest tests/` instead.
See TESTING.md for the new test structure.
"""
from __future__ import annotations

import pytest
pytest.skip("Migrated to tests/. Run pytest tests/ instead.", allow_module_level=True)

# Original content below (unreachable due to skip above)
"""
Tests for routing, follow-up, integration, and new optimization features.

Covers P4 test gaps from optimize_todo.md:
- SupervisorAgent.route_question() weighted scoring
- follow_up.py::answer_follow_up() per department
- SynthesisDepartmentAgent fallback
- run_condition skipping for Contact tasks
- Token budget settings
- Max-retry cap configurability
- File locking in long_term_store
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


# ---------------------------------------------------------------------------
# 1. Routing tests — SupervisorAgent.route_question()
# ---------------------------------------------------------------------------

def test_route_contact_keywords():
    from src.agents.supervisor import SupervisorAgent
    sup = SupervisorAgent()
    assert sup.route_question(question="Who is the procurement contact?")["route"] == "ContactDepartment"
    assert sup.route_question(question="Ansprechpartner bei Käuferfirmen")["route"] == "ContactDepartment"
    assert sup.route_question(question="LinkedIn decision-maker outreach")["route"] == "ContactDepartment"


def test_route_buyer_keywords():
    from src.agents.supervisor import SupervisorAgent
    sup = SupervisorAgent()
    assert sup.route_question(question="Who are the downstream buyers?")["route"] == "BuyerDepartment"
    assert sup.route_question(question="Käufer und Wiederverkauf")["route"] == "BuyerDepartment"
    assert sup.route_question(question="redeployment aftermarket paths")["route"] == "BuyerDepartment"


def test_route_market_keywords():
    from src.agents.supervisor import SupervisorAgent
    sup = SupervisorAgent()
    assert sup.route_question(question="What is the demand outlook?")["route"] == "MarketDepartment"
    assert sup.route_question(question="Markt Nachfrage und Angebot")["route"] == "MarketDepartment"
    assert sup.route_question(question="circular economy repurposing")["route"] == "MarketDepartment"


def test_route_synthesis_keywords():
    from src.agents.supervisor import SupervisorAgent
    sup = SupervisorAgent()
    assert sup.route_question(question="What is the Liquisto opportunity?")["route"] == "SynthesisDepartment"
    assert sup.route_question(question="Zusammenfassung und Gesamtbild")["route"] == "SynthesisDepartment"
    assert sup.route_question(question="next step for the meeting briefing")["route"] == "SynthesisDepartment"


def test_route_company_keywords():
    from src.agents.supervisor import SupervisorAgent
    sup = SupervisorAgent()
    assert sup.route_question(question="What is the company revenue?")["route"] == "CompanyDepartment"
    assert sup.route_question(question="Firma Umsatz und Bestand")["route"] == "CompanyDepartment"


def test_route_fallback_to_company():
    from src.agents.supervisor import SupervisorAgent
    sup = SupervisorAgent()
    result = sup.route_question(question="xyzzy foobar baz")
    assert result["route"] == "CompanyDepartment"


def test_route_overlapping_keywords_resolved_by_weight():
    """'buyer contact' has both buyer and contact keywords — contact should win due to higher specificity."""
    from src.agents.supervisor import SupervisorAgent
    sup = SupervisorAgent()
    result = sup.route_question(question="buyer contact person for procurement")
    # "contact" (3) + "person" (1) + "procurement" (0 for Contact but "buyer" (3) for Buyer)
    # Contact: contact=3, person=1 = 4; Buyer: buyer=3 = 3 → Contact wins
    assert result["route"] == "ContactDepartment"


def test_route_includes_score():
    from src.agents.supervisor import SupervisorAgent
    sup = SupervisorAgent()
    result = sup.route_question(question="market demand supply")
    assert "score" in result["reason"]


# ---------------------------------------------------------------------------
# 2. Follow-up tests — answer_follow_up()
# ---------------------------------------------------------------------------

def _make_pipeline_data():
    from src.models.schemas import empty_pipeline_data
    data = empty_pipeline_data()
    data["company_profile"]["company_name"] = "TestCo"
    data["company_profile"]["description"] = "A test company"
    data["company_profile"]["economic_situation"]["assessment"] = "Stable"
    data["industry_analysis"]["assessment"] = "Growing market"
    data["industry_analysis"]["demand_outlook"] = "Positive"
    data["market_network"]["peer_competitors"]["assessment"] = "Competitive"
    data["market_network"]["downstream_buyers"]["assessment"] = "Active"
    data["contact_intelligence"]["narrative_summary"] = "3 contacts found"
    data["contact_intelligence"]["coverage_quality"] = "medium"
    data["synthesis"]["executive_summary"] = "Strong opportunity"
    data["synthesis"]["opportunity_assessment_summary"] = "Excess inventory path"
    return data


def _make_run_context():
    return {
        "short_term_memory": {
            "department_packages": {
                "CompanyDepartment": {"open_questions": ["Q1"]},
                "MarketDepartment": {"open_questions": ["Q2"]},
                "BuyerDepartment": {"open_questions": ["Q3"]},
                "ContactDepartment": {"open_questions": ["Q4"]},
                "SynthesisDepartment": {"opportunity_assessment": "test"},
            }
        }
    }


def test_follow_up_company_route(tmp_path):
    from src.orchestration.follow_up import answer_follow_up, RUNS_DIR
    import src.orchestration.follow_up as fu_mod
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()
    original_runs = fu_mod.RUNS_DIR
    fu_mod.RUNS_DIR = tmp_path
    try:
        result = answer_follow_up(
            run_id="test_run",
            route="CompanyDepartment",
            question="What does the company do?",
            pipeline_data=_make_pipeline_data(),
            run_context=_make_run_context(),
        )
        assert result["routed_to"] == "CompanyDepartment"
        assert "TestCo" in result["answer"]
    finally:
        fu_mod.RUNS_DIR = original_runs


def test_follow_up_market_route(tmp_path):
    from src.orchestration.follow_up import answer_follow_up
    import src.orchestration.follow_up as fu_mod
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()
    original_runs = fu_mod.RUNS_DIR
    fu_mod.RUNS_DIR = tmp_path
    try:
        result = answer_follow_up(
            run_id="test_run",
            route="MarketDepartment",
            question="Market outlook?",
            pipeline_data=_make_pipeline_data(),
            run_context=_make_run_context(),
        )
        assert result["routed_to"] == "MarketDepartment"
        assert "Positive" in result["answer"]
    finally:
        fu_mod.RUNS_DIR = original_runs


def test_follow_up_buyer_route(tmp_path):
    from src.orchestration.follow_up import answer_follow_up
    import src.orchestration.follow_up as fu_mod
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()
    original_runs = fu_mod.RUNS_DIR
    fu_mod.RUNS_DIR = tmp_path
    try:
        result = answer_follow_up(
            run_id="test_run",
            route="BuyerDepartment",
            question="Who are the buyers?",
            pipeline_data=_make_pipeline_data(),
            run_context=_make_run_context(),
        )
        assert result["routed_to"] == "BuyerDepartment"
        assert "Competitive" in result["answer"] or "Active" in result["answer"]
    finally:
        fu_mod.RUNS_DIR = original_runs


def test_follow_up_contact_route(tmp_path):
    from src.orchestration.follow_up import answer_follow_up
    import src.orchestration.follow_up as fu_mod
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()
    original_runs = fu_mod.RUNS_DIR
    fu_mod.RUNS_DIR = tmp_path
    try:
        result = answer_follow_up(
            run_id="test_run",
            route="ContactDepartment",
            question="Who are the contacts?",
            pipeline_data=_make_pipeline_data(),
            run_context=_make_run_context(),
        )
        assert result["routed_to"] == "ContactDepartment"
        assert "3 contacts" in result["answer"]
    finally:
        fu_mod.RUNS_DIR = original_runs


def test_follow_up_synthesis_route(tmp_path):
    from src.orchestration.follow_up import answer_follow_up
    import src.orchestration.follow_up as fu_mod
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()
    original_runs = fu_mod.RUNS_DIR
    fu_mod.RUNS_DIR = tmp_path
    try:
        result = answer_follow_up(
            run_id="test_run",
            route="SynthesisDepartment",
            question="What is the opportunity?",
            pipeline_data=_make_pipeline_data(),
            run_context=_make_run_context(),
        )
        assert result["routed_to"] == "SynthesisDepartment"
        assert "Strong opportunity" in result["answer"] or "Excess" in result["answer"]
    finally:
        fu_mod.RUNS_DIR = original_runs


def test_follow_up_unknown_route_defaults_to_company(tmp_path):
    from src.orchestration.follow_up import answer_follow_up
    import src.orchestration.follow_up as fu_mod
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()
    original_runs = fu_mod.RUNS_DIR
    fu_mod.RUNS_DIR = tmp_path
    try:
        result = answer_follow_up(
            run_id="test_run",
            route="UnknownDepartment",
            question="Random question",
            pipeline_data=_make_pipeline_data(),
            run_context=_make_run_context(),
        )
        assert result["routed_to"] == "CompanyDepartment"
    finally:
        fu_mod.RUNS_DIR = original_runs


# ---------------------------------------------------------------------------
# 3. Config / settings tests
# ---------------------------------------------------------------------------

def test_max_task_retries_default():
    from src.config.settings import MAX_TASK_RETRIES
    assert MAX_TASK_RETRIES == 2


def test_token_budget_defaults():
    from src.config.settings import SOFT_TOKEN_BUDGET, HARD_TOKEN_CAP
    assert SOFT_TOKEN_BUDGET == 200_000
    assert HARD_TOKEN_CAP == 500_000


# ---------------------------------------------------------------------------
# 4. File locking in long_term_store
# ---------------------------------------------------------------------------

def test_long_term_store_has_lock(tmp_path):
    from src.memory.long_term_store import FileLongTermMemoryStore
    store = FileLongTermMemoryStore(tmp_path / "memory.json")
    assert hasattr(store, "_lock")
    store.upsert_strategy({"name": "test_pattern", "score": 1.0})
    items = store.load()
    assert len(items) == 1
    assert items[0]["name"] == "test_pattern"


def test_long_term_store_concurrent_writes(tmp_path):
    """Two stores writing to the same file should not corrupt it."""
    from src.memory.long_term_store import FileLongTermMemoryStore
    path = tmp_path / "shared.json"
    store_a = FileLongTermMemoryStore(path)
    store_b = FileLongTermMemoryStore(path)
    store_a.upsert_strategy({"name": "pattern_a", "score": 1.0})
    store_b.upsert_strategy({"name": "pattern_b", "score": 2.0})
    items = store_a.load()
    names = {item["name"] for item in items}
    assert "pattern_a" in names
    assert "pattern_b" in names


# ---------------------------------------------------------------------------
# 5. Speaker selector tests
# ---------------------------------------------------------------------------

def test_department_selector_initial_step():
    from src.orchestration.speaker_selector import build_department_selector
    from unittest.mock import MagicMock
    agents = {}
    for name in ["Lead", "Researcher", "Critic", "Judge", "Coding"]:
        agent = MagicMock()
        agent.name = name
        agents[name] = agent
    run_state = {}
    selector = build_department_selector(
        run_state=run_state,
        agent_map=agents,
        lead_name="Lead",
        researcher_name="Researcher",
        critic_name="Critic",
        judge_name="Judge",
        coding_name="Coding",
    )
    gc = MagicMock()
    gc.messages = []
    result = selector(agents["Lead"], gc)
    assert result == agents["Researcher"]
    assert run_state["workflow_step"] == "research"


def test_synthesis_selector_initial_step():
    from src.orchestration.speaker_selector import build_synthesis_selector
    from unittest.mock import MagicMock
    agents = {}
    for name in ["Lead", "Analyst", "Critic", "Judge"]:
        agent = MagicMock()
        agent.name = name
        agents[name] = agent
    run_state = {}
    selector = build_synthesis_selector(
        run_state=run_state,
        agent_map=agents,
        lead_name="Lead",
        analyst_name="Analyst",
        critic_name="Critic",
        judge_name="Judge",
    )
    gc = MagicMock()
    gc.messages = []
    result = selector(agents["Lead"], gc)
    assert result == agents["Analyst"]
    assert run_state["synthesis_step"] == "read"


# ---------------------------------------------------------------------------
# 6. Shared search cache test
# ---------------------------------------------------------------------------

def test_shared_search_cache_across_departments():
    from src.orchestration.department_runtime import DepartmentRuntime
    cache = {}
    rt1 = DepartmentRuntime("CompanyDepartment", search_cache=cache)
    rt2 = DepartmentRuntime("MarketDepartment", search_cache=cache)
    # Both workers should share the same cache object
    assert rt1.lead.worker._search_cache is rt2.lead.worker._search_cache


# ---------------------------------------------------------------------------
# 7. Assignment carries contract fields from use_cases.py
# ---------------------------------------------------------------------------

def test_assignment_carries_contract_fields():
    from src.domain.intake import SupervisorBrief
    from src.orchestration.task_router import build_initial_assignments
    brief = SupervisorBrief(
        submitted_company_name="TestCo", submitted_web_domain="testco.de",
        verified_company_name="TestCo", verified_legal_name="TestCo",
        name_confidence="high", website_reachable=True,
        homepage_url="https://testco.de", page_title="TestCo",
        meta_description="", raw_homepage_excerpt="TestCo makes parts",
        normalized_domain="testco.de", industry_hint="Automotive",
    )
    assignments = build_initial_assignments(brief)
    # Every assignment should carry contract fields
    for a in assignments:
        assert a.output_schema_key, f"{a.task_key} missing output_schema_key"
        assert a.industry_hint == "Automotive"
    # Contact tasks should have run_condition set
    contact_tasks = [a for a in assignments if a.task_key in ("contact_discovery", "contact_qualification")]
    for ct in contact_tasks:
        assert ct.run_condition is not None
        assert ct.depends_on  # should have upstream deps


def test_assignment_defaults_for_manual_construction():
    """Manually constructed Assignments (tests, follow-up) should not break."""
    from src.orchestration.task_router import Assignment
    a = Assignment(
        task_key="test", assignee="X", target_section="s",
        label="L", objective="O", model_name="m", allowed_tools=("search",),
    )
    assert a.depends_on == ()
    assert a.run_condition is None
    assert a.input_artifacts == ()
    assert a.output_schema_key == ""
    assert a.industry_hint == "n/v"


# ---------------------------------------------------------------------------
# 8. Generic run_condition evaluation
# ---------------------------------------------------------------------------

def test_evaluate_run_conditions_skips_when_no_buyer():
    from src.orchestration.task_router import Assignment, evaluate_run_conditions
    assignments = [
        Assignment(
            task_key="contact_discovery", assignee="ContactDepartment",
            target_section="contact_intelligence", label="Contact discovery",
            objective="Find contacts", model_name="m", allowed_tools=("search",),
            run_condition="buyer_department_has_prioritized_firms",
        ),
    ]
    state = {"department_packages": {"BuyerDepartment": {"accepted_points": []}}, "task_statuses": {}}
    runnable, skipped = evaluate_run_conditions(assignments, pipeline_state=state)
    assert len(runnable) == 0
    assert len(skipped) == 1
    assert skipped[0]["status"] == "skipped"


def test_evaluate_run_conditions_runs_when_buyer_has_points():
    from src.orchestration.task_router import Assignment, evaluate_run_conditions
    assignments = [
        Assignment(
            task_key="contact_discovery", assignee="ContactDepartment",
            target_section="contact_intelligence", label="Contact discovery",
            objective="Find contacts", model_name="m", allowed_tools=("search",),
            run_condition="buyer_department_has_prioritized_firms",
        ),
    ]
    state = {"department_packages": {"BuyerDepartment": {"accepted_points": ["peer_competitors.assessment"]}}, "task_statuses": {}}
    runnable, skipped = evaluate_run_conditions(assignments, pipeline_state=state)
    assert len(runnable) == 1
    assert len(skipped) == 0


def test_evaluate_run_conditions_no_condition_always_runs():
    from src.orchestration.task_router import Assignment, evaluate_run_conditions
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


def test_evaluate_contact_qualification_condition():
    from src.orchestration.task_router import Assignment, evaluate_run_conditions
    assignments = [
        Assignment(
            task_key="contact_qualification", assignee="ContactDepartment",
            target_section="contact_intelligence", label="Qualification",
            objective="Qualify contacts", model_name="m", allowed_tools=("search",),
            run_condition="contact_discovery_completed",
        ),
    ]
    # Not completed yet
    state = {"department_packages": {}, "task_statuses": {"contact_discovery": "rejected"}}
    runnable, skipped = evaluate_run_conditions(assignments, pipeline_state=state)
    assert len(skipped) == 1
    # Now completed
    state["task_statuses"]["contact_discovery"] = "accepted"
    runnable, skipped = evaluate_run_conditions(assignments, pipeline_state=state)
    assert len(runnable) == 1
