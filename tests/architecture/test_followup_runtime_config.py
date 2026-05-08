from __future__ import annotations

from src.orchestration.followup_config import FOLLOWUP_TARGET_SECTION_BY_DEPARTMENT


def test_followup_target_section_mapping_is_complete_for_runtime_departments() -> None:
    assert FOLLOWUP_TARGET_SECTION_BY_DEPARTMENT["CompanyDepartment"] == "company_profile"
    assert FOLLOWUP_TARGET_SECTION_BY_DEPARTMENT["MarketDepartment"] == "industry_analysis"
    assert FOLLOWUP_TARGET_SECTION_BY_DEPARTMENT["BuyerDepartment"] == "market_network"
    assert FOLLOWUP_TARGET_SECTION_BY_DEPARTMENT["ContactDepartment"] == "contact_intelligence"
