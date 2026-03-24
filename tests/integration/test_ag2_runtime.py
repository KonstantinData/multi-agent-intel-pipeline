"""Integration tests for AG2 GroupChat flows with monkeypatched LLM.

Covers:
- Single department AG2 GroupChat run (real tool closures, mocked LLM)
- Contact Department end-to-end
- SynthesisDepartmentAgent.run() with mocked department packages
- Fallback package assembly when max_round is hit
- No supervisor in department loop (CHG-03)
- Shared search cache across departments
- Assignment contract fields from use_cases.py

Requires AG2/autogen — auto-skipped if not installed.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
import inspect

import pytest

_DUMMY_KEY = "sk-test-integration-dummy-key-not-real"


@pytest.fixture(autouse=True)
def _set_dummy_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", _DUMMY_KEY)


from src.domain.intake import SupervisorBrief
from src.orchestration.task_router import Assignment


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_brief() -> SupervisorBrief:
    return SupervisorBrief(
        submitted_company_name="TestCo GmbH",
        submitted_web_domain="testco.de",
        verified_company_name="TestCo GmbH",
        verified_legal_name="TestCo GmbH",
        name_confidence="high",
        website_reachable=True,
        homepage_url="https://testco.de",
        page_title="TestCo - Industrial Parts",
        meta_description="TestCo manufactures industrial spare parts",
        raw_homepage_excerpt="TestCo GmbH manufactures precision spare parts and components for the automotive industry.",
        normalized_domain="testco.de",
        industry_hint="Automotive",
        observations=["Website reachable."],
        sources=[{"title": "TestCo", "url": "https://testco.de", "source_type": "owned", "summary": "Homepage"}],
    )


def _make_supervisor() -> MagicMock:
    sup = MagicMock()
    sup.decide_revision.return_value = {
        "retry": False, "same_department": True,
        "authorize_coding_specialist": False, "reason": "Keep conservative.",
    }
    sup.route_question.return_value = {"route": "CompanyDepartment", "reason": "test", "source": "test"}
    return sup


def _company_assignments(brief):
    return [
        Assignment(
            task_key="company_fundamentals", assignee="CompanyDepartment",
            target_section="company_profile", label="Company fundamentals",
            objective=f"Build verified company fundamentals for {brief.company_name}.",
            model_name="gpt-4.1-mini",
            allowed_tools=("search", "page_fetch", "llm_structured"),
        ),
    ]


def _contact_assignments(brief):
    return [
        Assignment(
            task_key="contact_discovery", assignee="ContactDepartment",
            target_section="contact_intelligence", label="Contact discovery",
            objective=f"Identify decision-makers at buyer firms for {brief.company_name}.",
            model_name="gpt-4.1-mini",
            allowed_tools=("search", "page_fetch", "llm_structured"),
        ),
    ]


def _simulate_department_chat(lead_agent, brief, assignments, supervisor):
    def fake_initiate_chat(self_agent, manager, message="", **kwargs):
        tools: dict[str, Any] = {}
        for agent in manager.groupchat.agents:
            for tool_name, tool_fn in getattr(agent, "_function_map", {}).items():
                tools[tool_name] = tool_fn
        for assignment in assignments:
            tk = assignment.task_key
            if "run_research" in tools:
                tools["run_research"](task_key=tk)
            if "review_research" in tools:
                tools["review_research"](task_key=tk)
        if "finalize_package" in tools:
            tools["finalize_package"](summary=f"Integration test summary for {brief.company_name}.")

    with patch("autogen.ConversableAgent.initiate_chat", fake_initiate_chat):
        return lead_agent.run(
            brief=brief, assignments=assignments,
            current_section=None,
        )


# ---------------------------------------------------------------------------
# Department GroupChat tests
# ---------------------------------------------------------------------------

class TestDepartmentGroupChatRun:
    def test_company_department_produces_valid_package(self):
        from src.agents.lead import DepartmentLeadAgent
        brief = _make_brief()
        lead = DepartmentLeadAgent("CompanyDepartment")
        payload, messages, package = _simulate_department_chat(
            lead, brief, _company_assignments(brief), _make_supervisor()
        )
        assert package is not None
        assert package["department"] == "CompanyDepartment"
        assert len(package["completed_tasks"]) == 1
        assert package["completed_tasks"][0]["task_key"] == "company_fundamentals"
        assert isinstance(payload, dict)
        assert payload.get("company_name") == brief.company_name
        assert package["confidence"] in ("high", "medium", "low")
        assert "report_segment" in package
        assert package["report_segment"]["department"] == "CompanyDepartment"

    def test_company_department_task_status_is_valid(self):
        from src.agents.lead import DepartmentLeadAgent
        brief = _make_brief()
        lead = DepartmentLeadAgent("CompanyDepartment")
        _, _, package = _simulate_department_chat(
            lead, brief, _company_assignments(brief), _make_supervisor()
        )
        status = package["completed_tasks"][0]["status"]
        assert status in ("accepted", "degraded", "rejected")

    def test_company_department_sources_populated(self):
        from src.agents.lead import DepartmentLeadAgent
        brief = _make_brief()
        lead = DepartmentLeadAgent("CompanyDepartment")
        payload, _, _ = _simulate_department_chat(
            lead, brief, _company_assignments(brief), _make_supervisor()
        )
        assert isinstance(payload.get("sources"), list)


class TestContactDepartmentEndToEnd:
    def test_contact_department_produces_package(self):
        from src.agents.lead import DepartmentLeadAgent
        brief = _make_brief()
        lead = DepartmentLeadAgent("ContactDepartment")
        _, _, package = _simulate_department_chat(
            lead, brief, _contact_assignments(brief), _make_supervisor()
        )
        assert package["department"] == "ContactDepartment"
        assert len(package["completed_tasks"]) == 1
        assert package["completed_tasks"][0]["task_key"] == "contact_discovery"

    def test_contact_payload_has_contact_fields(self):
        from src.agents.lead import DepartmentLeadAgent
        brief = _make_brief()
        lead = DepartmentLeadAgent("ContactDepartment")
        payload, _, _ = _simulate_department_chat(
            lead, brief, _contact_assignments(brief), _make_supervisor()
        )
        assert "contacts" in payload
        assert isinstance(payload["contacts"], list)
        assert "coverage_quality" in payload
        assert "narrative_summary" in payload

    def test_contact_department_confidence_set(self):
        from src.agents.lead import DepartmentLeadAgent
        brief = _make_brief()
        lead = DepartmentLeadAgent("ContactDepartment")
        _, _, package = _simulate_department_chat(
            lead, brief, _contact_assignments(brief), _make_supervisor()
        )
        assert package["confidence"] in ("high", "medium", "low")


# ---------------------------------------------------------------------------
# Synthesis Department
# ---------------------------------------------------------------------------

def _make_department_packages():
    segment_template = {
        "confidence": "medium", "key_findings": ["Finding A"],
        "open_questions": [], "sources": [],
    }
    return {
        "CompanyDepartment": {
            "department": "CompanyDepartment",
            "section_payload": {"company_name": "TestCo GmbH"},
            "report_segment": {"department": "CompanyDepartment", "narrative_summary": "TestCo is an automotive parts manufacturer.", **segment_template},
        },
        "MarketDepartment": {
            "department": "MarketDepartment",
            "section_payload": {"industry_name": "Automotive"},
            "report_segment": {"department": "MarketDepartment", "narrative_summary": "Automotive parts market shows moderate demand.", **segment_template},
        },
        "BuyerDepartment": {
            "department": "BuyerDepartment",
            "section_payload": {"target_company": "TestCo GmbH"},
            "report_segment": {"department": "BuyerDepartment", "narrative_summary": "Three peer companies identified.", **segment_template},
        },
        "ContactDepartment": {
            "department": "ContactDepartment",
            "section_payload": {"contacts": []},
            "report_segment": {"department": "ContactDepartment", "narrative_summary": "No verified contacts found.", "confidence": "low", "key_findings": [], "open_questions": ["No contacts"], "sources": []},
        },
    }


class TestSynthesisDepartmentRun:
    def test_synthesis_produces_schema_compliant_output(self):
        from src.agents.synthesis_department import SynthesisDepartmentAgent
        agent = SynthesisDepartmentAgent()
        brief = _make_brief()
        packages = _make_department_packages()

        def fake_initiate_chat(self_agent, manager, message="", **kwargs):
            tools: dict[str, Any] = {}
            for ag in manager.groupchat.agents:
                for tool_name, tool_fn in getattr(ag, "_function_map", {}).items():
                    tools[tool_name] = tool_fn
            if "read_report_segment" in tools:
                for dept in ["CompanyDepartment", "MarketDepartment", "BuyerDepartment", "ContactDepartment"]:
                    tools["read_report_segment"](department=dept)
            if "finalize_synthesis" in tools:
                tools["finalize_synthesis"](
                    opportunity_assessment="Excess inventory monetization is the primary path.",
                    negotiation_relevance="Moderate urgency due to automotive downturn.",
                    executive_summary="TestCo presents a clear Liquisto opportunity in spare parts monetization.",
                )

        with patch("autogen.ConversableAgent.initiate_chat", fake_initiate_chat):
            synthesis, messages = agent.run(
                brief=brief, department_packages=packages,
                supervisor=_make_supervisor(), departments={},
                synthesis_context={
                    "target_company": "TestCo GmbH",
                    "liquisto_service_relevance": [{"service_area": "excess_inventory", "relevance": "medium", "reasoning": "test"}],
                    "recommended_engagement_paths": ["direct buyer outreach"],
                    "case_assessments": [], "buyer_market_summary": "Active buyer market",
                    "key_risks": ["Low contact coverage"],
                    "next_steps": ["Validate buyer appetite"], "sources": [],
                },
            )
        assert synthesis["target_company"] == "TestCo GmbH"
        assert synthesis["generation_mode"] == "normal"
        assert synthesis["confidence"] in ("high", "medium", "low")
        assert "executive_summary" in synthesis
        assert "opportunity_assessment" in synthesis
        assert "negotiation_relevance" in synthesis

    def test_synthesis_fallback_on_max_round(self):
        from src.agents.synthesis_department import SynthesisDepartmentAgent
        agent = SynthesisDepartmentAgent()
        brief = _make_brief()

        def fake_initiate_chat(self_agent, manager, message="", **kwargs):
            pass

        with patch("autogen.ConversableAgent.initiate_chat", fake_initiate_chat):
            synthesis, _ = agent.run(
                brief=brief, department_packages=_make_department_packages(),
                supervisor=_make_supervisor(), departments={},
                synthesis_context={"target_company": "TestCo GmbH", "confidence": "low"},
            )
        assert synthesis["generation_mode"] == "fallback"
        assert synthesis["target_company"] == "TestCo GmbH"
        assert synthesis["confidence"] == "low"


# ---------------------------------------------------------------------------
# Fallback package on max_round
# ---------------------------------------------------------------------------

class TestFallbackPackageOnMaxRound:
    def test_company_fallback_package_on_empty_chat(self):
        from src.agents.lead import DepartmentLeadAgent
        brief = _make_brief()
        lead = DepartmentLeadAgent("CompanyDepartment")

        def fake_initiate_chat(self_agent, manager, message="", **kwargs):
            pass

        with patch("autogen.ConversableAgent.initiate_chat", fake_initiate_chat):
            payload, messages, package = lead.run(
                brief=brief, assignments=_company_assignments(brief),
                current_section=None,
            )
        assert package is not None
        assert package["department"] == "CompanyDepartment"
        for task in package["completed_tasks"]:
            assert task["status"] == "rejected"
        assert package["confidence"] == "low"

    def test_fallback_with_partial_research(self):
        from src.agents.lead import DepartmentLeadAgent
        brief = _make_brief()
        lead = DepartmentLeadAgent("CompanyDepartment")
        assignments = _company_assignments(brief)

        def fake_initiate_chat(self_agent, manager, message="", **kwargs):
            for agent in manager.groupchat.agents:
                for tool_name, tool_fn in getattr(agent, "_function_map", {}).items():
                    if tool_name == "run_research":
                        tool_fn(task_key="company_fundamentals")
                        return

        with patch("autogen.ConversableAgent.initiate_chat", fake_initiate_chat):
            payload, _, package = lead.run(
                brief=brief, assignments=assignments,
                current_section=None,
            )
        assert package is not None
        assert package["department"] == "CompanyDepartment"
        task = package["completed_tasks"][0]
        assert task["task_key"] == "company_fundamentals"
        assert task["status"] in ("accepted", "degraded", "rejected")
        assert payload.get("company_name") is not None


# ---------------------------------------------------------------------------
# CHG-03: No supervisor in department loop
# ---------------------------------------------------------------------------

class TestNoSupervisorInDepartmentLoop:
    def test_department_lead_run_has_no_supervisor_param(self):
        from src.agents.lead import DepartmentLeadAgent
        lead = DepartmentLeadAgent("CompanyDepartment")
        sig = inspect.signature(lead.run)
        assert "supervisor" not in sig.parameters

    def test_department_runtime_run_has_no_supervisor_param(self):
        from src.orchestration.department_runtime import DepartmentRuntime
        rt = DepartmentRuntime.__new__(DepartmentRuntime)
        sig = inspect.signature(rt.run)
        assert "supervisor" not in sig.parameters

    def test_lead_has_no_request_supervisor_revision_tool(self):
        import src.agents.lead as lead_mod
        import re
        source = inspect.getsource(lead_mod)
        code_lines = [
            ln for ln in source.split("\n")
            if not ln.strip().startswith("#") and not ln.strip().startswith('"""') and not ln.strip().startswith("'''")
        ]
        for line in code_lines:
            if re.search(r"\brequest_supervisor_revision\s*[=(]", line):
                raise AssertionError(
                    f"request_supervisor_revision used as code in lead.py: {line!r}"
                )

    def test_supervisor_decide_revision_not_called_in_lead(self):
        import src.agents.lead as lead_mod
        source = inspect.getsource(lead_mod)
        assert "decide_revision" not in source


# ---------------------------------------------------------------------------
# Shared search cache
# ---------------------------------------------------------------------------

class TestSharedSearchCache:
    def test_shared_search_cache_across_departments(self):
        from src.orchestration.department_runtime import DepartmentRuntime
        cache = {}
        rt1 = DepartmentRuntime("CompanyDepartment", search_cache=cache)
        rt2 = DepartmentRuntime("MarketDepartment", search_cache=cache)
        assert rt1.lead.worker._search_cache is rt2.lead.worker._search_cache


# ---------------------------------------------------------------------------
# Assignment contract fields
# ---------------------------------------------------------------------------

class TestAssignmentContractFields:
    def test_assignment_carries_contract_fields(self):
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
        for a in assignments:
            assert a.output_schema_key, f"{a.task_key} missing output_schema_key"
            assert a.industry_hint == "Automotive"
        contact_tasks = [a for a in assignments if a.task_key in ("contact_discovery", "contact_qualification")]
        for ct in contact_tasks:
            assert ct.run_condition is not None
            assert ct.depends_on

    def test_assignment_defaults_for_manual_construction(self):
        a = Assignment(
            task_key="test", assignee="X", target_section="s",
            label="L", objective="O", model_name="m", allowed_tools=("search",),
        )
        assert a.depends_on == ()
        assert a.run_condition is None
        assert a.input_artifacts == ()
        assert a.output_schema_key == ""
        assert a.industry_hint == "n/v"
