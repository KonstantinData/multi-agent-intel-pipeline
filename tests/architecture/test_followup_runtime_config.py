from __future__ import annotations

from src.agents.lead import _FOLLOWUP_TARGET_SECTION_BY_DEPARTMENT


def test_followup_target_section_mapping_is_complete_for_runtime_departments():
    assert _FOLLOWUP_TARGET_SECTION_BY_DEPARTMENT["CompanyDepartment"] == "company_profile"
    assert _FOLLOWUP_TARGET_SECTION_BY_DEPARTMENT["MarketDepartment"] == "industry_analysis"
    assert _FOLLOWUP_TARGET_SECTION_BY_DEPARTMENT["BuyerDepartment"] == "market_network"
    assert _FOLLOWUP_TARGET_SECTION_BY_DEPARTMENT["ContactDepartment"] == "contact_intelligence"
