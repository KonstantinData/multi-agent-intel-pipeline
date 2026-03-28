"""Explicit tool grants per runtime role and task."""
from __future__ import annotations

BASE_TOOL_POLICY: dict[str, tuple[str, ...]] = {
    "Supervisor": ("website_snapshot", "search"),
    "CompanyDepartment": (),
    "MarketDepartment": (),
    "BuyerDepartment": (),
    "ContactDepartment": (),
    "CompanyLead": (),
    "MarketLead": (),
    "BuyerLead": (),
    "ContactLead": (),
    "CompanyResearcher": ("search", "page_fetch", "llm_structured"),
    "MarketResearcher": ("search", "page_fetch", "llm_structured"),
    "BuyerResearcher": ("search", "page_fetch", "llm_structured"),
    "ContactResearcher": ("search", "page_fetch", "llm_structured"),
    "CompanyCritic": (),
    "MarketCritic": (),
    "BuyerCritic": (),
    "ContactCritic": (),
    "CompanyJudge": (),
    "MarketJudge": (),
    "BuyerJudge": (),
    "ContactJudge": (),
    "CompanyCodingSpecialist": ("query_refinement",),
    "MarketCodingSpecialist": ("query_refinement",),
    "BuyerCodingSpecialist": ("query_refinement",),
    "ContactCodingSpecialist": ("query_refinement",),
}

TASK_TOOL_OVERRIDES: dict[tuple[str, str], tuple[str, ...]] = {
    ("Supervisor", "intake_normalization"): ("website_snapshot", "search"),
    ("CompanyResearcher", "company_fundamentals"): ("search", "page_fetch", "llm_structured"),
    ("CompanyResearcher", "economic_commercial_situation"): ("search", "page_fetch", "llm_structured"),
    ("CompanyResearcher", "product_asset_scope"): ("search", "page_fetch", "llm_structured"),
    ("MarketResearcher", "market_situation"): ("search", "page_fetch", "llm_structured"),
    ("MarketResearcher", "repurposing_circularity"): ("search", "page_fetch", "llm_structured"),
    ("MarketResearcher", "analytics_operational_improvement"): ("search", "page_fetch", "llm_structured"),
    ("BuyerResearcher", "peer_companies"): ("search", "page_fetch", "llm_structured"),
    ("BuyerResearcher", "monetization_redeployment"): ("search", "page_fetch", "llm_structured"),
    ("ContactResearcher", "contact_discovery"): ("search", "page_fetch", "llm_structured"),
    ("ContactResearcher", "contact_qualification"): ("search", "page_fetch", "llm_structured"),
    ("CompanyCodingSpecialist", "query_refinement"): ("query_refinement",),
    ("MarketCodingSpecialist", "query_refinement"): ("query_refinement",),
    ("BuyerCodingSpecialist", "query_refinement"): ("query_refinement",),
    ("ContactCodingSpecialist", "query_refinement"): ("query_refinement",),
}


def resolve_allowed_tools(agent_name: str, task_key: str) -> tuple[str, ...]:
    """Return the explicit tool grant for one role-task pair."""
    return TASK_TOOL_OVERRIDES.get((agent_name, task_key), BASE_TOOL_POLICY.get(agent_name, ()))


def tool_is_allowed(allowed_tools: tuple[str, ...] | list[str], tool_name: str) -> bool:
    """Convenience predicate used by workers."""
    return tool_name in set(allowed_tools)
