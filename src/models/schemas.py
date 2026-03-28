"""Pydantic schemas for the supervisor-centric pipeline."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field

# ---------------------------------------------------------------------------
# Canonical vocabulary — single source of truth for status/confidence/mode
# ---------------------------------------------------------------------------

# Task lifecycle status (set by router for skipped, by Judge for others)
TaskStatus = Literal["accepted", "degraded", "skipped", "rejected", "pending"]

# Evidence confidence level (applies to packages and synthesis)
ConfidenceLevel = Literal["high", "medium", "low"]

# Synthesis generation mode (orthogonal to confidence)
GenerationMode = Literal["normal", "fallback", "blocked"]


# ---------------------------------------------------------------------------
# P2-2: Blocked-Artifact — typed model for rejected sections/synthesis
# ---------------------------------------------------------------------------

class BlockedArtifact(BaseModel):
    """Typed representation of a section or synthesis that was rejected by the gate."""
    section_status: str = "blocked"
    reason: str = "n/v"
    open_questions: list[str] = Field(default_factory=list)
    sources: list[Any] = Field(default_factory=list)


class SourceRecord(BaseModel):
    title: str = "n/v"
    url: str = ""
    source_type: str = "secondary"
    summary: str = ""


class KeyPerson(BaseModel):
    name: str = "n/v"
    role: str = "n/v"


class ContactPerson(BaseModel):
    name: str = "n/v"
    firma: str = "n/v"
    rolle_titel: str = "n/v"
    funktion: str = "n/v"
    senioritaet: str = "n/v"
    standort: str = "n/v"
    quelle: str = "n/v"
    confidence: str = "inferred"
    relevance_reason: str = "n/v"
    suggested_outreach_angle: str = "n/v"


class ContactIntelligenceSection(BaseModel):
    contacts: list[ContactPerson] = Field(default_factory=list)
    prioritized_contacts: list[ContactPerson] = Field(default_factory=list)
    firms_searched: int = 0
    contacts_found: int = 0
    coverage_quality: str = "n/v"
    narrative_summary: str = "n/v"
    open_questions: list[str] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)


class DomainReportSegment(BaseModel):
    department: str = "n/v"
    narrative_summary: str = "n/v"
    confidence: str = "low"
    key_findings: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)


class BackRequest(BaseModel):
    department: str = "n/v"
    type: str = "clarify"
    subject: str = "n/v"
    context: str = "n/v"


class EconomicSituation(BaseModel):
    revenue_trend: str = "n/v"
    profitability: str = "n/v"
    recent_events: list[str] = Field(default_factory=list)
    inventory_signals: list[str] = Field(default_factory=list)
    financial_pressure: str = "n/v"
    assessment: str = "n/v"


class CompanyProfile(BaseModel):
    company_name: str = "n/v"
    legal_form: str = "n/v"
    founded: str = "n/v"
    headquarters: str = "n/v"
    website: str = "n/v"
    industry: str = "n/v"
    employees: str = "n/v"
    revenue: str = "n/v"
    products_and_services: list[str] = Field(default_factory=list)
    product_asset_scope: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("product_asset_scope", "product_material_relevance"),
    )
    goods_classification: str = "n/v"  # made | distributed | held_in_stock | mixed | unclear
    key_people: list[KeyPerson] = Field(default_factory=list)
    description: str = "n/v"
    economic_situation: EconomicSituation = Field(default_factory=EconomicSituation)
    sources: list[SourceRecord] = Field(default_factory=list)


class IndustryAnalysis(BaseModel):
    industry_name: str = "n/v"
    market_size: str = "n/v"
    trend_direction: str = "n/v"
    growth_rate: str = "n/v"
    key_trends: list[str] = Field(default_factory=list)
    overcapacity_signals: list[str] = Field(default_factory=list)
    excess_stock_indicators: str = "n/v"
    demand_outlook: str = "n/v"
    repurposing_signals: list[str] = Field(default_factory=list)
    analytics_signals: list[str] = Field(default_factory=list)
    assessment: str = "n/v"
    sources: list[SourceRecord] = Field(default_factory=list)


class CompanyRecord(BaseModel):
    name: str = "n/v"
    city: str = "n/v"
    country: str = "n/v"
    relevance: str = "n/v"


class MarketTier(BaseModel):
    companies: list[CompanyRecord] = Field(default_factory=list)
    assessment: str = "n/v"
    sources: list[SourceRecord] = Field(default_factory=list)


class MarketNetwork(BaseModel):
    target_company: str = "n/v"
    peer_competitors: MarketTier = Field(default_factory=MarketTier)
    downstream_buyers: MarketTier = Field(default_factory=MarketTier)
    service_providers: MarketTier = Field(default_factory=MarketTier)
    cross_industry_buyers: MarketTier = Field(default_factory=MarketTier)
    monetization_paths: list[str] = Field(default_factory=list)
    redeployment_paths: list[str] = Field(default_factory=list)


class GapDetail(BaseModel):
    agent: str = "n/v"
    field_path: str = "*"
    issue_type: str = "gap"
    severity: str = "moderate"
    summary: str = "n/v"
    recommendation: str = "n/v"


class QualityReview(BaseModel):
    validated_agents: list[str] = Field(default_factory=list)
    evidence_health: str = "n/v"
    open_gaps: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    gap_details: list[GapDetail] = Field(default_factory=list)


class ServiceRelevance(BaseModel):
    service_area: str = "n/v"
    relevance: str = "n/v"
    reasoning: str = "n/v"


class CaseArgument(BaseModel):
    argument: str = "n/v"
    direction: str = "pro"
    based_on: str = "n/v"


class CaseAssessment(BaseModel):
    option: str = "n/v"
    arguments: list[CaseArgument] = Field(default_factory=list)
    summary: str = "n/v"


class Synthesis(BaseModel):
    target_company: str = "n/v"
    executive_summary: str = "n/v"
    liquisto_service_relevance: list[ServiceRelevance] = Field(default_factory=list)
    opportunity_assessment_summary: str = "n/v"
    recommended_engagement_paths: list[str] = Field(default_factory=list)
    case_assessments: list[CaseAssessment] = Field(default_factory=list)
    buyer_market_summary: str = "n/v"
    total_peer_competitors: int = 0
    total_downstream_buyers: int = 0
    total_service_providers: int = 0
    total_cross_industry_buyers: int = 0
    key_risks: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)
    # Tracks how this synthesis was produced (orthogonal to confidence)
    generation_mode: str = "normal"
    confidence: str = "medium"
    # P2-4: Fields produced by SynthesisDepartmentAgent that were previously
    # silently discarded by Pydantic. Now persisted explicitly.
    back_requests_issued: int = 0
    back_requests: list[dict[str, Any]] = Field(default_factory=list)
    department_confidences: dict[str, str] = Field(default_factory=dict)


class ResearchReadiness(BaseModel):
    usable: bool = False
    score: int = 0
    reasons: list[str] = Field(default_factory=list)


class ValidationErrorRecord(BaseModel):
    agent: str = "n/v"
    section: str = "n/v"
    details: str = "n/v"


class DepartmentTaskResult(BaseModel):
    task_key: str = "n/v"
    label: str = "n/v"
    # Valid values: accepted | degraded | skipped | rejected | pending
    status: str = "pending"
    accepted_points: list[str] = Field(default_factory=list)
    open_points: list[str] = Field(default_factory=list)
    summary: str = "n/v"


class DepartmentPackage(BaseModel):
    department: str = "n/v"
    target_section: str = "n/v"
    summary: str = "n/v"
    section_payload: dict[str, Any] = Field(default_factory=dict)
    completed_tasks: list[DepartmentTaskResult] = Field(default_factory=list)
    accepted_points: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    visual_focus: list[str] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)
    autogen_group: dict[str, Any] = Field(default_factory=dict)
    report_segment: DomainReportSegment = Field(default_factory=DomainReportSegment)
    # Derived from Judge outcomes across completed_tasks
    confidence: str = "medium"


class FollowUpAnswer(BaseModel):
    run_id: str = "n/v"
    routed_to: str = "n/v"
    question: str = "n/v"
    answer: str = "n/v"
    evidence_used: list[str] = Field(default_factory=list)
    unresolved_points: list[str] = Field(default_factory=list)
    requires_additional_research: bool = False


class PipelineData(BaseModel):
    company_profile: CompanyProfile = Field(default_factory=CompanyProfile)
    industry_analysis: IndustryAnalysis = Field(default_factory=IndustryAnalysis)
    market_network: MarketNetwork = Field(default_factory=MarketNetwork)
    contact_intelligence: ContactIntelligenceSection = Field(default_factory=ContactIntelligenceSection)
    quality_review: QualityReview = Field(default_factory=QualityReview)
    synthesis: Synthesis = Field(default_factory=Synthesis)
    research_readiness: ResearchReadiness = Field(default_factory=ResearchReadiness)
    validation_errors: list[ValidationErrorRecord] = Field(default_factory=list)


def validate_pipeline_data(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize pipeline payloads for exports and UI loading."""
    model = PipelineData.model_validate(payload)
    return model.model_dump(mode="json")


def empty_pipeline_data() -> dict[str, Any]:
    """Return a fully structured empty payload."""
    return PipelineData().model_dump(mode="json")
