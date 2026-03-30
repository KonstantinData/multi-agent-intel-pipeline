"""Compose a DashboardBundle from runtime data.

Single source of truth for both Streamlit UI and PDF report rendering.
All visual elements are derived from real run artifacts — no mock data.
"""
from __future__ import annotations

from typing import Any

from src.models.visualization import (
    ChartSeries,
    ChartSpec,
    DashboardBundle,
    DashboardSection,
    InsightCallout,
    KpiCard,
    TableBlock,
)


def _nv(val: Any, fallback: str = "") -> str:
    s = str(val or "").strip()
    return fallback if s in ("", "n/v", "N/V") else s


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_executive_kpis(
    *,
    pipeline_data: dict[str, Any],
    run_context: dict[str, Any],
    status: str,
) -> DashboardSection:
    company = pipeline_data.get("company_profile", {})
    readiness = pipeline_data.get("research_readiness", {})
    answer_matrix = run_context.get("answer_matrix", {})
    memory = run_context.get("short_term_memory", {})
    contacts_section = pipeline_data.get("contact_intelligence", {})

    answered = sum(
        1 for e in answer_matrix.values()
        if e.get("status") in {"answered", "partially_answered"}
    )
    total_q = len(answer_matrix) or 1
    contacts = contacts_section.get("prioritized_contacts") or contacts_section.get("contacts", [])
    evidence_count = len(memory.get("evidence_packets", []))

    kpis = [
        KpiCard(
            title="Run Status",
            value=_nv(status, "—"),
            color="#16B688" if status == "meeting_ready" else "#c47f00",
            source="run_context.status",
        ),
        KpiCard(
            title="Questions Covered",
            value=f"{answered}/{total_q}",
            subtitle=f"{round(answered / total_q * 100)}%",
            source="answer_matrix",
        ),
        KpiCard(
            title="Readiness Score",
            value=f"{readiness.get('score', 0)}/100",
            trend="up" if readiness.get("usable") else "down",
            source="research_readiness.score",
        ),
        KpiCard(
            title="Contacts Found",
            value=str(len(contacts)),
            source="contact_intelligence",
        ),
        KpiCard(
            title="Evidence Packets",
            value=str(evidence_count),
            source="short_term_memory.evidence_packets",
        ),
        KpiCard(
            title="Revenue",
            value=_nv(company.get("revenue"), "—"),
            source="company_profile.revenue",
        ),
    ]
    return DashboardSection(section_id="executive_kpis", title="Executive KPIs", kpis=kpis)


def _build_coverage_chart(answer_matrix: dict[str, dict[str, Any]]) -> DashboardSection:
    counts: dict[str, int] = {"answered": 0, "partially_answered": 0, "pending": 0, "blocked": 0}
    for entry in answer_matrix.values():
        s = entry.get("status", "pending")
        counts[s] = counts.get(s, 0) + 1

    labels = list(counts.keys())
    values = list(counts.values())
    chart = ChartSpec(
        chart_id="question_coverage",
        chart_type="donut",
        title="Meeting Question Coverage",
        labels=labels,
        series=[ChartSeries(label="coverage", values=values, color="#16B688")],
        source="answer_matrix",
    )
    return DashboardSection(section_id="coverage", title="Question Coverage", charts=[chart])


def _build_opportunity_chart(synthesis: dict[str, Any]) -> DashboardSection:
    service_relevance = synthesis.get("liquisto_service_relevance", [])
    if not service_relevance:
        return DashboardSection(section_id="opportunity", title="Opportunity Assessment")

    labels = [item.get("service_area", "").replace("_", " ").title() for item in service_relevance]
    _score_map = {"high": 3, "medium": 2, "low": 1, "unclear": 0}
    values = [_score_map.get((item.get("relevance") or "").lower(), 0) for item in service_relevance]

    chart = ChartSpec(
        chart_id="opportunity_areas",
        chart_type="bar",
        title="Liquisto Opportunity Areas",
        subtitle="Relevance score by service area",
        labels=labels,
        series=[ChartSeries(label="relevance", values=values, color="#0D95C5")],
        source="synthesis.liquisto_service_relevance",
    )

    callouts = []
    recommended = synthesis.get("recommended_engagement_paths", [])
    if recommended and recommended[0] != "further_validation_required":
        callouts.append(InsightCallout(
            callout_id="primary_path",
            icon="🎯",
            title=f"Primary: {recommended[0].replace('_', ' ').title()}",
            body=_nv(synthesis.get("opportunity_assessment_summary", "")),
            severity="success",
            source="synthesis.recommended_engagement_paths",
        ))

    return DashboardSection(
        section_id="opportunity", title="Opportunity Assessment",
        charts=[chart], callouts=callouts,
    )


def _build_contact_table(contacts_section: dict[str, Any]) -> DashboardSection:
    contacts = contacts_section.get("prioritized_contacts") or contacts_section.get("contacts", [])
    if not contacts:
        return DashboardSection(section_id="contacts", title="Contact Intelligence")

    rows = []
    for c in contacts[:10]:
        rows.append([
            _nv(c.get("name"), "—"),
            _nv(c.get("rolle_titel") or c.get("funktion", ""), "—"),
            _nv(c.get("firma", ""), "—"),
            _nv(c.get("senioritaet", ""), "—"),
        ])

    table = TableBlock(
        table_id="contact_table",
        title="Prioritized Contacts",
        columns=["Name", "Role", "Company", "Seniority"],
        rows=rows,
        source="contact_intelligence",
    )

    kpis = [
        KpiCard(
            title="Contacts Found",
            value=str(len(contacts)),
            source="contact_intelligence.contacts",
        ),
        KpiCard(
            title="Firms Covered",
            value=str(contacts_section.get("firms_searched", 0)),
            source="contact_intelligence.firms_searched",
        ),
        KpiCard(
            title="Coverage Quality",
            value=_nv(contacts_section.get("coverage_quality"), "—"),
            source="contact_intelligence.coverage_quality",
        ),
    ]
    return DashboardSection(
        section_id="contacts", title="Contact Intelligence",
        kpis=kpis, tables=[table],
    )


def _build_actions_section(
    *,
    meeting_actions: list[dict[str, Any]],
    resolution_state: dict[str, Any],
) -> DashboardSection:
    callouts = []
    _icons = {
        "prepare_meeting": "🎯", "collect_missing_evidence": "🔍",
        "ask_user_selection": "📋", "hold": "⏸️",
    }
    for action in meeting_actions[:6]:
        callouts.append(InsightCallout(
            callout_id=f"action_{action.get('action_type', 'hold')}",
            icon=_icons.get(action.get("action_type", ""), "▸"),
            title=_nv(action.get("title", ""), "—"),
            body=_nv(action.get("description", "")),
            severity="success" if action.get("action_type") == "prepare_meeting" else "info",
            source="meeting_actions",
        ))

    # Customer confirmation items
    plan = resolution_state.get("resolution_plan", {})
    unresolved = plan.get("unresolved", {})
    for item in unresolved.get("customer_confirmation_items", [])[:4]:
        callouts.append(InsightCallout(
            callout_id="customer_confirm",
            icon="🔒",
            title=f"Customer confirmation: {str(item)[:80]}",
            body="Requires customer-side validation.",
            severity="warning",
            source="resolution_plan.unresolved.customer_confirmation_items",
        ))

    return DashboardSection(section_id="actions", title="Meeting Actions", callouts=callouts)


def _build_department_timing_chart(budget: dict[str, Any]) -> DashboardSection:
    timings = budget.get("department_timings", {})
    if not timings:
        return DashboardSection(section_id="timings", title="Department Timings")

    labels = list(timings.keys())
    values = [round(v, 1) for v in timings.values()]
    chart = ChartSpec(
        chart_id="dept_timings",
        chart_type="bar",
        title="Department Execution Time (seconds)",
        labels=labels,
        series=[ChartSeries(label="seconds", values=values, color="#004E99")],
        source="budget.department_timings",
    )
    return DashboardSection(section_id="timings", title="Department Timings", charts=[chart])


def _build_evidence_treemap(memory: dict[str, Any]) -> DashboardSection:
    """Treemap of evidence packets grouped by task_key."""
    packets = memory.get("evidence_packets", [])
    if not packets:
        return DashboardSection(section_id="evidence_treemap", title="Evidence Distribution")

    task_counts: dict[str, int] = {}
    for p in packets:
        meta = p.get("metadata", {}) if isinstance(p, dict) else {}
        key = meta.get("task_key", "unknown")
        task_counts[key] = task_counts.get(key, 0) + 1

    if not task_counts:
        return DashboardSection(section_id="evidence_treemap", title="Evidence Distribution")

    labels = [k.replace("_", " ").title() for k in task_counts]
    values = list(task_counts.values())
    chart = ChartSpec(
        chart_id="evidence_treemap",
        chart_type="treemap",
        title="Evidence Packets by Research Task",
        labels=labels,
        series=[ChartSeries(label="packets", values=values, color="#0D95C5")],
        source="short_term_memory.evidence_packets",
    )
    return DashboardSection(section_id="evidence_treemap", title="Evidence Distribution", charts=[chart])


def _build_geo_map(pipeline_data: dict[str, Any]) -> DashboardSection:
    """Map of companies with country data from buyer/peer landscape."""
    market = pipeline_data.get("market_network", {})
    points: list[tuple[str, str]] = []  # (company_name, country)

    for tier_key in ("peer_competitors", "downstream_buyers", "service_providers", "cross_industry_buyers"):
        tier = market.get(tier_key, {})
        if not isinstance(tier, dict):
            continue
        for company in tier.get("companies", []):
            if not isinstance(company, dict):
                continue
            name = str(company.get("name", "")).strip()
            country = str(company.get("country", "")).strip()
            if name and name not in {"n/v", "n/a"} and country and country not in {"n/v", "n/a", ""}:
                points.append((name, country))

    if not points:
        return DashboardSection(section_id="geo_map", title="Geographic Footprint")

    # Aggregate by country
    country_counts: dict[str, int] = {}
    for _, country in points:
        country_counts[country] = country_counts.get(country, 0) + 1

    labels = list(country_counts.keys())
    values = list(country_counts.values())
    chart = ChartSpec(
        chart_id="company_geo",
        chart_type="map",
        title="Buyer & Peer Geographic Distribution",
        subtitle=f"{len(points)} companies across {len(country_counts)} countries",
        labels=labels,
        series=[ChartSeries(label="companies", values=values, color="#004E99")],
        source="market_network.*.companies.country",
    )
    return DashboardSection(section_id="geo_map", title="Geographic Footprint", charts=[chart])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compose_dashboard(
    *,
    run_id: str,
    status: str,
    pipeline_data: dict[str, Any],
    run_context: dict[str, Any],
    budget: dict[str, Any] | None = None,
) -> DashboardBundle:
    """Build a DashboardBundle from real runtime artifacts.

    This is the single composition point — both UI and PDF consume the result.
    """
    company = pipeline_data.get("company_profile", {})
    synthesis = pipeline_data.get("synthesis", {})
    contacts_section = pipeline_data.get("contact_intelligence", {})
    answer_matrix = run_context.get("answer_matrix", {})
    memory = run_context.get("short_term_memory", {})
    resolution_state = run_context.get("resolution_state", {})
    meeting_actions = pipeline_data.get("meeting_actions", []) or memory.get("meeting_actions", [])

    sections = [
        _build_executive_kpis(
            pipeline_data=pipeline_data,
            run_context=run_context,
            status=status,
        ),
        _build_coverage_chart(answer_matrix),
        _build_opportunity_chart(synthesis),
        _build_evidence_treemap(memory),
        _build_contact_table(contacts_section),
        _build_actions_section(
            meeting_actions=meeting_actions,
            resolution_state=resolution_state,
        ),
        _build_geo_map(pipeline_data),
    ]

    if budget:
        sections.append(_build_department_timing_chart(budget))

    return DashboardBundle(
        run_id=run_id,
        company_name=_nv(company.get("company_name"), run_id),
        status=status,
        sections=[s for s in sections if s.kpis or s.charts or s.tables or s.callouts],
        metadata={
            "readiness_score": pipeline_data.get("research_readiness", {}).get("score", 0),
            "evidence_health": pipeline_data.get("quality_review", {}).get("evidence_health", "low"),
        },
    )
