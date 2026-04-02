from __future__ import annotations

from src.orchestration.department_knowledge import (
    evaluate_department_policy_gate,
    load_department_policy,
    load_department_source_profile,
)


def test_load_department_kb_profiles():
    policy = load_department_policy("CompanyDepartment")
    sources = load_department_source_profile("CompanyDepartment")
    assert policy.department == "CompanyDepartment"
    assert "financial_deep_dive.assessment" in policy.required_fields
    assert sources.get("department") == "CompanyDepartment"
    assert len(sources.get("sources", [])) >= 1


def test_company_policy_gate_flags_missing_required_fields():
    policy = load_department_policy("CompanyDepartment")
    result = evaluate_department_policy_gate(
        department="CompanyDepartment",
        policy=policy,
        section_payload={
            "company_name": "n/v",
            "description": "n/v",
            "financial_deep_dive": {"assessment": "n/v", "key_financials": [], "inventory_positions": []},
        },
        completed_tasks=[{"status": "degraded"}],
        sources=[],
        open_questions=[],
    )
    assert result["passed"] is False
    assert result["missing_required_fields"]
    assert any(item.get("field_key") == "min_sources" for item in result["blockers"])


def test_contact_policy_gate_uses_internal_customer_when_no_free_sources():
    policy = load_department_policy("ContactDepartment")
    result = evaluate_department_policy_gate(
        department="ContactDepartment",
        policy=policy,
        section_payload={
            "target_company_summary": "n/v",
            "target_company_contacts": [],
            "target_company_access_path": [],
        },
        completed_tasks=[{"status": "degraded"}, {"status": "degraded"}],
        sources=[],
        open_questions=["No publicly verifiable decision-maker found (keine freien Quellen)."],
    )
    assert result["passed"] is False
    assert result["blockers"]
    assert all(item.get("availability") == "internal_customer" for item in result["blockers"])
