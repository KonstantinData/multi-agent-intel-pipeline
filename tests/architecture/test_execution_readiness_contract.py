from __future__ import annotations

from src.orchestration.synthesis import (
    assess_research_readiness,
    build_contact_enrichment_stage,
    build_primary_source_stage,
)


def _base_company_profile() -> dict:
    return {
        "company_name": "TestCo",
        "industry": "Industrial Equipment",
        "description": "Industrial manufacturer",
        "products_and_services": ["Fans", "Drive systems"],
        "financial_deep_dive": {
            "assessment": "Inventory pressure visible",
            "key_financials": ["Revenue declined 8% YoY"],
            "inventory_positions": ["Inventory increased 12% YoY"],
            "inventory_risks": [],
            "balance_sheet_signals": [],
            "sources": [
                {"title": "Annual Report 2025", "url": "https://example.com/annual-report-2025.pdf", "source_type": "primary"},
            ],
        },
        "sources": [
            {"title": "SEC filing", "url": "https://example.com/10-k", "source_type": "primary"},
        ],
    }


def test_primary_source_stage_extracts_primary_families_and_hard_signals():
    stage = build_primary_source_stage(
        company_profile=_base_company_profile(),
        industry_analysis={},
        market_network={},
    )
    assert stage["public_primary_sources_available"] is True
    assert stage["coverage_quality"] in {"strong", "partial"}
    assert stage["hard_financial_inventory_signal_count"] >= 1


def test_contact_enrichment_marks_missing_public_sources_for_unverified_contacts():
    stage = build_contact_enrichment_stage(
        company_profile={"company_name": "TestCo"},
        contact_intelligence={
            "target_company_contacts": [
                {
                    "name": "Jane Doe",
                    "rolle_titel": "Head of Procurement",
                    "funktion": "Procurement",
                    "confidence": "inferred",
                    "quelle": "n/v",
                }
            ]
        },
    )
    enriched = stage["target_contacts_enriched"]
    assert enriched
    assert enriched[0].get("source_availability_note") == "keine freien Quellen"


def test_readiness_contract_returns_discovery_ready_for_internal_only_blockers():
    company_profile = _base_company_profile()
    readiness = assess_research_readiness(
        company_profile=company_profile,
        industry_analysis={"industry_name": "Industrial", "assessment": "stable"},
        market_network={"target_company": "TestCo"},
        contact_intelligence={"target_company_contacts": []},
        quality_review={"evidence_health": "medium", "open_gaps": []},
        synthesis={
            "generation_mode": "normal",
            "executive_summary": "Summary",
            "opportunity_assessment_summary": "Opportunity",
            "recommended_engagement_paths": ["excess_inventory"],
        },
    )
    assert readiness["usable"] is False
    assert readiness["discovery_ready"] is True
    blockers = readiness["readiness_blockers"]
    assert blockers
    assert all(item.get("availability") == "internal_customer" for item in blockers)
    assert readiness["data_request_sheet"]["status"] == "required"


def test_readiness_contract_stays_blocked_when_primary_sources_missing():
    profile = _base_company_profile()
    profile["financial_deep_dive"]["sources"] = []
    profile["sources"] = []
    readiness = assess_research_readiness(
        company_profile=profile,
        industry_analysis={"industry_name": "Industrial", "assessment": "stable"},
        market_network={"target_company": "TestCo"},
        contact_intelligence={"target_company_contacts": []},
        quality_review={"evidence_health": "medium", "open_gaps": []},
        synthesis={
            "generation_mode": "normal",
            "executive_summary": "Summary",
            "opportunity_assessment_summary": "Opportunity",
            "recommended_engagement_paths": ["excess_inventory"],
        },
    )
    public_blockers = [
        b for b in readiness["readiness_blockers"]
        if b.get("availability") == "public"
    ]
    assert public_blockers
    assert readiness["discovery_ready"] is False


def test_readiness_contract_includes_department_policy_gate_blockers():
    readiness = assess_research_readiness(
        company_profile=_base_company_profile(),
        industry_analysis={"industry_name": "Industrial", "assessment": "stable"},
        market_network={"target_company": "TestCo"},
        contact_intelligence={"target_company_contacts": []},
        quality_review={"evidence_health": "medium", "open_gaps": []},
        synthesis={
            "generation_mode": "normal",
            "executive_summary": "Summary",
            "opportunity_assessment_summary": "Opportunity",
            "recommended_engagement_paths": ["excess_inventory"],
        },
        department_packages={
            "CompanyDepartment": {
                "policy_gate": {
                    "passed": False,
                    "blockers": [
                        {
                            "blocker_id": "company_missing_inventory",
                            "field_key": "financial_deep_dive.inventory_positions",
                            "availability": "public",
                            "severity": "hard",
                            "reason": "Required field missing.",
                            "owner": "Company Department",
                            "next_step": "Run targeted follow-up.",
                        }
                    ],
                }
            }
        },
    )
    assert readiness["usable"] is False
    assert any(
        item.get("blocker_id") == "company_missing_inventory"
        for item in readiness["readiness_blockers"]
    )
    assert readiness["department_gate_overview"]["CompanyDepartment"]["passed"] is False
