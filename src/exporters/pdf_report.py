"""Generate a polished Liquisto briefing PDF."""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.app.use_cases import sanitize_success_unresolved
from src.models.visualization import ChartSpec, DashboardBundle, DashboardSection, InsightCallout, TableBlock
from src.utils import strict_json_dumps

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


def _display_domain(value: str) -> str:
    text = _safe_text(value, "")
    match = re.search(r"https?://[^\s)]+", text)
    if not match:
        return text
    url = match.group(0).rstrip(".,;:")
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    host = host[4:] if host.startswith("www.") else host
    if not host:
        return text
    return text.replace(match.group(0), host)


def _localized_contact_source(value: Any, lang: str) -> str:
    text = _safe_text(value, "—")
    if text == "—":
        return text
    if lang == "de":
        text = _offline_translate_text(text, "de")
    return _display_domain(text)


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
            "run_id": "RunID",
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
            "contact_org": "Organization / Location",
            "contact_channel": "Profile / Channel",
            "contact_source_verification": "Source & Verification",
            "contact_confidence": "Confidence",
            "missing_roles": "Critical missing roles",
            "access_path": "Recommended access path",
            "missing_role_name": "Missing role",
            "missing_role_why": "Why critical",
            "missing_role_area": "Likely org area",
            "missing_role_channel": "Best search channel",
            "open_label": "Label",
            "open_owner_timing": "Owner / Timing",
            "open_impact": "Decision impact",
            "step_phase": "Phase",
            "step_owner": "Owner",
            "step_action": "Action",
            "step_output": "Hypothesis / output / done",
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
        "snapshot": "Management-Übersicht",
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
        "stakeholder_section": "Ansprechpartner-Übersicht",
        "target_contacts": "Kontakte im Zielunternehmen",
        "buyer_contacts": "Käufer- und Partnerkontakte",
        "contact_role": "Rolle",
        "contact_company": "Firma",
        "contact_angle": "Gesprächseinstieg",
        "confidence": "Sicherheit",
        "primary_path": "Hauptpfad",
        "research_score": "Recherchewert",
        "run_id": "RunID",
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
        "contact_org": "Organisation / Standort",
        "contact_channel": "Profil / Kanal",
        "contact_source_verification": "Quelle & Verifikation",
        "contact_confidence": "Sicherheitsgrad",
        "missing_roles": "Fehlende Schlüsselrollen",
        "access_path": "Empfohlener Zugangspfad",
        "missing_role_name": "Fehlende Rolle",
        "missing_role_why": "Warum kritisch",
        "missing_role_area": "Wahrscheinlicher Bereich",
        "missing_role_channel": "Bester Suchkanal",
        "open_label": "Label",
        "open_owner_timing": "Verantwortlich / Zeitpunkt",
        "open_impact": "Entscheidungswirkung",
        "step_phase": "Phase",
        "step_owner": "Verantwortlich",
        "step_action": "Aktion",
        "step_output": "Hypothese / Ergebnis / Abschluss",
        "inventory": "Inventar",
        "ebit": "EBIT",
        "net_loss": "Nettoverlust",
        "write_downs": "Wertberichtigungen",
        "net_debt": "Nettoverschuldung",
        "working_capital": "Nettoumlaufvermögen",
        "open_value": "Offen",
        "coverage": "Abdeckung",
    }


_OFFLINE_EXACT_TRANSLATIONS = {
    "de": {
        "Manufacturing": "Fertigung",
        "Mechanical Engineering": "Maschinenbau",
        "over 1 billion EUR (2025)": "über 1 Milliarde EUR (2025)",
        "growing": "wachsend",
        "axial fans — manufactured": "Axialventilatoren — hergestellt",
        "centrifugal fans — manufactured": "Radialventilatoren — hergestellt",
        "frequency inverters — manufactured": "Frequenzumrichter — hergestellt",
        "active harmonic filters — manufactured": "Aktive Oberschwingungsfilter — hergestellt",
        "Workforce increased from 5,300 to 5,800 employees recently.": "Die Belegschaft stieg zuletzt von 5.300 auf 5.800 Mitarbeitende.",
        "There is no public evidence of restructuring, layoffs, insolvency, or inventory write-downs.": "Es gibt keine öffentlichen Hinweise auf Restrukturierung, Entlassungen, Insolvenz oder Abwertungen auf Bestände.",
        "The company supplies electric in-wheel hub drives (ZAwheel) integrated into city buses used for urban transport.": "Das Unternehmen liefert elektrische Radnabenantriebe (ZAwheel), die in Stadtbussen für den urbanen Verkehr eingesetzt werden.",
        "ZIEHL-ABEGG is a privately held company that does not publicly disclose detailed consolidated financial statements including balance sheet, net debt, or inventory write-downs.": "ZIEHL-ABEGG ist ein privat geführtes Unternehmen und veröffentlicht keine detaillierten konsolidierten Abschlüsse mit Bilanz, Nettoverschuldung oder Bestandsabwertungen.",
        "This geographic shift in demand underscores the importance of tailored regional demand forecasting and inventory management.": "Diese geografische Nachfrageverschiebung unterstreicht die Bedeutung einer regional zugeschnittenen Nachfrageprognose und Bestandssteuerung.",
        "Too few financial datapoints extracted": "Zu wenige Finanzdaten extrahiert",
        "No inventory positions extracted": "Keine Inventarpositionen extrahiert",
        "No balance-sheet signals extracted": "Keine Bilanzsignale extrahiert",
        "Head of Supply Chain / Material Management DACH / EU": "Leitung Lieferkette / Materialmanagement DACH / EU",
        "Head of Procurement / Purchasing": "Leitung Einkauf / Beschaffung",
        "Plant Lead Poland": "Werkleitung Polen",
        "Plant Lead Kupferzell / Germany": "Werkleitung Kupferzell / Deutschland",
        "Only publicly evidenced named stakeholders are listed; no placeholder email addresses or phone numbers are generated.": "Es werden nur öffentlich belegte, namentliche Ansprechpartner aufgeführt; Platzhalter-E-Mail-Adressen oder Telefonnummern werden nicht erzeugt.",
        "The current map is strongest at the executive level around": "Die aktuelle Übersicht ist auf Ebene der Geschäftsleitung am stärksten rund um",
        "The remaining operational gaps are:": "Die verbleibenden operativen Lücken sind:",
        "Close these roles before any cold outreach sequence is written.": "Schließen Sie diese Rollen, bevor eine Cold-Outreach-Sequenz ausgearbeitet wird.",
        "specialized fans — manufactured": "Spezialventilatoren — hergestellt",
        "elevator machines — manufactured": "Aufzugsmaschinen — hergestellt",
        "electromotors — manufactured": "Elektromotoren — hergestellt",
        "control technology products (e.g., active harmonic filters) — manufactured": "Regeltechnik-Produkte (z. B. aktive Oberschwingungsfilter) — hergestellt",
        "sensors for in-house controllers — manufactured": "Sensoren für interne Steuerungen — hergestellt",
        "drive technology components — manufactured": "Antriebstechnik-Komponenten — hergestellt",
        "Repair and refurbishment services for used or": "Reparatur- und Aufbereitungsleistungen für gebrauchte oder",
        "Retrofit and upgrade solutions for existing": "Retrofit- und Upgrade-Lösungen für bestehende",
        "Repurposing used motors and fans for": "Weiterverwendung gebrauchter Motoren und Ventilatoren für",
        "Refurbishing and reselling components for use in": "Aufbereitung und Weiterverkauf von Komponenten zur Nutzung in",
        "Integration of electric drive technology into": "Integration von elektrischer Antriebstechnik in",
        "Utilizing control technology platforms for new": "Nutzung von Regeltechnik-Plattformen für neue",
        "No validated repurposing path is available yet.": "Es liegt noch kein validierter Weiterverwendungspfad vor.",
        "new industrial automation or HVAC system": "neue industrielle Automatisierungs- oder HLK-Systeme",
        "Service / Retrofit": "Service / Nachrüstung",
        "Supply-Chain": "Lieferkette",
        "Revenue growth of": "Umsatzwachstum von",
        "Revenue decline of approximately": "Umsatzrückgang von etwa",
        "Revenue exceeds": "Umsatz übersteigt",
        "growth over": "Wachstum von über",
        "year-on-year": "im Jahresvergleich",
        "Opening of new": "Eröffnung eines neuen",
        "manufacturing hub": "Fertigungsstandorts",
        "Addition of more than": "Aufstockung um mehr als",
        "temporary workers": "Zeitarbeitskräfte",
        "Close the operational contact gap around": "Schließen Sie die operative Kontaktlücke rund um",
        "via Sales Navigator, assistant, and switchboard routes before or immediately after first response.": "über LinkedIn-Recherche, Assistenz- und Zentralenpfade vor oder unmittelbar nach der ersten Rückmeldung.",
        "Will ask für quantified working-capital impact und a low-friction first step.": "Wird nach quantifiziertem Working-Capital-Effekt und einem niedrigschwelligen ersten Schritt fragen.",
        "Prepare a hypothesis-led executive outreach for": "Bereiten Sie eine hypothesenbasierte Ansprache der Geschäftsleitung vor für",
        "that frames Liquisto as an analytics and visibility wedge, not as a generic inventory vendor.": "die Liquisto als Analytik- und Transparenzhebel positioniert und nicht als generischen Bestandsanbieter.",
        "Validate the five critical questions in sequence: visibility gap, steering rhythm, data access, segmentation, and decision ownership especially in the Polish plant footprint.": "Validieren Sie die fünf kritischen Fragen in Reihenfolge: Transparenzlücke, Steuerungsrhythmus, Datenzugang, Segmentierung und Entscheidungshoheit, insbesondere im polnischen Werksverbund.",
        "The first meeting can convert the case from directional interest into a qualified monetization or analytics opportunity.": "Das erste Gespräch kann den Fall von grundsätzlichem Interesse in eine qualifizierte Monetarisierungs- oder Analytik-Chance überführen.",
        "Convert the first meeting into a qualification gate for a real analytics pilot or visibility diagnostic.": "Überführen Sie das erste Gespräch in ein Qualifizierungsgate für einen realen Analytik-Piloten oder eine Transparenzdiagnose.",
        "At least one operational owner or named escalation route is documented for follow-up.": "Für das Follow-up ist mindestens ein operativer Verantwortlicher oder ein benannter Eskalationspfad dokumentiert.",
        "Germany": "Deutschland",
        "Poland": "Polen",
        "Chief Financial Officer (CFO)": "Finanzvorstand (CFO)",
        "Chief Executive Officer (CEO)": "Vorstandsvorsitzender (CEO)",
        "Chief Technology Officer (CTO)": "Technikvorstand (CTO)",
        "Executive Vice President of Operations": "Leiter Operations",
        "Press contact": "Pressekontakt",
        "inferred": "abgeleitet",
        "Conservative output — synthesis incomplete.": "Konservative Ausgabe – Synthese unvollständig.",
        "Synthesis did not complete within max_round.": "Synthese wurde innerhalb der max_round nicht abgeschlossen.",
        "Synthesis was not accepted by the Supervisor gate.": "Die Synthese wurde vom Supervisor-Gate nicht akzeptiert.",
        "Economic pressure signals and buyer-path evidence indicate potential excess asset disposition needs.": "Finanzielle Drucksignale und Buyer-Pfad-Evidenz deuten auf potenziellen Bedarf zum Abbau von Überbeständen hin.",
        "Operational visibility, planning, or balance-sheet complexity indicates analytics leverage.": "Operative Transparenz, Planungsprobleme oder Bilanzkomplexität sprechen für einen Analytics-Hebel.",
        "Strong excess inventory opportunity.": "Starke Chance im Bereich Überbestände.",
        "Economic buyer": "Wirtschaftlicher Entscheider",
        "Economic buyer for working-capital topics.": "Wirtschaftlicher Entscheider für Working-Capital-Themen.",
        "Procurement gatekeeper": "Einkaufs-Gatekeeper",
        "Operational sponsor": "Operativer Sponsor",
        "Aftermarket owner": "Aftermarket-Verantwortlicher",
        "Technical owner": "Technischer Verantwortlicher",
        "Executive sponsor": "Top-Management-Sponsor",
        "Stakeholder": "Ansprechpartner",
        "Company or public web source": "Unternehmens- oder öffentliche Webquelle",
        "Public source": "Öffentliche Quelle",
        "Verified": "Verifiziert",
        "Partially verified": "Teilweise verifiziert",
        "Partially verified via company source": "Teilweise verifiziert über Unternehmensquelle",
        "Role inferred from public company evidence.": "Rolle aus öffentlichen Unternehmensquellen abgeleitet.",
        "Inventory Volume": "Bestandsvolumen",
        "Standardization": "Standardisierung",
        "WIP Stage": "WIP-Stadium",
        "Governance": "Governance",
        "Decision Owner": "Entscheider",
        "Visibility Gap": "Transparenzlücke",
        "Repurposing Fit": "Weiterverwendungs-Fit",
        "What is the current slow-moving inventory volume?": "Wie hoch ist das aktuelle Volumen langsam drehender Bestände?",
        "Determines commercial size.": "Bestimmt die kommerzielle Größenordnung.",
        "Excess inventory is material.": "Überbestände sind materiell relevant.",
        "Decides whether Liquisto should lead with inventory-to-cash.": "Entscheidet, ob Liquisto mit Inventory-to-Cash führen sollte.",
        "Prepare CFO-first outreach": "CFO-zentrierte Ansprache vorbereiten",
        "Secure executive sponsor": "Executive Sponsor sichern",
        "Tailored outreach note": "Individuell zugeschnittene Outreach-Nachricht",
        "Meeting invitation sent": "Gesprächseinladung versendet",
        "Named sponsor exists": "Benannter Unterstützer vorhanden",
        "Liquisto Account Lead": "Liquisto Account Lead",
        "Liquisto SDR / Research": "Liquisto SDR / Research",
        "Liquisto Commercial": "Liquisto Commercial",
        "Analytics": "Analytik",
        "analytics": "Analytik",
        "Working Capital": "Nettoumlaufvermögen",
        "working capital": "Nettoumlaufvermögen",
        "Working-Capital": "Nettoumlaufvermögen",
        "working-capital": "Nettoumlaufvermögen",
        "Supply Chain": "Lieferkette",
        "supply chain": "Lieferkette",
        "Procurement": "Einkauf",
        "procurement": "Einkauf",
        "Executive": "Geschäftsleitung",
        "Aftermarket": "Servicegeschäft",
        "Owner": "Verantwortlich",
        "Done": "Abschluss",
        "email addresses": "E-Mail-Adressen",
        "phone numbers": "Telefonnummern",
        "Key decision-maker for financial and working-capital topics.": "Zentraler Entscheider für Finanz- und Working-Capital-Themen.",
        "Ultimate operational decision-maker, sponsor for efficiency projects.": "Oberster operativer Entscheider und Sponsor für Effizienzprojekte.",
        "Key decision-maker for financial and working-capital initiatives": "Zentraler Entscheider für Finanz- und Working-Capital-Initiativen",
        "Ultimate operational decision-maker, sponsor for efficiency projects": "Oberster operativer Entscheider und Sponsor für Effizienzprojekte",
    },
    "en": {
        "Fertigung": "Manufacturing",
        "Maschinenbau": "Mechanical Engineering",
        "Konservative Ausgabe – Synthese unvollständig.": "Conservative output — synthesis incomplete.",
        "Synthese wurde innerhalb der max_round nicht abgeschlossen.": "Synthesis did not complete within max_round.",
        "Die Synthese wurde vom Supervisor-Gate nicht akzeptiert.": "Synthesis was not accepted by the Supervisor gate.",
        "Starke Chance im Bereich Überbestände.": "Strong excess inventory opportunity.",
        "Wirtschaftlicher Entscheider": "Economic buyer",
        "Wirtschaftlicher Entscheider für Working-Capital-Themen.": "Economic buyer for working-capital topics.",
        "Einkaufs-Gatekeeper": "Procurement gatekeeper",
        "Operativer Sponsor": "Operational sponsor",
        "Aftermarket-Verantwortlicher": "Aftermarket owner",
        "Technischer Verantwortlicher": "Technical owner",
        "Top-Management-Sponsor": "Executive sponsor",
        "Unternehmens- oder öffentliche Webquelle": "Company or public web source",
        "Öffentliche Quelle": "Public source",
        "Verifiziert": "Verified",
        "Teilweise verifiziert": "Partially verified",
        "Teilweise verifiziert über Unternehmensquelle": "Partially verified via company source",
        "Rolle aus öffentlichen Unternehmensquellen abgeleitet.": "Role inferred from public company evidence.",
        "Bestandsvolumen": "Inventory Volume",
        "Standardisierung": "Standardization",
        "WIP-Stadium": "WIP Stage",
        "Governance": "Governance",
        "Entscheider": "Decision Owner",
        "Transparenzlücke": "Visibility Gap",
        "Weiterverwendungs-Fit": "Repurposing Fit",
        "Wie hoch ist das aktuelle Volumen langsam drehender Bestände?": "What is the current slow-moving inventory volume?",
        "Bestimmt die kommerzielle Größenordnung.": "Determines commercial size.",
        "Überbestände sind materiell relevant.": "Excess inventory is material.",
        "Entscheidet, ob Liquisto mit Inventory-to-Cash führen sollte.": "Decides whether Liquisto should lead with inventory-to-cash.",
        "CFO-zentrierte Ansprache vorbereiten": "Prepare CFO-first outreach",
        "Executive Sponsor sichern": "Secure executive sponsor",
        "Individuell zugeschnittene Outreach-Nachricht": "Tailored outreach note",
        "Meeting-Einladung versendet": "Meeting invitation sent",
        "Benannter Sponsor vorhanden": "Named sponsor exists",
    },
}


def _offline_translate_text(text: str, target_lang: str) -> str:
    rendered = str(text or "")
    if not rendered.strip():
        return rendered

    exact = _OFFLINE_EXACT_TRANSLATIONS.get(target_lang, {})
    if rendered in exact:
        return exact[rendered]

    replacements = (
        [
            ("Chief Financial Officer (CFO)", "Finanzvorstand (CFO)"),
            ("Chief Executive Officer (CEO)", "Vorstandsvorsitzender (CEO)"),
            ("Chief Technology Officer (CTO)", "Technikvorstand (CTO)"),
            ("Executive Vice President of Operations", "Leiter Operations"),
            ("Press contact", "Pressekontakt"),
            ("Germany", "Deutschland"),
            ("Poland", "Polen"),
            ("inferred", "abgeleitet"),
            ("Economic buyer", "Wirtschaftlicher Entscheider"),
            ("Procurement gatekeeper", "Einkaufs-Gatekeeper"),
            ("Operational sponsor", "Operativer Sponsor"),
            ("Aftermarket owner", "Aftermarket-Verantwortlicher"),
            ("Technical owner", "Technischer Verantwortlicher"),
            ("Executive sponsor", "Top-Management-Sponsor"),
            ("Executive Board Member", "Mitglied der Geschäftsleitung"),
            ("Executive leadership", "Geschäftsleitung"),
            ("Financial leadership", "Finanzleitung"),
            ("Procurement / Supply Chain", "Einkauf / Lieferkette"),
            ("Working Capital", "Nettoumlaufvermögen"),
            ("working capital", "Nettoumlaufvermögen"),
            ("Supply Chain", "Lieferkette"),
            ("supply chain", "Lieferkette"),
            ("Material Management", "Materialmanagement"),
            ("Procurement", "Einkauf"),
            ("procurement", "Einkauf"),
            ("Purchasing", "Beschaffung"),
            ("Head of ", "Leitung "),
            ("Plant Lead ", "Werkleitung "),
            ("Analytics", "Analytik"),
            ("analytics", "Analytik"),
            ("Aftermarket", "Servicegeschäft"),
            ("LinkedIn Sales Navigator", "LinkedIn-Recherche"),
            ("Sales Navigator", "LinkedIn-Recherche"),
            ("company leadership pages", "Unternehmensführungsseiten"),
            ("assistant", "Assistenz"),
            ("switchboard", "Zentrale"),
            ("manufactured", "hergestellt"),
            ("growing", "wachsend"),
            ("over 1 billion EUR (2025)", "über 1 Milliarde EUR (2025)"),
            ("Workforce increased from 5,300 to 5,800 employees recently.", "Die Belegschaft stieg zuletzt von 5.300 auf 5.800 Mitarbeitende."),
            ("The company ", "Das Unternehmen "),
            ("There is no public evidence of restructuring, layoffs, insolvency, or inventory write-downs.", "Es gibt keine öffentlichen Hinweise auf Restrukturierung, Entlassungen, Insolvenz oder Abwertungen auf Bestände."),
            ("Overall, ZIEHL-ABEGG faces supply pressure from regional demand imbalances but is positioned to leverage growth in emerging markets and new capacity investments.", "Insgesamt steht ZIEHL-ABEGG unter Angebotsdruck durch regionale Nachfrageungleichgewichte, ist aber gut positioniert, um Wachstum in aufstrebenden Märkten und neue Kapazitätsinvestitionen zu nutzen."),
            ("ZIEHL-ABEGG is a privately held company that does not publicly disclose detailed consolidated financial statements including balance sheet, net debt, or inventory write-downs.", "ZIEHL-ABEGG ist ein privat geführtes Unternehmen und veröffentlicht keine detaillierten konsolidierten Abschlüsse mit Bilanz, Nettoverschuldung oder Bestandsabwertungen."),
            ("This geographic shift in demand underscores the importance of tailored regional demand forecasting and inventory management.", "Diese geografische Nachfrageverschiebung unterstreicht die Bedeutung einer regional zugeschnittenen Nachfrageprognose und Bestandssteuerung."),
            ("Too few financial datapoints extracted", "Zu wenige Finanzdaten extrahiert"),
            ("No inventory positions extracted", "Keine Inventarpositionen extrahiert"),
            ("No balance-sheet signals extracted", "Keine Bilanzsignale extrahiert"),
            ("conference mentions", "Konferenznennungen"),
            ("email addresses", "E-Mail-Adressen"),
            ("phone numbers", "Telefonnummern"),
            ("Owner / Timing", "Verantwortlich / Zeitpunkt"),
            ("Owner", "Verantwortlich"),
            ("Hypothesis / output / done", "Hypothese / Ergebnis / Abschluss"),
            ("Done", "Abschluss"),
            ("Company or public web source", "Unternehmens- oder öffentliche Webquelle"),
            ("Public source", "Öffentliche Quelle"),
            ("Press contact:", "Pressekontakt:"),
            ("Verified via ", "Verifiziert über "),
            ("Partially verified via ", "Teilweise verifiziert über "),
            (" via ", " über "),
            (" and ", " und "),
            (" for ", " für "),
            (" with ", " mit "),
            (" from ", " von "),
            (" into ", " in "),
            (" before ", " vor "),
            (" after ", " nach "),
            (" around ", " rund um "),
            (" through ", " durch "),
            ("meeting", "Gespräch"),
            ("Meeting", "Gespräch"),
            ("stakeholder", "Ansprechpartner"),
            ("Stakeholder", "Ansprechpartner"),
            ("sponsor", "Unterstützer"),
            ("Sponsor", "Unterstützer"),
            ("dashboard", "Übersicht"),
            ("Dashboard", "Übersicht"),
            ("phase", "Abschnitt"),
            ("Phase", "Abschnitt"),
            ("systems", "Systeme"),
            ("Systems", "Systeme"),
            ("repair", "Reparatur"),
            ("Repair", "Reparatur"),
            ("refurbishment", "Aufbereitung"),
            ("Refurbishment", "Aufbereitung"),
            ("refurbishing", "Aufbereitung"),
            ("Refurbishing", "Aufbereitung"),
            ("reselling", "Weiterverkauf"),
            ("Reselling", "Weiterverkauf"),
            ("components", "Komponenten"),
            ("Components", "Komponenten"),
            ("integration of", "Integration von"),
            ("Integration of", "Integration von"),
            ("utilizing", "Nutzung von"),
            ("Utilizing", "Nutzung von"),
            ("visibility", "Transparenz"),
            ("Visibility", "Transparenz"),
            ("Opening of new ", "Eröffnung eines neuen "),
            ("new vehicles, elevators, und industrial equipment", "neue Fahrzeuge, Aufzüge und Industrieausrüstung"),
            ("technologies to industrial partners", "Technologien für Industriepartner"),
            ("secondary industrial applications or less", "sekundäre industrielle Anwendungen oder geringer"),
            ("new industrial automation or HVAC system", "neue industrielle Automatisierungs- oder HLK-Systeme"),
            ("control technology platforms", "Regeltechnik-Plattformen"),
            ("adjacent markets such as medical equipment or", "benachbarte Märkte wie Medizintechnik oder"),
            (" to improve energy", " zur Verbesserung der Energieeffizienz"),
            ("repurposing", "Weiterverwendung"),
            ("Repurposing", "Weiterverwendung"),
            ("retrofit", "Nachrüstung"),
            ("Retrofit", "Nachrüstung"),
            ("upgrade", "Nachrüstung"),
            ("Upgrade", "Nachrüstung"),
            ("existing", "bestehende"),
            ("Existing", "Bestehende"),
            ("Supply-Chain", "Lieferkette"),
            ("equipment", "Ausrüstung"),
            ("applications", "Anwendungen"),
            ("Key decision-maker for financial and working-capital topics.", "Zentraler Entscheider für Finanz- und Working-Capital-Themen."),
            ("Ultimate operational decision-maker, sponsor for efficiency projects.", "Oberster operativer Entscheider und Sponsor für Effizienzprojekte."),
            ("Key decision-maker for financial and working-capital initiatives", "Zentraler Entscheider für Finanz- und Working-Capital-Initiativen"),
            ("Ultimate operational decision-maker, sponsor for efficiency projects", "Oberster operativer Entscheider und Sponsor für Effizienzprojekte"),
            ("Top-down introduction via company switchboard or network.", "Top-down-Einstieg über Zentrale oder bestehendes Netzwerk."),
            ("Relevant for inventory, working capital, or operating-model validation.", "Relevant für die Validierung von Beständen, Working Capital oder Betriebsmodell."),
            ("Prepare a hypothesis-led outreach for ", "Bereiten Sie eine hypothesenbasierte Ansprache für "),
            (" anchored in the leading path `", " vor, verankert im führenden Pfad `"),
            (" and the likely working-capital impact.", "` sowie dem wahrscheinlichen Working-Capital-Effekt."),
            ("Identify the missing operational role `", "Identifizieren Sie die fehlende operative Rolle `"),
            (" and map the best access path before outreach or immediately after first response.", "` und klären Sie den besten Zugangspfad vor dem Outreach oder direkt nach der ersten Rückmeldung."),
            ("Validate the five critical questions in sequence: inventory volume, standardization, WIP stage, governance constraints, and decision ownership.", "Validieren Sie die fünf kritischen Fragen nacheinander: Bestandsvolumen, Standardisierung, WIP-Stadium, Governance-Grenzen und Entscheidungshoheit."),
            ("Send a 24-hour recap with the validated opportunity path, named sponsor, and explicit request for the next operational working session.", "Senden Sie innerhalb von 24 Stunden ein Recap mit validiertem Opportunity-Pfad, benanntem Sponsor und einer expliziten Bitte um den nächsten operativen Arbeitstermin."),
            ("Request a lightweight NDA package with inventory aging, slow movers, WIP segmentation, and any write-down or working-capital views for the affected region.", "Fordern Sie ein schlankes NDA-Paket mit Lageralterung, Slow Movern, WIP-Segmentierung sowie möglichen Wertberichtigungs- oder Working-Capital-Sichten für die betroffene Region an."),
            ("Validate the top buyer categories against CRM and existing network fit before any external buyer outreach begins.", "Validieren Sie die wichtigsten Käuferkategorien gegen CRM und bestehenden Netzwerk-Fit, bevor externer Buyer-Outreach startet."),
            ("Open top-down with ", "Top-down mit "),
            (", then request handoff to the operational owner for inventory, procurement, or plant execution.", " eröffnen, dann Übergabe an den operativen Verantwortlichen für Bestand, Einkauf oder Werksumsetzung anfordern."),
            ("Close the remaining stakeholder gap before outreach by identifying: ", "Schließen Sie die verbleibende Ansprechpartner-Lücke vor dem Outreach durch die Identifikation von: "),
            ("Keep buyer/partner contacts separate from target-company stakeholders; do not mix them in the target-contact section.", "Käufer- und Partnerkontakte getrennt von Zielunternehmens-Ansprechpartnern halten; nicht im Zielkontaktblock mischen."),
            ("What is the current book-value and physical volume of slow-moving or excess inventory at ", "Wie hoch sind aktueller Buchwert und physisches Volumen langsam drehender oder überschüssiger Bestände bei "),
            (", split by site and business line?", ", aufgeschlüsselt nach Standort und Geschäftsbereich?"),
            ("What share of the overhang is standard, resale-capable inventory versus customer-specific OEM configuration?", "Welcher Anteil des Überhangs ist standardisiert und wiederverkaufsfähig im Vergleich zu kundenspezifischen OEM-Konfigurationen?"),
            ("Where is inventory currently stuck most heavily: raw materials, purchased electronics, WIP, or finished goods?", "Wo ist Bestand aktuell am stärksten gebunden: Rohmaterial, zugekaufte Elektronik, WIP oder Fertigware?"),
            ("Which brand, channel, compliance, or customer-conflict rules limit secondary sales, aftermarket resale, or discreet buyer matching?", "Welche Marken-, Kanal-, Compliance- oder Kundenschutzregeln begrenzen Sekundärverkäufe, Aftermarket-Resale oder diskretes Buyer-Matching?"),
            ("Who owns the release decision for excess inventory in Europe, and who can sponsor NDA-based data sharing after the meeting?", "Wer verantwortet in Europa die Freigabeentscheidung für Überbestände, und wer kann nach dem Gespräch ein NDA-basiertes Datenteilen unterstützen?"),
            ("Where does ", "Wo fehlen bei "),
            (" currently lack reliable inventory visibility across plants, regions, or business lines?", " derzeit belastbare Bestands-Transparenz über Werke, Regionen oder Geschäftsbereiche hinweg?"),
            ("Which materials, legacy parts, or subassemblies cannot be sold directly but could be repurposed into adjacent industrial use cases?", "Welche Materialien, Altteile oder Baugruppen lassen sich nicht direkt verkaufen, könnten aber in benachbarte industrielle Use Cases weiterverwendet werden?"),
            ("This determines whether the excess-inventory case is commercially material enough for immediate action.", "Das bestimmt, ob der Excess-Inventory-Case kommerziell relevant genug für unmittelbares Handeln ist."),
            ("This defines whether analytics should be the commercial entry point.", "Das definiert, ob Analytics der kommerzielle Einstiegshebel sein sollte."),
            ("This decides whether redeployment can happen quickly or only via selective channels.", "Das entscheidet, ob Weiterverwendung schnell oder nur über selektive Kanäle möglich ist."),
            ("The optimal monetization path differs completely by asset maturity and material state.", "Der optimale Monetarisierungspfad unterscheidet sich grundlegend nach Asset-Reife und Materialzustand."),
            ("Commercial feasibility depends on whether management allows controlled external monetization.", "Die kommerzielle Umsetzbarkeit hängt davon ab, ob das Management eine kontrollierte externe Monetarisierung zulässt."),
            ("Without a named operational sponsor, the opportunity will stall after an encouraging first discussion.", "Ohne benannten operativen Sponsor wird die Opportunity nach einem guten Erstgespräch ins Stocken geraten."),
            ("Repurposing only works if non-standard stock still has technical and commercial reuse value.", "Weiterverwendung funktioniert nur, wenn nicht standardisierter Bestand noch technischen und kommerziellen Wiederverwendungswert hat."),
            ("There is enough trapped working capital to justify a monetization mandate.", "Es ist genug gebundenes Working Capital vorhanden, um ein Monetarisierungsmandat zu rechtfertigen."),
            ("A meaningful portion of stock is transferable to secondary OEM or aftermarket demand.", "Ein relevanter Teil des Bestands lässt sich in sekundäre OEM- oder Aftermarket-Nachfrage überführen."),
            ("The overhang can be segmented into discrete pools with different liquidation routes.", "Der Überhang lässt sich in getrennte Bestandscluster mit unterschiedlichen Liquidationswegen segmentieren."),
            ("The company can monetize excess stock without damaging premium positioning or OEM relationships.", "Das Unternehmen kann Überbestände monetarisieren, ohne Premium-Positionierung oder OEM-Beziehungen zu beschädigen."),
            ("A reachable owner exists who can move from discussion to data room and pilot scope.", "Es gibt einen erreichbaren Verantwortlichen, der von der Diskussion in einen Datenraum- und Pilotumfang überführen kann."),
            ("A circularity-led path can absorb inventory that direct buyers cannot take.", "Ein zirkularitätsgetriebener Pfad kann Bestand aufnehmen, den direkte Käufer nicht übernehmen."),
            ("Confirms whether Liquisto should lead with inventory-to-cash rather than analytics-only positioning.", "Bestätigt, ob Liquisto eher mit Inventory-to-Cash statt nur mit Analytics-Positionierung führen sollte."),
            ("Confirms whether Liquisto", "Bestätigt, ob Liquisto"),
            ("Changes buyer targeting, discount logic, and expected conversion speed.", "Verändert Buyer-Targeting, Rabattlogik und erwartete Konversionsgeschwindigkeit."),
            ("Determines whether Liquisto pitches finished-goods redeployment, component brokerage, or circularity routes first.", "Bestimmt, ob Liquisto zuerst Fertigwaren-Weiterverwendung, Komponenten-Brokerage oder Zirkularitätswege pitchen sollte."),
            ("Determines whether Liquisto", "Bestimmt, ob Liquisto"),
            ("Defines which buyer categories and go-to-market mechanics are viable.", "Definiert, welche Käuferkategorien und Go-to-Market-Mechaniken tragfähig sind."),
            ("Determines whether Liquisto can progress directly to post-meeting data collection.", "Bestimmt, ob Liquisto direkt in die Datensammlung nach dem Gespräch übergehen kann."),
            ("Enter the meeting with a credible commercial narrative instead of a generic inventory pitch.", "Mit einer glaubwürdigen kommerziellen Story statt mit einem generischen Inventory-Pitch ins Gespräch gehen."),
            ("One tailored opening message and a 3-point meeting narrative.", "Eine zugeschnittene Eröffnungsnachricht und eine 3-Punkte-Gesprächs-Story."),
            ("The opening clearly links stock release to the stakeholder's agenda.", "Die Ansprache verknüpft Bestandsfreisetzung klar mit der Agenda des Ansprechpartners."),
            ("Target-company sponsor identified", "Unterstützer im Zielunternehmen identifiziert"),
            ("Avoid single-threaded outreach into CEO/CFO only.", "Vermeidet ein eindimensionales Outreach nur an CEO/CFO."),
            ("Named operational stakeholder or explicit switchboard/escalation path.", "Benannter operativer Ansprechpartner oder expliziter Zentrale-/Eskalationspfad."),
            ("At least one operational sponsor below the executive level is identified.", "Mindestens ein operativer Unterstützer unterhalb der Geschäftsleitung ist identifiziert."),
            ("LinkedIn / public-contact search", "LinkedIn- / Public-Contact-Recherche"),
            ("Convert the first meeting into a qualification gate for a real inventory monetization or analytics project.", "Das erste Gespräch in ein Qualifizierungsgate für ein echtes Inventory-Monetization- oder Analytics-Projekt überführen."),
            ("Structured answers that confirm or disprove the lead hypothesis.", "Strukturierte Antworten, die die Leit-Hypothese bestätigen oder widerlegen."),
            ("At least three of the five questions are answered with concrete operational detail.", "Mindestens drei der fünf Fragen werden mit konkretem operativem Detail beantwortet."),
            ("Meeting secured", "Gespräch gesichert"),
            ("Turn meeting momentum into a committed follow-up step.", "Gesprächs-Momentum in einen verbindlichen Folgeschritt überführen."),
            ("Recap email with agreed next call, stakeholder list, and validation summary.", "Recap-E-Mail mit vereinbartem Folgetermin, Ansprechpartner-Liste und Validierungszusammenfassung."),
            ("A follow-up meeting or data-review slot is scheduled.", "Ein Follow-up-Gespräch oder Datenreview-Termin ist angesetzt."),
            ("Positive first meeting", "Positives Erstgespräch"),
            ("Move from hypothesis to quantified deal sizing.", "Von der Hypothese zur quantifizierten Deal-Bewertung übergehen."),
            ("Structured data extract suitable for buyer matching or inventory diagnostics.", "Strukturierter Datenextrakt, geeignet für Buyer-Matching oder Bestandsdiagnostik."),
            ("Data package received or explicitly approved for transfer.", "Datenpaket erhalten oder explizit zur Übergabe freigegeben."),
            ("Named operational owner and NDA approval", "Benannter operativer Verantwortlicher und NDA-Freigabe"),
            ("Keep redeployment outreach tightly matched to asset fit and channel constraints.", "Weiterverwendungs-Outreach eng an Asset-Fit und Kanalrestriktionen ausrichten."),
            ("Shortlisted buyer lanes with CRM overlap and exclusion rules.", "Shortlist der Käuferpfade mit CRM-Überlappung und Ausschlussregeln."),
            ("Only buyer categories with verified asset-fit remain in the plan.", "Nur Käuferkategorien mit verifiziertem Asset-Fit verbleiben im Plan."),
            ("Meeting confirms monetizable stock exists", "Gespräch bestätigt monetarisierbaren Bestand"),
        ]
        if target_lang == "de"
        else [
            ("Wirtschaftlicher Entscheider", "Economic buyer"),
            ("Einkaufs-Gatekeeper", "Procurement gatekeeper"),
            ("Operativer Sponsor", "Operational sponsor"),
            ("Aftermarket-Verantwortlicher", "Aftermarket owner"),
            ("Technischer Verantwortlicher", "Technical owner"),
            ("Top-Management-Sponsor", "Executive sponsor"),
            ("Unternehmens- oder öffentliche Webquelle", "Company or public web source"),
            ("Öffentliche Quelle", "Public source"),
            ("Verifiziert über ", "Verified via "),
            ("Teilweise verifiziert über ", "Partially verified via "),
            ("Top-down-Einstieg über Zentrale oder bestehendes Netzwerk.", "Top-down introduction via company switchboard or network."),
            ("Mit einer glaubwürdigen kommerziellen Story statt mit einem generischen Inventory-Pitch ins Meeting gehen.", "Enter the meeting with a credible commercial narrative instead of a generic inventory pitch."),
        ]
    )
    for source, target in replacements:
        rendered = rendered.replace(source, target)
    return rendered


def _offline_translate_obj(value: Any, target_lang: str) -> Any:
    if isinstance(value, dict):
        return {key: _offline_translate_obj(item, target_lang) for key, item in value.items()}
    if isinstance(value, list):
        return [_offline_translate_obj(item, target_lang) for item in value]
    if isinstance(value, tuple):
        return tuple(_offline_translate_obj(item, target_lang) for item in value)
    if isinstance(value, str):
        return _offline_translate_text(value, target_lang)
    return value


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

def _make_header_footer(page_label: str, _report_title: str):  # noqa: ANN001
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
        canvas.setFillColor(TEXT_MUTED)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(PAGE_WIDTH - doc.rightMargin, PAGE_HEIGHT - 9 * mm, f"{page_label} {doc.page}")
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.6)
        canvas.line(doc.leftMargin, 11 * mm, PAGE_WIDTH - doc.rightMargin, 11 * mm)
        canvas.restoreState()
    return _header_footer


# ── cover ─────────────────────────────────────────────────────────────────────

def _cover_block(
    company_name: str,
    subtitle: str,
    prepared_for: str,
    date_label: str,
    run_id_label: str,
    run_id: str,
    styles: dict[str, ParagraphStyle],
) -> Table:
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
        Paragraph(
            (
                f"<b>{company_name}</b><br/>{subtitle}<br/>"
                f"<font size='9' color='#4A5E60'>{prepared_for} · {date_label}: {date_str} · {run_id_label}: {run_id}</font>"
            ),
            styles["title"],
        )
    ], [accent_strip]]
    table = Table(content, colWidths=[170 * mm])
    table.setStyle(TableStyle([
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


def _resolve_run_id(pipeline_data: dict[str, Any]) -> str:
    direct = _safe_text(pipeline_data.get("run_id"), "")
    if direct and direct not in {"n/v", "n/a"}:
        return direct
    final_briefing = pipeline_data.get("final_briefing") or {}
    if isinstance(final_briefing, dict):
        nested = _safe_text(final_briefing.get("run_id"), "")
        if nested and nested not in {"n/v", "n/a"}:
            return nested
    metadata = pipeline_data.get("metadata") or {}
    if isinstance(metadata, dict):
        nested = _safe_text(metadata.get("run_id"), "")
        if nested and nested not in {"n/v", "n/a"}:
            return nested
    return "n/v"


_FINANCE_SIGNAL_TOKENS = (
    "revenue",
    "umsatz",
    "ebit",
    "ebitda",
    "net debt",
    "netto",
    "loss",
    "verlust",
    "inventory",
    "inventar",
    "bestand",
    "write-down",
    "wertberichtigung",
    "working capital",
    "umlaufverm",
    "balance sheet",
    "bilanz",
    "cash",
    "mio",
    "million",
    "bn",
    "billion",
    "eur",
    "%",
)

_NON_FINANCE_SIGNAL_TOKENS = (
    "analytics",
    "analytik",
    "transparenz",
    "transparency",
    "ai",
    "daten",
    "data",
    "platform",
    "plattform",
    "reporting",
    "forecast",
    "prognose",
)

_FINANCE_HARD_SIGNAL_TOKENS = (
    "revenue",
    "umsatz",
    "ebit",
    "ebitda",
    "net debt",
    "nette debt",
    "verlust",
    "loss",
    "write-down",
    "wertberichtigung",
    "working capital",
    "umlaufverm",
    "balance sheet",
    "bilanz",
    "cash",
    "liquidit",
)

_INVENTORY_SIGNAL_TOKENS = (
    "inventory",
    "inventar",
    "bestand",
    "lager",
)

_INVENTORY_PRESSURE_TOKENS = (
    "excess",
    "uberhang",
    "überhang",
    "aging",
    "obsolet",
    "abschreibung",
    "write-down",
    "wertberichtigung",
    "capital bind",
    "kapitalbindung",
    "slow-moving",
    "slow moving",
    "reichweite",
    "days inventory",
)


def _is_finance_inventory_signal(text: str) -> bool:
    lower = text.lower()
    has_finance_token = any(token in lower for token in _FINANCE_SIGNAL_TOKENS)
    has_non_finance_token = any(token in lower for token in _NON_FINANCE_SIGNAL_TOKENS)
    has_hard_signal_token = any(token in lower for token in _FINANCE_HARD_SIGNAL_TOKENS)
    has_inventory_token = any(token in lower for token in _INVENTORY_SIGNAL_TOKENS)
    has_inventory_pressure = any(token in lower for token in _INVENTORY_PRESSURE_TOKENS)
    if not has_finance_token:
        return False
    if has_non_finance_token and not has_hard_signal_token and not (has_inventory_token and has_inventory_pressure):
        return False
    if has_hard_signal_token:
        return True
    return has_inventory_token and has_inventory_pressure


def _filter_finance_inventory_signals(values: list[str], *, lang: str) -> list[str]:
    filtered = [item for item in values if _is_finance_inventory_signal(item)]
    if filtered:
        return filtered
    return [
        "No balance-sheet or inventory signal extracted"
        if lang == "en"
        else "Kein belastbares Bilanz- oder Inventarsignal extrahiert"
    ]


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
    signal_texts = [sentence for sentence in _sentence_candidates(texts) if _is_finance_inventory_signal(sentence)]
    signal_source = signal_texts if signal_texts else texts
    open_value = labels.get("open_value", "Open")
    return [
        (labels["revenue_trend"], _truncate(econ.get("revenue_trend"), 72, open_value)),
        (labels["ebit"], _first_matching_sentence(signal_source, [r"\bebit\b"], open_value)),
        (labels["net_loss"], _first_matching_sentence(signal_source, [r"net loss", r"jahresfehlbetrag"], open_value)),
        (labels["write_downs"], _first_matching_sentence(signal_source, [r"write[- ]down", r"impair", r"wertberichtigung"], open_value)),
        (labels["net_debt"], _first_matching_sentence(signal_source, [r"net debt", r"leverage", r"nettoverschuld"], open_value)),
        (labels["working_capital"], _first_matching_sentence(signal_source, [r"working capital", r"net working capital", r"umlaufverm"], open_value)),
        (
            labels["inventory"],
            _first_matching_sentence(
                signal_source,
                [
                    r"(inventory|inventar|vorr|lager|bestand).*(write[- ]down|wertberichtigung|obsolet|aging|slow[- ]moving|capital|uberhang|überhang|reichweite)",
                    r"(write[- ]down|wertberichtigung|obsolet|aging|slow[- ]moving|capital|uberhang|überhang|reichweite).*(inventory|inventar|vorr|lager|bestand)",
                ],
                open_value,
            ),
        ),
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


def _confidence_ampel_color(value: Any) -> colors.Color:
    rendered = _safe_text(value, "").lower()
    if any(token in rendered for token in ("hoch", "high", "verified", "verifiziert")):
        return BRAND_GREEN
    if any(token in rendered for token in ("mittel", "medium", "partial", "teilweise")):
        return BRAND_AMBER
    if any(token in rendered for token in ("niedrig", "low", "unverified", "unverifiziert")):
        return BRAND_RED
    return TEXT_MUTED


def _contact_profile_card(
    *,
    name: Any,
    role: Any,
    organization_location: Any,
    relevance: Any,
    outreach_angle: Any,
    profile_channel: Any,
    source_verification: Any,
    confidence: Any,
    labels: dict[str, str],
    styles: dict[str, ParagraphStyle],
    lang: str,
    likely_objection: Any = "",
) -> Table:
    resolved_name = _safe_text(name, "—")
    resolved_role = _safe_text(role, "—")
    resolved_org = _safe_text(organization_location, "—")
    resolved_relevance = _safe_text(relevance, "—")
    resolved_angle = _safe_text(outreach_angle, "—")
    resolved_channel = _safe_text(profile_channel, "—")
    resolved_source = _safe_text(source_verification, "—")
    resolved_confidence = _safe_text(confidence, "—")
    objection_text = _safe_text(likely_objection, "")
    objection_label = "Likely objection" if lang == "en" else "Wahrscheinlicher Einwand"

    confidence_color = _confidence_ampel_color(resolved_confidence)
    confidence_display = (
        _display_confidence(resolved_confidence, lang)
        if resolved_confidence.lower() in {"high", "medium", "low", "hoch", "mittel", "niedrig"}
        else resolved_confidence
    )

    header_html = (
        f"<b>{resolved_name}</b><br/>"
        f"<font color='#005A9C'><b>{resolved_role}</b></font>"
    )
    org_html = f"<b>{labels['contact_org']}:</b> {resolved_org}"
    body_lines = [
        f"• <b>{labels['contact_relevance']}:</b> {resolved_relevance}",
        f"• <b>{labels['contact_angle']}:</b> {resolved_angle}",
    ]
    if objection_text and objection_text not in {"n/v", "n/a", "—"}:
        body_lines.append(f"• <b>{objection_label}:</b> {objection_text}")
    body_html = "<br/>".join(body_lines)
    footer_html = (
        f"<b>{labels['contact_channel']}:</b> {resolved_channel}<br/>"
        f"<b>{labels['contact_source_verification']}:</b> {resolved_source}"
    )

    confidence_badge = Table(
        [[Paragraph(f"<b>{labels['contact_confidence']}</b><br/>{confidence_display}", styles["small"])]],
        colWidths=[30 * mm],
    )
    confidence_badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _accent_surface(confidence_color)),
        ("BOX", (0, 0), (-1, -1), 0.8, confidence_color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    header_block = Table(
        [[Paragraph(header_html, styles["body"]), confidence_badge]],
        colWidths=[120 * mm, 30 * mm],
    )
    header_block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    card = Table(
        [
            [header_block],
            [Paragraph(org_html, styles["small"])],
            [Paragraph(body_html, styles["body"])],
            [Paragraph(footer_html, styles["small"])],
        ],
        colWidths=[170 * mm],
    )
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F7FAFF")),
        ("BACKGROUND", (0, 1), (-1, 1), WHITE),
        ("BACKGROUND", (0, 2), (-1, 2), SURFACE),
        ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#F9FCFC")),
        ("LINEBEFORE", (0, 0), (0, -1), 4, BRAND_BLUE),
        ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER),
        ("LINEBELOW", (0, 1), (-1, 1), 0.4, BORDER),
        ("LINEBELOW", (0, 2), (-1, 2), 0.4, BORDER),
    ]))
    return card


def _target_contact_cards(
    cards: list[dict[str, Any]],
    labels: dict[str, str],
    styles: dict[str, ParagraphStyle],
    lang: str,
) -> list[Any]:
    flowables: list[Any] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        flowables.append(
            _contact_profile_card(
                name=card.get("name"),
                role=card.get("role"),
                organization_location=card.get("organization_location"),
                relevance=card.get("relevance_buying_center"),
                outreach_angle=card.get("outreach_rationale") or card.get("relevance_buying_center"),
                profile_channel=_localized_contact_source(card.get("profile_contact_channel"), lang),
                source_verification=_localized_contact_source(card.get("source_verification"), lang),
                confidence=card.get("confidence"),
                labels=labels,
                styles=styles,
                lang=lang,
                likely_objection=card.get("likely_objection"),
            )
        )
        flowables.append(Spacer(1, 2.2 * mm))
    if flowables:
        flowables.pop()
    return flowables


def _buyer_contact_cards(
    contacts: list[dict[str, Any]],
    labels: dict[str, str],
    styles: dict[str, ParagraphStyle],
    lang: str,
) -> list[Any]:
    flowables: list[Any] = []
    for contact in contacts:
        if not isinstance(contact, dict):
            continue
        org = " / ".join(
            part for part in [
                _safe_text(contact.get("firma"), ""),
                _safe_text(contact.get("standort"), ""),
            ] if part and part not in {"n/v", "n/a", "—"}
        )
        flowables.append(
            _contact_profile_card(
                name=contact.get("name"),
                role=contact.get("rolle_titel") or contact.get("funktion"),
                organization_location=org or "—",
                relevance=contact.get("relevance_reason") or contact.get("confidence"),
                outreach_angle=contact.get("suggested_outreach_angle") or contact.get("relevance_reason"),
                profile_channel=_localized_contact_source(contact.get("quelle"), lang),
                source_verification=_localized_contact_source(contact.get("quelle"), lang),
                confidence=contact.get("confidence"),
                labels=labels,
                styles=styles,
                lang=lang,
            )
        )
        flowables.append(Spacer(1, 2.2 * mm))
    if flowables:
        flowables.pop()
    return flowables


def _missing_role_cards(
    roles: list[dict[str, Any]],
    labels: dict[str, str],
    styles: dict[str, ParagraphStyle],
    lang: str,
) -> list[Any]:
    flowables: list[Any] = []
    next_action_label = "Next search action" if lang == "en" else "Nächste Suchaktion"
    for role in roles:
        if not isinstance(role, dict):
            continue
        role_name = _safe_text(role.get("role_name"), "—")
        likely_area = _safe_text(role.get("likely_org_area"), "—")
        why_critical = _safe_text(role.get("why_critical"), "—")
        best_channel = _safe_text(role.get("best_search_channel"), "—")
        next_action = _safe_text(role.get("next_search_action"), "—")

        header_html = (
            f"<b>{role_name}</b><br/>"
            f"<font color='#D97706'><b>{labels['missing_role_area']}:</b> {likely_area}</font>"
        )
        body_html = f"• <b>{labels['missing_role_why']}:</b> {why_critical}"
        footer_html = (
            f"<b>{labels['missing_role_channel']}:</b> {best_channel}<br/>"
            f"<b>{next_action_label}:</b> {next_action}"
        )

        card = Table(
            [
                [Paragraph(header_html, styles["body"])],
                [Paragraph(body_html, styles["body"])],
                [Paragraph(footer_html, styles["small"])],
            ],
            colWidths=[170 * mm],
        )
        card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), WHITE),
            ("BACKGROUND", (0, 1), (-1, 1), SURFACE_WARM),
            ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#FFF9F2")),
            ("BOX", (0, 0), (-1, -1), 0.7, BRAND_AMBER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        flowables.append(card)
        flowables.append(Spacer(1, 2.2 * mm))
    if flowables:
        flowables.pop()
    return flowables


def _open_question_table(questions: list[dict[str, Any]], labels: dict[str, str],
                         styles: dict[str, ParagraphStyle], lang: str) -> Table:
    data = [[
        Paragraph(f"<b>{labels['open_label']}</b>", styles["table_header"]),
        Paragraph(f"<b>{labels['open_questions']}</b>", styles["table_header"]),
        Paragraph(f"<b>{labels['open_owner_timing']}</b>", styles["table_header"]),
        Paragraph(f"<b>{labels['open_impact']}</b>", styles["table_header"]),
    ]]
    for item in questions:
        if not isinstance(item, dict):
            continue
        owner_timing = " / ".join(
            part for part in [
                _safe_text(item.get("owner"), ""),
                _phase_label(str(item.get("timing", "")), lang),
            ] if part
        )
        data.append([
            Paragraph(_safe_text(item.get("label"), "—"), styles["table_cell"]),
            Paragraph(_safe_text(item.get("question"), "—"), styles["table_cell"]),
            Paragraph(_safe_text(owner_timing, "—"), styles["table_cell"]),
            Paragraph(_safe_text(item.get("decision_impact"), "—"), styles["table_cell"]),
        ])
    if len(data) == 1:
        data.append([Paragraph("—", styles["table_cell"])] * 4)
    table = Table(data, colWidths=[24 * mm, 72 * mm, 30 * mm, 44 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_RED),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SURFACE]),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _phase_label(value: str, lang: str) -> str:
    mapping = {
        "en": {
            "pre_meeting": "Pre-meeting",
            "during_meeting": "During meeting",
            "post_meeting": "Post-meeting",
            "post_meeting_under_nda": "Post-meeting under NDA",
        },
        "de": {
            "pre_meeting": "Vor dem Gespräch",
            "during_meeting": "Im Gespräch",
            "post_meeting": "Nach dem Gespräch",
            "post_meeting_under_nda": "Nach dem Gespräch unter NDA",
        },
    }
    rendered = str(value or "").strip()
    normalized = rendered.lower().replace(" ", "_").replace("-", "_")
    lang_map = mapping.get(lang, mapping["en"])
    if normalized in lang_map:
        return lang_map[normalized]
    if "post" in normalized and "nda" in normalized:
        return lang_map["post_meeting_under_nda"]
    if "pre" in normalized or normalized.startswith("vor_"):
        return lang_map["pre_meeting"]
    if "during" in normalized or "im_gespr" in normalized:
        return lang_map["during_meeting"]
    if "post" in normalized or normalized.startswith("nach_"):
        return lang_map["post_meeting"]
    return _safe_text(value, "—")


def _next_step_table(steps: list[dict[str, Any]], labels: dict[str, str],
                     styles: dict[str, ParagraphStyle], lang: str) -> Table:
    data = [[
        Paragraph(f"<b>{labels['step_phase']}</b>", styles["table_header"]),
        Paragraph(f"<b>{labels['step_owner']}</b>", styles["table_header"]),
        Paragraph(f"<b>{labels['step_action']}</b>", styles["table_header"]),
        Paragraph(f"<b>{labels['step_output']}</b>", styles["table_header"]),
    ]]
    for item in steps:
        if not isinstance(item, dict):
            continue
        output = (
            f"{_safe_text(item.get('asset_hypothesis'), '')} / "
            f"{_safe_text(item.get('expected_output'), '')} / "
            f"{_safe_text(item.get('definition_of_done'), '')}"
        ).strip(" /")
        data.append([
            Paragraph(_truncate(_phase_label(str(item.get("phase", "")), lang), 26, "—"), styles["table_cell"]),
            Paragraph(_truncate(item.get("owner"), 34, "—"), styles["table_cell"]),
            Paragraph(_truncate(item.get("action"), 120, "—"), styles["table_cell"]),
            Paragraph(_truncate(output, 110, "—"), styles["table_cell"]),
        ])
    if len(data) == 1:
        data.append([Paragraph("—", styles["table_cell"])] * 4)
    table = Table(data, colWidths=[24 * mm, 28 * mm, 70 * mm, 48 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SURFACE]),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
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
TRANSLATION_TIMEOUT_SECONDS = 90.0
_ENGLISH_MARKERS = {
    "the", "and", "with", "for", "from", "into", "through", "over", "under", "before", "after",
    "meeting", "inventory", "buyer", "buyers", "sponsor", "owner", "owners", "plant", "data",
    "project", "projects", "visibility", "growth", "decline", "stable", "company", "manufacturer",
    "manufacturing", "control", "technology", "systems", "global", "revenue", "financial",
    "operational", "working", "capital", "services", "service", "partner", "contacts", "contact",
    "critical", "question", "questions", "search", "pages", "lead", "identify", "local", "press",
    "release", "releases", "partially", "verified", "source", "sources", "likely", "could",
    "would", "should", "there", "enough", "strongest", "opportunity", "landscape", "path",
    "paths", "next", "step", "steps", "report", "preparation", "commercial", "support",
    "fit", "demand", "supply", "chain", "procurement",
}


def _looks_untranslated_for_german(text: str) -> bool:
    rendered = str(text or "").strip()
    if not rendered or rendered in {"n/v", "n/a", "—"}:
        return False
    lowered = re.sub(r"https?://\S+", " ", rendered.lower())
    lowered = re.sub(r"\b[a-z0-9.-]+\.[a-z]{2,}\b", " ", lowered)
    words = re.findall(r"[a-z][a-z'-]{2,}", lowered)
    if not words:
        return False
    marker_hits = sum(1 for word in words if word in _ENGLISH_MARKERS)
    strong_phrases = (
        " is a ",
        " are ",
        " with ",
        " for ",
        " and ",
        " the ",
        "year-on-year",
        "working capital",
        "supply chain",
        "linkedin sales navigator",
    )
    return marker_hits >= 2 or any(phrase in lowered for phrase in strong_phrases)


def _set_nested_value(payload: Any, path: tuple[Any, ...], value: str) -> Any:
    if not path:
        return value
    key = path[0]
    if len(path) == 1:
        if isinstance(payload, dict):
            payload[key] = value
            return payload
        if isinstance(payload, list):
            payload[key] = value
            return payload
        if isinstance(payload, tuple):
            items = list(payload)
            items[key] = value
            return tuple(items)
        return payload
    if isinstance(payload, dict):
        payload[key] = _set_nested_value(payload[key], path[1:], value)
        return payload
    if isinstance(payload, list):
        payload[key] = _set_nested_value(payload[key], path[1:], value)
        return payload
    if isinstance(payload, tuple):
        items = list(payload)
        items[key] = _set_nested_value(items[key], path[1:], value)
        return tuple(items)
    return payload


def _translate_residual_strings(payload: Any, target_lang: str) -> Any:
    if target_lang != "de":
        return payload
    try:
        from openai import OpenAI
        from src.config.settings import DEFAULT_MODEL, get_openai_api_key

        api_key = get_openai_api_key()
        if not api_key:
            return payload

        pending: dict[str, str] = {}
        paths: dict[str, tuple[Any, ...]] = {}

        def _walk(value: Any, path: tuple[Any, ...] = ()) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    _walk(item, path + (key,))
                return
            if isinstance(value, list):
                for index, item in enumerate(value):
                    _walk(item, path + (index,))
                return
            if isinstance(value, tuple):
                for index, item in enumerate(value):
                    _walk(item, path + (index,))
                return
            if isinstance(value, str) and _looks_untranslated_for_german(value):
                token = f"t{len(paths)}"
                paths[token] = path
                pending[token] = value

        _walk(payload)
        if not pending:
            return payload

        client = OpenAI(api_key=api_key, timeout=TRANSLATION_TIMEOUT_SECONDS, max_retries=0)
        tokens = list(paths.keys())
        chunk_size = 24
        for start in range(0, len(tokens), chunk_size):
            chunk_tokens = tokens[start:start + chunk_size]
            chunk_payload = {token: pending[token] for token in chunk_tokens}
            try:
                resp = client.chat.completions.create(
                    model=DEFAULT_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are fixing residual untranslated text inside a German executive PDF export. "
                                "Translate every JSON value fully into idiomatic German. "
                                "Do not leave English words behind unless they are company names, URLs, legal names, "
                                "or abbreviations like CEO/CFO/EBIT/NDA. "
                                "Return only a valid JSON object with the exact same keys."
                            ),
                        },
                        {"role": "user", "content": strict_json_dumps(chunk_payload, ensure_ascii=False)},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                    timeout=TRANSLATION_TIMEOUT_SECONDS,
                )
                translated: dict[str, str] = json.loads(resp.choices[0].message.content)
            except Exception:
                continue
            for token in chunk_tokens:
                if token in translated:
                    payload = _set_nested_value(payload, paths[token], translated[token])
        return payload
    except Exception:
        return payload


def _translate_content(pipeline_data: dict[str, Any], target_lang: str) -> dict[str, Any]:
    """Translate all narrative text fields to *target_lang* in one OpenAI call.

    Returns a deep-copied, translated version of pipeline_data.
    Falls back silently to the original on any error.
    """
    data = copy.deepcopy(pipeline_data)
    try:
        from openai import OpenAI  # local import — only needed here
        from src.config.settings import get_openai_api_key

        api_key = get_openai_api_key()
        if not api_key:
            return _offline_translate_obj(data, target_lang)
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
        for i, item in enumerate(syn.get("critical_open_questions", []) or []):
            if isinstance(item, dict):
                _add(f"coq_label_{i}", item.get("label", ""))
                _add(f"coq_question_{i}", item.get("question", ""))
                _add(f"coq_why_{i}", item.get("why_critical", ""))
                _add(f"coq_hyp_{i}", item.get("hypothesis_tested", ""))
                _add(f"coq_owner_{i}", item.get("owner", ""))
                _add(f"coq_timing_{i}", item.get("timing", ""))
                _add(f"coq_criticality_{i}", item.get("meeting_criticality", ""))
                _add(f"coq_impact_{i}", item.get("decision_impact", ""))
        for i, item in enumerate(syn.get("recommended_next_steps", []) or []):
            if isinstance(item, dict):
                _add(f"nstep_phase_{i}", item.get("phase", ""))
                _add(f"nstep_owner_{i}", item.get("owner", ""))
                _add(f"nstep_action_{i}", item.get("action", ""))
                _add(f"nstep_target_{i}", item.get("target_person", ""))
                _add(f"nstep_hyp_{i}", item.get("asset_hypothesis", ""))
                _add(f"nstep_goal_{i}", item.get("goal", ""))
                _add(f"nstep_output_{i}", item.get("expected_output", ""))
                _add(f"nstep_success_{i}", item.get("success_criterion", ""))
                _add(f"nstep_done_{i}", item.get("definition_of_done", ""))
                _add(f"nstep_dep_{i}", item.get("dependency", ""))
        for i, item in enumerate(contacts.get("target_company_contact_cards", []) or []):
            if isinstance(item, dict):
                _add(f"card_role_{i}", item.get("role", ""))
                _add(f"card_org_{i}", item.get("organization_location", ""))
                _add(f"card_rel_{i}", item.get("relevance_buying_center", ""))
                _add(f"card_channel_{i}", item.get("profile_contact_channel", ""))
                _add(f"card_verify_{i}", item.get("source_verification", ""))
                _add(f"card_rationale_{i}", item.get("outreach_rationale", ""))
                _add(f"card_objection_{i}", item.get("likely_objection", ""))
        for i, item in enumerate(contacts.get("target_company_missing_roles", []) or []):
            if isinstance(item, dict):
                _add(f"missing_role_{i}", item.get("role_name", ""))
                _add(f"missing_why_{i}", item.get("why_critical", ""))
                _add(f"missing_area_{i}", item.get("likely_org_area", ""))
                _add(f"missing_channel_{i}", item.get("best_search_channel", ""))
                _add(f"missing_action_{i}", item.get("next_search_action", ""))
        for i, item in enumerate(contacts.get("target_company_access_path", []) or []):
            _add(f"access_path_{i}", item)

        if not batch:
            return data

        # ── single LLM call ─────────────────────────────────────────────────
        from src.config.settings import DEFAULT_MODEL
        lang_name = _LANG_NAMES.get(target_lang, target_lang)
        client = OpenAI(api_key=api_key, timeout=TRANSLATION_TIMEOUT_SECONDS, max_retries=0)
        translated: dict[str, str] = {}
        keys = list(batch.keys())
        chunk_size = 28
        for start in range(0, len(keys), chunk_size):
            chunk_keys = keys[start:start + chunk_size]
            chunk_payload = {key: batch[key] for key in chunk_keys}
            resp = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"You are a professional business translator. "
                            f"Translate every JSON value fully into {lang_name}. "
                            f"The input may contain mixed-language content. "
                            f"Do not leave source-language sentences unchanged. "
                            f"Keep company names, brand names, legal entity names, "
                            f"abbreviations, URLs, and numeric values unchanged. "
                            f"Return ONLY a valid JSON object with the exact same keys."
                        ),
                    },
                    {"role": "user", "content": strict_json_dumps(chunk_payload, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                timeout=TRANSLATION_TIMEOUT_SECONDS,
            )
            translated.update(json.loads(resp.choices[0].message.content))

        def _get(key: str, original: Any) -> Any:
            return translated.get(key, original)

        # ── write translated values back ─────────────────────────────────────
        syn["executive_summary"]              = _get("syn_exec",   syn.get("executive_summary", ""))
        syn["opportunity_assessment_summary"] = _get("syn_opp",    syn.get("opportunity_assessment_summary", ""))
        syn["buyer_market_summary"]           = _get("syn_buyers", syn.get("buyer_market_summary", ""))

        syn["key_risks"]  = [_get(f"risk_{i}", t) for i, t in enumerate(syn.get("key_risks",  []) or [])]
        syn["next_steps"] = [_get(f"step_{i}", t) for i, t in enumerate(syn.get("next_steps", []) or [])]
        for i, item in enumerate(syn.get("critical_open_questions", []) or []):
            if isinstance(item, dict):
                item["label"] = _get(f"coq_label_{i}", item.get("label", ""))
                item["question"] = _get(f"coq_question_{i}", item.get("question", ""))
                item["why_critical"] = _get(f"coq_why_{i}", item.get("why_critical", ""))
                item["hypothesis_tested"] = _get(f"coq_hyp_{i}", item.get("hypothesis_tested", ""))
                item["owner"] = _get(f"coq_owner_{i}", item.get("owner", ""))
                item["timing"] = _get(f"coq_timing_{i}", item.get("timing", ""))
                item["meeting_criticality"] = _get(f"coq_criticality_{i}", item.get("meeting_criticality", ""))
                item["decision_impact"] = _get(f"coq_impact_{i}", item.get("decision_impact", ""))
        for i, item in enumerate(syn.get("recommended_next_steps", []) or []):
            if isinstance(item, dict):
                item["phase"] = _get(f"nstep_phase_{i}", item.get("phase", ""))
                item["owner"] = _get(f"nstep_owner_{i}", item.get("owner", ""))
                item["action"] = _get(f"nstep_action_{i}", item.get("action", ""))
                item["target_person"] = _get(f"nstep_target_{i}", item.get("target_person", ""))
                item["asset_hypothesis"] = _get(f"nstep_hyp_{i}", item.get("asset_hypothesis", ""))
                item["goal"] = _get(f"nstep_goal_{i}", item.get("goal", ""))
                item["expected_output"] = _get(f"nstep_output_{i}", item.get("expected_output", ""))
                item["success_criterion"] = _get(f"nstep_success_{i}", item.get("success_criterion", ""))
                item["definition_of_done"] = _get(f"nstep_done_{i}", item.get("definition_of_done", ""))
                item["dependency"] = _get(f"nstep_dep_{i}", item.get("dependency", ""))

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
        for i, item in enumerate(contacts.get("target_company_contact_cards", []) or []):
            if isinstance(item, dict):
                item["role"] = _get(f"card_role_{i}", item.get("role", ""))
                item["organization_location"] = _get(f"card_org_{i}", item.get("organization_location", ""))
                item["relevance_buying_center"] = _get(f"card_rel_{i}", item.get("relevance_buying_center", ""))
                item["profile_contact_channel"] = _get(f"card_channel_{i}", item.get("profile_contact_channel", ""))
                item["source_verification"] = _get(f"card_verify_{i}", item.get("source_verification", ""))
                item["outreach_rationale"] = _get(f"card_rationale_{i}", item.get("outreach_rationale", ""))
                item["likely_objection"] = _get(f"card_objection_{i}", item.get("likely_objection", ""))
        for i, item in enumerate(contacts.get("target_company_missing_roles", []) or []):
            if isinstance(item, dict):
                item["role_name"] = _get(f"missing_role_{i}", item.get("role_name", ""))
                item["why_critical"] = _get(f"missing_why_{i}", item.get("why_critical", ""))
                item["likely_org_area"] = _get(f"missing_area_{i}", item.get("likely_org_area", ""))
                item["best_search_channel"] = _get(f"missing_channel_{i}", item.get("best_search_channel", ""))
                item["next_search_action"] = _get(f"missing_action_{i}", item.get("next_search_action", ""))
        contacts["target_company_access_path"] = [
            _get(f"access_path_{i}", t) for i, t in enumerate(contacts.get("target_company_access_path", []) or [])
        ]
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
        return _offline_translate_obj(data, target_lang)


def generate_pdf(pipeline_data: dict[str, Any], *, lang: str = "de") -> bytes:
    labels  = _translation(lang)
    styles  = _styles()

    # Translate all narrative content into the requested output language.
    if lang == "de":
        pipeline_data = copy.deepcopy(pipeline_data)
        pipeline_data = _offline_translate_obj(pipeline_data, lang)
    elif lang in _LANG_NAMES:
        pipeline_data = _translate_content(pipeline_data, lang)
    elif lang in _LANG_NAMES:
        pipeline_data = _offline_translate_obj(pipeline_data, lang)
    elif lang in _LANG_NAMES:
        pipeline_data = _translate_residual_strings(pipeline_data, lang)
    elif lang in _LANG_NAMES:
        pipeline_data = _offline_translate_obj(pipeline_data, lang)

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
    run_id = _resolve_run_id(pipeline_data)

    # Research readiness
    rs_score  = int(readiness.get("score", 0))

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
        (labels["run_id"], run_id),
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
    financial_signals = _filter_finance_inventory_signals(financial_signals, lang=lang)
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
    target_contact_cards = contacts_section.get("target_company_contact_cards") or [
        {
            "name": _safe_text(contact.get("name"), "—"),
            "role": _safe_text(contact.get("rolle_titel") or contact.get("funktion"), "—"),
            "organization_location": _safe_text(contact.get("firma") or contact.get("standort"), "—"),
            "relevance_buying_center": _safe_text(contact.get("relevance_reason") or contact.get("confidence"), "—"),
            "profile_contact_channel": _safe_text(contact.get("quelle"), "—"),
            "source_verification": _safe_text(contact.get("confidence"), "—"),
            "confidence": _safe_text(contact.get("confidence"), "—"),
        }
        for contact in target_contacts[:4]
        if isinstance(contact, dict)
    ]
    missing_roles = contacts_section.get("target_company_missing_roles") or []
    access_path = contacts_section.get("target_company_access_path") or []
    critical_questions = synthesis.get("critical_open_questions") or []
    recommended_steps = synthesis.get("recommended_next_steps") or []
    top_risks = risks[:3]

    top_actions = []
    for step in recommended_steps[:3]:
        if not isinstance(step, dict):
            continue
        action_text = _safe_text(step.get("action"), "")
        goal_text = _truncate(step.get("goal"), 72, "")
        if action_text and goal_text:
            top_actions.append(f"{action_text} - {goal_text}")
        elif action_text:
            top_actions.append(action_text)
    if not top_actions:
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

    if lang == "de":
        render_payload = {
            "revenue": revenue,
            "executive_summary": executive_summary,
            "products": products,
            "material_scope": material_scope,
            "service_relevance": service_relevance,
            "risks": risks,
            "next_steps": next_steps,
            "profile_rows": profile_rows,
            "dashboard_kpis": dashboard_kpis,
            "opportunity_reasons": opportunity_reasons,
            "key_trigger_items": key_trigger_items,
            "finance_rows": finance_rows,
            "financial_signals": financial_signals,
            "portfolio_events": portfolio_events,
            "narrative_overview": narrative_overview,
            "why_liquisto": why_liquisto,
            "business_model": business_model,
            "divisions": divisions,
            "financial_position": financial_position,
            "trigger_events": trigger_events,
            "financial_cards": financial_cards,
            "target_contacts": target_contacts,
            "buyer_contacts": buyer_contacts,
            "target_contact_cards": target_contact_cards,
            "missing_roles": missing_roles,
            "access_path": access_path,
            "critical_questions": critical_questions,
            "recommended_steps": recommended_steps,
            "top_risks": top_risks,
            "top_actions": top_actions,
            "validation_pairs": validation_pairs,
            "primary_label": primary_label,
            "primary_fit": primary_fit,
            "primary_reasoning": primary_reasoning,
        }
        render_payload = _offline_translate_obj(render_payload, "de")
        render_payload = _translate_residual_strings(render_payload, "de")
        render_payload = _offline_translate_obj(render_payload, "de")

        revenue = render_payload["revenue"]
        executive_summary = render_payload["executive_summary"]
        products = render_payload["products"]
        material_scope = render_payload["material_scope"]
        service_relevance = render_payload["service_relevance"]
        risks = render_payload["risks"]
        next_steps = render_payload["next_steps"]
        profile_rows = render_payload["profile_rows"]
        dashboard_kpis = render_payload["dashboard_kpis"]
        opportunity_reasons = render_payload["opportunity_reasons"]
        key_trigger_items = render_payload["key_trigger_items"]
        finance_rows = render_payload["finance_rows"]
        financial_signals = render_payload["financial_signals"]
        portfolio_events = render_payload["portfolio_events"]
        narrative_overview = render_payload["narrative_overview"]
        why_liquisto = render_payload["why_liquisto"]
        business_model = render_payload["business_model"]
        divisions = render_payload["divisions"]
        financial_position = render_payload["financial_position"]
        trigger_events = render_payload["trigger_events"]
        financial_cards = render_payload["financial_cards"]
        target_contacts = render_payload["target_contacts"]
        buyer_contacts = render_payload["buyer_contacts"]
        target_contact_cards = render_payload["target_contact_cards"]
        missing_roles = render_payload["missing_roles"]
        access_path = render_payload["access_path"]
        critical_questions = render_payload["critical_questions"]
        recommended_steps = render_payload["recommended_steps"]
        top_risks = render_payload["top_risks"]
        top_actions = render_payload["top_actions"]
        validation_pairs = render_payload["validation_pairs"]
        primary_label = render_payload["primary_label"]
        primary_fit = render_payload["primary_fit"]
        primary_reasoning = render_payload["primary_reasoning"]

        revenue = _offline_translate_text(revenue, "de")
        executive_summary = _offline_translate_text(executive_summary, "de")
        products = [_offline_translate_text(item, "de") for item in products]
        material_scope = [_offline_translate_text(item, "de") for item in material_scope]
        risks = [_offline_translate_text(item, "de") for item in risks]
        next_steps = [_offline_translate_text(item, "de") for item in next_steps]
        opportunity_reasons = [_offline_translate_text(item, "de") for item in opportunity_reasons]
        key_trigger_items = [_offline_translate_text(item, "de") for item in key_trigger_items]
        financial_signals = [_offline_translate_text(item, "de") for item in financial_signals]
        portfolio_events = [_offline_translate_text(item, "de") for item in portfolio_events]
        narrative_overview = _offline_translate_text(narrative_overview, "de")
        why_liquisto = _offline_translate_text(why_liquisto, "de")
        business_model = _offline_translate_text(business_model, "de")
        divisions = [_offline_translate_text(item, "de") for item in divisions]
        financial_position = _offline_translate_text(financial_position, "de")
        trigger_events = [_offline_translate_text(item, "de") for item in trigger_events]
        financial_cards = [tuple(_offline_translate_text(part, "de") if isinstance(part, str) else part for part in card) for card in financial_cards]
        target_contact_cards = _offline_translate_obj(target_contact_cards, "de")
        missing_roles = _offline_translate_obj(missing_roles, "de")
        access_path = [_offline_translate_text(item, "de") for item in access_path]
        critical_questions = _offline_translate_obj(critical_questions, "de")
        recommended_steps = _offline_translate_obj(recommended_steps, "de")
        top_risks = [_offline_translate_text(item, "de") for item in top_risks]
        top_actions = [_offline_translate_text(item, "de") for item in top_actions]
        profile_rows = [tuple(_offline_translate_text(part, "de") if isinstance(part, str) else part for part in row) for row in profile_rows]
        dashboard_kpis = [tuple(_offline_translate_text(part, "de") if isinstance(part, str) else part for part in row) for row in dashboard_kpis]
        finance_rows = [tuple(_offline_translate_text(part, "de") if isinstance(part, str) else part for part in row) for row in finance_rows]
        validation_pairs = [tuple(_offline_translate_text(part, "de") if isinstance(part, str) else part for part in row) for row in validation_pairs]
        primary_label = _offline_translate_text(primary_label, "de")
        primary_fit = _offline_translate_text(primary_fit, "de")
        primary_reasoning = _offline_translate_text(primary_reasoning, "de")

    # ── build story ──────────────────────────────────────────────────────────

    story: list[Any] = []

    # Cover
    story.append(_cover_block(
        company_name,
        labels["report_subtitle"],
        labels["prepared_for"],
        labels["date_label"],
        labels["run_id"],
        run_id,
        styles,
    ))
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
    story.append(_bullet_col(labels["key_triggers"], key_trigger_items, styles, 168 * mm, BRAND_TEAL))
    story.append(Spacer(1, 2.5 * mm))
    story.append(_bullet_col(labels["why_now"], opportunity_reasons, styles, 168 * mm, BRAND_GREEN))
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
    story.append(_bullet_col(labels["business_model"], [business_model], styles, 168 * mm, BRAND_BLUE))
    story.append(Spacer(1, 2.5 * mm))
    story.append(_bullet_col(labels["divisions"], divisions, styles, 168 * mm, BRAND_TEAL))
    story.append(Spacer(1, 2.5 * mm))
    story.append(_bullet_col(labels["products_scope"], material_scope or products, styles, 168 * mm, BRAND_TEAL))
    story.append(Spacer(1, 2.5 * mm))
    story.append(_bullet_col(labels["trigger_events"], trigger_events, styles, 168 * mm, BRAND_AMBER))
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
    story.append(_bullet_col(labels["financial_signals"], financial_signals, styles, 168 * mm, BRAND_AMBER))
    story.append(Spacer(1, 2.5 * mm))
    story.append(_bullet_col(labels["portfolio_events"], portfolio_events, styles, 168 * mm, BRAND_BLUE))

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
    story.append(_summary_callout(
        "Method note" if lang == "en" else "Methodenhinweis",
        (
            "Phone numbers and email addresses are shown only when they are publicly evidenced. No placeholder contacts or invented direct channels are generated."
            if lang == "en" else
            "Telefonnummern und E-Mail-Adressen werden nur gezeigt, wenn sie öffentlich belastbar belegt sind. Es werden keine Platzhalterkontakte oder erfundenen Direktkanäle erzeugt."
        ),
        styles,
        accent=BRAND_AMBER,
        background=WHITE,
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(labels["target_contacts"], styles["section"]))
    if target_contact_cards:
        for flowable in _target_contact_cards(target_contact_cards[:4], labels, styles, lang):
            story.append(flowable)
    else:
        story.append(_summary_callout(
            "Critical gap" if lang == "en" else "Kritische Lücke",
            "No sufficiently verified target-company stakeholders are available for the briefing."
            if lang == "en" else
            "Für das Briefing liegen keine ausreichend verifizierten Zielunternehmens-Stakeholder vor.",
            styles,
            accent=BRAND_RED,
            background=WHITE,
        ))
    if missing_roles:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(labels["missing_roles"], styles["section"]))
        for flowable in _missing_role_cards(missing_roles[:4], labels, styles, lang):
            story.append(flowable)
    if access_path:
        story.append(Spacer(1, 4 * mm))
        story.append(_bullet_col(labels["access_path"], access_path[:4], styles, 168 * mm, BRAND_BLUE))
    if buyer_contacts:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(labels["buyer_contacts"], styles["section"]))
        for flowable in _buyer_contact_cards(buyer_contacts[:3], labels, styles, lang):
            story.append(flowable)
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
    if critical_questions:
        story.append(_open_question_table(critical_questions[:5], labels, styles, lang))
    else:
        story.append(_summary_callout(
            "Critical gap" if lang == "en" else "Kritische Lücke",
            "No deal-critical validation questions were produced."
            if lang == "en" else
            "Es wurden keine deal-kritischen Validierungsfragen erzeugt.",
            styles,
            accent=BRAND_RED,
            background=WHITE,
        ))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(labels["validation_plan"], styles["section"]))
    if recommended_steps:
        story.append(_next_step_table(recommended_steps[:6], labels, styles, lang))
    else:
        story.append(_summary_callout(
            "Critical gap" if lang == "en" else "Kritische Lücke",
            "No operational action plan is available for the next step."
            if lang == "en" else
            "Es liegt kein operativer Aktionsplan für den nächsten Schritt vor.",
            styles,
            accent=BRAND_RED,
            background=WHITE,
        ))

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
