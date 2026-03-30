"""Task-specific sub-schemas, central SCHEMA_REGISTRY, and section assembly.

Each task in STANDARD_TASK_BACKLOG has an ``output_schema_key`` that maps to a
Pydantic model here.  All runtime code that needs to validate or instantiate a
task output resolves through SCHEMA_REGISTRY — not through ad-hoc imports or
string matching.

Assembly convention
-------------------
Task-level sub-schemas are narrow slices of the broader section-level models
(CompanyProfile, IndustryAnalysis, MarketNetwork, ContactIntelligenceSection).
``assemble_section()`` merges raw payload dicts into validated section-level
Pydantic models for PipelineData assembly.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.models.schemas import (
    CompanyProfile,
    CompanyRecord,
    ContactIntelligenceSection,
    ContactPerson,
    EconomicSituation,
    FinancialDeepDive,
    IndustryAnalysis,
    MarketNetwork,
    MarketTier,
    SourceRecord,
    TransactionEventIntelligence,
)


# ---------------------------------------------------------------------------
# Company department sub-schemas
# ---------------------------------------------------------------------------


class CompanyFundamentals(BaseModel):
    """Core identity, offering, and business model fields."""
    company_name: str = "n/v"
    legal_form: str = "n/v"
    founded: str = "n/v"
    headquarters: str = "n/v"
    website: str = "n/v"
    industry: str = "n/v"
    employees: str = "n/v"
    revenue: str = "n/v"
    products_and_services: list[str] = Field(default_factory=list)
    description: str = "n/v"
    sources: list[SourceRecord] = Field(default_factory=list)


class ProductAssetScope(BaseModel):
    """Goods, components, materials, and inventory positions."""
    product_asset_scope: list[str] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)


# EconomicSituation is already defined in schemas.py — reused directly.
# output_schema_key "EconomicSituation" resolves to that class.


class FinancialDeepDiveResult(BaseModel):
    """Balance-sheet and working-capital extraction from primary financial sources."""
    financial_deep_dive: FinancialDeepDive = Field(default_factory=FinancialDeepDive)


class TransactionEventIntelligenceResult(BaseModel):
    """Strategic events such as M&A, carve-outs, JVs, and regulatory disclosures."""
    transaction_event_intelligence: TransactionEventIntelligence = Field(default_factory=TransactionEventIntelligence)


# ---------------------------------------------------------------------------
# Market department sub-schemas
# ---------------------------------------------------------------------------


class MarketSituation(BaseModel):
    """Demand trend, supply pressure, and market assessment."""
    industry_name: str = "n/v"
    market_size: str = "n/v"
    trend_direction: str = "n/v"
    growth_rate: str = "n/v"
    key_trends: list[str] = Field(default_factory=list)
    overcapacity_signals: list[str] = Field(default_factory=list)
    excess_stock_indicators: str = "n/v"
    demand_outlook: str = "n/v"
    assessment: str = "n/v"
    sources: list[SourceRecord] = Field(default_factory=list)


class RepurposingCircularity(BaseModel):
    """Repurposing and circularity landscape signals."""
    repurposing_signals: list[str] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)


class AnalyticsSignals(BaseModel):
    """Analytics and operational improvement signals."""
    analytics_signals: list[str] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Buyer department sub-schemas
# ---------------------------------------------------------------------------


class PeerCompanies(BaseModel):
    """Peer and competitor company map."""
    target_company: str = "n/v"
    peer_competitors: MarketTier = Field(default_factory=MarketTier)


class MonetizationRedeployment(BaseModel):
    """Downstream buyer and redeployment landscape."""
    target_company: str = "n/v"
    downstream_buyers: MarketTier = Field(default_factory=MarketTier)
    service_providers: MarketTier = Field(default_factory=MarketTier)
    cross_industry_buyers: MarketTier = Field(default_factory=MarketTier)
    monetization_paths: list[str] = Field(default_factory=list)
    redeployment_paths: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Contact department sub-schemas
# ---------------------------------------------------------------------------


class ContactDiscoveryResult(BaseModel):
    """Decision-makers found at prioritized buyer firms."""
    contacts: list[ContactPerson] = Field(default_factory=list)
    firms_searched: int = 0
    contacts_found: int = 0
    coverage_quality: str = "n/v"
    open_questions: list[str] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)


class ContactQualificationResult(BaseModel):
    """Qualified and prioritized contacts with outreach angles."""
    prioritized_contacts: list[ContactPerson] = Field(default_factory=list)
    narrative_summary: str = "n/v"
    open_questions: list[str] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)


class TargetCompanyContactsResult(BaseModel):
    """Decision-makers at the target company itself."""
    target_company_contacts: list[ContactPerson] = Field(default_factory=list)
    target_company_prioritized_contacts: list[ContactPerson] = Field(default_factory=list)
    target_company_summary: str = "n/v"
    open_questions: list[str] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Synthesis department sub-schemas
# ---------------------------------------------------------------------------


class OpportunityAssessment(BaseModel):
    """Liquisto opportunity assessment after cross-domain review."""
    opportunity_assessment_summary: str = "n/v"
    recommended_engagement_paths: list[str] = Field(default_factory=list)


class NegotiationRelevance(BaseModel):
    """Negotiation leverage signals for the upcoming meeting."""
    key_risks: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Central registry — resolves output_schema_key strings to Pydantic classes
# ---------------------------------------------------------------------------

SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {
    "CompanyFundamentals": CompanyFundamentals,
    "EconomicSituation": EconomicSituation,
    "FinancialDeepDiveResult": FinancialDeepDiveResult,
    "ProductAssetScope": ProductAssetScope,
    "TransactionEventIntelligenceResult": TransactionEventIntelligenceResult,
    "MarketSituation": MarketSituation,
    "RepurposingCircularity": RepurposingCircularity,
    "AnalyticsSignals": AnalyticsSignals,
    "PeerCompanies": PeerCompanies,
    "MonetizationRedeployment": MonetizationRedeployment,
    "ContactDiscoveryResult": ContactDiscoveryResult,
    "ContactQualificationResult": ContactQualificationResult,
    "TargetCompanyContactsResult": TargetCompanyContactsResult,
    "OpportunityAssessment": OpportunityAssessment,
    "NegotiationRelevance": NegotiationRelevance,
}


def resolve_output_schema(schema_key: str) -> type[BaseModel]:
    """Return the Pydantic class for a given output_schema_key.

    Raises KeyError with a clear message if the key is not registered,
    so contract drift is caught at runtime rather than silently ignored.
    """
    try:
        return SCHEMA_REGISTRY[schema_key]
    except KeyError:
        registered = ", ".join(sorted(SCHEMA_REGISTRY))
        raise KeyError(
            f"output_schema_key '{schema_key}' is not in SCHEMA_REGISTRY. "
            f"Registered keys: {registered}"
        ) from None


# ---------------------------------------------------------------------------
# Section assembly — typed merge of sub-schema payloads into section models
# ---------------------------------------------------------------------------

# Maps target_section name → section-level Pydantic model
SECTION_MODEL_MAP: dict[str, type[BaseModel]] = {
    "company_profile": CompanyProfile,
    "industry_analysis": IndustryAnalysis,
    "market_network": MarketNetwork,
    "contact_intelligence": ContactIntelligenceSection,
}


def assemble_section(target_section: str, raw_payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a raw section payload against its section-level Pydantic model.

    Returns a clean dict produced by ``model.model_dump(mode="json")``.
    If ``target_section`` has no registered model, returns ``raw_payload`` as-is.
    """
    model_cls = SECTION_MODEL_MAP.get(target_section)
    if model_cls is None:
        return dict(raw_payload)
    return model_cls.model_validate(raw_payload).model_dump(mode="json")
