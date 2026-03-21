"""Pydantic models for all structured pipeline outputs."""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


# --- Shared ---

class Source(BaseModel):
    publisher: str
    url: str
    title: str = ""
    accessed: str = ""


class ConciergeOutput(BaseModel):
    company_name: str
    web_domain: str
    language: str
    observations: list[str] = Field(default_factory=list)


class ReviewFieldIssue(BaseModel):
    field_path: str = ""
    issue_type: str = "validation_error"
    summary: str
    recommendation: str = ""


class ReviewFeedback(BaseModel):
    approved: bool = False
    issues: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)
    field_issues: list[ReviewFieldIssue] = Field(default_factory=list)


class RepairPlan(BaseModel):
    producer_name: str
    stage_key: str
    primary_task: str
    subtask_delta: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    done_when: list[str] = Field(default_factory=list)


class EvidenceTier(str, Enum):
    CANDIDATE = "candidate"
    QUALIFIED = "qualified"
    VERIFIED = "verified"


# --- Step 2: Company Intelligence ---

class KeyPerson(BaseModel):
    name: str
    role: str

class EconomicSituation(BaseModel):
    revenue_trend: str = "n/v"
    profitability: str = "n/v"
    recent_events: list[str] = Field(default_factory=list)
    inventory_signals: list[str] = Field(default_factory=list)
    financial_pressure: str = "n/v"
    assessment: str = "n/v"

class CompanyProfile(BaseModel):
    company_name: str
    legal_form: str = "n/v"
    founded: str = "n/v"
    headquarters: str = "n/v"
    website: str = "n/v"
    industry: str = "n/v"
    employees: str = "n/v"
    revenue: str = "n/v"
    products_and_services: list[str] = Field(default_factory=list)
    key_people: list[KeyPerson] = Field(default_factory=list)
    description: str = ""
    economic_situation: EconomicSituation = Field(default_factory=EconomicSituation)
    sources: list[Source] = Field(default_factory=list)


# --- Step 3: Strategic Signals ---

class TrendDirection(str, Enum):
    GROWING = "wachsend"
    STABLE = "stabil"
    DECLINING = "schrumpfend"
    UNCERTAIN = "unsicher"

class IndustryAnalysis(BaseModel):
    industry_name: str
    market_size: str = "n/v"
    trend_direction: TrendDirection = TrendDirection.UNCERTAIN
    growth_rate: str = "n/v"
    key_trends: list[str] = Field(default_factory=list)
    overcapacity_signals: list[str] = Field(default_factory=list)
    excess_stock_indicators: str = "n/v"
    demand_outlook: str = "n/v"
    assessment: str = "n/v"
    sources: list[Source] = Field(default_factory=list)


# --- Step 4: Market Network (4 Buyer Tiers) ---

class Buyer(BaseModel):
    name: str
    website: str = "n/v"
    city: str = "n/v"
    country: str = "n/v"
    relevance: str = ""
    matching_products: list[str] = Field(default_factory=list)
    evidence_tier: EvidenceTier = EvidenceTier.CANDIDATE
    source: Source | None = None

class PeerCompetitors(BaseModel):
    """Competitors producing same/similar products – potential buyers of parts."""
    companies: list[Buyer] = Field(default_factory=list)
    assessment: str = "n/v"
    sources: list[Source] = Field(default_factory=list)

class DownstreamBuyers(BaseModel):
    """Companies buying products from Intake + Peers, incl. spare-part users."""
    companies: list[Buyer] = Field(default_factory=list)
    assessment: str = "n/v"
    sources: list[Source] = Field(default_factory=list)

class ServiceProviders(BaseModel):
    """Service firms maintaining/repairing equipment – need spare parts."""
    companies: list[Buyer] = Field(default_factory=list)
    assessment: str = "n/v"
    sources: list[Source] = Field(default_factory=list)

class CrossIndustryBuyers(BaseModel):
    """Companies from other industries that could use products/parts."""
    companies: list[Buyer] = Field(default_factory=list)
    assessment: str = "n/v"
    sources: list[Source] = Field(default_factory=list)

class MarketNetwork(BaseModel):
    target_company: str
    peer_competitors: PeerCompetitors = Field(default_factory=PeerCompetitors)
    downstream_buyers: DownstreamBuyers = Field(default_factory=DownstreamBuyers)
    service_providers: ServiceProviders = Field(default_factory=ServiceProviders)
    cross_industry_buyers: CrossIndustryBuyers = Field(default_factory=CrossIndustryBuyers)


# --- Step 5: Evidence QA ---

class QAGapDetail(BaseModel):
    agent: str
    field_path: str = ""
    issue_type: str
    severity: str = "significant"
    summary: str
    recommendation: str = ""


class QualityReview(BaseModel):
    validated_agents: list[str] = Field(default_factory=list)
    evidence_health: str = "n/v"
    open_gaps: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    gap_details: list[QAGapDetail] = Field(default_factory=list)


# --- Step 6: Synthesis ---

class LiquistoCaseArgument(BaseModel):
    """One pro/contra argument for a Liquisto option."""
    argument: str
    direction: str  # "pro" or "contra"
    based_on: str   # which evidence supports this

class LiquistoCaseAssessment(BaseModel):
    """Assessment for one Liquisto option (Kaufen/Kommission/Ablehnen)."""
    option: str  # "kaufen", "kommission", "ablehnen"
    arguments: list[LiquistoCaseArgument] = Field(default_factory=list)
    summary: str = ""

class LiquistServiceRelevance(BaseModel):
    """Which of the 3 Liquisto service areas might be relevant and why."""
    service_area: str  # "excess_inventory", "repurposing", "analytics"
    relevance: str     # "hoch", "mittel", "niedrig", "unklar"
    reasoning: str = ""

class SynthesisReport(BaseModel):
    target_company: str
    executive_summary: str = ""
    liquisto_service_relevance: list[LiquistServiceRelevance] = Field(default_factory=list)
    case_assessments: list[LiquistoCaseAssessment] = Field(default_factory=list)
    buyer_market_summary: str = ""
    total_peer_competitors: int = 0
    total_downstream_buyers: int = 0
    total_service_providers: int = 0
    total_cross_industry_buyers: int = 0
    key_risks: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
