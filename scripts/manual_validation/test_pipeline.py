"""DEPRECATED — heavy end-to-end pipeline tests.

Not yet migrated to tests/. Requires AG2 + OpenAI + reportlab.
Run directly with: python -m pytest test_pipeline.py
See TESTING.md for the new test structure.
"""
from __future__ import annotations

import json
import sys
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.agents.worker import ResearchWorker
from src.config import get_model_pricing, get_role_model_selection, summarize_worker_report_costs
from src.domain.intake import SupervisorBrief
from src.exporters.pdf_report import generate_pdf
from src.memory.policies import should_store_strategy
from src.orchestration.synthesis import assess_research_readiness, build_synthesis_context
from src.orchestration.task_router import build_initial_assignments
from src.pipeline_runner import _extract_pipeline_data, run_pipeline


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_negative_placeholder_signals_are_not_treated_as_positive():
    synthesis = build_synthesis_context(
        company_profile={"company_name": "Example GmbH", "industry": "Mechanical Engineering"},
        industry_analysis={
            "analytics_signals": [],
            "key_trends": [],
        },
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

    require(bool(synthesis["recommended_engagement_paths"] == ["further_validation_required"]), 'synthesis["recommended_engagement_paths"] == ["further_validation_required"]')
    require(bool(all(item["relevance"] == "unclear" for item in synthesis["liquisto_service_relevance"])), 'all(item["relevance"] == "unclear" for item in synthesis["liquisto_service_relevance"])')


def test_should_store_strategy_only_for_usable_completed_runs():
    require(bool(should_store_strategy(status="completed", usable=True) is True), 'should_store_strategy(status="completed", usable=True) is True')
    require(bool(should_store_strategy(status="completed_but_not_usable", usable=False) is False), 'should_store_strategy(status="completed_but_not_usable", usable=False) is False')
    require(bool(should_store_strategy(status="failed", usable=False) is False), 'should_store_strategy(status="failed", usable=False) is False')


def test_extract_pipeline_data_reads_structured_messages():
    messages = [
        {
            "agent": "CompanyResearcher",
            "content": json.dumps(
                {
                    "section": "company_profile",
                    "payload": {"company_name": "ACME", "website": "https://acme.example"},
                }
            ),
        },
        {
            "agent": "CrossDomainStrategicAnalyst",
            "content": json.dumps({"section": "synthesis", "payload": {"target_company": "ACME"}}),
        },
    ]

    data = _extract_pipeline_data(messages)

    require(bool(data["company_profile"]["company_name"] == "ACME"), 'data["company_profile"]["company_name"] == "ACME"')
    require(bool(data["synthesis"]["target_company"] == "ACME"), 'data["synthesis"]["target_company"] == "ACME"')


def test_standard_backlog_contains_liquisto_scope_tasks():
    brief = SupervisorBrief(
        submitted_company_name="ACME GmbH",
        submitted_web_domain="acme.example",
        verified_company_name="ACME GmbH",
        verified_legal_name="ACME GmbH",
        name_confidence="high",
        website_reachable=True,
        homepage_url="https://acme.example",
        page_title="ACME",
        meta_description="Industrial automation components.",
        raw_homepage_excerpt="Industrial automation components.",
        normalized_domain="acme.example",
    )

    assignments = build_initial_assignments(brief)
    task_keys = [item.task_key for item in assignments]

    require(bool(len(assignments) >= 10), 'len(assignments) >= 10')
    require(bool("product_asset_scope" in task_keys), '"product_asset_scope" in task_keys')
    require(bool("repurposing_circularity" in task_keys), '"repurposing_circularity" in task_keys')
    require(bool("analytics_operational_improvement" in task_keys), '"analytics_operational_improvement" in task_keys')
    require(bool("liquisto_opportunity_assessment" in task_keys), '"liquisto_opportunity_assessment" in task_keys')
    require(bool("negotiation_relevance" in task_keys), '"negotiation_relevance" in task_keys')

    first = assignments[0]
    require(bool(first.model_name), 'first.model_name')
    require(bool(first.allowed_tools), 'first.allowed_tools')


def test_role_model_selection_is_explicit():
    supervisor_model, supervisor_structured = get_role_model_selection("Supervisor")
    worker_model, worker_structured = get_role_model_selection("CompanyResearcher")

    require(bool(supervisor_model == "gpt-4.1"), 'supervisor_model == "gpt-4.1"')
    require(bool(supervisor_structured == "gpt-4.1"), 'supervisor_structured == "gpt-4.1"')
    require(bool(worker_model == "gpt-4.1-mini"), 'worker_model == "gpt-4.1-mini"')
    require(bool(worker_structured == "gpt-4.1-mini"), 'worker_structured == "gpt-4.1-mini"')


def test_cost_summary_uses_model_pricing():
    usage = summarize_worker_report_costs(
        [
            {
                "worker": "CompanyResearcher",
                "model_name": "gpt-4.1-mini",
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 500,
                    "total_tokens": 1500,
                },
            }
        ]
    )

    require(bool(get_model_pricing("gpt-4.1-mini") == {"input": 0.40, "output": 1.60}), 'get_model_pricing("gpt-4.1-mini") == {"input": 0.40, "output": 1.60}')
    require(bool(usage["total"]["total_cost"] > 0), 'usage["total"]["total_cost"] > 0')
    require(bool("gpt-4.1-mini" in usage["total"]["models"]), '"gpt-4.1-mini" in usage["total"]["models"]')


def test_worker_normalizes_nested_llm_section_payload():
    worker = ResearchWorker("CompanyResearcher")
    payload_updates = {"company_profile": {"company_name": "ACME", "industry": "Automation"}}

    normalized = worker._normalize_payload_updates("company_profile", payload_updates)

    require(bool(normalized == {"company_name": "ACME", "industry": "Automation"}), 'normalized == {"company_name": "ACME", "industry": "Automation"}')


def test_worker_sanitizes_rich_llm_list_payloads():
    worker = ResearchWorker("CompanyResearcher")
    payload = worker._sanitize_for_section(
        "company_profile",
        {
            "product_asset_scope": [
                {"product_category": "Control Units", "commercial_relevance": "High"},
                "Actuators",
            ]
        },
    )

    require(
        bool(
            payload["product_asset_scope"]
            == [
                "Control Units | High",
                "Actuators",
            ]
        ),
        'payload["product_asset_scope"] == ["Control Units | High", "Actuators"]',
    )


def test_worker_falls_back_when_llm_payload_breaks_schema(monkeypatch):
    worker = ResearchWorker("CompanyResearcher")
    brief = SupervisorBrief(
        submitted_company_name="ACME GmbH",
        submitted_web_domain="acme.example",
        verified_company_name="ACME GmbH",
        verified_legal_name="ACME GmbH",
        name_confidence="high",
        website_reachable=True,
        homepage_url="https://acme.example",
        page_title="ACME",
        meta_description="Industrial automation components.",
        raw_homepage_excerpt="Industrial automation components.",
        normalized_domain="acme.example",
        sources=[{"title": "ACME", "url": "https://acme.example", "source_type": "owned", "summary": "Overview"}],
    )

    monkeypatch.setattr(worker, "_llm_enabled", lambda **kwargs: True)
    monkeypatch.setattr(
        worker,
        "_llm_synthesis",
        lambda evidence_pack, **kwargs: {
            "payload_updates": {"company_profile": {"economic_situation": "bad-shape"}},
            "facts": [],
            "market_signals": [],
            "buyer_hypotheses": [],
            "open_questions": [],
            "next_actions": [],
            "usage": {"llm_calls": 1, "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )
    monkeypatch.setattr("src.agents.worker.perform_search", lambda *args, **kwargs: [])

    report = worker.run(
        brief=brief,
        task_key="product_asset_scope",
        target_section="company_profile",
        objective="Assess product relevance",
        current_sections={},
    )

    require(bool(report["payload"]["company_name"] == "ACME GmbH"), 'report["payload"]["company_name"] == "ACME GmbH"')
    require(bool(report["open_questions"]), 'report["open_questions"]')


def test_assess_research_readiness_requires_multiple_sections():
    readiness = assess_research_readiness(
        company_profile={"company_name": "ACME"},
        industry_analysis={"industry_name": "Software"},
        market_network={"target_company": "ACME"},
        contact_intelligence={},
        quality_review={"evidence_health": "medium"},
    )

    require(bool(readiness["usable"] is True), 'readiness["usable"] is True')
    require(bool(readiness["score"] >= 70), 'readiness["score"] >= 70')


def test_run_pipeline_returns_supervisor_centric_artifacts(monkeypatch):
    def fake_company_research(domain: str, company_name: str) -> dict:
        return {
            "normalized_domain": domain,
            "homepage_url": f"https://{domain}",
            "snapshot": {
                "reachable": True,
                "title": f"{company_name} | Official Site",
                "meta_description": "Industrial components for automation and motion systems.",
                "visible_text": "Automation Motion Components Spare Parts Service",
            },
            "verified_company_name": company_name,
            "verified_legal_name": company_name,
            "name_confidence": "high",
            "summary": "Industrial components for automation and motion systems.",
        }

    def fake_search(query: str, *, max_results: int = 5, timeout: int = 8) -> list[dict[str, str]]:
        return [
            {
                "title": "Distributor Network Example",
                "url": "https://example.org/distributors",
                "source_type": "secondary",
                "summary": "",
            }
        ]

    monkeypatch.setattr("src.agents.supervisor.build_company_research", fake_company_research)
    monkeypatch.setattr("src.agents.worker.perform_search", fake_search)

    result = run_pipeline(company_name="ACME GmbH", web_domain="acme.example")

    require(bool(result["status"] in {"completed", "completed_but_not_usable"}), 'result["status"] in {"completed", "completed_but_not_usable"}')
    require(bool(result["pipeline_data"]["company_profile"]["company_name"] == "ACME GmbH"), 'result["pipeline_data"]["company_profile"]["company_name"] == "ACME GmbH"')
    require(bool("CrossDomainStrategicAnalyst" in [item["assignee"] for item in result["run_context"]["active_tasks"]]), '"CrossDomainStrategicAnalyst" in [item["assignee"] for item in result["run_context"]["active_tasks"]]')
    require(bool(result["pipeline_data"]["synthesis"]["target_company"] == "ACME GmbH"), 'result["pipeline_data"]["synthesis"]["target_company"] == "ACME GmbH"')
    require(bool(result["budget"]["elapsed_seconds"] >= 0), 'result["budget"]["elapsed_seconds"] >= 0')
    require(bool(len(result["run_context"]["active_tasks"]) >= 10), 'len(result["run_context"]["active_tasks"]) >= 10')
    require(bool(any(item.get("task_key") == "liquisto_opportunity_assessment" for item in result["run_context"]["active_tasks"])), 'any(item.get("task_key") == "liquisto_opportunity_assessment" for item in result["run_context"]["active_tasks"])')
    require(
        bool(
            any(
                item.get("allowed_tools")
                for item in result["run_context"]["active_tasks"]
                if item.get("assignee") == "CompanyDepartment"
            )
        ),
        'any(item.get("allowed_tools") for item in result["run_context"]["active_tasks"] if item.get("assignee") == "CompanyDepartment")',
    )
    require(bool(any(item.get("model_name") for item in result["run_context"]["active_tasks"])), 'any(item.get("model_name") for item in result["run_context"]["active_tasks"])')
    require(bool(result["usage"]["total"]["total_cost"] >= 0), 'result["usage"]["total"]["total_cost"] >= 0')
    require(bool(Path(result["run_dir"]).exists()), 'Path(result["run_dir"]).exists()')


def test_generate_pdf_focuses_on_briefing_not_run_process():
    payload = {
        "company_profile": {
            "company_name": "ACME GmbH",
            "industry": "Industrial Automation",
            "website": "https://acme.example",
            "legal_form": "GmbH",
            "products_and_services": ["Actuators", "Control units"],
            "product_asset_scope": ["Control units are relevant for resale and redeployment."],
            "economic_situation": {
                "revenue_trend": "n/v",
                "profitability": "n/v",
                "financial_pressure": "n/v",
                "assessment": "Public signals remain limited.",
            },
        },
        "industry_analysis": {
            "trend_direction": "gemischt",
            "demand_outlook": "Mixed demand signals.",
            "assessment": "Demand is mixed and should be validated with external reports.",
            "key_trends": ["Automation upgrades", "Spare-part demand"],
        },
        "market_network": {
            "peer_competitors": {"companies": [], "assessment": "Peer scan remains indicative."},
            "downstream_buyers": {"companies": [], "assessment": "Buyer paths require validation."},
            "service_providers": {"companies": [], "assessment": "Service-provider path remains open."},
            "cross_industry_buyers": {"companies": [], "assessment": "Cross-industry path remains speculative."},
        },
        "quality_review": {
            "evidence_health": "medium",
            "open_gaps": ["Buyer validation remains open."],
        },
        "synthesis": {
            "target_company": "ACME GmbH",
            "executive_summary": "ACME is relevant for Liquisto due to mixed market signals and plausible buyer paths.",
            "opportunity_assessment_summary": "Excess inventory and analytics are plausible engagement paths.",
            "liquisto_service_relevance": [
                {"service_area": "excess_inventory", "relevance": "mittel", "reasoning": "Buyer path appears plausible."},
                {"service_area": "analytics", "relevance": "mittel", "reasoning": "Operational visibility gaps are plausible."},
            ],
            "key_risks": ["Buyer validation remains open."],
            "next_steps": ["Validate likely buyers before the meeting."],
            "sources": [{"title": "ACME website", "url": "https://acme.example", "source_type": "owned", "summary": "Company overview."}],
        },
    }

    pdf_bytes = generate_pdf(payload, lang="de")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf_bytes)).pages)

    require(bool("Management-Übersicht" in text), '"Management-Übersicht" in text')
    require(bool("Primäre Empfehlung" in text), '"Primäre Empfehlung" in text')
    require(bool("Zielunternehmen-Kontakte" in text), '"Zielunternehmen-Kontakte" in text')
    require(bool("Executive Dashboard" not in text), '"Executive Dashboard" not in text')
    require(bool("Open Questions & Validation Plan" not in text), '"Open Questions & Validation Plan" not in text')
    require(bool("Evidenz-Anhang" not in text), '"Evidenz-Anhang" not in text')
    require(bool("Runtime-Events" not in text), '"Runtime-Events" not in text')
    require(bool("GroupChat-Runden" not in text), '"GroupChat-Runden" not in text')
