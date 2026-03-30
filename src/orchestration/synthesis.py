"""Cross-domain synthesis and report shaping."""
from __future__ import annotations

import json
from typing import Any

from src.orchestration.envelope import resolve_visual_focus
from src.utils import dedup_safe as _dedup_safe


NEGATIVE_PREFIXES = ("no ", "not ", "none", "kein", "keine", "keinen")


def _positive_signals(items: list[str]) -> list[str]:
    positives: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered.startswith(NEGATIVE_PREFIXES):
            continue
        positives.append(text)
    return positives


def _is_genuine_gap(text: str) -> bool:
    """Filter noise entries from open_gaps: bare field names, internal labels, etc."""
    t = text.strip()
    if not t:
        return False
    if " " not in t:                           # bare field names like "coverage_quality"
        return False
    if "." in t and " " not in t.split(".")[0]:  # dotted paths like "economic_situation.inventory_signals"
        return False
    tl = t.lower()
    if tl.startswith("no supporting source"):
        return False
    if tl.startswith("no inventory signals found"):
        return False
    if tl.startswith("coverage quality not assessed"):
        return False
    if tl.startswith("supporting page excerpts"):
        return False
    if tl.startswith("no external search"):
        return False
    return True


def build_quality_review(memory_snapshot: dict[str, Any]) -> dict[str, Any]:
    approvals = memory_snapshot.get("critic_approvals", {})
    approved_tasks = [task_key for task_key, approved in approvals.items() if approved]
    task_statuses = memory_snapshot.get("task_statuses", {})
    accepted_backlog = [task_key for task_key, status in task_statuses.items() if status == "accepted"]
    sources = memory_snapshot.get("sources", [])
    # LEGACY (RA-10): open_questions consumed here for quality_review gap detection.
    # The authoritative gap model is gap_candidates from typed department outputs.
    open_questions = memory_snapshot.get("open_questions", [])
    external_sources = [
        source for source in sources if isinstance(source, dict) and source.get("source_type") not in {"owned", "first_party"}
    ]
    open_points = memory_snapshot.get("open_points", {})
    unresolved_points = sorted({point for points in open_points.values() for point in points})
    evidence_health = "low"
    # Count tasks that produced usable evidence (accepted or degraded with facts)
    usable_task_count = len(accepted_backlog)
    degraded_with_evidence = [
        task_key for task_key, status in task_statuses.items()
        if status == "degraded"
    ]
    # Degraded tasks still contribute to evidence health if they produced facts
    evidence_packets = memory_snapshot.get("evidence_packets", [])
    high_confidence_packets = [
        p for p in evidence_packets
        if isinstance(p, dict) and p.get("confidence") == "high"
    ]
    usable_task_count += min(len(degraded_with_evidence), 3)  # cap degraded contribution

    if usable_task_count >= 8 and len(external_sources) >= 2 and not unresolved_points:
        evidence_health = "high"
    elif usable_task_count >= 5 and len(external_sources) >= 1:
        evidence_health = "medium"
    elif usable_task_count >= 4 and len(high_confidence_packets) >= 5:
        evidence_health = "medium"  # strong evidence packets compensate for fewer accepted tasks

    raw_gaps = _dedup_safe([*open_questions, *unresolved_points])
    filtered_gaps = [g for g in raw_gaps if _is_genuine_gap(g)]

    return {
        "validated_agents": ["Supervisor", "CompanyDepartment", "MarketDepartment", "BuyerDepartment", "ContactDepartment", *sorted(approved_tasks)],
        "evidence_health": evidence_health,
        "open_gaps": filtered_gaps,
        "recommendations": [
            "Validate likely buyers against CRM before the meeting.",
            "Confirm economic pressure signals with fresher external evidence where possible.",
        ],
        "gap_details": [
            {
                "agent": "Supervisor",
                "field_path": "*",
                "issue_type": "open_question",
                "severity": "moderate",
                "summary": question,
                "recommendation": "Use follow-up mode or customer discovery to close this gap.",
            }
            for question in filtered_gaps[:5]
        ],
    }


_ECO_PRESSURE_KEYWORDS = (
    "restructur", "layoff", "redundanc", "downsiz", "excess stock",
    "write-down", "inventory pressure", "plant clos", "workforce reduc",
    "job cut", "cost cut", "shutdown", "overstock",
)


def _service_relevance(
    industry: dict[str, Any],
    market: dict[str, Any],
    company_profile: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    monetization = _positive_signals(market.get("monetization_paths", []))
    redeployment = _positive_signals(market.get("redeployment_paths", []))
    analytics = _positive_signals(industry.get("analytics_signals", []))
    downstream_buyers = market.get("downstream_buyers", {}).get("companies", [])
    financial = (company_profile or {}).get("financial_deep_dive", {})
    event_intel = (company_profile or {}).get("transaction_event_intelligence", {})
    inventory_positions = _positive_signals(financial.get("inventory_positions", []))
    inventory_risks = _positive_signals(financial.get("inventory_risks", []))
    balance_sheet_signals = _positive_signals(financial.get("balance_sheet_signals", []))
    carve_out_signals = _positive_signals(event_intel.get("carve_out_signals", []))

    # Check economic_situation for restructuring / inventory pressure signals
    eco = (company_profile or {}).get("economic_situation", {})
    eco_text = " ".join(
        [
            " ".join(str(e) for e in eco.get("recent_events", [])),
            str(eco.get("assessment", "")),
            str(eco.get("financial_pressure", "")),
        ]
    ).lower()
    has_eco_pressure = any(kw in eco_text for kw in _ECO_PRESSURE_KEYWORDS)

    scored_items: list[tuple[int, dict[str, str]]] = []

    excess_score = 0
    if monetization and downstream_buyers:
        excess_score += 2
    if has_eco_pressure:
        excess_score += 2
    if inventory_positions:
        excess_score += 3
    if inventory_risks or balance_sheet_signals:
        excess_score += 2
    if carve_out_signals:
        excess_score += 1
    scored_items.append(
        (
            excess_score,
            {
                "service_area": "excess_inventory",
                "relevance": "high" if excess_score >= 5 else "medium" if excess_score >= 2 else "unclear",
                "reasoning": (
                    "Primary-source inventory and balance-sheet signals support an inventory-to-cash angle."
                    if inventory_positions or inventory_risks or balance_sheet_signals
                    else "Economic pressure signals and buyer-path evidence indicate potential excess asset disposition needs."
                    if (monetization and downstream_buyers) or has_eco_pressure
                    else "No validated monetization route with buyer or financial evidence is available yet."
                ),
            },
        )
    )

    repurposing_score = 0
    if redeployment:
        repurposing_score += 2
    if carve_out_signals:
        repurposing_score += 2
    scored_items.append(
        (
            repurposing_score,
            {
                "service_area": "repurposing",
                "relevance": "medium" if repurposing_score >= 2 else "unclear",
                "reasoning": (
                    "Redeployment pathways and portfolio-change signals suggest staged repurposing options."
                    if redeployment or carve_out_signals
                    else "No validated repurposing path is available yet."
                ),
            },
        )
    )

    analytics_score = 0
    if analytics:
        analytics_score += 2
    if balance_sheet_signals:
        analytics_score += 1
    scored_items.append(
        (
            analytics_score,
            {
                "service_area": "analytics",
                "relevance": "medium" if analytics_score >= 2 else "unclear",
                "reasoning": (
                    "Operational visibility, planning, or balance-sheet complexity indicates analytics leverage."
                    if analytics or balance_sheet_signals
                    else "No concrete analytics pain point is available yet."
                ),
            },
        )
    )
    scored_items.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in scored_items]


def build_synthesis_context(
    *,
    company_profile: dict[str, Any],
    industry_analysis: dict[str, Any],
    market_network: dict[str, Any],
    contact_intelligence: dict[str, Any],
    quality_review: dict[str, Any],
    memory_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Prepare a synthesis context payload from department outputs.

    This is pre-processing input for the AG2 SynthesisDepartment, not a
    parallel synthesis author.  When AG2 succeeds, the AG2 output takes
    authority (generation_mode="normal").  When AG2 times out or fails,
    this context is promoted to the final synthesis with
    generation_mode="fallback".  Confidence is derived from input package
    quality — fallback does NOT automatically mean low confidence.
    """
    service_relevance = _service_relevance(industry_analysis, market_network, company_profile)
    if quality_review.get("evidence_health") == "low":
        service_relevance = [
            {
                **item,
                "relevance": "unclear",
                "reasoning": "Evidence quality is too weak for a confident service recommendation.",
            }
            for item in service_relevance
        ]
    positive_service_areas = [item["service_area"] for item in service_relevance if item["relevance"] != "unclear"]
    recommended_paths = positive_service_areas or ["further_validation_required"]
    financial = company_profile.get("financial_deep_dive", {})
    event_intel = company_profile.get("transaction_event_intelligence", {})

    peer_competitors = market_network.get("peer_competitors", {}).get("companies", [])
    downstream_buyers = market_network.get("downstream_buyers", {}).get("companies", [])
    service_providers = market_network.get("service_providers", {}).get("companies", [])
    cross_industry_buyers = market_network.get("cross_industry_buyers", {}).get("companies", [])

    case_assessments = [
        {
            "option": item["service_area"],
            "arguments": [
                {
                    "argument": item["reasoning"],
                    "direction": "pro" if item["relevance"] != "unclear" else "contra",
                    "based_on": "validated_department_packages",
                }
            ],
            "summary": item["reasoning"],
        }
        for item in service_relevance
    ]

    _OPEN_QUESTION_STARTERS = (
        "what ", "how ", "who ", "when ", "where ", "why ", "which ",
        "are there", "is there", "does ", "do ", "can ",
    )

    def _is_genuine_risk(text: str) -> bool:
        t = text.strip()
        if not t:
            return False
        if t.startswith("Point '"):               # critic internal: "Point 'field' is still insufficient..."
            return False
        if " " not in t:                           # bare field names like "buyer_or_path_signal"
            return False
        if t.lower().startswith("no supporting source"):
            return False
        tl = t.lower()
        if any(tl.startswith(s) for s in _OPEN_QUESTION_STARTERS):  # open questions belong in next_steps
            return False
        if tl.startswith("no verified") or tl.startswith("no external search") or tl.startswith("supporting page excerpts"):
            return False
        return True

    _filtered_risks = [r for r in _dedup_safe(quality_review.get("open_gaps", [])) if _is_genuine_risk(r)]
    if _filtered_risks:
        key_risks = _filtered_risks
    elif quality_review.get("evidence_health") in {"high", "medium"}:
        # Good run — name the real gaps that remain
        _fallback_risks: list[str] = []
        if not market_network.get("peer_competitors", {}).get("companies"):
            _fallback_risks.append("Competitive landscape not yet verified — confirm peer positioning before the meeting.")
        if not downstream_buyers:
            _fallback_risks.append("Downstream buyer list is indicative only — validate against CRM.")
        if not market_network.get("cross_industry_buyers", {}).get("companies"):
            _fallback_risks.append("Cross-industry buyer paths not identified — may limit resale scope.")
        if not (contact_intelligence.get("verified_contacts") or contact_intelligence.get("contacts")):
            _fallback_risks.append("No verified decision-maker contacts found — identify procurement lead before outreach.")
        key_risks = _fallback_risks or ["Evidence base is solid; validate contacts and financials directly in the meeting."]
    else:
        key_risks = ["Public web evidence remains incomplete and should be validated in the meeting."]
    # LEGACY (RA-10): next_steps exists for backward compatibility with PDF/UI
    # fallback rendering. The authoritative action model is meeting_actions
    # produced by FinalBriefingComposer. Do not add new consumers of next_steps.
    next_steps = _dedup_safe(memory_snapshot.get("next_actions", [])) or [
        "Validate buyer paths and inventory pressure directly with the prospect."
    ]

    verified_contacts = (
        contact_intelligence.get("target_company_contacts", [])
        or contact_intelligence.get("target_company_prioritized_contacts", [])
        or contact_intelligence.get("contacts", [])
    )
    contact_coverage = contact_intelligence.get("coverage_quality", "n/v")
    top_path = recommended_paths[0]
    inventory_positions = _positive_signals(financial.get("inventory_positions", []))
    inventory_risks = _positive_signals(financial.get("inventory_risks", []))
    key_financials = _positive_signals(financial.get("key_financials", []))
    event_signals = _positive_signals(event_intel.get("strategic_events", []))
    if top_path == "excess_inventory":
        opportunity_summary = (
            "Excess inventory / inventory-to-cash is the leading path because primary financial signals indicate inventory or balance-sheet pressure."
            if inventory_positions or inventory_risks
            else "Excess inventory is the leading path because buyer routes and pressure signals align."
        )
    elif top_path == "repurposing":
        opportunity_summary = "Repurposing is the leading path because portfolio-change signals and redeployment routes align."
    elif top_path == "analytics":
        opportunity_summary = "Analytics is the leading path because operational and planning signals are stronger than liquidation evidence."
    else:
        opportunity_summary = "Current evidence supports further validation before a primary Liquisto path is chosen."

    return {
        "target_company": company_profile.get("company_name", "n/v"),
        "executive_summary": (
            f"{company_profile.get('company_name', 'The target company')} appears to operate in "
            f"{company_profile.get('industry', 'an unclear industry')}. "
            "The briefing is based on approved company, market, buyer, and contact department packages."
        ),
        "contact_coverage": contact_coverage,
        "total_verified_contacts": len(verified_contacts),
        "liquisto_service_relevance": service_relevance,
        "opportunity_assessment_summary": opportunity_summary,
        "recommended_engagement_paths": recommended_paths,
        "case_assessments": case_assessments,
        "buyer_market_summary": market_network.get("downstream_buyers", {}).get("assessment", "n/v"),
        "total_peer_competitors": len(peer_competitors),
        "total_downstream_buyers": len(downstream_buyers),
        "total_service_providers": len(service_providers),
        "total_cross_industry_buyers": len(cross_industry_buyers),
        "key_risks": key_risks + (
            ["Primary financial evidence is still thin — confirm annual-report inventory and debt figures."]
            if not (inventory_positions or key_financials)
            else []
        ),
        "next_steps": next_steps + (
            ["Open the meeting with an inventory-to-cash validation angle grounded in current financial pressure."]
            if top_path == "excess_inventory" and (inventory_positions or inventory_risks)
            else []
        ) + (
            ["Validate the strategic event timeline and decision-maker ownership before outreach."]
            if event_signals
            else []
        ),
        "sources": memory_snapshot.get("sources", []),
        # Confidence derived from input package quality (orthogonal to generation_mode)
        "confidence": quality_review.get("evidence_health", "low"),
    }


def build_report_package(
    *,
    pipeline_data: dict[str, Any],
    department_packages: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    synthesis = pipeline_data.get("synthesis", {})
    company = pipeline_data.get("company_profile", {})
    quality = pipeline_data.get("quality_review", {})
    return {
        "report_status": "ready",
        "report_title": f"Liquisto Briefing - {company.get('company_name', 'n/v')}",
        "executive_summary": synthesis.get("executive_summary", "n/v"),
        "department_visual_focus": {
            name: resolve_visual_focus(package)
            for name, package in department_packages.items()
        },
        "recommended_sections": [
            "Executive summary",
            "Company snapshot",
            "Market and operational signals",
            "Buyer and redeployment paths",
            "Contact intelligence and outreach angles",
            "Liquisto opportunity assessment",
            "Negotiation relevance and next steps",
            "Evidence appendix",
        ],
        "open_gaps": quality.get("open_gaps", []),
    }


def assess_research_readiness(
    *,
    company_profile: dict[str, Any],
    industry_analysis: dict[str, Any],
    market_network: dict[str, Any],
    contact_intelligence: dict[str, Any],
    quality_review: dict[str, Any],
) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []
    # Core sections (80 pts total)
    if company_profile.get("company_name") != "n/v":
        score += 30
    else:
        reasons.append("Company profile is still incomplete.")
    if industry_analysis.get("industry_name") != "n/v":
        score += 20
    else:
        reasons.append("Industry analysis is incomplete.")
    if market_network.get("target_company") != "n/v":
        score += 15
    else:
        reasons.append("Buyer landscape is incomplete.")
    # Contact section (15 pts — optional, but scored)
    has_contacts = bool(
        contact_intelligence.get("contacts")
        or contact_intelligence.get("prioritized_contacts")
    )
    contact_coverage = str(contact_intelligence.get("coverage_quality", "n/v")).lower()
    if has_contacts and contact_coverage not in {"n/v", "low"}:
        score += 15
    elif has_contacts:
        score += 8
        reasons.append("Contact coverage is low — identify procurement lead before outreach.")
    else:
        reasons.append("No verified contacts found — identify decision-maker before outreach.")
    # Evidence quality (20 pts)
    if quality_review.get("evidence_health") == "high":
        score += 20
    elif quality_review.get("evidence_health") == "medium":
        score += 10
        reasons.append("Evidence quality is only moderate and should be strengthened before the meeting.")
    else:
        # Low evidence health — but check if sections have substantive content
        # that the strict task-status counting missed
        has_substantive_company = bool(
            company_profile.get("description") and company_profile["description"] != "n/v"
            and company_profile.get("products_and_services")
        )
        has_substantive_market = bool(
            industry_analysis.get("assessment") and industry_analysis["assessment"] != "n/v"
        )
        if has_substantive_company and has_substantive_market:
            score += 5  # partial credit for substantive content despite low health
            reasons.append("Evidence quality is weak but core sections have substantive content.")
        else:
            reasons.append("Evidence quality is too weak for a confident meeting brief.")
    if quality_review.get("open_gaps"):
        reasons.append("Open critic gaps remain unresolved.")
    # Core sections (company + market) determine usability; contact is optional
    core_score = (30 if company_profile.get("company_name") != "n/v" else 0) + (15 if market_network.get("target_company") != "n/v" else 0)
    usable = score >= 60 and quality_review.get("evidence_health") in {"high", "medium"}
    partial = not usable and core_score >= 30 and quality_review.get("evidence_health") in {"high", "medium", "low"}
    result = {"usable": usable, "score": score, "reasons": reasons}
    if partial:
        result["partial"] = True
    return result
