"""PDF report generator for Liquisto Market Intelligence briefings."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from fpdf import FPDF


# --- Translations ---

_T = {
    "de": {
        "title": "Liquisto Market Intelligence Briefing",
        "generated": "Erstellt am",
        "readiness_dashboard": "Ergebnisübersicht",
        "card_company": "Firmenprofil",
        "card_market": "Marktquellen",
        "card_evidence": "Evidenz",
        "card_buyers": "Käufer",
        "visual_coverage": "Datenabdeckung",
        "visual_company": "Firmenprofil",
        "visual_market": "Marktbild",
        "visual_buyers": "Käufernetzwerk",
        "visual_decision": "Entscheidungsschema",
        "metric_filled_fields": "gefüllte Felder",
        "metric_external_sources": "externe Quellen",
        "metric_tier_coverage": "Tier-Abdeckung",
        "decision_signal": "Signal",
        "exec_summary": "Zusammenfassung",
        "company_profile": "Firmenprofil",
        "field_company": "Unternehmen",
        "field_legal_form": "Rechtsform",
        "field_founded": "Gegründet",
        "field_hq": "Hauptsitz",
        "field_website": "Website",
        "field_industry": "Branche",
        "field_employees": "Mitarbeiter",
        "field_revenue": "Umsatz",
        "field_products": "Produkte & Dienstleistungen",
        "field_key_people": "Schlüsselpersonen",
        "economic_situation": "Wirtschaftslage",
        "field_revenue_trend": "Umsatztrend",
        "field_profitability": "Profitabilität",
        "field_financial_pressure": "Finanzdruck",
        "field_assessment": "Einschätzung",
        "field_recent_events": "Aktuelle Ereignisse",
        "field_inventory_signals": "Bestandssignale",
        "industry_analysis": "Branchenanalyse",
        "field_market_size": "Marktgröße",
        "field_trend": "Trendrichtung",
        "field_growth": "Wachstumsrate",
        "field_demand": "Nachfrageausblick",
        "field_overcapacity": "Überkapazitätssignale",
        "field_excess_stock": "Überschussbestand-Indikatoren",
        "field_key_trends": "Schlüsseltrends",
        "buyer_network": "Käufernetzwerk",
        "tier_peers": "Peer-Konkurrenten",
        "tier_downstream": "Abnehmer",
        "tier_service": "Service-Anbieter",
        "tier_cross": "Cross-Industry Käufer",
        "evidence_qa": "Recherchehinweise",
        "field_evidence_health": "Evidenzqualität",
        "field_open_gaps": "Offene Lücken",
        "field_recommendations": "Empfehlungen",
        "liquisto_relevance": "Liquisto Service-Relevanz",
        "case_assessment": "Einschätzung je Option",
        "option_kaufen": "Kaufen",
        "option_kommission": "Kommission",
        "option_ablehnen": "Ablehnen",
        "pro": "PRO",
        "contra": "CONTRA",
        "based_on": "Basierend auf",
        "buyer_summary": "Käufermarkt-Zusammenfassung",
        "risks": "Risiken",
        "next_steps": "Nächste Schritte",
        "sources": "Quellen",
        "no_data": "Keine Daten verfügbar",
        "buyer_count": "Buyer-Anzahl",
        "tier": "Tier",
        "assessment": "Bewertung",
        "result_table": "Ergebnistabelle",
        "research_note": "Kurzer Recherchehinweis",
        "service_area_excess_inventory": "Überbestände",
        "service_area_repurposing": "Umnutzung",
        "service_area_analytics": "Analytics",
        "status_high": "hoch",
        "status_medium": "mittel",
        "status_low": "niedrig",
        "status_unclear": "unklar",
        "trend_uncertain": "unsicher",
        "signal_pro": "pro-dominant",
        "signal_contra": "contra-dominant",
        "signal_mixed": "gemischt",
        "summary_missing_market": "Für Marktgröße, Wachstum, Nachfrage und Überbestandslage liegen keine belastbaren externen Marktquellen vor.",
        "summary_missing_buyers": "Für das Käufernetzwerk konnten keine belastbaren Buyer-, Wettbewerber- oder Service-Treffer validiert werden.",
        "summary_missing_company": "Im Firmenprofil fehlen weiterhin zentrale Basisdaten.",
        "summary_company_intro": "{company} ist im vorliegenden Datensatz als Anbieter von {industry} mit Fokus auf {products} erfasst.",
        "summary_quality": "Die belastbare Evidenzlage ist derzeit {quality}.",
        "main_sections_note": "Der Hauptteil dieses Reports fokussiert ausschließlich auf die recherchierten Ergebnisse.",
    },
    "en": {
        "title": "Liquisto Market Intelligence Briefing",
        "generated": "Generated on",
        "readiness_dashboard": "Readiness Dashboard",
        "card_company": "Company Profile",
        "card_market": "Market Sources",
        "card_evidence": "Evidence",
        "card_buyers": "Buyers",
        "visual_coverage": "Coverage Snapshot",
        "visual_company": "Company Profile",
        "visual_market": "Market Evidence",
        "visual_buyers": "Buyer Network",
        "visual_decision": "Decision Schema",
        "metric_filled_fields": "filled fields",
        "metric_external_sources": "external sources",
        "metric_tier_coverage": "tier coverage",
        "decision_signal": "Signal",
        "exec_summary": "Executive Summary",
        "company_profile": "Company Profile",
        "field_company": "Company",
        "field_legal_form": "Legal Form",
        "field_founded": "Founded",
        "field_hq": "Headquarters",
        "field_website": "Website",
        "field_industry": "Industry",
        "field_employees": "Employees",
        "field_revenue": "Revenue",
        "field_products": "Products & Services",
        "field_key_people": "Key People",
        "economic_situation": "Economic Situation",
        "field_revenue_trend": "Revenue Trend",
        "field_profitability": "Profitability",
        "field_financial_pressure": "Financial Pressure",
        "field_assessment": "Assessment",
        "field_recent_events": "Recent Events",
        "field_inventory_signals": "Inventory Signals",
        "industry_analysis": "Industry Analysis",
        "field_market_size": "Market Size",
        "field_trend": "Trend Direction",
        "field_growth": "Growth Rate",
        "field_demand": "Demand Outlook",
        "field_overcapacity": "Overcapacity Signals",
        "field_excess_stock": "Excess Stock Indicators",
        "field_key_trends": "Key Trends",
        "buyer_network": "Buyer Network",
        "tier_peers": "Peer Competitors",
        "tier_downstream": "Downstream Buyers",
        "tier_service": "Service Providers",
        "tier_cross": "Cross-Industry Buyers",
        "evidence_qa": "Research Notes",
        "field_evidence_health": "Evidence Health",
        "field_open_gaps": "Open Gaps",
        "field_recommendations": "Recommendations",
        "liquisto_relevance": "Liquisto Service Relevance",
        "case_assessment": "Case Assessment per Option",
        "option_kaufen": "Buy",
        "option_kommission": "Commission",
        "option_ablehnen": "Decline",
        "pro": "PRO",
        "contra": "CONTRA",
        "based_on": "Based on",
        "buyer_summary": "Buyer Market Summary",
        "risks": "Risks",
        "next_steps": "Next Steps",
        "sources": "Sources",
        "no_data": "No data available",
        "buyer_count": "Buyer Count",
        "tier": "Tier",
        "assessment": "Assessment",
        "result_table": "Results Table",
        "research_note": "Short research note",
        "service_area_excess_inventory": "Excess Inventory",
        "service_area_repurposing": "Repurposing",
        "service_area_analytics": "Analytics",
        "status_high": "high",
        "status_medium": "medium",
        "status_low": "low",
        "status_unclear": "unclear",
        "trend_uncertain": "uncertain",
        "signal_pro": "pro-dominant",
        "signal_contra": "contra-dominant",
        "signal_mixed": "mixed",
        "summary_missing_market": "No credible external market sources are available for market size, growth, demand, or excess inventory conditions.",
        "summary_missing_buyers": "No validated buyer, competitor, or service-provider matches were identified for the buyer network.",
        "summary_missing_company": "Core company basics are still missing from the profile.",
        "summary_company_intro": "{company} is captured in the current dataset as a supplier in {industry} with focus areas including {products}.",
        "summary_quality": "The currently supportable evidence level is {quality}.",
        "main_sections_note": "The main body of this report focuses exclusively on researched business results.",
    },
}


class _ReportPDF(FPDF):
    def __init__(self, lang: str = "de"):
        super().__init__()
        self.lang = lang
        self.t = _T.get(lang, _T["en"])
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, self.t["title"], align="R", new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"{self.page_no()}/{{nb}}", align="C")

    def section_title(self, title: str):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(0, 51, 102)
        self.ln(6)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)

    def sub_title(self, title: str):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(0, 0, 0)
        self.ln(3)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def field(self, label: str, value: str):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(60, 60, 60)
        self.cell(55, 6, f"{label}:")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 6, _render_text(value, self.lang))
        self.ln(1)

    def body_text(self, text: str):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 5, _render_text(text, self.lang))
        self.ln(2)

    def bullet(self, text: str):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(0, 0, 0)
        self.cell(6, 5, "-")
        self.multi_cell(0, 5, _render_text(text, self.lang))
        self.ln(1)

    def tag(self, label: str, color: tuple[int, int, int] = (0, 102, 51)):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*color)
        self.cell(0, 5, label, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def stat_card(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        title: str,
        value: str,
        subtitle: str = "",
        accent: tuple[int, int, int] = (0, 51, 102),
    ):
        self.set_draw_color(220, 225, 235)
        self.set_fill_color(248, 250, 253)
        self.rect(x, y, w, h, style="DF")
        self.set_fill_color(*accent)
        self.rect(x, y, 2.5, h, style="F")
        self.set_xy(x + 6, y + 4)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(90, 90, 90)
        self.cell(w - 10, 5, _safe(title), new_x="LMARGIN", new_y="NEXT")
        self.set_x(x + 6)
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(20, 20, 20)
        self.cell(w - 10, 8, _safe(value), new_x="LMARGIN", new_y="NEXT")
        if subtitle:
            self.set_x(x + 6)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(110, 110, 110)
            self.multi_cell(w - 10, 4, _safe(subtitle))

    def progress_row(
        self,
        label: str,
        ratio: float,
        value_text: str,
        color: tuple[int, int, int] = (0, 102, 153),
    ):
        ratio = max(0.0, min(1.0, ratio))
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(60, 60, 60)
        self.cell(38, 6, _safe(label))
        bar_x = self.get_x()
        bar_y = self.get_y() + 1.5
        bar_w = 92
        bar_h = 4
        self.set_draw_color(215, 220, 230)
        self.set_fill_color(236, 240, 245)
        self.rect(bar_x, bar_y, bar_w, bar_h, style="DF")
        self.set_fill_color(*color)
        self.rect(bar_x, bar_y, bar_w * ratio, bar_h, style="F")
        self.set_xy(bar_x + bar_w + 4, self.get_y())
        self.set_font("Helvetica", "", 8)
        self.set_text_color(90, 90, 90)
        self.cell(0, 6, _safe(value_text), new_x="LMARGIN", new_y="NEXT")

    def decision_chip_row(self, items: list[tuple[str, str, tuple[int, int, int]]]):
        x = self.l_margin
        y = self.get_y()
        chip_w = (self.w - self.l_margin - self.r_margin - 8) / 3
        chip_h = 18
        for index, (title, value, color) in enumerate(items):
            chip_x = x + index * (chip_w + 4)
            self.set_draw_color(220, 225, 235)
            self.set_fill_color(248, 250, 253)
            self.rect(chip_x, y, chip_w, chip_h, style="DF")
            self.set_fill_color(*color)
            self.rect(chip_x + 3, y + 5, 6, 6, style="F")
            self.set_xy(chip_x + 12, y + 3)
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(40, 40, 40)
            self.cell(chip_w - 15, 4, _safe(title), new_x="LMARGIN", new_y="NEXT")
            self.set_xy(chip_x + 12, y + 8)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(90, 90, 90)
            self.multi_cell(chip_w - 15, 4, _safe(value))
        self.set_y(y + chip_h + 4)


def _safe(value: Any) -> str:
    text = str(value or "n/v").strip()
    # Replace characters that latin-1 can't encode
    replacements = {
        "\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u2022": "-",
        "\u20ac": "EUR", "\u00df": "ss",
    }
    for char, repl in replacements.items():
        text = text.replace(char, repl)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _render_text(value: Any, lang: str) -> str:
    return _safe(_localize_text(value, lang))


def _localize_text(value: Any, lang: str) -> str:
    text = str(value or "n/v")
    replacements = {
        "de": {
            "Gear and transmission technology": "Zahnrad- und Getriebetechnik",
            "gear and transmission technology": "Zahnrad- und Getriebetechnik",
            "Planetary gears": "Planetengetriebe",
            "planetary gears": "Planetengetriebe",
            "Drive gearboxes": "Antriebsgetriebe",
            "Transmission components": "Getriebekomponenten",
            "Service Providers": "Service-Anbieter",
            "Peer Competitors": "Peer-Konkurrenten",
            "Downstream Buyers": "Abnehmer",
            "Cross-Industry Buyers": "Cross-Industry Käufer",
            "Evidence health": "Evidenzqualität",
        },
        "en": {
            "Zahnrad- und Getriebetechnik": "gear and transmission technology",
            "Planetengetriebe": "planetary gears",
            "Antriebsgetriebe": "drive gearboxes",
            "Getriebekomponenten": "transmission components",
            "Service-Anbieter": "Service Providers",
            "Peer-Konkurrenten": "Peer Competitors",
            "Abnehmer": "Downstream Buyers",
            "Evidenzqualität": "Evidence health",
        },
    }
    for source, target in replacements.get(lang, {}).items():
        text = text.replace(source, target)
    return text


def _get(data: dict, *keys, default="n/v") -> Any:
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            return default
    return current or default


def _is_filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized not in {"", "n/v", "unknown", "unsicher"}
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    if isinstance(value, dict):
        return len(value) > 0
    return True


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return max(0.0, min(1.0, numerator / denominator))


def _count_external_sources(industry: dict[str, Any]) -> int:
    count = 0
    for source in industry.get("sources", []) or []:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url", "") or "").strip().lower()
        if not url:
            continue
        if "wikipedia.org" in url or "imsgear.com" in url or "zf.com" in url:
            continue
        count += 1
    return count


def _company_profile_coverage(profile: dict[str, Any]) -> tuple[int, int]:
    checks = [
        profile.get("legal_form"),
        profile.get("founded"),
        profile.get("headquarters"),
        profile.get("employees"),
        profile.get("revenue"),
        profile.get("key_people"),
    ]
    return sum(1 for value in checks if _is_filled(value)), len(checks)


def _industry_coverage(industry: dict[str, Any]) -> tuple[int, int]:
    checks = [
        industry.get("market_size"),
        industry.get("growth_rate"),
        industry.get("demand_outlook"),
        industry.get("excess_stock_indicators"),
        industry.get("key_trends"),
        industry.get("overcapacity_signals"),
    ]
    return sum(1 for value in checks if _is_filled(value)), len(checks)


def _market_coverage(market: dict[str, Any]) -> tuple[int, int, int]:
    tiers = [
        market.get("peer_competitors", {}),
        market.get("downstream_buyers", {}),
        market.get("service_providers", {}),
        market.get("cross_industry_buyers", {}),
    ]
    covered = 0
    buyer_count = 0
    for tier in tiers:
        if not isinstance(tier, dict):
            continue
        companies = tier.get("companies", []) or []
        buyer_count += len(companies)
        if companies:
            covered += 1
    return covered, len(tiers), buyer_count


def _decision_signal(case: dict[str, Any]) -> tuple[str, tuple[int, int, int]]:
    arguments = case.get("arguments", []) or []
    pro = sum(1 for arg in arguments if str(arg.get("direction", "")).strip().lower() == "pro")
    contra = sum(1 for arg in arguments if str(arg.get("direction", "")).strip().lower() == "contra")
    if contra > pro:
        return "contra-dominant", (180, 0, 0)
    if pro > contra:
        return "pro-dominant", (0, 128, 0)
    return "mixed", (160, 120, 0)


def _localized_status(value: Any, lang: str) -> str:
    t = _T.get(lang, _T["en"])
    mapping = {
        "hoch": t["status_high"],
        "high": t["status_high"],
        "mittel": t["status_medium"],
        "medium": t["status_medium"],
        "moderate": t["status_medium"],
        "niedrig": t["status_low"],
        "low": t["status_low"],
        "unklar": t["status_unclear"],
        "unclear": t["status_unclear"],
        "unsicher": t["trend_uncertain"],
        "uncertain": t["trend_uncertain"],
        "n/v": "n/v",
    }
    normalized = str(value or "").strip().lower()
    return mapping.get(normalized, str(value or "n/v"))


def _localized_service_area(value: str, lang: str) -> str:
    t = _T.get(lang, _T["en"])
    return {
        "excess_inventory": t["service_area_excess_inventory"],
        "repurposing": t["service_area_repurposing"],
        "analytics": t["service_area_analytics"],
    }.get(str(value or "").strip().lower(), str(value or "n/v"))


def _localized_signal_label(value: str, lang: str) -> str:
    t = _T.get(lang, _T["en"])
    return {
        "pro-dominant": t["signal_pro"],
        "contra-dominant": t["signal_contra"],
        "mixed": t["signal_mixed"],
    }.get(str(value or "").strip().lower(), str(value or "n/v"))


def _top_products(profile: dict[str, Any]) -> str:
    products = [str(item).strip() for item in profile.get("products_and_services", []) or [] if str(item).strip()]
    if not products:
        return "n/v"
    return ", ".join(products[:3])


def _build_localized_summary(pipeline_data: dict[str, Any], lang: str) -> str:
    t = _T.get(lang, _T["en"])
    profile = pipeline_data.get("company_profile", {}) or {}
    industry = pipeline_data.get("industry_analysis", {}) or {}
    market = pipeline_data.get("market_network", {}) or {}
    qa = pipeline_data.get("quality_review", {}) or {}

    parts = [
        t["summary_company_intro"].format(
            company=_safe(_get(profile, "company_name")),
            industry=_safe(_get(profile, "industry")),
            products=_safe(_top_products(profile)),
        )
    ]
    if not _is_filled(profile.get("founded")) or not _is_filled(profile.get("headquarters")):
        parts.append(t["summary_missing_company"])
    if _count_external_sources(industry) == 0:
        parts.append(t["summary_missing_market"])
    covered_tiers, _total_tiers, buyer_count = _market_coverage(market)
    if buyer_count == 0 and covered_tiers == 0:
        parts.append(t["summary_missing_buyers"])
    parts.append(t["summary_quality"].format(quality=_localized_status(_get(qa, "evidence_health"), lang)))
    return " ".join(parts)


def _build_localized_research_note(pipeline_data: dict[str, Any], lang: str) -> str:
    t = _T.get(lang, _T["en"])
    profile = pipeline_data.get("company_profile", {}) or {}
    industry = pipeline_data.get("industry_analysis", {}) or {}
    market = pipeline_data.get("market_network", {}) or {}
    covered_tiers, total_tiers, buyer_count = _market_coverage(market)
    note_parts = [
        f"{t['visual_company']}: {_company_profile_coverage(profile)[0]}/{_company_profile_coverage(profile)[1]} {t['metric_filled_fields']}.",
        f"{t['visual_market']}: {_count_external_sources(industry)} {t['metric_external_sources']}.",
        f"{t['visual_buyers']}: {covered_tiers}/{total_tiers} {t['metric_tier_coverage']}, {buyer_count} {t['buyer_count'].lower()}.",
    ]
    return " ".join(note_parts)


def _localized_risks(pipeline_data: dict[str, Any], lang: str) -> list[str]:
    t = _T.get(lang, _T["en"])
    profile = pipeline_data.get("company_profile", {}) or {}
    industry = pipeline_data.get("industry_analysis", {}) or {}
    market = pipeline_data.get("market_network", {}) or {}
    risks: list[str] = []
    if not _is_filled(profile.get("founded")) or not _is_filled(profile.get("headquarters")):
        risks.append(t["summary_missing_company"])
    if _count_external_sources(industry) == 0:
        risks.append(t["summary_missing_market"])
    covered_tiers, _total_tiers, buyer_count = _market_coverage(market)
    if buyer_count == 0 and covered_tiers == 0:
        risks.append(t["summary_missing_buyers"])
    return risks


def _localized_next_steps(pipeline_data: dict[str, Any], lang: str) -> list[str]:
    if lang == "de":
        return [
            "Offizielle Unternehmensquellen oder Registerdaten für Gründung, Hauptsitz und Management ergänzen.",
            "Aktuelle Marktquellen für Marktgröße, Wachstum, Nachfrage und Überbestandslage beschaffen.",
            "Buyer-Longlist mit Primärquellen, Referenzen oder belastbaren Wettbewerbsüberschneidungen nachschärfen.",
        ]
    return [
        "Add official company or registry sources for founding date, headquarters, and management.",
        "Source current market evidence for market size, growth, demand, and excess inventory conditions.",
        "Strengthen the buyer longlist with primary-source references or verified competitor overlaps.",
    ]


def generate_pdf(pipeline_data: dict[str, Any], lang: str = "de") -> bytes:
    """Generate a PDF report from pipeline data. Returns PDF as bytes."""
    t = _T.get(lang, _T["en"])
    pdf = _ReportPDF(lang=lang)
    pdf.alias_nb_pages()
    pdf.add_page()

    # Title page
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(0, 51, 102)
    pdf.ln(30)
    pdf.cell(0, 15, t["title"], align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(80, 80, 80)
    company = _get(pipeline_data, "company_profile", "company_name")
    pdf.cell(0, 10, _safe(company), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("Helvetica", "I", 10)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pdf.cell(0, 8, f"{t['generated']} {now}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(12)

    qa = pipeline_data.get("quality_review", {}) or {}
    market = pipeline_data.get("market_network", {}) or {}
    profile = pipeline_data.get("company_profile", {}) or {}
    industry = pipeline_data.get("industry_analysis", {}) or {}
    company_filled, company_total = _company_profile_coverage(profile)
    covered_tiers, total_tiers, buyer_count = _market_coverage(market)
    evidence_label = _localized_status(_get(qa, "evidence_health"), lang)
    card_y = pdf.get_y()
    card_w = (pdf.w - pdf.l_margin - pdf.r_margin - 9) / 4
    pdf.section_title(t["readiness_dashboard"])
    card_y = pdf.get_y()
    pdf.stat_card(pdf.l_margin, card_y, card_w, 22, t["card_company"], f"{company_filled}/{company_total}", t["metric_filled_fields"], accent=(0, 92, 153))
    pdf.stat_card(pdf.l_margin + card_w + 3, card_y, card_w, 22, t["card_market"], str(_count_external_sources(industry)), t["metric_external_sources"], accent=(180, 90, 0))
    pdf.stat_card(pdf.l_margin + 2 * (card_w + 3), card_y, card_w, 22, t["card_evidence"], evidence_label, accent=(120, 0, 120))
    pdf.stat_card(pdf.l_margin + 3 * (card_w + 3), card_y, card_w, 22, t["card_buyers"], str(buyer_count), t["buyer_count"], accent=(0, 128, 0))
    pdf.set_y(card_y + 28)
    pdf.body_text(t["main_sections_note"])

    # --- Executive Summary ---
    pdf.add_page()
    synthesis = pipeline_data.get("synthesis", {})
    industry_filled, industry_total = _industry_coverage(industry)
    pdf.section_title(t["exec_summary"])
    pdf.body_text(_build_localized_summary(pipeline_data, lang))
    pdf.sub_title(t["visual_coverage"])
    pdf.progress_row(
        t["visual_company"],
        _safe_ratio(company_filled, company_total),
        f"{company_filled}/{company_total} {t['metric_filled_fields']}",
        color=(0, 92, 153),
    )
    pdf.progress_row(
        t["visual_market"],
        _safe_ratio(industry_filled, industry_total),
        f"{industry_filled}/{industry_total} {t['metric_filled_fields']} • {_count_external_sources(industry)} {t['metric_external_sources']}",
        color=(160, 110, 0),
    )
    pdf.progress_row(
        t["visual_buyers"],
        _safe_ratio(covered_tiers, total_tiers),
        f"{covered_tiers}/{total_tiers} {t['metric_tier_coverage']} • {buyer_count} {t['buyer_count'].lower()}",
        color=(0, 128, 0),
    )
    pdf.ln(2)

    # --- Company Profile ---
    pdf.section_title(t["company_profile"])
    pdf.field(t["field_company"], _get(profile, "company_name"))
    pdf.field(t["field_legal_form"], _get(profile, "legal_form"))
    pdf.field(t["field_founded"], _get(profile, "founded"))
    pdf.field(t["field_hq"], _get(profile, "headquarters"))
    pdf.field(t["field_website"], _get(profile, "website"))
    pdf.field(t["field_industry"], _get(profile, "industry"))
    pdf.field(t["field_employees"], _get(profile, "employees"))
    pdf.field(t["field_revenue"], _get(profile, "revenue"))

    products = _get(profile, "products_and_services", default=[])
    if products and isinstance(products, list):
        pdf.sub_title(t["field_products"])
        for p in products:
            pdf.bullet(str(p))

    people = _get(profile, "key_people", default=[])
    if people and isinstance(people, list):
        pdf.sub_title(t["field_key_people"])
        for person in people:
            if isinstance(person, dict):
                pdf.bullet(f"{person.get('name', '?')} – {person.get('role', '?')}")

    # Economic situation
    econ = _get(profile, "economic_situation", default={})
    if isinstance(econ, dict):
        pdf.sub_title(t["economic_situation"])
        pdf.field(t["field_revenue_trend"], _get(econ, "revenue_trend"))
        pdf.field(t["field_profitability"], _get(econ, "profitability"))
        pdf.field(t["field_financial_pressure"], _get(econ, "financial_pressure"))
        for event in _get(econ, "recent_events", default=[]) or []:
            pdf.bullet(str(event))

    # --- Industry Analysis ---
    pdf.section_title(t["industry_analysis"])
    pdf.field(t["field_industry"], _get(industry, "industry_name"))
    pdf.field(t["field_market_size"], _get(industry, "market_size"))
    pdf.field(t["field_trend"], _localized_status(_get(industry, "trend_direction"), lang))
    pdf.field(t["field_growth"], _get(industry, "growth_rate"))
    pdf.field(t["field_demand"], _get(industry, "demand_outlook"))
    pdf.field(t["field_excess_stock"], _get(industry, "excess_stock_indicators"))

    overcap = _get(industry, "overcapacity_signals", default=[])
    pdf.sub_title(t["field_overcapacity"])
    if overcap and isinstance(overcap, list):
        for s in overcap:
            pdf.bullet(str(s))
    else:
        pdf.body_text(t["no_data"])

    trends = _get(industry, "key_trends", default=[])
    pdf.sub_title(t["field_key_trends"])
    if trends and isinstance(trends, list):
        for tr in trends:
            pdf.bullet(str(tr))
    else:
        pdf.body_text(t["no_data"])

    # --- Buyer Network ---
    pdf.section_title(t["buyer_network"])
    pdf.sub_title(t["result_table"])
    pdf.field(t["tier"], f"{t['tier_peers']}: {len(_get(market, 'peer_competitors', default={}).get('companies', []) if isinstance(_get(market, 'peer_competitors', default={}), dict) else [])}")
    pdf.field(t["tier"], f"{t['tier_downstream']}: {len(_get(market, 'downstream_buyers', default={}).get('companies', []) if isinstance(_get(market, 'downstream_buyers', default={}), dict) else [])}")
    pdf.field(t["tier"], f"{t['tier_service']}: {len(_get(market, 'service_providers', default={}).get('companies', []) if isinstance(_get(market, 'service_providers', default={}), dict) else [])}")
    pdf.field(t["tier"], f"{t['tier_cross']}: {len(_get(market, 'cross_industry_buyers', default={}).get('companies', []) if isinstance(_get(market, 'cross_industry_buyers', default={}), dict) else [])}")

    for tier_key, tier_label in [
        ("peer_competitors", t["tier_peers"]),
        ("downstream_buyers", t["tier_downstream"]),
        ("service_providers", t["tier_service"]),
        ("cross_industry_buyers", t["tier_cross"]),
    ]:
        tier = _get(market, tier_key, default={})
        if not isinstance(tier, dict):
            continue
        companies = tier.get("companies", [])
        pdf.sub_title(f"{tier_label} ({len(companies)})")
        if not companies:
            pdf.body_text(t["no_data"])
        for buyer in companies[:10]:
            if isinstance(buyer, dict):
                name = buyer.get("name", "?")
                rel = buyer.get("relevance", "")
                loc = ", ".join(filter(None, [buyer.get("city"), buyer.get("country")]))
                line = f"{name}"
                if loc:
                    line += f" ({loc})"
                if rel:
                    line += f" – {rel}"
                pdf.bullet(line)

    # --- Liquisto Service Relevance ---
    relevance = _get(synthesis, "liquisto_service_relevance", default=[])
    if relevance and isinstance(relevance, list):
        pdf.section_title(t["liquisto_relevance"])
        for item in relevance:
            if isinstance(item, dict):
                area = _localized_service_area(str(item.get("service_area", "?")), lang)
                rel = _localized_status(item.get("relevance", "?"), lang)
                color = {"hoch": (0, 128, 0), "high": (0, 128, 0), "mittel": (200, 150, 0), "medium": (200, 150, 0), "niedrig": (180, 0, 0), "low": (180, 0, 0)}.get(
                    str(item.get("relevance", "")).lower(), (80, 80, 80)
                )
                pdf.tag(f"{area}: {rel}", color)

    # --- Case Assessment (Pro/Contra) ---
    assessments = _get(synthesis, "case_assessments", default=[])
    if assessments and isinstance(assessments, list):
        pdf.section_title(t["case_assessment"])
        chips: list[tuple[str, str, tuple[int, int, int]]] = []
        for case in assessments[:3]:
            if not isinstance(case, dict):
                continue
            option = str(case.get("option", "?"))
            option_label = {
                "kaufen": t["option_kaufen"],
                "kommission": t["option_kommission"],
                "ablehnen": t["option_ablehnen"],
            }.get(option.lower(), option)
            signal, color = _decision_signal(case)
            chips.append((option_label, f"{t['decision_signal']}: {_localized_signal_label(signal, lang)}", color))
        if chips:
            pdf.sub_title(t["visual_decision"])
            pdf.decision_chip_row(chips)
        for case in assessments:
            if not isinstance(case, dict):
                continue
            option = case.get("option", "?")
            option_label = {
                "kaufen": t["option_kaufen"],
                "kommission": t["option_kommission"],
                "ablehnen": t["option_ablehnen"],
            }.get(option.lower(), option)
            pdf.sub_title(option_label)
            signal, _color = _decision_signal(case)
            pdf.body_text(f"{t['decision_signal']}: {_localized_signal_label(signal, lang)}")

    # --- Buyer Summary + Risks + Next Steps ---
    pdf.section_title(t["buyer_summary"])
    pdf.body_text(_build_localized_research_note(pipeline_data, lang))

    localized_risks = _localized_risks(pipeline_data, lang)
    if localized_risks:
        pdf.section_title(t["risks"])
        for r in localized_risks[:4]:
            pdf.bullet(str(r))

    localized_steps = _localized_next_steps(pipeline_data, lang)
    if localized_steps:
        pdf.section_title(t["next_steps"])
        for s in localized_steps[:4]:
            pdf.bullet(str(s))

    # --- Research Notes / Run Summary at the end ---
    if qa:
        pdf.section_title(t["evidence_qa"])
        pdf.field(t["field_evidence_health"], _localized_status(_get(qa, "evidence_health"), lang))
        pdf.sub_title(t["research_note"])
        pdf.body_text(_build_localized_research_note(pipeline_data, lang))

    output = pdf.output()
    if isinstance(output, bytes):
        return output
    if isinstance(output, bytearray):
        return bytes(output)
    if isinstance(output, str):
        return output.encode("latin-1")
    return bytes(output)
