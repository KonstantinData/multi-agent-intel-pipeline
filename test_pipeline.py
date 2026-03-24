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

from src.exporters.pdf_report import generate_pdf
from src.agents.worker import ResearchWorker
from src.config import get_model_pricing, get_role_model_selection, summarize_worker_report_costs
from src.orchestration.task_router import build_initial_assignments
from src.memory.policies import should_store_strategy
from src.orchestration.synthesis import assess_research_readiness, build_synthesis_context
from src.pipeline_runner import _extract_pipeline_data, run_pipeline
from src.domain.intake import SupervisorBrief


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
        quality_review={"open_gaps": []},
        memory_snapshot={"sources": [], "next_actions": []},
    )

    assert synthesis["recommended_engagement_paths"] == ["further_validation_required"]
    assert all(item["relevance"] == "unclear" for item in synthesis["liquisto_service_relevance"])


def test_should_store_strategy_only_for_usable_completed_runs():
    assert should_store_strategy(status="completed", usable=True) is True
    assert should_store_strategy(status="completed_but_not_usable", usable=False) is False
    assert should_store_strategy(status="failed", usable=False) is False


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

    assert data["company_profile"]["company_name"] == "ACME"
    assert data["synthesis"]["target_company"] == "ACME"


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

    assert len(assignments) >= 10
    assert "product_asset_scope" in task_keys
    assert "repurposing_circularity" in task_keys
    assert "analytics_operational_improvement" in task_keys
    assert "liquisto_opportunity_assessment" in task_keys
    assert "negotiation_relevance" in task_keys

    first = assignments[0]
    assert first.model_name
    assert first.allowed_tools


def test_role_model_selection_is_explicit():
    supervisor_model, supervisor_structured = get_role_model_selection("Supervisor")
    worker_model, worker_structured = get_role_model_selection("CompanyResearcher")

    assert supervisor_model == "gpt-4.1"
    assert supervisor_structured == "gpt-4.1"
    assert worker_model == "gpt-4.1-mini"
    assert worker_structured == "gpt-4.1-mini"


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

    assert get_model_pricing("gpt-4.1-mini") == {"input": 0.40, "output": 1.60}
    assert usage["total"]["total_cost"] > 0
    assert "gpt-4.1-mini" in usage["total"]["models"]


def test_worker_normalizes_nested_llm_section_payload():
    worker = ResearchWorker("CompanyResearcher")
    payload_updates = {"company_profile": {"company_name": "ACME", "industry": "Automation"}}

    normalized = worker._normalize_payload_updates("company_profile", payload_updates)

    assert normalized == {"company_name": "ACME", "industry": "Automation"}


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

    assert payload["product_asset_scope"] == [
        "Control Units | High",
        "Actuators",
    ]


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

    assert report["payload"]["company_name"] == "ACME GmbH"
    assert report["open_questions"]


def test_assess_research_readiness_requires_multiple_sections():
    readiness = assess_research_readiness(
        company_profile={"company_name": "ACME"},
        industry_analysis={"industry_name": "Software"},
        market_network={"target_company": "ACME"},
        quality_review={"evidence_health": "medium"},
    )

    assert readiness["usable"] is True
    assert readiness["score"] >= 70


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

    assert result["status"] in {"completed", "completed_but_not_usable"}
    assert result["pipeline_data"]["company_profile"]["company_name"] == "ACME GmbH"
    assert "CrossDomainStrategicAnalyst" in [item["assignee"] for item in result["run_context"]["active_tasks"]]
    assert result["pipeline_data"]["synthesis"]["target_company"] == "ACME GmbH"
    assert result["budget"]["elapsed_seconds"] >= 0
    assert len(result["run_context"]["active_tasks"]) >= 10
    assert any(item.get("task_key") == "liquisto_opportunity_assessment" for item in result["run_context"]["active_tasks"])
    assert any(
        item.get("allowed_tools")
        for item in result["run_context"]["active_tasks"]
        if item.get("assignee") == "CompanyDepartment"
    )
    assert any(item.get("model_name") for item in result["run_context"]["active_tasks"])
    assert result["usage"]["total"]["total_cost"] >= 0
    assert Path(result["run_dir"]).exists()


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

    assert "Management Snapshot" in text
    assert "Buyer- und Redeployment-Landschaft" in text
    assert "Evidenz-Anhang" in text
    assert "Runtime-Events" not in text
    assert "GroupChat-Runden" not in text
