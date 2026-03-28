"""Shared use-case definitions for Liquisto preparation runs."""
from __future__ import annotations

from typing import Any


LIQUISTO_STANDARD_SCOPE = """
Prepare a Liquisto pre-meeting briefing for a new target company.

The briefing must help a Liquisto colleague prepare for a customer meeting where
Liquisto wants to understand the target company, its market situation, and the
most plausible value-creation paths for a future commercial engagement.

Always investigate these information blocks:
1. Company fundamentals: identity, products, offering, footprint, visible leadership, and business model.
2. Economic and commercial situation: signs of pressure, growth, contraction, inventory stress, demand weakness, shortage/excess dynamics, liquidity pressure, or strategic change.
3. Market situation: demand trend, supply pressure, overcapacity, growth/stagnation/decline, and why.
4. Peer companies: direct and close competitors producing the same or similar goods.
5. Product and asset scope: identify which goods, components, materials, spare parts, or inventory positions are visible in the target company. Distinguish between products the company appears to make itself, products it mainly distributes or resells, and materials, spare parts, or stock it holds. Include internal assets only when they appear relevant for inventory, redeployment, repurposing, or operational analysis. Highlight which items are most likely to matter for later buyer, resale, redeployment, repurposing, aftermarket, or inventory-management analysis, and explain why.
6. Monetization and redeployment landscape: identify plausible resale, redeployment, reuse, or secondary-market paths for the goods and assets identified above. This includes specific peer buyers, downstream customers, aftermarket or service organizations, distributors, brokers, marketplaces, and cross-industry users where there is a credible fit. State what each buyer path may absorb and why it is relevant.
7. Repurposing and circularity landscape: identify plausible repurposing paths for unused materials, components, or assets, including adjacent use cases, circular-economy pathways, innovation partners, or communities when relevant.
8. Analytics and operational improvement landscape: identify signals of reporting gaps, planning complexity, inventory visibility problems, decision bottlenecks, or resource-efficiency opportunities where analytics or decision support could create value.
9. Liquisto opportunity assessment: only after completing the research, assess which Liquisto path appears most plausible based on the evidence and why. The possible outcomes are:
   - excess inventory monetization and inventory optimization
   - repurposing and circular-economy use cases for unused materials
   - analytics, reporting, and decision support for resource efficiency
   - or a combination of these paths when the evidence supports it
10. Negotiation relevance: signals that help Liquisto estimate pricing power, urgency, buyer demand, repurposing leverage, analytics potential, and the strongest next commercial angle for the meeting.

The user only provides company name and web domain. The system must infer the
rest of the standard research scope automatically.
""".strip()


# ---------------------------------------------------------------------------
# Validation rule format (used by CriticAgent):
#
#   {
#       "check": "non_placeholder" | "min_items" | "min_length" | "nested_field_non_placeholder",
#       "field": "dotted.path.into.payload",
#       "sub_field": "<str>",   # required for nested_field_non_placeholder
#       "value": <int>,         # required for min_items / min_length / nested_field_non_placeholder
#       "class": "core" | "supporting",
#       "message": "human-readable failure reason",
#   }
#
# check semantics:
#   non_placeholder                — field value must not be "n/v" / empty / None
#   min_items                      — field must be a sequence with >= value items
#   min_length                     — field must be a string with >= value characters
#   nested_field_non_placeholder   — >= value items in the list at field must have
#                                    a non-placeholder value at sub_field
#
# class semantics:
#   core       — must pass for task to be accepted; determines degraded/rejected
#   supporting — improves confidence but task can still be accepted without it
# ---------------------------------------------------------------------------

STANDARD_TASK_BACKLOG: list[dict[str, Any]] = [
    {
        "task_key": "company_fundamentals",
        "label": "Company fundamentals",
        "assignee": "CompanyDepartment",
        "target_section": "company_profile",
        "objective_template": "Build verified company fundamentals for {company_name}, including identity, offering, footprint, and business model.",
        "depends_on": [],
        "run_condition": None,
        "output_schema_key": "CompanyFundamentals",
        "validation_rules": [
            {"check": "non_placeholder", "field": "company_name", "class": "core", "message": "Company name is not identified"},
            {"check": "non_placeholder", "field": "website", "class": "core", "message": "Company website is not verified"},
            {"check": "non_placeholder", "field": "industry", "class": "core", "message": "Industry classification is missing"},
            {"check": "non_placeholder", "field": "description", "class": "core", "message": "Business description is absent"},
            {"check": "min_items", "field": "products_and_services", "value": 2, "class": "core", "message": "Fewer than 2 products or services listed"},
            {"check": "non_placeholder", "field": "headquarters", "class": "supporting", "message": "Headquarters location is missing"},
            {"check": "non_placeholder", "field": "revenue", "class": "supporting", "message": "Revenue figure is missing"},
        ],
    },
    {
        "task_key": "economic_commercial_situation",
        "label": "Economic and commercial situation",
        "assignee": "CompanyDepartment",
        "target_section": "company_profile",
        "objective_template": "Assess public signals of economic and commercial pressure for {company_name}, including growth, contraction, inventory stress, shortage or excess dynamics, and strategic change.",
        "depends_on": ["company_fundamentals"],
        "run_condition": None,
        "output_schema_key": "EconomicSituation",
        "validation_rules": [
            {"check": "non_placeholder", "field": "economic_situation.assessment", "class": "core", "message": "Economic assessment is missing"},
            {"check": "min_items", "field": "economic_situation.recent_events", "value": 1, "class": "core", "message": "No recent commercial events recorded"},
            {"check": "non_placeholder", "field": "economic_situation.financial_pressure", "class": "core", "message": "Financial pressure assessment is missing"},
            {"check": "min_items", "field": "economic_situation.inventory_signals", "value": 1, "class": "supporting", "message": "No inventory signals found"},
            {"check": "non_placeholder", "field": "economic_situation.revenue_trend", "class": "supporting", "message": "Revenue trend is missing"},
        ],
    },
    {
        "task_key": "market_situation",
        "label": "Market situation",
        "assignee": "MarketDepartment",
        "target_section": "industry_analysis",
        "objective_template": "Assess the market situation for {company_name}: demand trend, supply pressure, overcapacity, growth or decline, and why.",
        "depends_on": [],
        "run_condition": None,
        "output_schema_key": "MarketSituation",
        "validation_rules": [
            {"check": "non_placeholder", "field": "industry_name", "class": "core", "message": "Industry name is missing"},
            {"check": "non_placeholder", "field": "assessment", "class": "core", "message": "Market assessment is missing"},
            {"check": "non_placeholder", "field": "demand_outlook", "class": "core", "message": "Demand outlook is not assessed"},
            {"check": "non_placeholder", "field": "trend_direction", "class": "core", "message": "Market trend direction is missing"},
            {"check": "min_items", "field": "key_trends", "value": 2, "class": "core", "message": "Fewer than 2 market trends identified"},
            {"check": "non_placeholder", "field": "growth_rate", "class": "supporting", "message": "Growth rate is missing"},
            {"check": "non_placeholder", "field": "market_size", "class": "supporting", "message": "Market size is missing"},
        ],
    },
    {
        "task_key": "peer_companies",
        "label": "Peer companies",
        "assignee": "BuyerDepartment",
        "target_section": "market_network",
        "objective_template": "Identify direct and close peer companies producing the same or similar goods as {company_name}.",
        "depends_on": ["market_situation"],
        "run_condition": None,
        "output_schema_key": "PeerCompanies",
        "validation_rules": [
            {"check": "non_placeholder", "field": "target_company", "class": "core", "message": "Target company is not confirmed"},
            {"check": "non_placeholder", "field": "peer_competitors.assessment", "class": "core", "message": "Peer landscape assessment is missing"},
            {"check": "min_items", "field": "peer_competitors.companies", "value": 3, "class": "core", "message": "Fewer than 3 peer companies identified"},
            {"check": "nested_field_non_placeholder", "field": "peer_competitors.companies", "sub_field": "relevance", "value": 2, "class": "core", "message": "Fewer than 2 peers have a relevance explanation"},
        ],
    },
    {
        "task_key": "product_asset_scope",
        "label": "Product and asset scope",
        "assignee": "CompanyDepartment",
        "target_section": "company_profile",
        "objective_template": "Identify which goods, components, materials, spare parts, or inventory positions are visible in {company_name}. Distinguish between products the company appears to make itself, products it mainly distributes or resells, and materials, spare parts, or stock it holds. Include internal assets only when they appear relevant for inventory, redeployment, repurposing, or operational analysis, and highlight which items matter most for later buyer, resale, redeployment, repurposing, aftermarket, or inventory-management analysis.",
        "depends_on": ["company_fundamentals"],
        "run_condition": None,
        "output_schema_key": "ProductAssetScope",
        "validation_rules": [
            {"check": "min_items", "field": "product_asset_scope", "value": 2, "class": "core", "message": "Fewer than 2 product or asset scope items identified"},
            {"check": "non_placeholder", "field": "goods_classification", "class": "core", "message": "Goods classification is missing"},
        ],
    },
    {
        "task_key": "monetization_redeployment",
        "label": "Monetization and redeployment landscape",
        "assignee": "BuyerDepartment",
        "target_section": "market_network",
        "objective_template": "Identify plausible resale, redeployment, reuse, and secondary-market paths for the goods and assets identified for {company_name}, including likely buyers and why each route is relevant.",
        "depends_on": ["peer_companies"],
        "run_condition": None,
        "output_schema_key": "MonetizationRedeployment",
        "validation_rules": [
            {"check": "non_placeholder", "field": "target_company", "class": "core", "message": "Target company is not confirmed"},
            {"check": "min_items", "field": "downstream_buyers.companies", "value": 1, "class": "core", "message": "No downstream buyers identified"},
            {"check": "non_placeholder", "field": "downstream_buyers.assessment", "class": "core", "message": "Downstream buyer assessment is missing"},
            {"check": "min_items", "field": "monetization_paths", "value": 1, "class": "core", "message": "No monetization paths defined"},
            {"check": "min_items", "field": "redeployment_paths", "value": 1, "class": "core", "message": "No redeployment paths defined"},
            {"check": "nested_field_non_placeholder", "field": "downstream_buyers.companies", "sub_field": "relevance", "value": 1, "class": "core", "message": "No downstream buyer has a relevance explanation"},
        ],
    },
    {
        "task_key": "repurposing_circularity",
        "label": "Repurposing and circularity landscape",
        "assignee": "MarketDepartment",
        "target_section": "industry_analysis",
        "objective_template": "Identify plausible repurposing and circularity paths for unused materials, components, or adjacent assets from {company_name}.",
        "depends_on": ["market_situation"],
        "run_condition": None,
        "output_schema_key": "RepurposingCircularity",
        "validation_rules": [
            {"check": "min_items", "field": "repurposing_signals", "value": 2, "class": "core", "message": "Fewer than 2 repurposing signals identified"},
        ],
    },
    {
        "task_key": "analytics_operational_improvement",
        "label": "Analytics and operational improvement landscape",
        "assignee": "MarketDepartment",
        "target_section": "industry_analysis",
        "objective_template": "Identify planning, reporting, inventory-visibility, or decision-support signals where analytics could create value for {company_name}.",
        "depends_on": ["market_situation"],
        "run_condition": None,
        "output_schema_key": "AnalyticsSignals",
        "validation_rules": [
            {"check": "min_items", "field": "analytics_signals", "value": 2, "class": "core", "message": "Fewer than 2 analytics signals identified"},
        ],
    },
    {
        "task_key": "contact_discovery",
        "label": "Contact discovery at prioritized buyer firms",
        "assignee": "ContactDepartment",
        "target_section": "contact_intelligence",
        "objective_template": "Identify publicly visible decision-makers and relevant contacts at buyer firms identified for {company_name}. Focus on procurement, asset management, operations, and supply chain functions.",
        "depends_on": ["peer_companies", "monetization_redeployment"],
        "run_condition": "buyer_department_has_prioritized_firms",
        "output_schema_key": "ContactDiscoveryResult",
        "validation_rules": [
            {"check": "min_items", "field": "contacts", "value": 3, "class": "core", "message": "Fewer than 3 contacts identified at buyer firms"},
            {"check": "non_placeholder", "field": "coverage_quality", "class": "core", "message": "Coverage quality not assessed"},
            {"check": "nested_field_non_placeholder", "field": "contacts", "sub_field": "firma", "value": 2, "class": "core", "message": "Fewer than 2 contacts have a verified company name"},
        ],
    },
    {
        "task_key": "contact_qualification",
        "label": "Contact qualification and outreach angles",
        "assignee": "ContactDepartment",
        "target_section": "contact_intelligence",
        "objective_template": "Qualify identified contacts for {company_name} buyer firms by seniority, function, and Liquisto relevance. Suggest a concrete outreach angle per contact based on the buyer context.",
        "depends_on": ["contact_discovery"],
        "run_condition": "contact_discovery_completed",
        "output_schema_key": "ContactQualificationResult",
        "validation_rules": [
            {"check": "min_items", "field": "prioritized_contacts", "value": 1, "class": "core", "message": "No contacts qualified and prioritized"},
            {"check": "non_placeholder", "field": "narrative_summary", "class": "core", "message": "No qualification narrative provided"},
            {"check": "nested_field_non_placeholder", "field": "prioritized_contacts", "sub_field": "senioritaet", "value": 1, "class": "core", "message": "No prioritized contact has seniority assessed"},
            {"check": "nested_field_non_placeholder", "field": "prioritized_contacts", "sub_field": "suggested_outreach_angle", "value": 1, "class": "core", "message": "No prioritized contact has an outreach angle"},
        ],
    },
    {
        "task_key": "liquisto_opportunity_assessment",
        "label": "Liquisto opportunity assessment",
        "assignee": "SynthesisDepartment",
        "target_section": "synthesis",
        "objective_template": "After the research is complete, assess which Liquisto path is most plausible for {company_name} based on the evidence and explain why.",
        "depends_on": ["company_fundamentals", "market_situation", "peer_companies", "monetization_redeployment"],
        "run_condition": None,
        "output_schema_key": "OpportunityAssessment",
        "validation_rules": [
            {"check": "non_placeholder", "field": "opportunity_assessment_summary", "class": "core", "message": "Opportunity assessment is missing"},
            {"check": "min_items", "field": "recommended_engagement_paths", "value": 1, "class": "core", "message": "No recommended engagement paths identified"},
            {"check": "min_items", "field": "liquisto_service_relevance", "value": 1, "class": "supporting", "message": "No service relevance assessments provided"},
        ],
    },
    {
        "task_key": "negotiation_relevance",
        "label": "Negotiation relevance",
        "assignee": "SynthesisDepartment",
        "target_section": "synthesis",
        "objective_template": "Summarize signals that help Liquisto estimate urgency, pricing power, buyer demand, repurposing leverage, analytics potential, and the strongest next meeting angle for {company_name}.",
        "depends_on": ["liquisto_opportunity_assessment"],
        "run_condition": None,
        "output_schema_key": "NegotiationRelevance",
        "validation_rules": [
            {"check": "min_items", "field": "next_steps", "value": 1, "class": "core", "message": "No next steps defined"},
            {"check": "min_items", "field": "key_risks", "value": 1, "class": "core", "message": "No key risks identified"},
        ],
    },
]


# ---------------------------------------------------------------------------
# Lookup helpers — single source of truth for validation rules
# ---------------------------------------------------------------------------

_TASK_VALIDATION_RULES: dict[str, list[dict[str, Any]]] = {
    task["task_key"]: task.get("validation_rules", [])
    for task in STANDARD_TASK_BACKLOG
}

_TASK_CONTRACT_BY_KEY: dict[str, dict[str, Any]] = {
    task["task_key"]: task
    for task in STANDARD_TASK_BACKLOG
}


def get_task_validation_rules(task_key: str) -> list[dict[str, Any]]:
    """Return the validation_rules list for a given task_key.

    Returns an empty list for unknown task_keys (e.g. synthesis tasks
    that go through a different quality path).
    """
    return _TASK_VALIDATION_RULES.get(task_key, [])


def get_task_contract(task_key: str) -> dict[str, Any] | None:
    """Return the full task contract dict for a given task_key, or None."""
    return _TASK_CONTRACT_BY_KEY.get(task_key)


def build_standard_scope() -> str:
    """Return the canonical Liquisto research mandate."""
    return LIQUISTO_STANDARD_SCOPE


def build_standard_backlog() -> list[dict[str, Any]]:
    """Return the canonical supervisor task backlog."""
    return [dict(item) for item in STANDARD_TASK_BACKLOG]
