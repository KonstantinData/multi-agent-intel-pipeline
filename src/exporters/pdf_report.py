"""Generate a polished Liquisto briefing PDF."""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from src.app.use_cases import sanitize_success_unresolved
from src.models.visualization import ChartSpec, DashboardBundle, DashboardSection, InsightCallout, TableBlock

from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PAGE_WIDTH, PAGE_HEIGHT = A4
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGO_PATH = PROJECT_ROOT / "assets" / "image" / "liquisto_logo.png"

BRAND_NAVY  = colors.HexColor("#13485A")
BRAND_MID   = colors.HexColor("#0F5E5F")
BRAND_BLUE  = colors.HexColor("#004E99")
BRAND_SKY   = colors.HexColor("#E6F3F3")
BRAND_TEAL  = colors.HexColor("#0D95C5")
BRAND_GREEN = colors.HexColor("#16B688")
BRAND_AMBER = colors.HexColor("#D97706")
BRAND_RED   = colors.HexColor("#DC2626")
TEXT_PRIMARY = colors.HexColor("#1A2B2D")
TEXT_MUTED   = colors.HexColor("#4A5E60")
BORDER       = colors.HexColor("#B0C4C5")
SURFACE      = colors.HexColor("#F4F8F7")
SURFACE_WARM = colors.HexColor("#FFF8F0")
WHITE        = colors.white


# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_text(value: Any, default: str = "n/v") -> str:
    text = str(value or "").strip()
    return text if text else default


def _safe_join(values: Any, default: str = "n/v") -> str:
    if not values:
        return default
    if isinstance(values, str):
        return values.strip() or default
    if isinstance(values, list):
        rendered = [_safe_text(item, "").strip() for item in values if _safe_text(item, "").strip()]
        return ", ".join(rendered) if rendered else default
    return _safe_text(values, default)


def _top_items(values: Any, limit: int = 5) -> list[str]:
    if not isinstance(values, list):
        return []
    rendered = [_safe_text(item, "").strip() for item in values]
    return [item for item in rendered if item][:limit]


def _relevance_to_score(label: str) -> tuple[int, colors.Color]:
    mapping = {
        "hoch": (85, BRAND_GREEN), "high": (85, BRAND_GREEN),
        "mittel": (60, BRAND_BLUE), "medium": (60, BRAND_BLUE),
        "niedrig": (30, BRAND_AMBER), "low": (30, BRAND_AMBER),
        "unklar": (15, TEXT_MUTED), "unclear": (15, TEXT_MUTED),
    }
    return mapping.get((label or "").strip().lower(), (15, TEXT_MUTED))


def _translation(lang: str) -> dict[str, str]:
    if lang == "en":
        return {
            "report_title": "Liquisto Briefing",
            "report_subtitle": "Target company assessment for commercial preparation",
            "prepared_for": "Prepared for Liquisto",
            "date_label": "Report date",
            "snapshot": "Executive Dashboard",
            "summary": "Executive Summary",
            "service_fit": "Opportunity Thesis",
            "company_profile": "Company Profile",
            "market_section": "Market & Demand Context",
            "buyer_section": "Buyer & Redeployment Landscape",
            "risk_section": "Critical Risks",
            "action_section": "Recommended Next Steps",
            "sources_section": "Evidence Appendix",
            "readiness": "Research Readiness",
            "usable_yes": "USABLE",
            "usable_no": "NOT USABLE",
            "industry": "Industry",
            "website": "Website",
            "products": "Products & Services",
            "material_relevance": "Product & Asset Scope",
            "economic_view": "Economic Situation",
            "market_trend": "Trend",
            "demand_outlook": "Demand Outlook",
            "market_assessment": "Market Assessment",
            "key_trends": "Key Trends",
            "buyer_tier": "Tier",
            "buyer_count": "Count",
            "buyer_assessment": "Assessment",
            "peer_competitors": "Peer Competitors",
            "downstream_buyers": "Downstream Buyers",
            "service_providers": "Service Providers",
            "cross_industry_buyers": "Cross-Industry Buyers",
            "source_title": "Title / URL",
            "source_type": "Type",
            "known_companies": "Known Companies",
            "page_label": "Page",
            "col_country": "Country",
            "col_relevance": "Relevance",
            "rel_high": "High",
            "rel_medium": "Medium",
            "rel_low": "Low",
            "legal_form": "Legal Form",
            "founded": "Founded",
            "headquarters": "Headquarters",
            "hq_short": "HQ",
            "employees": "Employees",
            "revenue": "Revenue",
            "revenue_trend": "Revenue Trend",
            "profitability": "Profitability",
            "financial_pressure": "Financial Pressure",
            "assessment": "Assessment",
            "primary_recommendation": "Primary Recommendation",
            "meeting_focus": "Meeting Focus",
            "opportunity_rank": "Priority",
            "opportunity_path": "Path",
            "opportunity_fit": "Fit",
            "why_now": "Why now",
            "key_triggers": "Key triggers",
            "finance_section": "Financial & Inventory Signals",
            "financial_snapshot": "Financial Snapshot",
            "portfolio_events": "Portfolio and restructuring events",
            "stakeholder_section": "Stakeholder Map",
            "target_contacts": "Target company contacts",
            "buyer_contacts": "Buyer and partner contacts",
            "contact_role": "Role",
            "contact_company": "Company",
            "contact_angle": "Outreach angle",
            "confidence": "Confidence",
            "primary_path": "Primary Path",
            "research_score": "Research Score",
            "top_actions": "Immediate Actions",
            "narrative_overview": "Commercial Angle",
            "financial_signals": "Balance-sheet and inventory signals",
            "products_scope": "Product and asset scope",
            "run_status": "Run Status",
            "top_risks": "Top Risks",
            "next_recommended_step": "Next Step",
            "why_liquisto": "Why Liquisto",
            "leading_path": "Leading path",
            "business_model": "Business model",
            "divisions": "Divisions",
            "financial_position": "Financial position",
            "trigger_events": "Trigger events",
            "validation_section": "Open Questions & Validation Plan",
            "open_questions": "Critical open questions",
            "validation_plan": "Validation plan",
            "contact_relevance": "Relevance",
            "inventory": "Inventory",
            "ebit": "EBIT",
            "net_loss": "Net Loss",
            "write_downs": "Write-downs",
            "net_debt": "Net Debt",
            "working_capital": "Working Capital",
            "open_value": "Open",
            "coverage": "Coverage",
        }
    return {
        "report_title": "Liquisto Bericht",
        "report_subtitle": "Zielkundenanalyse für die kommerzielle Vorbereitung",
        "prepared_for": "Erstellt für Liquisto",
        "date_label": "Berichtsdatum",
        "snapshot": "Management-Dashboard",
        "summary": "Management-Zusammenfassung",
        "service_fit": "Chancen-These",
        "company_profile": "Unternehmensprofil",
        "market_section": "Markt- und Nachfragekontext",
        "buyer_section": "Käufer- und Weiterverwendungslandschaft",
        "risk_section": "Zentrale Risiken",
        "action_section": "Nächste Schritte",
        "sources_section": "Evidenz-Anhang",
        "readiness": "Recherche-Qualität",
        "usable_yes": "VERWENDBAR",
        "usable_no": "NICHT VERWENDBAR",
        "industry": "Branche",
        "website": "Webseite",
        "products": "Produkte & Leistungen",
        "material_relevance": "Produkt- und Bestandsumfang",
        "economic_view": "Wirtschaftliche Lage",
        "market_trend": "Trendrichtung",
        "demand_outlook": "Nachfrageausblick",
        "market_assessment": "Markteinschätzung",
        "key_trends": "Wesentliche Trends",
        "buyer_tier": "Kategorie",
        "buyer_count": "Anz.",
        "buyer_assessment": "Einschätzung",
        "peer_competitors": "Wettbewerber",
        "downstream_buyers": "Abnehmer",
        "service_providers": "Dienstleister",
        "cross_industry_buyers": "Branchenübergreifende Käufer",
        "source_title": "Titel / URL",
        "source_type": "Typ",
        "known_companies": "Bekannte Unternehmen",
        "page_label": "Seite",
        "col_country": "Land",
        "col_relevance": "Relevanz",
        "rel_high": "Hoch",
        "rel_medium": "Mittel",
        "rel_low": "Niedrig",
        "legal_form": "Rechtsform",
        "founded": "Gründung",
        "headquarters": "Hauptsitz",
        "hq_short": "Hauptsitz",
        "employees": "Mitarbeiter",
        "revenue": "Umsatz",
        "revenue_trend": "Umsatztrend",
        "profitability": "Profitabilität",
        "financial_pressure": "Finanzdruck",
        "assessment": "Einschätzung",
        "primary_recommendation": "Primäre Empfehlung",
        "meeting_focus": "Gesprächsfokus",
        "opportunity_rank": "Priorität",
        "opportunity_path": "Pfad",
        "opportunity_fit": "Passung",
        "why_now": "Warum jetzt",
        "key_triggers": "Wichtige Auslöser",
        "finance_section": "Finanz- & Inventarsignale",
        "financial_snapshot": "Finanzüberblick",
        "portfolio_events": "Portfolio- und Restrukturierungsereignisse",
        "stakeholder_section": "Stakeholder-Übersicht",
        "target_contacts": "Kontakte im Zielunternehmen",
        "buyer_contacts": "Käufer- und Partnerkontakte",
        "contact_role": "Rolle",
        "contact_company": "Firma",
        "contact_angle": "Gesprächseinstieg",
        "confidence": "Sicherheit",
        "primary_path": "Hauptpfad",
        "research_score": "Recherchewert",
        "top_actions": "Prioritäre Aktionen",
        "narrative_overview": "Gesprächsansatz",
        "financial_signals": "Bilanz- und Inventarsignale",
        "products_scope": "Produkt- und Bestandsumfang",
        "run_status": "Run-Status",
        "top_risks": "Top-Risiken",
        "next_recommended_step": "Nächster Schritt",
        "why_liquisto": "Warum Liquisto",
        "leading_path": "Führender Pfad",
        "business_model": "Geschäftsmodell",
        "divisions": "Divisionen",
        "financial_position": "Finanzlage",
        "trigger_events": "Auslösende Ereignisse",
        "validation_section": "Offene Fragen & Validierungsplan",
        "open_questions": "Kritische offene Fragen",
        "validation_plan": "Validierungsplan",
        "contact_relevance": "Relevanz",
        "inventory": "Inventar",
        "ebit": "EBIT",
        "net_loss": "Nettoverlust",
        "write_downs": "Wertberichtigungen",
        "net_debt": "Nettoverschuldung",
        "working_capital": "Nettoumlaufvermögen",
        "open_value": "Offen",
        "coverage": "Abdeckung",
    }


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("ReportTitle", parent=sample["Title"],
            fontName="Helvetica-Bold", fontSize=24, leading=28,
            textColor=BRAND_NAVY, alignment=TA_LEFT, spaceAfter=4),
        "subtitle": ParagraphStyle("ReportSubtitle", parent=sample["BodyText"],
            fontName="Helvetica", fontSize=10, leading=13,
            textColor=TEXT_MUTED, alignment=TA_LEFT),
        "cover_meta": ParagraphStyle("CoverMeta", parent=sample["BodyText"],
            fontName="Helvetica", fontSize=9, leading=12,
            textColor=TEXT_MUTED, alignment=TA_LEFT),
        "section": ParagraphStyle("SectionTitle", parent=sample["Heading2"],
            fontName="Helvetica-Bold", fontSize=13, leading=16,
            textColor=BRAND_NAVY, spaceAfter=6, spaceBefore=4),
        "body": ParagraphStyle("Body", parent=sample["BodyText"],
            fontName="Helvetica", fontSize=9.5, leading=13, textColor=TEXT_PRIMARY),
        "small": ParagraphStyle("Small", parent=sample["BodyText"],
            fontName="Helvetica", fontSize=8, leading=10, textColor=TEXT_MUTED),
        "kpi_label": ParagraphStyle("KpiLabel", parent=sample["BodyText"],
            fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=TEXT_MUTED),
        "kpi_value": ParagraphStyle("KpiValue", parent=sample["BodyText"],
            fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=BRAND_NAVY),
        "kpi_value_small": ParagraphStyle("KpiValueSmall", parent=sample["BodyText"],
            fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=BRAND_NAVY),
        "tile_label": ParagraphStyle("TileLabel", parent=sample["BodyText"],
            fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=TEXT_PRIMARY),
        "tile_high": ParagraphStyle("TileHigh", parent=sample["BodyText"],
            fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=BRAND_GREEN),
        "tile_medium": ParagraphStyle("TileMedium", parent=sample["BodyText"],
            fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=BRAND_BLUE),
        "tile_low": ParagraphStyle("TileLow", parent=sample["BodyText"],
            fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=BRAND_AMBER),
        "tile_unclear": ParagraphStyle("TileUnclear", parent=sample["BodyText"],
            fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=TEXT_MUTED),
        "table_header": ParagraphStyle("TableHeader", parent=sample["BodyText"],
            fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=WHITE),
        "table_cell": ParagraphStyle("TableCell", parent=sample["BodyText"],
            fontName="Helvetica", fontSize=8.5, leading=11, textColor=TEXT_PRIMARY),
    }


def _display_confidence(value: str, lang: str) -> str:
    mapping = {
        "en": {"high": "High", "medium": "Medium", "low": "Low"},
        "de": {"high": "Hoch", "medium": "Mittel", "low": "Niedrig"},
    }
    lookup = mapping.get(lang, mapping["en"])
    return lookup.get((value or "").strip().lower(), _safe_text(value, "n/v"))


def _display_run_status(value: str, lang: str) -> str:
    mapping = {
        "en": {
            "meeting_ready": "Meeting ready",
            "blocked_not_meeting_ready": "Blocked",
            "needs_user_selection": "User selection required",
            "running": "Running",
            "failed": "Failed",
        },
        "de": {
            "meeting_ready": "Gesprächsbereit",
            "blocked_not_meeting_ready": "Blockiert",
            "needs_user_selection": "Nutzerauswahl erforderlich",
            "running": "Läuft",
            "failed": "Fehlgeschlagen",
        },
    }
    lookup = mapping.get(lang, mapping["en"])
    return lookup.get((value or "").strip().lower(), _safe_text(value, "n/v"))


def _accent_surface(accent: colors.Color) -> colors.Color:
    if accent == BRAND_AMBER:
        return SURFACE_WARM
    if accent == BRAND_BLUE:
        return colors.HexColor("#F5F9FF")
    if accent == BRAND_TEAL:
        return BRAND_SKY
    if accent == BRAND_RED:
        return colors.HexColor("#FFF4F4")
    return SURFACE


def _logo_flowable(width_mm: float = 42) -> Image | Spacer:
    if not LOGO_PATH.exists():
        return Spacer(1, 1)
    width = width_mm * mm
    height = width * (113 / 500)
    return Image(str(LOGO_PATH), width=width, height=height, mask="auto")


# ── Bundle-driven PDF rendering helpers ────────────────────────────────────────

def _pdf_donut_drawing(chart: ChartSpec) -> Drawing | None:
    """Render a donut/pie chart as a ReportLab Drawing."""
    if not chart.series or not chart.series[0].values:
        return None
    labels = chart.labels
    raw_values = chart.series[0].values
    values = [v if isinstance(v, (int, float)) else 0 for v in raw_values]
    total = sum(values) or 1

    w, h = 170 * mm, 22 * mm
    d = Drawing(w, h)
    _colors_map = {
        "answered": BRAND_BLUE, "partially_answered": BRAND_AMBER,
        "pending": BRAND_SKY, "blocked": BRAND_RED,
    }
    x_cursor = 0.0
    bar_h = 10
    bar_y = 4
    for label, val in zip(labels, values):
        seg_w = (val / total) * (w - 20 * mm)
        color = _colors_map.get(label, BRAND_TEAL)
        d.add(Rect(x_cursor, bar_y, seg_w, bar_h, fillColor=color, strokeColor=None))
        x_cursor += seg_w
    # Legend below
    x_legend = 0.0
    for label, val in zip(labels, values):
        color = _colors_map.get(label, BRAND_TEAL)
        d.add(Rect(x_legend, bar_y + bar_h + 4, 6, 6, fillColor=color, strokeColor=None))
        d.add(String(x_legend + 8, bar_y + bar_h + 4, f"{label}: {val}",
                     fontName="Helvetica", fontSize=7, fillColor=TEXT_MUTED))
        x_legend += 42 * mm
    return d


def _pdf_bar_drawing(chart: ChartSpec) -> Drawing | None:
    """Render a horizontal bar chart as a ReportLab Drawing."""
    if not chart.series or not chart.labels:
        return None
    values = [v if isinstance(v, (int, float)) else 0 for v in chart.series[0].values]
    max_val = max(values) or 1
    n = len(chart.labels)
    bar_h = 10
    gap = 4
    h = n * (bar_h + gap) + 12
    w = 170 * mm
    d = Drawing(w, h)
    bar_max_w = 100 * mm
    palette = [BRAND_BLUE, BRAND_AMBER, BRAND_TEAL, BRAND_MID]
    for i, (label, val) in enumerate(zip(chart.labels, values)):
        y = h - (i + 1) * (bar_h + gap)
        seg_w = (val / max_val) * bar_max_w if max_val else 0
        d.add(Rect(40 * mm, y, seg_w, bar_h, fillColor=palette[i % len(palette)], strokeColor=None, radius=2))
        d.add(String(0, y + 2, label[:25], fontName="Helvetica", fontSize=7, fillColor=TEXT_PRIMARY))
        d.add(String(40 * mm + seg_w + 2, y + 2, str(val), fontName="Helvetica-Bold", fontSize=7, fillColor=TEXT_PRIMARY))
    return d


def _pdf_treemap_drawing(chart: ChartSpec) -> Drawing | None:
    """Render a treemap as proportional rectangles in a single row."""
    if not chart.series or not chart.series[0].values:
        return None
    labels = chart.labels
    raw_values = chart.series[0].values
    values = [v if isinstance(v, (int, float)) else 0 for v in raw_values]
    total = sum(values) or 1

    w, h = 170 * mm, 28 * mm
    d = Drawing(w, h)
    _palette = [BRAND_BLUE, BRAND_AMBER, BRAND_TEAL, BRAND_MID, BRAND_NAVY,
                colors.HexColor("#2A7CB8"), colors.HexColor("#F59E0B")]
    x_cursor = 0.0
    rect_h = 18
    rect_y = 8
    for i, (label, val) in enumerate(zip(labels, values)):
        seg_w = max((val / total) * w, 8)  # min visible width
        color = _palette[i % len(_palette)]
        d.add(Rect(x_cursor, rect_y, seg_w - 1, rect_h, fillColor=color, strokeColor=WHITE, strokeWidth=1, radius=2))
        if seg_w > 20 * mm:
            d.add(String(x_cursor + 3, rect_y + rect_h - 8, f"{label[:18]}",
                         fontName="Helvetica-Bold", fontSize=6.5, fillColor=WHITE))
            d.add(String(x_cursor + 3, rect_y + 2, str(val),
                         fontName="Helvetica", fontSize=6, fillColor=WHITE))
        x_cursor += seg_w
    return d


def _pdf_map_drawing(chart: ChartSpec) -> Drawing | None:
    """Render a geographic distribution as horizontal bars (same as bar)."""
    return _pdf_bar_drawing(chart)


def _pdf_bundle_table(table: TableBlock, styles: dict[str, ParagraphStyle]) -> Table | None:
    """Render a TableBlock as a ReportLab Table."""
    if not table.rows:
        return None
    header = [
        [Paragraph(f"<b>{col}</b>", styles["table_header"]) for col in table.columns]
    ] if table.columns else []
    body = [
        [Paragraph(cell, styles["table_cell"]) for cell in row]
        for row in table.rows[:12]
    ]
    data = header + body
    n_cols = len(table.columns) if table.columns else (len(table.rows[0]) if table.rows else 1)
    col_w = 170 * mm / n_cols
    t = Table(data, colWidths=[col_w] * n_cols, repeatRows=1 if header else 0)
    style_cmds = [
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        style_cmds.append(("BACKGROUND", (0, 0), (-1, 0), BRAND_NAVY))
        style_cmds.append(("TEXTCOLOR", (0, 0), (-1, 0), WHITE))
    for i in range(len(body)):
        bg = WHITE if i % 2 == 0 else SURFACE
        style_cmds.append(("BACKGROUND", (0, i + len(header)), (-1, i + len(header)), bg))
    t.setStyle(TableStyle(style_cmds))
    return t


def _pdf_callout_block(callout: InsightCallout, styles: dict[str, ParagraphStyle]) -> Table:
    """Render an InsightCallout as a colored left-border block."""
    _severity_colors = {"success": BRAND_GREEN, "warning": BRAND_AMBER, "error": BRAND_RED, "info": BRAND_BLUE}
    accent = _severity_colors.get(callout.severity, BRAND_BLUE)
    title_text = f"{callout.icon} <b>{callout.title}</b>" if callout.title else ""
    body_text = callout.body or ""
    content = title_text
    if body_text:
        content += f"<br/>{body_text}" if content else body_text
    t = Table([[Paragraph(content, styles["body"])]], colWidths=[170 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("LINEBEFORE", (0, 0), (0, -1), 3, accent),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _render_bundle_section_to_pdf(
    section: DashboardSection,
    styles: dict[str, ParagraphStyle],
    story: list,
) -> None:
    """Render a full DashboardSection into the PDF story."""
    # KPIs as a KPI bar
    if section.kpis:
        kpi_tuples = [(k.title, k.value) for k in section.kpis[:6] if k.value and k.value != "—"]
        if kpi_tuples:
            story.append(_kpi_bar(kpi_tuples, styles))
            story.append(Spacer(1, 3 * mm))

    # Charts
    _chart_renderers = {
        "donut": _pdf_donut_drawing,
        "bar": _pdf_bar_drawing,
        "stacked_bar": _pdf_bar_drawing,
        "treemap": _pdf_treemap_drawing,
        "map": _pdf_map_drawing,
    }
    for chart in section.charts:
        story.append(Paragraph(f"<b>{chart.title}</b>", styles["body"]))
        if chart.subtitle:
            story.append(Paragraph(chart.subtitle, styles["small"]))
        renderer = _chart_renderers.get(chart.chart_type)
        if renderer:
            drawing = renderer(chart)
            if drawing:
                story.append(drawing)
        story.append(Spacer(1, 3 * mm))

    # Tables
    for table in section.tables:
        story.append(Paragraph(f"<b>{table.title}</b>", styles["body"]))
        t = _pdf_bundle_table(table, styles)
        if t:
            story.append(t)
        story.append(Spacer(1, 3 * mm))

    # Callouts
    for callout in section.callouts:
        story.append(_pdf_callout_block(callout, styles))
        story.append(Spacer(1, 2 * mm))


# ── page chrome ───────────────────────────────────────────────────────────────

def _make_header_footer(page_label: str, report_title: str):  # noqa: ANN001
    def _header_footer(canvas, doc) -> None:  # noqa: ANN001
        canvas.saveState()
        canvas.setFillColor(WHITE)
        canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
        canvas.setFillColor(BRAND_NAVY)
        canvas.rect(0, PAGE_HEIGHT - 3 * mm, PAGE_WIDTH, 3 * mm, fill=1, stroke=0)
        if LOGO_PATH.exists():
            canvas.drawImage(
                str(LOGO_PATH),
                doc.leftMargin,
                PAGE_HEIGHT - 13 * mm,
                width=22 * mm,
                height=(22 * 113 / 500) * mm,
                mask="auto",
                preserveAspectRatio=True,
                anchor="sw",
            )
        canvas.setFillColor(BRAND_NAVY)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(doc.leftMargin + 26 * mm, PAGE_HEIGHT - 9 * mm, report_title)
        canvas.setFillColor(TEXT_MUTED)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(PAGE_WIDTH - doc.rightMargin, PAGE_HEIGHT - 9 * mm, f"{page_label} {doc.page}")
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.6)
        canvas.line(doc.leftMargin, 11 * mm, PAGE_WIDTH - doc.rightMargin, 11 * mm)
        canvas.restoreState()
    return _header_footer


# ── cover ─────────────────────────────────────────────────────────────────────

def _cover_block(company_name: str, subtitle: str, prepared_for: str,
                 date_label: str, styles: dict[str, ParagraphStyle]) -> Table:
    date_str = datetime.now().strftime("%Y-%m-%d")
    accent_strip = Table([["", "", ""]], colWidths=[90 * mm, 50 * mm, 30 * mm], rowHeights=[2.5 * mm])
    accent_strip.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), BRAND_NAVY),
        ("BACKGROUND", (1, 0), (1, 0), BRAND_TEAL),
        ("BACKGROUND", (2, 0), (2, 0), BRAND_AMBER),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    content = [[
        _logo_flowable(46),
        Paragraph(
            f"<b>{company_name}</b><br/>{subtitle}<br/><font size='9' color='#4A5E60'>{prepared_for} · {date_label}: {date_str}</font>",
            styles["title"],
        ),
    ], [accent_strip, ""]]
    table = Table(content, colWidths=[48 * mm, 122 * mm])
    table.setStyle(TableStyle([
        ("SPAN", (0, 1), (1, 1)),
        ("BACKGROUND", (0, 0), (-1, 0), WHITE),
        ("BOX", (0, 0), (-1, 0), 0.8, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, 0), 14),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
        ("LEFTPADDING", (0, 1), (-1, 1), 0),
        ("RIGHTPADDING", (0, 1), (-1, 1), 0),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 0),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


# ── KPI bar ───────────────────────────────────────────────────────────────────

def _kpi_bar(kpis: list[tuple[str, str]], styles: dict[str, ParagraphStyle]) -> Table:
    """Fact card row sized dynamically to available width."""
    cells = []
    count = max(len(kpis), 1)
    outer_width = 170 * mm
    inner_width = (outer_width / count) - 12
    for label, value in kpis:
        val_style = styles["kpi_value_small"] if len(value) > 20 else styles["kpi_value"]
        inner = Table(
            [[Paragraph(label, styles["kpi_label"])], [Paragraph(value, val_style)]],
            colWidths=[inner_width],
        )
        inner.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        cells.append(inner)
    table = Table([cells], colWidths=[outer_width / count] * len(cells))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.7, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return table


# ── readiness bar ─────────────────────────────────────────────────────────────

def _readiness_bar(score: int, usable: bool, evidence_health: str,
                   labels: dict[str, str]) -> Drawing:
    w = 170 * mm
    h = 11 * mm
    d = Drawing(w, h)
    bar_w = 100 * mm
    bar_h = 5
    bar_y = (h - bar_h) / 2
    fill_color = BRAND_GREEN if usable else BRAND_AMBER
    d.add(Rect(0, bar_y, bar_w, bar_h, fillColor=BRAND_SKY, strokeColor=None, radius=2))
    d.add(Rect(0, bar_y, bar_w * (score / 100), bar_h, fillColor=fill_color, strokeColor=None, radius=2))
    d.add(String(bar_w + 4, bar_y, f"{score}/100", fontName="Helvetica-Bold",
                 fontSize=9, fillColor=TEXT_PRIMARY))
    badge_text = f"  {labels['usable_yes']} ✓" if usable else f"  {labels['usable_no']}"
    badge_color = BRAND_GREEN if usable else BRAND_RED
    d.add(String(bar_w + 36, bar_y, badge_text, fontName="Helvetica-Bold",
                 fontSize=8, fillColor=badge_color))
    label_text = f"{labels['readiness']}"
    d.add(String(0, bar_y + bar_h + 2, label_text,
                 fontName="Helvetica", fontSize=7, fillColor=TEXT_MUTED))
    return d


# ── opportunity tiles ─────────────────────────────────────────────────────────

def _opportunity_tiles(items: list[dict[str, Any]], styles: dict[str, ParagraphStyle]) -> Table:
    """3 side-by-side colored tiles for the service areas."""
    _rel_style = {
        "high": styles["tile_high"], "hoch": styles["tile_high"],
        "medium": styles["tile_medium"], "mittel": styles["tile_medium"],
        "low": styles["tile_low"], "niedrig": styles["tile_low"],
    }
    tile_w = 170 / 3 * mm
    cells = []
    for item in items[:3]:
        label = _safe_text(item.get("service_area", "")).replace("_", " ").title()
        relevance = _safe_text(item.get("relevance", "unclear"))
        reasoning = _safe_text(item.get("reasoning", ""))
        if len(reasoning) > 100:
            reasoning = reasoning[:97] + "…"
        _, bar_color = _relevance_to_score(relevance)
        rel_style = _rel_style.get(relevance.lower(), styles["tile_unclear"])
        tile = Table(
            [
                [""],  # colored header band
                [Paragraph(f"<b>{label}</b>", styles["tile_label"])],
                [Paragraph(relevance.title(), rel_style)],
                [Paragraph(reasoning, styles["small"])],
            ],
            colWidths=[tile_w - 6],
            rowHeights=[4, None, None, None],
        )
        tile.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), bar_color),
            ("BACKGROUND", (0, 1), (-1, -1), WHITE),
            ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (0, 0), 0),
            ("BOTTOMPADDING", (0, 0), (0, 0), 0),
            ("TOPPADDING", (0, 1), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ]))
        cells.append(tile)

    while len(cells) < 3:
        cells.append(Spacer(1, 1))

    table = Table([cells], colWidths=[tile_w] * 3)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


# ── info table (filters n/v rows) ─────────────────────────────────────────────

def _info_table(rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle],
                widths: tuple[float, float]) -> Table | None:
    data = [
        [Paragraph(f"<b>{label}</b>", styles["table_cell"]),
         Paragraph(value, styles["table_cell"])]
        for label, value in rows
        if value and value.strip() not in {"n/v", "n/a", ""}
    ]
    if not data:
        return None
    table = Table(data, colWidths=list(widths))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _truncate(text: Any, limit: int = 180, default: str = "n/v") -> str:
    rendered = _safe_text(text, default)
    if rendered == default:
        return rendered
    if len(rendered) <= limit:
        return rendered
    return f"{rendered[: limit - 1].rstrip()}…"


def _dedupe_items(values: list[str], limit: int = 5) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        rendered = _safe_text(value, "").strip()
        if not rendered:
            continue
        key = rendered.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(rendered)
        if len(result) >= limit:
            break
    return result


def _compact_event(value: Any, limit: int = 135) -> str:
    rendered = _safe_text(value, "")
    if not rendered:
        return ""
    parts = [part.strip() for part in rendered.split("|") if part.strip()]
    if len(parts) >= 4:
        summary = " | ".join(parts[:4])
        return _truncate(summary, limit, "")
    return _truncate(rendered, limit, "")


def _service_area_label(value: str, lang: str) -> str:
    mapping = {
        "excess_inventory": "Excess Inventory" if lang == "en" else "Bestandsabbau",
        "repurposing": "Repurposing" if lang == "en" else "Weiterverwendung",
        "analytics": "Analytics" if lang == "en" else "Analytik",
        "further_validation_required": "Further validation required" if lang == "en" else "Weitere Validierung nötig",
    }
    key = (value or "").strip().lower()
    if key in mapping:
        return mapping[key]
    return _safe_text(value).replace("_", " ").title()


def _section_band(title: str, subtitle: str, styles: dict[str, ParagraphStyle],
                  *, accent: colors.Color = BRAND_BLUE) -> Table:
    content = [
        [Paragraph(f"<b>{title}</b>", styles["section"])],
        [Paragraph(subtitle, styles["small"])],
    ]
    table = Table(content, colWidths=[170 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _accent_surface(accent)),
        ("LINEBEFORE", (0, 0), (0, -1), 4, accent),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def _summary_callout(title: str, body: str, styles: dict[str, ParagraphStyle],
                     *, accent: colors.Color = BRAND_GREEN,
                     background: colors.Color = WHITE) -> Table:
    table = Table(
        [[Paragraph(f"<b>{title}</b>", styles["body"])],
         [Paragraph(body, styles["body"])]],
        colWidths=[170 * mm],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background if background != WHITE else _accent_surface(accent)),
        ("LINEBEFORE", (0, 0), (0, -1), 4, accent),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _kpi_grid(kpis: list[tuple[str, str]], styles: dict[str, ParagraphStyle],
              *, columns: int = 3) -> Table:
    usable = [(label, value) for label, value in kpis if value and value != "n/v"]
    if not usable:
        usable = [("n/v", "n/v")]
    rows: list[list[Any]] = []
    row: list[Any] = []
    cell_width = (170 * mm) / columns
    for index, (label, value) in enumerate(usable):
        val_style = styles["kpi_value_small"] if len(value) > 18 else styles["kpi_value"]
        card = Table(
            [[Paragraph(label, styles["kpi_label"])], [Paragraph(value, val_style)]],
            colWidths=[cell_width - 16],
        )
        card.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        row.append(card)
        if (index + 1) % columns == 0:
            rows.append(row)
            row = []
    if row:
        while len(row) < columns:
            row.append(Spacer(1, 1))
        rows.append(row)
    table = Table(rows, colWidths=[cell_width] * columns)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.7, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return table


def _extract_revenue_display(profile: dict[str, Any], industry: dict[str, Any]) -> str:
    current = _safe_text(profile.get("revenue"))
    econ = profile.get("economic_situation", {}) or {}
    deep_dive = profile.get("financial_deep_dive", {}) or {}
    recent_events = [str(item) for item in (econ.get("recent_events") or [])]
    searchable = " ".join(
        [
            _safe_text(industry.get("demand_outlook"), ""),
            _safe_text(econ.get("assessment"), ""),
            _safe_text(deep_dive.get("assessment"), ""),
            *recent_events,
            *[str(item) for item in (deep_dive.get("key_financials") or [])],
        ]
    )
    matches = re.findall(r"(?:sales|revenue)[^€]{0,40}(€\s?\d+(?:\.\d+)?\s?(?:billion|million|bn|m))", searchable, flags=re.IGNORECASE)
    normalized_matches = _dedupe_items(matches, limit=3)
    current_flagged = any(
        current != "n/v"
        and current.lower() in event.lower()
        and any(keyword in event.lower() for keyword in ("impact", "deconsolidation", "product line"))
        for event in recent_events
    )
    if current_flagged:
        for candidate in normalized_matches:
            if candidate.lower() != current.lower():
                return candidate
    if current != "n/v":
        return current
    return normalized_matches[0] if normalized_matches else "n/v"


def _run_status_from_pipeline(pipeline_data: dict[str, Any]) -> str:
    bundle = pipeline_data.get("dashboard_bundle") or {}
    if isinstance(bundle, dict):
        status = _safe_text(bundle.get("status"), "")
        if status:
            return status
    readiness = pipeline_data.get("meeting_readiness_assessment") or {}
    if isinstance(readiness, dict):
        status = _safe_text(readiness.get("run_status"), "")
        if status and status != "running":
            return status
    final_briefing = pipeline_data.get("final_briefing") or {}
    if isinstance(final_briefing, dict):
        status = _safe_text(final_briefing.get("status"), "")
        if status and status != "running":
            return status
    return "meeting_ready"


def _sentence_candidates(texts: list[str]) -> list[str]:
    combined = " ".join(texts)
    chunks = re.split(r"(?<=[.!?])\s+|\n+", combined)
    return [chunk.strip(" -") for chunk in chunks if chunk.strip()]


def _first_matching_sentence(texts: list[str], patterns: list[str], default: str = "Open") -> str:
    sentences = _sentence_candidates(texts)
    for sentence in sentences:
        lower = sentence.lower()
        if any(re.search(pattern, lower) for pattern in patterns):
            return _truncate(sentence, 86, default)
    return default


def _extract_financial_cards(profile: dict[str, Any], industry: dict[str, Any], synthesis: dict[str, Any],
                             labels: dict[str, str]) -> list[tuple[str, str]]:
    econ = profile.get("economic_situation", {}) or {}
    deep_dive = profile.get("financial_deep_dive", {}) or {}
    texts = [
        _safe_text(industry.get("demand_outlook"), ""),
        _safe_text(industry.get("assessment"), ""),
        _safe_text(econ.get("revenue_trend"), ""),
        _safe_text(econ.get("profitability"), ""),
        _safe_text(econ.get("assessment"), ""),
        _safe_text(deep_dive.get("assessment"), ""),
        _safe_text(synthesis.get("executive_summary"), ""),
        *[str(item) for item in (econ.get("recent_events") or [])],
        *[str(item) for item in (deep_dive.get("key_financials") or [])],
        *[str(item) for item in (deep_dive.get("balance_sheet_signals") or [])],
        *[str(item) for item in (deep_dive.get("inventory_positions") or [])],
        *[str(item) for item in (deep_dive.get("inventory_risks") or [])],
    ]
    open_value = labels.get("open_value", "Open")
    return [
        (labels["revenue_trend"], _truncate(econ.get("revenue_trend"), 72, open_value)),
        (labels["ebit"], _first_matching_sentence(texts, [r"\bebit\b"], open_value)),
        (labels["net_loss"], _first_matching_sentence(texts, [r"net loss", r"jahresfehlbetrag"], open_value)),
        (labels["write_downs"], _first_matching_sentence(texts, [r"write[- ]down", r"impair", r"wertberichtigung"], open_value)),
        (labels["net_debt"], _first_matching_sentence(texts, [r"net debt", r"leverage", r"nettoverschuld"], open_value)),
        (labels["working_capital"], _first_matching_sentence(texts, [r"working capital", r"net working capital"], open_value)),
        (labels["inventory"], _first_matching_sentence(texts, [r"\binventor", r"vorr"], open_value)),
    ]


def _extract_divisions(profile: dict[str, Any], contacts_section: dict[str, Any]) -> list[str]:
    texts = [
        _safe_text(profile.get("description"), ""),
        _safe_text(contacts_section.get("target_company_summary"), ""),
    ]
    for contact in (contacts_section.get("target_company_contacts") or [])[:8]:
        if isinstance(contact, dict):
            texts.extend([
                _safe_text(contact.get("rolle_titel"), ""),
                _safe_text(contact.get("funktion"), ""),
            ])
    divisions: list[str] = []
    for text in texts:
        if not text:
            continue
        for match in re.findall(r"([A-Z][A-Za-z/&,\- ]+?) division", text):
            divisions.extend([item.strip() for item in re.split(r",| and ", match) if item.strip()])
        for match in re.findall(r"for ([A-Z][A-Za-z/&,\- ]+?) divisions", text):
            divisions.extend([item.strip() for item in re.split(r",| and ", match) if item.strip()])
    cleaned = _dedupe_items(divisions, limit=4)
    return cleaned or _top_items(profile.get("products_and_services"), 3)


def _validation_pairs(risks: list[str], actions: list[str], labels: dict[str, str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for index, risk in enumerate(risks[:4]):
        action = (
            actions[index]
            if index < len(actions)
            else actions[-1]
            if actions
            else ("Validate directly in the meeting." if labels.get("date_label") == "Report date" else "Direkt im Gespräch validieren.")
        )
        pairs.append((_truncate(risk, 88), _truncate(action, 100)))
    return pairs


def _primary_recommendation(synthesis: dict[str, Any], lang: str) -> tuple[str, str, str]:
    service_relevance = synthesis.get("liquisto_service_relevance", []) or []
    recommended = synthesis.get("recommended_engagement_paths", []) or []
    primary_key = recommended[0] if recommended else ""
    primary_item = next(
        (item for item in service_relevance if _safe_text(item.get("service_area"), "").lower() == primary_key.lower()),
        service_relevance[0] if service_relevance else {},
    )
    label = _service_area_label(primary_key or _safe_text(primary_item.get("service_area"), ""), lang)
    relevance = _safe_text(primary_item.get("relevance"), synthesis.get("confidence") or "medium")
    reasoning = _truncate(
        primary_item.get("reasoning")
        or synthesis.get("opportunity_assessment_summary")
        or synthesis.get("executive_summary"),
        220,
    )
    return label, relevance, reasoning


def _opportunity_table(recommended_paths: list[str], service_relevance: list[dict[str, Any]],
                       labels: dict[str, str], styles: dict[str, ParagraphStyle], lang: str) -> Table:
    items_by_key = {
        _safe_text(item.get("service_area"), "").lower(): item
        for item in service_relevance
        if isinstance(item, dict)
    }
    ranked_paths = recommended_paths or list(items_by_key)
    data: list[list[Any]] = [[
        Paragraph(f"<b>{labels['opportunity_rank']}</b>", styles["table_header"]),
        Paragraph(f"<b>{labels['opportunity_path']}</b>", styles["table_header"]),
        Paragraph(f"<b>{labels['opportunity_fit']}</b>", styles["table_header"]),
        Paragraph(f"<b>{labels['why_now']}</b>", styles["table_header"]),
    ]]
    for rank, path in enumerate(ranked_paths[:3], start=1):
        item = items_by_key.get(path.lower(), {})
        data.append([
            Paragraph(str(rank), styles["table_cell"]),
            Paragraph(_service_area_label(path, lang), styles["table_cell"]),
            Paragraph(_safe_text(item.get("relevance"), "n/v").title(), styles["table_cell"]),
            Paragraph(_truncate(item.get("reasoning") or item.get("summary"), 180), styles["table_cell"]),
        ])
    if len(data) == 1:
        data.append([
            Paragraph("1", styles["table_cell"]),
            Paragraph("n/v", styles["table_cell"]),
            Paragraph("n/v", styles["table_cell"]),
            Paragraph("n/v", styles["table_cell"]),
        ])
    table = Table(data, colWidths=[14 * mm, 38 * mm, 24 * mm, 94 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SURFACE]),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _contact_table(contacts: list[dict[str, Any]], labels: dict[str, str],
                   styles: dict[str, ParagraphStyle]) -> Table:
    data = [[
        Paragraph("<b>Name</b>", styles["table_header"]),
        Paragraph(f"<b>{labels['contact_role']}</b>", styles["table_header"]),
        Paragraph(f"<b>{labels['contact_relevance']}</b>", styles["table_header"]),
        Paragraph(f"<b>{labels['contact_angle']}</b>", styles["table_header"]),
    ]]
    for contact in contacts:
        company = _truncate(contact.get("firma"), 30, "")
        name = _safe_text(contact.get("name"), "—")
        if company:
            name = f"{name}<br/><font size='7' color='#4A5E60'>{company}</font>"
        relevance = _truncate(
            contact.get("relevance_reason") or contact.get("confidence"),
            88,
            "—",
        )
        angle = _truncate(
            contact.get("suggested_outreach_angle") or contact.get("relevance_reason"),
            120,
            "—",
        )
        data.append([
            Paragraph(name, styles["table_cell"]),
            Paragraph(_truncate(contact.get("rolle_titel") or contact.get("funktion"), 72, "—"), styles["table_cell"]),
            Paragraph(relevance, styles["table_cell"]),
            Paragraph(angle, styles["table_cell"]),
        ])
    if len(data) == 1:
        data.append([
            Paragraph("—", styles["table_cell"]),
            Paragraph("—", styles["table_cell"]),
            Paragraph("—", styles["table_cell"]),
            Paragraph("—", styles["table_cell"]),
        ])
    table = Table(data, colWidths=[34 * mm, 40 * mm, 44 * mm, 52 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SURFACE]),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


# ── two-column bullets ────────────────────────────────────────────────────────

def _bullet_col(title: str, items: list[str], styles: dict[str, ParagraphStyle],
                col_w: float, accent: colors.Color = BRAND_BLUE) -> Table:
    body = "<br/>".join(f"- {item}" for item in (items or ["n/v"])[:6])
    box = Table(
        [[Paragraph(f"<b>{title}</b>", styles["body"])],
         [Paragraph(body, styles["body"])]],
        colWidths=[col_w],
    )
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("LINEBEFORE", (0, 0), (0, -1), 4, accent),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return box


# ── buyer landscape ───────────────────────────────────────────────────────────

def _relevance_color(label: str) -> colors.Color:
    l = (label or "").strip().lower()
    if l in {"high", "hoch"}:    return BRAND_GREEN
    if l in {"medium", "mittel"}: return BRAND_BLUE
    if l in {"low", "niedrig"}:   return BRAND_AMBER
    return TEXT_MUTED


def _buyer_landscape(market: dict[str, Any], labels: dict[str, str],
                     styles: dict[str, ParagraphStyle]) -> list[Any]:
    """
    One table per tier (if companies exist), each showing individual company rows.
    Tier header (navy) → one row per company: Name | Country | Relevance
    """
    tiers = [
        (labels["peer_competitors"],      market.get("peer_competitors", {})),
        (labels["downstream_buyers"],     market.get("downstream_buyers", {})),
        (labels["service_providers"],     market.get("service_providers", {})),
        (labels["cross_industry_buyers"], market.get("cross_industry_buyers", {})),
    ]

    col_name    = 100 * mm
    col_country =  38 * mm
    col_rel     =  32 * mm

    _rel_label = {
        "high":    labels["rel_high"],   "hoch":    labels["rel_high"],
        "medium":  labels["rel_medium"], "mittel":  labels["rel_medium"],
        "low":     labels["rel_low"],    "niedrig": labels["rel_low"],
    }

    def _fmt_relevance(raw: str) -> str:
        r = (raw or "").strip()
        return _rel_label.get(r.lower(), r) if r not in {"n/v", ""} else "—"

    flowables: list[Any] = []

    for tier_label, payload in tiers:
        companies = (payload.get("companies", []) if isinstance(payload, dict) else [])[:2]
        if not companies:
            continue

        # Tier header row
        data: list[list[Any]] = [[
            Paragraph(f"<b>{tier_label}</b>",              styles["table_header"]),
            Paragraph(f"<b>{labels['col_country']}</b>",   styles["table_header"]),
            Paragraph(f"<b>{labels['col_relevance']}</b>", styles["table_header"]),
        ]]

        for i, c in enumerate(companies):
            name    = _truncate(c.get("company_name") or c.get("name") if isinstance(c, dict) else str(c), 42)
            country = _safe_text(c.get("country", "") if isinstance(c, dict) else "")
            rel_raw = _safe_text(c.get("relevance", "") if isinstance(c, dict) else "")
            rel_txt = _truncate(_fmt_relevance(rel_raw), 44, "—")
            rel_color = _relevance_color(rel_raw)

            bg = WHITE if i % 2 == 0 else SURFACE
            data.append([
                Paragraph(name, styles["table_cell"]),
                Paragraph(country if country not in {"n/v", ""} else "—", styles["table_cell"]),
                Paragraph(f'<font color="#{int(rel_color.red*255):02x}{int(rel_color.green*255):02x}{int(rel_color.blue*255):02x}"><b>{rel_txt}</b></font>',
                          styles["table_cell"]),
            ])

        table = Table(data, colWidths=[col_name, col_country, col_rel], repeatRows=1)

        # Build per-row background commands
        style_cmds = [
            ("BACKGROUND",   (0, 0), (-1, 0),  BRAND_NAVY),
            ("TEXTCOLOR",    (0, 0), (-1, 0),  WHITE),
            ("BOX",          (0, 0), (-1, -1), 0.6, BORDER),
            ("INNERGRID",    (0, 0), (-1, -1), 0.5, BORDER),
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING",   (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ]
        for i in range(len(companies)):
            bg = WHITE if i % 2 == 0 else SURFACE
            style_cmds.append(("BACKGROUND", (0, i + 1), (-1, i + 1), bg))

        table.setStyle(TableStyle(style_cmds))
        flowables.append(table)
        flowables.append(Spacer(1, 3 * mm))

    return flowables if flowables else [Paragraph("n/v", styles["body"])]


# ── risk table ────────────────────────────────────────────────────────────────

def _risk_table(risks: list[str], styles: dict[str, ParagraphStyle]) -> Table:
    data = [[Paragraph(f"▸  {risk}", styles["body"])] for risk in risks[:5]]
    if not data:
        data = [[Paragraph("n/v", styles["body"])]]
    table = Table(data, colWidths=[170 * mm])
    table.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, SURFACE_WARM]),
        ("LINEBEFORE", (0, 0), (0, -1), 3, BRAND_RED),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


# ── next steps table ──────────────────────────────────────────────────────────

def _steps_table(steps: list[str], styles: dict[str, ParagraphStyle]) -> Table:
    data = [[Paragraph(f"{i + 1}.  {step}", styles["body"])]
            for i, step in enumerate(steps[:5])]
    if not data:
        data = [[Paragraph("n/v", styles["body"])]]
    table = Table(data, colWidths=[170 * mm])
    table.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, SURFACE]),
        ("LINEBEFORE", (0, 0), (0, -1), 3, BRAND_GREEN),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


# ── evidence table ────────────────────────────────────────────────────────────

def _source_table(sources: list[dict[str, Any]], labels: dict[str, str],
                  styles: dict[str, ParagraphStyle]) -> Table:
    data = [[
        Paragraph(f"<b>{labels['source_title']}</b>", styles["table_header"]),
        Paragraph(f"<b>{labels['source_type']}</b>",  styles["table_header"]),
    ]]
    if not sources:
        data.append([Paragraph("n/v", styles["table_cell"]),
                     Paragraph("—", styles["table_cell"])])
    else:
        for item in sources[:14]:
            title = _safe_text(item.get("title") or item.get("publisher") or item.get("url"))
            url   = _safe_text(item.get("url", ""))
            stype = _safe_text(item.get("source_type") or "source")
            url_display = url[:90] + ("…" if len(url) > 90 else "") if url != "n/v" else ""
            cell_text = title
            if url_display and url_display != title:
                cell_text = f"{title}<br/><font size='7' color='#1f5aa6'>{url_display}</font>"
            data.append([
                Paragraph(cell_text, styles["table_cell"]),
                Paragraph(stype, styles["table_cell"]),
            ])
    table = Table(data, colWidths=[138 * mm, 32 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SURFACE]),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


# ── main entry ────────────────────────────────────────────────────────────────

_LANG_NAMES = {"en": "English", "de": "German", "fr": "French", "es": "Spanish"}


def _translate_content(pipeline_data: dict[str, Any], target_lang: str) -> dict[str, Any]:
    """Translate all narrative text fields to *target_lang* in one OpenAI call.

    Returns a deep-copied, translated version of pipeline_data.
    Falls back silently to the original on any error.
    """
    try:
        from openai import OpenAI  # local import — only needed here
        from src.config.settings import get_openai_api_key

        api_key = get_openai_api_key()
        if not api_key:
            return pipeline_data

        data = copy.deepcopy(pipeline_data)
        syn  = data.get("synthesis", {}) or {}
        ind  = data.get("industry_analysis", {}) or {}
        prof = data.get("company_profile", {}) or {}
        mkt  = data.get("market_network", {}) or {}

        # ── collect every translatable string into a flat dict ──────────────
        batch: dict[str, str] = {}

        def _add(key: str, text: Any) -> None:
            s = str(text or "").strip()
            if s and s not in {"n/v", "n/a"}:
                batch[key] = s

        # Synthesis
        _add("syn_exec",   syn.get("executive_summary", ""))
        _add("syn_opp",    syn.get("opportunity_assessment_summary", ""))
        _add("syn_buyers", syn.get("buyer_market_summary", ""))
        for i, t in enumerate(syn.get("key_risks", []) or []):
            _add(f"risk_{i}", t)
        for i, t in enumerate(syn.get("next_steps", []) or []):
            _add(f"step_{i}", t)

        # Industry
        _add("ind_assessment", ind.get("assessment", ""))
        _add("ind_demand",     ind.get("demand_outlook", ""))
        _add("ind_trend",      ind.get("trend_direction", ""))
        for i, t in enumerate(ind.get("key_trends", []) or []):
            _add(f"ind_ktrend_{i}", t)

        # Company profile
        _add("prof_desc", prof.get("description", ""))
        _add("prof_revenue", prof.get("revenue", ""))
        _add("prof_employees", prof.get("employees", ""))
        for i, t in enumerate(prof.get("products_and_services", []) or []):
            _add(f"prod_{i}", t)
        for i, t in enumerate(prof.get("product_asset_scope", []) or []):
            _add(f"scope_{i}", t)
        econ = prof.get("economic_situation", {}) or {}
        _add("econ_revenue_trend", econ.get("revenue_trend", ""))
        _add("econ_profitability", econ.get("profitability", ""))
        _add("econ_fin_pressure", econ.get("financial_pressure", ""))
        _add("econ_assessment", econ.get("assessment", ""))
        for i, t in enumerate(econ.get("recent_events", []) or []):
            _add(f"econ_event_{i}", t)
        for i, t in enumerate(econ.get("inventory_signals", []) or []):
            _add(f"econ_inventory_{i}", t)
        deep = prof.get("financial_deep_dive", {}) or {}
        _add("deep_assessment", deep.get("assessment", ""))
        for i, t in enumerate(deep.get("key_financials", []) or []):
            _add(f"deep_fin_{i}", t)
        for i, t in enumerate(deep.get("inventory_positions", []) or []):
            _add(f"deep_inventory_{i}", t)
        for i, t in enumerate(deep.get("inventory_risks", []) or []):
            _add(f"deep_risk_{i}", t)
        for i, t in enumerate(deep.get("balance_sheet_signals", []) or []):
            _add(f"deep_balance_{i}", t)
        event_intel = prof.get("transaction_event_intelligence", {}) or {}
        _add("event_assessment", event_intel.get("assessment", ""))
        for i, t in enumerate(event_intel.get("strategic_events", []) or []):
            _add(f"event_strategic_{i}", t)
        for i, t in enumerate(event_intel.get("carve_out_signals", []) or []):
            _add(f"event_carve_{i}", t)
        for i, t in enumerate(event_intel.get("regulatory_signals", []) or []):
            _add(f"event_reg_{i}", t)

        # Market network assessments
        for tier_key in ("peer_competitors", "downstream_buyers",
                         "service_providers", "cross_industry_buyers"):
            tier = mkt.get(tier_key, {}) or {}
            _add(f"mkt_{tier_key}", (tier.get("assessment", "") if isinstance(tier, dict) else ""))
            if isinstance(tier, dict):
                for i, company in enumerate(tier.get("companies", []) or []):
                    if isinstance(company, dict):
                        _add(f"{tier_key}_rel_{i}", company.get("relevance", ""))

        contacts = data.get("contact_intelligence", {}) or {}
        _add("contacts_narrative", contacts.get("narrative_summary", ""))
        _add("contacts_target_summary", contacts.get("target_company_summary", ""))
        for prefix, records in (
            ("buyer_contact", contacts.get("prioritized_contacts", []) or contacts.get("contacts", [])),
            ("target_contact", contacts.get("target_company_prioritized_contacts", []) or contacts.get("target_company_contacts", [])),
        ):
            for i, contact in enumerate(records[:8]):
                if isinstance(contact, dict):
                    _add(f"{prefix}_role_{i}", contact.get("rolle_titel", ""))
                    _add(f"{prefix}_function_{i}", contact.get("funktion", ""))
                    _add(f"{prefix}_relevance_{i}", contact.get("relevance_reason", ""))
                    _add(f"{prefix}_angle_{i}", contact.get("suggested_outreach_angle", ""))

        for i, action in enumerate(data.get("meeting_actions", []) or []):
            if isinstance(action, dict):
                _add(f"meeting_action_title_{i}", action.get("title", ""))
                _add(f"meeting_action_desc_{i}", action.get("description", ""))

        if not batch:
            return data

        # ── single LLM call ─────────────────────────────────────────────────
        from src.config.settings import DEFAULT_MODEL
        lang_name = _LANG_NAMES.get(target_lang, target_lang)
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a professional business translator. "
                        f"Translate all JSON values to {lang_name}. "
                        f"The input may contain mixed-language content. "
                        f"Rules: keep company names, brand names, proper nouns, "
                        f"abbreviations, URLs, and numeric values unchanged. "
                        f"Return ONLY a valid JSON object with the exact same keys."
                    ),
                },
                {"role": "user", "content": json.dumps(batch, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        translated: dict[str, str] = json.loads(resp.choices[0].message.content)

        def _get(key: str, original: Any) -> Any:
            return translated.get(key, original)

        # ── write translated values back ─────────────────────────────────────
        syn["executive_summary"]              = _get("syn_exec",   syn.get("executive_summary", ""))
        syn["opportunity_assessment_summary"] = _get("syn_opp",    syn.get("opportunity_assessment_summary", ""))
        syn["buyer_market_summary"]           = _get("syn_buyers", syn.get("buyer_market_summary", ""))

        syn["key_risks"]  = [_get(f"risk_{i}", t) for i, t in enumerate(syn.get("key_risks",  []) or [])]
        syn["next_steps"] = [_get(f"step_{i}", t) for i, t in enumerate(syn.get("next_steps", []) or [])]

        ind["assessment"]   = _get("ind_assessment", ind.get("assessment", ""))
        ind["demand_outlook"] = _get("ind_demand",   ind.get("demand_outlook", ""))
        ind["trend_direction"] = _get("ind_trend",   ind.get("trend_direction", ""))
        ind["key_trends"] = [_get(f"ind_ktrend_{i}", t) for i, t in enumerate(ind.get("key_trends", []) or [])]

        prof["description"] = _get("prof_desc", prof.get("description", ""))
        prof["revenue"] = _get("prof_revenue", prof.get("revenue", ""))
        prof["employees"] = _get("prof_employees", prof.get("employees", ""))
        prof["products_and_services"] = [_get(f"prod_{i}", t)  for i, t in enumerate(prof.get("products_and_services", []) or [])]
        prof["product_asset_scope"]   = [_get(f"scope_{i}", t) for i, t in enumerate(prof.get("product_asset_scope",   []) or [])]
        econ["revenue_trend"] = _get("econ_revenue_trend", econ.get("revenue_trend", ""))
        econ["profitability"] = _get("econ_profitability", econ.get("profitability", ""))
        econ["financial_pressure"] = _get("econ_fin_pressure", econ.get("financial_pressure", ""))
        econ["assessment"] = _get("econ_assessment", econ.get("assessment", ""))
        econ["recent_events"] = [_get(f"econ_event_{i}", t) for i, t in enumerate(econ.get("recent_events", []) or [])]
        econ["inventory_signals"] = [_get(f"econ_inventory_{i}", t) for i, t in enumerate(econ.get("inventory_signals", []) or [])]
        deep["assessment"] = _get("deep_assessment", deep.get("assessment", ""))
        deep["key_financials"] = [_get(f"deep_fin_{i}", t) for i, t in enumerate(deep.get("key_financials", []) or [])]
        deep["inventory_positions"] = [_get(f"deep_inventory_{i}", t) for i, t in enumerate(deep.get("inventory_positions", []) or [])]
        deep["inventory_risks"] = [_get(f"deep_risk_{i}", t) for i, t in enumerate(deep.get("inventory_risks", []) or [])]
        deep["balance_sheet_signals"] = [_get(f"deep_balance_{i}", t) for i, t in enumerate(deep.get("balance_sheet_signals", []) or [])]
        event_intel["assessment"] = _get("event_assessment", event_intel.get("assessment", ""))
        event_intel["strategic_events"] = [_get(f"event_strategic_{i}", t) for i, t in enumerate(event_intel.get("strategic_events", []) or [])]
        event_intel["carve_out_signals"] = [_get(f"event_carve_{i}", t) for i, t in enumerate(event_intel.get("carve_out_signals", []) or [])]
        event_intel["regulatory_signals"] = [_get(f"event_reg_{i}", t) for i, t in enumerate(event_intel.get("regulatory_signals", []) or [])]

        for tier_key in ("peer_competitors", "downstream_buyers",
                         "service_providers", "cross_industry_buyers"):
            tier = mkt.get(tier_key)
            if isinstance(tier, dict):
                tier["assessment"] = _get(f"mkt_{tier_key}", tier.get("assessment", ""))
                for i, company in enumerate(tier.get("companies", []) or []):
                    if isinstance(company, dict):
                        company["relevance"] = _get(f"{tier_key}_rel_{i}", company.get("relevance", ""))

        contacts["narrative_summary"] = _get("contacts_narrative", contacts.get("narrative_summary", ""))
        contacts["target_company_summary"] = _get("contacts_target_summary", contacts.get("target_company_summary", ""))
        for prefix, records in (
            ("buyer_contact", contacts.get("prioritized_contacts", []) or contacts.get("contacts", [])),
            ("target_contact", contacts.get("target_company_prioritized_contacts", []) or contacts.get("target_company_contacts", [])),
        ):
            for i, contact in enumerate(records[:8]):
                if isinstance(contact, dict):
                    contact["rolle_titel"] = _get(f"{prefix}_role_{i}", contact.get("rolle_titel", ""))
                    contact["funktion"] = _get(f"{prefix}_function_{i}", contact.get("funktion", ""))
                    contact["relevance_reason"] = _get(f"{prefix}_relevance_{i}", contact.get("relevance_reason", ""))
                    contact["suggested_outreach_angle"] = _get(f"{prefix}_angle_{i}", contact.get("suggested_outreach_angle", ""))

        for i, action in enumerate(data.get("meeting_actions", []) or []):
            if isinstance(action, dict):
                action["title"] = _get(f"meeting_action_title_{i}", action.get("title", ""))
                action["description"] = _get(f"meeting_action_desc_{i}", action.get("description", ""))

        return data

    except Exception:
        return pipeline_data  # silent fallback — render English on error


def generate_pdf(pipeline_data: dict[str, Any], *, lang: str = "de") -> bytes:
    labels  = _translation(lang)
    styles  = _styles()

    # Translate all narrative content into the requested output language.
    if lang in _LANG_NAMES:
        pipeline_data = _translate_content(pipeline_data, lang)

    pipeline_data = copy.deepcopy(pipeline_data)
    synthesis_payload = dict(pipeline_data.get("synthesis", {}) or {})
    synthesis_payload.pop("open_questions", None)
    pipeline_data["synthesis"] = synthesis_payload
    unresolved_payload = sanitize_success_unresolved(pipeline_data.get("unresolved", {}) or {})
    if unresolved_payload:
        pipeline_data["unresolved"] = unresolved_payload

    profile   = pipeline_data.get("company_profile", {}) or {}
    industry  = pipeline_data.get("industry_analysis", {}) or {}
    market    = pipeline_data.get("market_network", {}) or {}
    quality   = pipeline_data.get("quality_review", {}) or {}
    synthesis = pipeline_data.get("synthesis", {}) or {}
    readiness = pipeline_data.get("research_readiness", {}) or {}
    contacts_section = pipeline_data.get("contact_intelligence", {}) or {}
    econ = profile.get("economic_situation", {}) or {}
    deep_dive = profile.get("financial_deep_dive", {}) or {}
    transaction_intel = profile.get("transaction_event_intelligence", {}) or {}

    company_name      = _safe_text(
        profile.get("company_name") or synthesis.get("target_company"),
        "Target Company" if lang == "en" else "Zielunternehmen",
    )
    executive_summary = _safe_text(synthesis.get("executive_summary"))
    industry_name     = _safe_text(profile.get("industry") or industry.get("industry_name"))
    website           = _safe_text(profile.get("website"))
    products          = _top_items(profile.get("products_and_services"), 6)
    material_scope    = _top_items(profile.get("product_asset_scope") or profile.get("product_material_relevance"), 5)
    key_trends        = _top_items(industry.get("key_trends"), 5)
    service_relevance = synthesis.get("liquisto_service_relevance", []) or []

    # Filter risks
    _OPEN_STARTS = ("what ", "how ", "who ", "when ", "where ", "why ", "which ",
                    "are there", "is there", "does ", "do ", "can ")
    _BAD_STARTS  = ("point '", "no supporting source", "no verified", "no external search",
                    "supporting page excerpt")

    def _ok_risk(t: str) -> bool:
        s = t.strip()
        if not s or " " not in s:
            return False
        sl = s.lower()
        return not any(sl.startswith(p) for p in _OPEN_STARTS + _BAD_STARTS)

    raw_risks  = synthesis.get("key_risks") or []
    risks      = _top_items([r for r in raw_risks if _ok_risk(r)], 4)
    next_steps = _top_items(synthesis.get("next_steps"), 5)
    recommended_paths = synthesis.get("recommended_engagement_paths", []) or []
    primary_label, primary_fit, primary_reasoning = _primary_recommendation(synthesis, lang)

    # KPI facts
    revenue   = _extract_revenue_display(profile, industry)
    employees = _safe_text(profile.get("employees")).replace("Approximately ", "~").replace("approximately ", "~")
    hq        = _safe_text(profile.get("headquarters"))
    if hq != "n/v" and "," in hq:
        # Keep only city: works for "City, Country" and "City, State, Country"
        parts = [p.strip() for p in hq.split(",")]
        hq = parts[0] if len(parts) >= 2 else hq
    founded   = _safe_text(profile.get("founded"))
    confidence = _display_confidence(_safe_text(synthesis.get("confidence"), "medium"), lang)
    run_status = _display_run_status(_run_status_from_pipeline(pipeline_data), lang)

    # Research readiness
    rs_score  = int(readiness.get("score", 0))
    rs_usable = bool(readiness.get("usable", False))
    rs_health = _safe_text(quality.get("evidence_health"))

    # Company profile table rows
    profile_rows = [
        (labels["industry"],     industry_name),
        (labels["website"],      website),
        (labels["legal_form"],   _safe_text(profile.get("legal_form"))),
        (labels["founded"],      founded),
        (labels["headquarters"], _safe_text(profile.get("headquarters"))),
        (labels["employees"],    _safe_text(profile.get("employees"))),
        (labels["revenue"],      revenue),
    ]

    dashboard_kpis = [
        (labels["run_status"], run_status),
        (labels["revenue"], revenue),
        (labels["employees"], employees),
        (labels["confidence"], confidence),
        (labels["hq_short"], hq),
        (labels["primary_path"], primary_label),
        (labels["research_score"], f"{rs_score}/100" if rs_score else "n/v"),
    ]
    opportunity_reasons = _dedupe_items(
        [
            primary_reasoning,
            *[
                item.get("summary", "")
                for item in (synthesis.get("case_assessments") or [])
                if isinstance(item, dict)
            ],
            synthesis.get("opportunity_assessment_summary", ""),
        ],
        limit=4,
    )
    key_trigger_items = _dedupe_items(
        [
            *[_compact_event(item, 110) for item in (econ.get("recent_events") or [])],
            *[_compact_event(item, 110) for item in (transaction_intel.get("strategic_events") or [])],
            *key_trends,
        ],
        limit=4,
    )
    finance_rows = [
        (labels["revenue"], revenue),
        (labels["revenue_trend"], _truncate(econ.get("revenue_trend"), 110)),
        (labels["profitability"], _truncate(econ.get("profitability"), 110)),
        (labels["financial_pressure"], _safe_text(econ.get("financial_pressure"))),
        ("FY" if lang == "en" else "GJ", _safe_text(deep_dive.get("latest_fiscal_year"))),
        (labels["confidence"], confidence),
    ]
    financial_signals = _dedupe_items(
        [
            *[str(item) for item in (deep_dive.get("key_financials") or [])],
            *[str(item) for item in (deep_dive.get("inventory_positions") or [])],
            *[str(item) for item in (deep_dive.get("inventory_risks") or [])],
            *[str(item) for item in (deep_dive.get("balance_sheet_signals") or [])],
        ],
        limit=5,
    )
    if not financial_signals and _safe_text(deep_dive.get("assessment"), ""):
        financial_signals = [_truncate(deep_dive.get("assessment"), 180)]
    portfolio_events = _dedupe_items(
        [
            *[_compact_event(item, 118) for item in (transaction_intel.get("strategic_events") or [])],
            *[_compact_event(item, 118) for item in (econ.get("recent_events") or [])],
        ],
        limit=4,
    )
    narrative_overview = _truncate(
        synthesis.get("opportunity_assessment_summary") or synthesis.get("buyer_market_summary"),
        280,
    )
    why_liquisto = _truncate(
        synthesis.get("opportunity_assessment_summary") or primary_reasoning,
        220,
    )
    business_model = _truncate(profile.get("description"), 260)
    divisions = _extract_divisions(profile, contacts_section)
    financial_position = _truncate(econ.get("assessment"), 220)
    trigger_events = _dedupe_items(
        [
            *[_compact_event(item, 96) for item in (econ.get("recent_events") or [])],
            *[_compact_event(item, 96) for item in (transaction_intel.get("strategic_events") or [])],
        ],
        limit=4,
    )
    financial_cards = _extract_financial_cards(profile, industry, synthesis, labels)
    target_contacts = contacts_section.get("target_company_prioritized_contacts") or contacts_section.get("target_company_contacts") or []
    buyer_contacts = contacts_section.get("prioritized_contacts") or contacts_section.get("contacts") or []
    top_risks = risks[:3]

    top_actions = []
    for action in (pipeline_data.get("meeting_actions") or [])[:3]:
        if not isinstance(action, dict):
            continue
        title = _safe_text(action.get("title"), "")
        description = _truncate(action.get("description"), 70, "")
        if title and description:
            top_actions.append(f"{title} - {description}")
        elif title:
            top_actions.append(title)
    if not top_actions:
        top_actions = next_steps
    validation_pairs = _validation_pairs(top_risks or risks, top_actions or next_steps, labels)

    # ── build story ──────────────────────────────────────────────────────────

    story: list[Any] = []

    # Cover
    story.append(_cover_block(company_name, labels["report_subtitle"],
                              labels["prepared_for"], labels["date_label"], styles))
    story.append(Spacer(1, 5 * mm))

    story.append(_section_band(
        labels["snapshot"],
        "Decision-oriented overview for the first commercial conversation."
        if lang == "en" else
        "Entscheidungsorientierter Überblick für das erste kommerzielle Gespräch.",
        styles,
        accent=BRAND_TEAL,
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(_kpi_grid(dashboard_kpis, styles, columns=3))
    story.append(Spacer(1, 3 * mm))

    # Research readiness bar
    if rs_score > 0:
        story.append(_readiness_bar(rs_score, rs_usable, rs_health, labels))
        story.append(Spacer(1, 4 * mm))

    story.append(_summary_callout(
        f"{labels['primary_recommendation']}: {primary_label} ({primary_fit.title()})",
        primary_reasoning,
        styles,
        accent=BRAND_GREEN,
        background=WHITE,
    ))
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph(labels["summary"], styles["section"]))
    story.append(Paragraph(_truncate(executive_summary, 240), styles["body"]))
    story.append(Spacer(1, 2 * mm))
    story.append(_summary_callout(
        labels["top_risks"],
        f"{'; '.join(top_risks)}<br/><br/><b>{labels['next_recommended_step']}:</b> {_truncate(top_actions[0] if top_actions else '', 110, '')}",
        styles,
        accent=BRAND_RED,
        background=WHITE,
    ))

    story.append(PageBreak())

    story.append(_section_band(
        labels["service_fit"],
        "Lead with the strongest entry path, then support it with signals and alternatives."
        if lang == "en" else
        "Zuerst den stärksten Einstiegspfad führen, dann mit Signalen und Alternativen absichern.",
        styles,
        accent=BRAND_GREEN,
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(_opportunity_table(recommended_paths, service_relevance, labels, styles, lang))
    story.append(Spacer(1, 4 * mm))
    story.append(Table(
        [[
            _bullet_col(labels["key_triggers"], key_trigger_items, styles, 82 * mm, BRAND_TEAL),
            _bullet_col(labels["why_now"], opportunity_reasons, styles, 82 * mm, BRAND_GREEN),
        ]],
        colWidths=[84 * mm, 84 * mm],
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(_summary_callout(
        labels["why_liquisto"],
        why_liquisto,
        styles,
        accent=BRAND_BLUE,
        background=WHITE,
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(_summary_callout(
        labels["meeting_focus"],
        _truncate(narrative_overview, 150),
        styles,
        accent=BRAND_BLUE,
        background=SURFACE,
    ))

    story.append(PageBreak())

    story.append(_section_band(
        labels["company_profile"],
        "Compact company facts and asset scope relevant for commercial qualification."
        if lang == "en" else
        "Verdichtete Unternehmensdaten und Asset-Scope für die kommerzielle Qualifizierung.",
        styles,
        accent=BRAND_NAVY,
    ))
    story.append(Spacer(1, 3 * mm))
    prof_table = _info_table(profile_rows, styles, (46 * mm, 124 * mm))
    if prof_table:
        story.append(prof_table)
        story.append(Spacer(1, 4 * mm))
    story.append(Table(
        [[_bullet_col(labels["business_model"], [business_model], styles, 82 * mm, BRAND_BLUE),
          _bullet_col(labels["divisions"], divisions, styles, 82 * mm, BRAND_TEAL)]],
        colWidths=[84 * mm, 84 * mm],
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(Table(
        [[_bullet_col(labels["products_scope"], material_scope or products, styles, 82 * mm, BRAND_TEAL),
          _bullet_col(labels["trigger_events"], trigger_events, styles, 82 * mm, BRAND_AMBER)]],
        colWidths=[84 * mm, 84 * mm],
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(_summary_callout(
        labels["financial_position"],
        financial_position,
        styles,
        accent=BRAND_AMBER,
        background=WHITE,
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(_kpi_bar([
        (labels["revenue"], revenue),
        (labels["employees"], employees),
        (labels["hq_short"], hq),
        (labels["founded"], founded),
    ], styles))

    story.append(PageBreak())

    story.append(_section_band(
        labels["finance_section"],
        "Place the strongest financial pressure and inventory signals on one page."
        if lang == "en" else
        "Die stärksten Finanzdruck- und Inventarsignale auf einer Seite bündeln.",
        styles,
        accent=BRAND_AMBER,
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(_kpi_grid(financial_cards, styles, columns=2))
    story.append(Spacer(1, 3 * mm))
    story.append(Table(
        [[
            _bullet_col(labels["financial_signals"], financial_signals, styles, 82 * mm, BRAND_AMBER),
            _bullet_col(labels["portfolio_events"], portfolio_events, styles, 82 * mm, BRAND_BLUE),
        ]],
        colWidths=[84 * mm, 84 * mm],
    ))

    story.append(PageBreak())

    story.append(_section_band(
        labels["buyer_section"],
        "Show where assets can move and which buyer paths are currently most plausible."
        if lang == "en" else
        "Zeigen, wohin Assets bewegt werden können und welche Käuferpfade aktuell am plausibelsten sind.",
        styles,
        accent=BRAND_GREEN,
    ))
    story.append(Spacer(1, 3 * mm))
    for flowable in _buyer_landscape(market, labels, styles):
        story.append(flowable)

    # Monetization & redeployment paths
    monet_paths = _top_items(market.get("monetization_paths"), 5)
    redep_paths = _top_items(market.get("redeployment_paths"), 5)
    if monet_paths or redep_paths:
        story.append(Table(
            [[_bullet_col("Monetization Paths" if lang == "en" else "Monetarisierungspfade",
                          monet_paths or ["n/v"], styles, 82 * mm, BRAND_GREEN),
              _bullet_col("Redeployment Paths" if lang == "en" else "Weiterverwendungspfade",
                          redep_paths or ["n/v"], styles, 82 * mm, BRAND_TEAL)]],
            colWidths=[84 * mm, 84 * mm],
        ))
        story.append(Spacer(1, 3 * mm))

    story.append(PageBreak())
    story.append(_section_band(
        labels["stakeholder_section"],
        "Target-company decision-makers first, then external buyer and partner contacts."
        if lang == "en" else
        "Zuerst die Entscheider im Zielunternehmen, danach externe Käufer- und Partnerkontakte.",
        styles,
        accent=BRAND_NAVY,
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(labels["target_contacts"], styles["section"]))
    story.append(_contact_table(target_contacts[:4], labels, styles))
    if buyer_contacts:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(labels["buyer_contacts"], styles["section"]))
        story.append(_contact_table(buyer_contacts[:3], labels, styles))
    cov = _safe_text(contacts_section.get("coverage_quality"), "")
    if cov not in {"", "n/v", "n/a"}:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(f"{labels['coverage']}: {cov}", styles["small"]))

    story.append(PageBreak())

    story.append(_section_band(
        labels["validation_section"],
        "Keep only the few unresolved points that materially affect outreach quality and pair them with concrete validation steps."
        if lang == "en" else
        "Nur die wenigen offenen Punkte behalten, die die Outreach-Qualität materiell beeinflussen, und mit konkreten Validierungsschritten verknüpfen.",
        styles,
        accent=BRAND_RED,
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(Table(
        [[
            _bullet_col(labels["open_questions"], top_risks or risks, styles, 82 * mm, BRAND_RED),
            _bullet_col(labels["validation_plan"], top_actions or next_steps, styles, 82 * mm, BRAND_GREEN),
        ]],
        colWidths=[84 * mm, 84 * mm],
    ))
    story.append(Spacer(1, 4 * mm))
    validation_rows = [
        (f"{index + 1}. {_truncate(question, 70)}", _truncate(action, 90))
        for index, (question, action) in enumerate(validation_pairs)
    ]
    validation_table = _info_table(validation_rows, styles, (78 * mm, 92 * mm))
    if validation_table:
        story.append(validation_table)

    # ── render ───────────────────────────────────────────────────────────────

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=22 * mm,
        bottomMargin=14 * mm,
        title=f"{labels['report_title']} - {company_name}",
        author="Liquisto",
    )
    hf = _make_header_footer(labels["page_label"], labels["report_title"])
    doc.build(story, onFirstPage=hf, onLaterPages=hf)
    return buffer.getvalue()
