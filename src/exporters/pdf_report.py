"""Generate a polished Liquisto briefing PDF."""
from __future__ import annotations

import copy
import json
from datetime import datetime
from io import BytesIO
from typing import Any

from src.app.use_cases import sanitize_success_unresolved

from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PAGE_WIDTH, PAGE_HEIGHT = A4

BRAND_NAVY  = colors.HexColor("#102a43")
BRAND_BLUE  = colors.HexColor("#1f5aa6")
BRAND_SKY   = colors.HexColor("#d9e8ff")
BRAND_TEAL  = colors.HexColor("#0f766e")
BRAND_GREEN = colors.HexColor("#2f855a")
BRAND_AMBER = colors.HexColor("#c47f00")
BRAND_RED   = colors.HexColor("#b83232")
TEXT_PRIMARY = colors.HexColor("#1f2933")
TEXT_MUTED   = colors.HexColor("#52606d")
BORDER       = colors.HexColor("#d9e2ec")
SURFACE      = colors.HexColor("#f7f9fc")
SURFACE_WARM = colors.HexColor("#fff5f5")
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
            "report_subtitle": "Target company assessment for commercial preparation",
            "prepared_for": "Prepared for Liquisto",
            "date_label": "Report date",
            "snapshot": "Key Facts",
            "summary": "Executive Summary",
            "service_fit": "Liquisto Opportunity",
            "company_profile": "Company Profile",
            "market_section": "Market & Demand Context",
            "buyer_section": "Buyer & Redeployment Landscape",
            "risk_section": "Key Risks",
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
        }
    return {
        "report_subtitle": "Zielkundenanalyse für die kommerzielle Vorbereitung",
        "prepared_for": "Vorbereitet für Liquisto",
        "date_label": "Berichtsdatum",
        "snapshot": "Key Facts",
        "summary": "Executive Summary",
        "service_fit": "Liquisto-Empfehlung",
        "company_profile": "Unternehmensprofil",
        "market_section": "Markt- & Nachfragekontext",
        "buyer_section": "Käufer- & Redeployment-Landschaft",
        "risk_section": "Zentrale Risiken",
        "action_section": "Nächste Schritte",
        "sources_section": "Evidenz-Anhang",
        "readiness": "Recherche-Qualität",
        "usable_yes": "VERWENDBAR",
        "usable_no": "NICHT VERWENDBAR",
        "industry": "Branche",
        "website": "Webseite",
        "products": "Produkte & Leistungen",
        "material_relevance": "Produkt- & Asset-Scope",
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
    }


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("ReportTitle", parent=sample["Title"],
            fontName="Helvetica-Bold", fontSize=26, leading=30,
            textColor=WHITE, alignment=TA_LEFT, spaceAfter=4),
        "subtitle": ParagraphStyle("ReportSubtitle", parent=sample["BodyText"],
            fontName="Helvetica", fontSize=10, leading=13,
            textColor=WHITE, alignment=TA_LEFT),
        "cover_meta": ParagraphStyle("CoverMeta", parent=sample["BodyText"],
            fontName="Helvetica", fontSize=9, leading=12,
            textColor=colors.HexColor("#90aac7"), alignment=TA_LEFT),
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


# ── page chrome ───────────────────────────────────────────────────────────────

def _make_header_footer(page_label: str):  # noqa: ANN001
    def _header_footer(canvas, doc) -> None:  # noqa: ANN001
        canvas.saveState()
        canvas.setFillColor(WHITE)
        canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
        canvas.setFillColor(BRAND_NAVY)
        canvas.rect(0, PAGE_HEIGHT - 14 * mm, PAGE_WIDTH, 14 * mm, fill=1, stroke=0)
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 8.5)
        canvas.drawString(doc.leftMargin, PAGE_HEIGHT - 9 * mm, "Liquisto Research Briefing")
        canvas.setFillColor(TEXT_MUTED)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(PAGE_WIDTH - doc.rightMargin, 9 * mm, f"{page_label} {doc.page}")
        canvas.restoreState()
    return _header_footer


# ── cover ─────────────────────────────────────────────────────────────────────

def _cover_block(company_name: str, subtitle: str, prepared_for: str,
                 date_label: str, styles: dict[str, ParagraphStyle]) -> Table:
    date_str = datetime.now().strftime("%Y-%m-%d")
    content = [
        [Paragraph(f"<b>{company_name}</b>", styles["title"])],
        [Spacer(1, 2)],
        [Paragraph(subtitle, styles["subtitle"])],
        [Spacer(1, 8)],
        [Paragraph(f"{prepared_for}    ·    {date_label}: {date_str}", styles["cover_meta"])],
    ]
    table = Table(content, colWidths=[170 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    return table


# ── KPI bar ───────────────────────────────────────────────────────────────────

def _kpi_bar(kpis: list[tuple[str, str]], styles: dict[str, ParagraphStyle]) -> Table:
    """4 fact cards: Revenue | Employees | HQ | Founded."""
    cells = []
    for label, value in kpis:
        val_style = styles["kpi_value_small"] if len(value) > 20 else styles["kpi_value"]
        inner = Table(
            [[Paragraph(label, styles["kpi_label"])], [Paragraph(value, val_style)]],
            colWidths=[39 * mm],
        )
        inner.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        cells.append(inner)
    table = Table([cells], colWidths=[42.5 * mm] * len(cells))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
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
        companies = (payload.get("companies", []) if isinstance(payload, dict) else [])
        if not companies:
            continue

        # Tier header row
        data: list[list[Any]] = [[
            Paragraph(f"<b>{tier_label}</b>",              styles["table_header"]),
            Paragraph(f"<b>{labels['col_country']}</b>",   styles["table_header"]),
            Paragraph(f"<b>{labels['col_relevance']}</b>", styles["table_header"]),
        ]]

        for i, c in enumerate(companies):
            name    = _safe_text(c.get("company_name") or c.get("name") if isinstance(c, dict) else str(c))
            country = _safe_text(c.get("country", "") if isinstance(c, dict) else "")
            rel_raw = _safe_text(c.get("relevance", "") if isinstance(c, dict) else "")
            rel_txt = _fmt_relevance(rel_raw)
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

_LANG_NAMES = {"de": "German", "fr": "French", "es": "Spanish"}


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
        for i, t in enumerate(prof.get("products_and_services", []) or []):
            _add(f"prod_{i}", t)
        for i, t in enumerate(prof.get("product_asset_scope", []) or []):
            _add(f"scope_{i}", t)

        # Market network assessments
        for tier_key in ("peer_competitors", "downstream_buyers",
                         "service_providers", "cross_industry_buyers"):
            tier = mkt.get(tier_key, {}) or {}
            _add(f"mkt_{tier_key}", (tier.get("assessment", "") if isinstance(tier, dict) else ""))

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
                        f"Translate all JSON values from English to {lang_name}. "
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

        prof["products_and_services"] = [_get(f"prod_{i}", t)  for i, t in enumerate(prof.get("products_and_services", []) or [])]
        prof["product_asset_scope"]   = [_get(f"scope_{i}", t) for i, t in enumerate(prof.get("product_asset_scope",   []) or [])]

        for tier_key in ("peer_competitors", "downstream_buyers",
                         "service_providers", "cross_industry_buyers"):
            tier = mkt.get(tier_key)
            if isinstance(tier, dict):
                tier["assessment"] = _get(f"mkt_{tier_key}", tier.get("assessment", ""))

        return data

    except Exception:
        return pipeline_data  # silent fallback — render English on error


def generate_pdf(pipeline_data: dict[str, Any], *, lang: str = "de") -> bytes:
    labels  = _translation(lang)
    styles  = _styles()

    # Translate all narrative content when a non-English output is requested
    if lang != "en":
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

    company_name      = _safe_text(profile.get("company_name") or synthesis.get("target_company"), "Target Company")
    executive_summary = _safe_text(synthesis.get("executive_summary"))
    industry_name     = _safe_text(profile.get("industry") or industry.get("industry_name"))
    website           = _safe_text(profile.get("website"))
    products          = _top_items(profile.get("products_and_services"), 6)
    material_scope    = _top_items(profile.get("product_asset_scope") or profile.get("product_material_relevance"), 5)
    key_trends        = _top_items(industry.get("key_trends"), 5)
    service_relevance = synthesis.get("liquisto_service_relevance", []) or []
    sources           = synthesis.get("sources") or profile.get("sources") or []

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
    risks      = _top_items([r for r in raw_risks if _ok_risk(r)], 5)
    next_steps = _top_items(synthesis.get("next_steps"), 5)

    # KPI facts
    revenue   = _safe_text(profile.get("revenue"))
    employees = _safe_text(profile.get("employees")).replace("Approximately ", "~").replace("approximately ", "~")
    hq        = _safe_text(profile.get("headquarters"))
    if hq != "n/v" and "," in hq:
        # Keep only city: works for "City, Country" and "City, State, Country"
        parts = [p.strip() for p in hq.split(",")]
        hq = parts[0] if len(parts) >= 2 else hq
    founded   = _safe_text(profile.get("founded"))
    kpis = [
        (labels["industry"],    industry_name),
        (labels["revenue"],     revenue),
        (labels["employees"],   employees),
        (labels["hq_short"],    hq),
    ]

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

    market_rows = [
        (labels["market_trend"],    _safe_text(industry.get("trend_direction"))),
        (labels["demand_outlook"],  _safe_text(industry.get("demand_outlook"))[:120]),
        (labels["market_assessment"], _safe_text(industry.get("assessment"))[:300]),
        (labels["key_trends"],      _safe_join(key_trends)),
    ]

    econ = profile.get("economic_situation", {}) or {}
    econ_items = []
    for label_key, field in [
        ("revenue_trend",     "revenue_trend"),
        ("profitability",     "profitability"),
        ("financial_pressure","financial_pressure"),
        ("assessment",        "assessment"),
    ]:
        v = _safe_text(econ.get(field))
        if v != "n/v":
            econ_items.append(f"{labels[label_key]}: {v}")

    # ── build story ──────────────────────────────────────────────────────────

    story: list[Any] = []

    # Cover
    story.append(_cover_block(company_name, labels["report_subtitle"],
                              labels["prepared_for"], labels["date_label"], styles))
    story.append(Spacer(1, 5 * mm))

    # KPI bar
    story.append(Paragraph(labels["snapshot"], styles["section"]))
    story.append(_kpi_bar(kpis, styles))
    story.append(Spacer(1, 3 * mm))

    # Research readiness bar
    if rs_score > 0:
        story.append(_readiness_bar(rs_score, rs_usable, rs_health, labels))
        story.append(Spacer(1, 4 * mm))

    # Executive summary
    story.append(Paragraph(labels["summary"], styles["section"]))
    story.append(Paragraph(executive_summary, styles["body"]))
    story.append(Spacer(1, 5 * mm))

    # Opportunity tiles
    story.append(Paragraph(labels["service_fit"], styles["section"]))
    story.append(_opportunity_tiles(service_relevance, styles))
    story.append(Spacer(1, 7 * mm))

    # Company profile
    story.append(Paragraph(labels["company_profile"], styles["section"]))
    prof_table = _info_table(profile_rows, styles, (46 * mm, 124 * mm))
    if prof_table:
        story.append(prof_table)
        story.append(Spacer(1, 4 * mm))
    story.append(Table(
        [[_bullet_col(labels["products"], products, styles, 82 * mm, BRAND_BLUE),
          _bullet_col(labels["material_relevance"], material_scope, styles, 82 * mm, BRAND_TEAL)]],
        colWidths=[84 * mm, 84 * mm],
    ))
    story.append(Spacer(1, 6 * mm))

    # Market context
    story.append(Paragraph(labels["market_section"], styles["section"]))
    mkt_table = _info_table(market_rows, styles, (46 * mm, 124 * mm))
    if mkt_table:
        story.append(mkt_table)
        story.append(Spacer(1, 3 * mm))
    if econ_items:
        story.append(_bullet_col(labels["economic_view"], econ_items, styles, 170 * mm, BRAND_BLUE))
        story.append(Spacer(1, 3 * mm))
    story.append(Spacer(1, 3 * mm))

    # Buyer landscape
    story.append(Paragraph(labels["buyer_section"], styles["section"]))
    for flowable in _buyer_landscape(market, labels, styles):
        story.append(flowable)

    # Monetization & redeployment paths
    monet_paths = _top_items(market.get("monetization_paths"), 5)
    redep_paths = _top_items(market.get("redeployment_paths"), 5)
    if monet_paths or redep_paths:
        story.append(Table(
            [[_bullet_col("Monetization Paths" if lang == "en" else "Monetarisierungspfade",
                          monet_paths or ["n/v"], styles, 82 * mm, BRAND_GREEN),
              _bullet_col("Redeployment Paths" if lang == "en" else "Redeployment-Pfade",
                          redep_paths or ["n/v"], styles, 82 * mm, BRAND_TEAL)]],
            colWidths=[84 * mm, 84 * mm],
        ))
        story.append(Spacer(1, 3 * mm))

    # Repurposing & analytics signals
    repurp = _top_items(industry.get("repurposing_signals"), 5)
    analytics = _top_items(industry.get("analytics_signals"), 5)
    if repurp or analytics:
        story.append(Table(
            [[_bullet_col("Repurposing Signals" if lang == "en" else "Repurposing-Signale",
                          repurp or ["n/v"], styles, 82 * mm, BRAND_TEAL),
              _bullet_col("Analytics Signals" if lang == "en" else "Analytics-Signale",
                          analytics or ["n/v"], styles, 82 * mm, BRAND_BLUE)]],
            colWidths=[84 * mm, 84 * mm],
        ))
        story.append(Spacer(1, 3 * mm))

    story.append(Spacer(1, 4 * mm))

    # Contact intelligence
    contacts_section = pipeline_data.get("contact_intelligence", {}) or {}
    all_contacts = contacts_section.get("prioritized_contacts") or contacts_section.get("contacts", [])
    if all_contacts:
        story.append(Paragraph(
            "Contact Intelligence" if lang == "en" else "Kontakt-Intelligence",
            styles["section"],
        ))
        contact_data = [[
            Paragraph("<b>Name</b>", styles["table_header"]),
            Paragraph("<b>Role</b>" if lang == "en" else "<b>Rolle</b>", styles["table_header"]),
            Paragraph("<b>Company</b>" if lang == "en" else "<b>Firma</b>", styles["table_header"]),
        ]]
        for i, c in enumerate(all_contacts[:10]):
            name = _safe_text(c.get("name"), "\u2014")
            role = _safe_text(c.get("rolle_titel") or c.get("funktion", ""), "\u2014")
            firma = _safe_text(c.get("firma", ""), "\u2014")
            contact_data.append([
                Paragraph(name, styles["table_cell"]),
                Paragraph(role, styles["table_cell"]),
                Paragraph(firma, styles["table_cell"]),
            ])
        contact_table = Table(contact_data, colWidths=[50 * mm, 70 * mm, 50 * mm], repeatRows=1)
        ct_style = [
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
        for i in range(len(all_contacts[:10])):
            bg = WHITE if i % 2 == 0 else SURFACE
            ct_style.append(("BACKGROUND", (0, i + 1), (-1, i + 1), bg))
        contact_table.setStyle(TableStyle(ct_style))
        story.append(contact_table)
        cov = _safe_text(contacts_section.get("coverage_quality"), "\u2014")
        if cov != "\u2014":
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(
                f"Coverage: {cov}", styles["small"],
            ))
        story.append(Spacer(1, 5 * mm))

    # Risks
    story.append(Paragraph(labels["risk_section"], styles["section"]))
    story.append(_risk_table(risks, styles))
    story.append(Spacer(1, 5 * mm))

    # Next steps / Meeting Actions
    story.append(Paragraph(labels["action_section"], styles["section"]))
    # RA-06: meeting_actions are the primary action output
    meeting_actions_raw = pipeline_data.get("meeting_actions", [])
    if not meeting_actions_raw:
        # Fallback: extract from run_context short_term_memory if available
        meeting_actions_raw = (
            pipeline_data.get("run_context", {})
            .get("short_term_memory", {})
            .get("meeting_actions", [])
        )
    if meeting_actions_raw:
        _action_icons = {"prepare_meeting": "\u25b8", "collect_missing_evidence": "\u25b8",
                         "ask_user_selection": "\u25b8", "hold": "\u25b8"}
        action_items = [
            f"{_action_icons.get(a.get('action_type',''), '\u25b8')}  {_safe_text(a.get('title',''))}"
            + (f" \u2014 {_safe_text(a.get('description',''))[:120]}" if a.get('description') else "")
            for a in meeting_actions_raw[:6]
        ]
        story.append(_steps_table(action_items, styles))
    else:
        story.append(_steps_table(next_steps, styles))
    story.append(Spacer(1, 7 * mm))

    # Evidence appendix
    story.append(Paragraph(labels["sources_section"], styles["section"]))
    story.append(_source_table(sources, labels, styles))

    # ── render ───────────────────────────────────────────────────────────────

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=22 * mm,
        bottomMargin=14 * mm,
        title=f"Liquisto Briefing - {company_name}",
        author="Liquisto",
    )
    hf = _make_header_footer(labels["page_label"])
    doc.build(story, onFirstPage=hf, onLaterPages=hf)
    return buffer.getvalue()
