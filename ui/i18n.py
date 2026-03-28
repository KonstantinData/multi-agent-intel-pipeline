"""Liquisto UI — internationalisation labels (DE / EN)."""
from __future__ import annotations

Labels = dict[str, str]

_DE: Labels = {
    # ── page chrome ──────────────────────────────────────────────────────
    "page_title": "Liquisto Briefing",
    "page_heading": "Gesprächsvorbereitung",
    "page_subtitle": "Strukturierte Markt- und Unternehmensrecherche als Basis für den Kundentermin",
    "lang_toggle": "English",
    # ── sidebar ──────────────────────────────────────────────────────────
    "new_run": "Neuer Run",
    "company_name": "Unternehmen",
    "web_domain": "Web-Domain",
    "start_run": "Run starten",
    "load_run": "Run laden",
    "select_run": "Run auswählen",
    "load_selected": "Ausgewählten Run laden",
    "runtime_models": "Modelle",
    # ── tabs ─────────────────────────────────────────────────────────────
    "tab_briefing": "Briefing",
    "tab_research": "Recherche-Details",
    "tab_followup": "Rückfragen",
    "tab_quality": "Qualität & Status",
    "tab_log": "Protokoll",
    # ── live run ─────────────────────────────────────────────────────────
    "waiting": "Warte auf Start",
    "run_completed": "Run abgeschlossen",
    "live_feed": "Live-Nachrichten",
    # ── status banners ───────────────────────────────────────────────────
    "briefing_ready": "Briefing bereit",
    "briefing_partial": "Briefing mit Lücken",
    "briefing_unusable": "Recherche unvollständig — Briefing eingeschränkt nutzbar",
    "run_loaded": "Run geladen",
    # ── briefing tab ─────────────────────────────────────────────────────
    "recommendation": "Liquisto-Empfehlung",
    "primary_rec": "Primäre Empfehlung",
    "secondary_rec": "Zweite Option",
    "low_relevance": "Aktuell weniger relevant",
    "no_recommendation": "Keine ausreichende Datenbasis für eine Empfehlung — Recherche vertiefen oder Follow-up nutzen.",
    "fallback_note": "Empfehlung basiert auf strukturierter Datenauswertung (kein AG2-Syntheselauf).",
    "talk_about": "Im Termin ansprechen",
    "validate": "Im Termin validieren",
    "buyer_market": "Käufermarkt",
    "competitors_identified": "Wettbewerber identifiziert — Marktpositionierung ansprechen.",
    "no_talk_points": "Keine spezifischen Gesprächspunkte verfügbar.",
    "no_validation_points": "Keine offenen Validierungspunkte identifiziert.",
    "contacts": "Kontakte",
    "seniority": "Seniorität",
    "outreach": "Outreach",
    "more_contacts": "weitere Kontakte in der Recherche-Ansicht",
    "no_contacts": "Keine verifizierten Kontakte gefunden — Recherche-Details prüfen.",
    "next_step": "Empfohlener nächster Schritt",
    "default_next_step": "Follow-up durchführen oder Termin mit dem Kunden ansetzen.",
    "economic_signal": "Wirtschaftliches Signal",
    # ── confidence ───────────────────────────────────────────────────────
    "confidence_high": "🟢 Hohe Konfidenz",
    "confidence_medium": "🟡 Mittlere Konfidenz",
    "confidence_low": "🔴 Geringe Konfidenz",
    # ── service areas ────────────────────────────────────────────────────
    "svc_excess_inventory": "Überschuss-Inventar-Verwertung",
    "svc_repurposing": "Repurposing & Kreislaufwirtschaft",
    "svc_analytics": "Analytics & Entscheidungsunterstützung",
    "svc_further_validation": "Weitere Validierung erforderlich",
    "svc_desc_excess_inventory": "Wiederverkauf, Redeployment und Sekundärmarktpfade für Güter und Anlagen",
    "svc_desc_repurposing": "Kreislaufwirtschaft und Nachnutzungspfade für Materialien und Komponenten",
    "svc_desc_analytics": "Lagertransparenz, Entscheidungsunterstützung und operative Berichtsverbesserungen",
    # ── goods classification ─────────────────────────────────────────────
    "goods_manufacturer": "Hersteller",
    "goods_distributor": "Händler / Großhändler",
    "goods_held_in_stock": "Lagerhalter",
    "goods_mixed": "Gemischt (Herstellung + Handel)",
    "goods_unclear": "Geschäftsmodell unklar",
    # ── research tab ─────────────────────────────────────────────────────
    "company_profile": "Unternehmensprofil",
    "name": "Name",
    "website": "Webseite",
    "industry": "Branche",
    "goods_type": "Gütertyp",
    "products": "Produkte / Leistungen",
    "description": "Beschreibung",
    "economic_signals": "Wirtschaftliche Signale",
    "asset_scope": "Asset-Scope",
    "market_industry": "Markt und Industrie",
    "demand_outlook": "Nachfrage-Outlook",
    "repurposing_signals": "Repurposing-Signale",
    "analytics_signals": "Analytics-Signale",
    "buyer_network": "Käufer- und Wettbewerbernetzwerk",
    "competitors": "Wettbewerber",
    "downstream_buyers": "Downstream-Käufer",
    "monetization_paths": "Monetisierungspfade",
    "redeployment_paths": "Redeployment-Pfade",
    "contact_intelligence": "Kontakt-Intelligence",
    "coverage_quality": "Abdeckungsqualität",
    "function": "Funktion",
    "confidence": "Confidence",
    "relevance": "Relevanz",
    "outreach_angle": "Outreach-Angle",
    "no_contacts_found": "Keine Kontakte gefunden.",
    # ── quality tab ──────────────────────────────────────────────────────
    "research_quality": "Recherche-Qualität & Evidenz",
    "readiness_score": "Readiness-Score",
    "evidence_quality": "Evidenz-Qualität",
    "status": "Status",
    "open_gaps": "Offene Lücken",
    "task_status": "Task-Status",
    "department_packages": "Department-Pakete (intern)",
    "run_metadata": "Run-Metadaten",
    # ── follow-up ────────────────────────────────────────────────────────
    "followup_intro": "Stelle gezielte Fragen zu einem abgeschlossenen Run. Der Question Router entscheidet, welches Department antwortet.",
    "run_id": "Run ID",
    "followup_question": "Folgefrage",
    "followup_placeholder": "z.B. 'Welche Ansprechpartner gibt es bei Bosch?' oder 'Welche Drucksignale wurden bei der Marktanalyse gefunden?'",
    "submit_question": "Frage beantworten",
    "followup_required": "Run ID und Frage sind erforderlich.",
    "followup_routing": "Routing und Antwort wird vorbereitet…",
    "followup_not_found": "Run nicht gefunden.",
    "followup_error": "Fehler",
    "answered_by": "Beantwortet von",
    "evidence_used": "Verwendete Belege",
    "unresolved_points": "Offene Punkte",
    # ── pdf ──────────────────────────────────────────────────────────────
    "download_pdf_de": "PDF herunterladen (DE)",
    "download_pdf_en": "PDF herunterladen (EN)",
}

_EN: Labels = {
    # ── page chrome ──────────────────────────────────────────────────────
    "page_title": "Liquisto Briefing",
    "page_heading": "Meeting Preparation",
    "page_subtitle": "Structured market and company research as the basis for client meetings",
    "lang_toggle": "Deutsch",
    # ── sidebar ──────────────────────────────────────────────────────────
    "new_run": "New Run",
    "company_name": "Company",
    "web_domain": "Web domain",
    "start_run": "Start run",
    "load_run": "Load Run",
    "select_run": "Select run",
    "load_selected": "Load selected run",
    "runtime_models": "Models",
    # ── tabs ─────────────────────────────────────────────────────────────
    "tab_briefing": "Briefing",
    "tab_research": "Research Details",
    "tab_followup": "Follow-up",
    "tab_quality": "Quality & Status",
    "tab_log": "Log",
    # ── live run ─────────────────────────────────────────────────────────
    "waiting": "Waiting to start",
    "run_completed": "Run completed",
    "live_feed": "Live message feed",
    # ── status banners ───────────────────────────────────────────────────
    "briefing_ready": "Briefing ready",
    "briefing_partial": "Briefing with gaps",
    "briefing_unusable": "Research incomplete — briefing of limited use",
    "run_loaded": "Run loaded",
    # ── briefing tab ─────────────────────────────────────────────────────
    "recommendation": "Liquisto Recommendation",
    "primary_rec": "Primary recommendation",
    "secondary_rec": "Second option",
    "low_relevance": "Currently less relevant",
    "no_recommendation": "Insufficient data for a recommendation — deepen research or use follow-up.",
    "fallback_note": "Recommendation based on structured data analysis (no AG2 synthesis run).",
    "talk_about": "Discuss in meeting",
    "validate": "Validate in meeting",
    "buyer_market": "Buyer market",
    "competitors_identified": "competitors identified — discuss market positioning.",
    "no_talk_points": "No specific talking points available.",
    "no_validation_points": "No open validation points identified.",
    "contacts": "Contacts",
    "seniority": "Seniority",
    "outreach": "Outreach",
    "more_contacts": "more contacts in research details",
    "no_contacts": "No verified contacts found — check research details.",
    "next_step": "Recommended next step",
    "default_next_step": "Conduct follow-up or schedule meeting with the client.",
    "economic_signal": "Economic signal",
    # ── confidence ───────────────────────────────────────────────────────
    "confidence_high": "🟢 High confidence",
    "confidence_medium": "🟡 Medium confidence",
    "confidence_low": "🔴 Low confidence",
    # ── service areas ────────────────────────────────────────────────────
    "svc_excess_inventory": "Excess Inventory Recovery",
    "svc_repurposing": "Repurposing & Circular Economy",
    "svc_analytics": "Analytics & Decision Support",
    "svc_further_validation": "Further Validation Required",
    "svc_desc_excess_inventory": "Resale, redeployment and secondary market paths for goods and assets",
    "svc_desc_repurposing": "Circular economy and reuse paths for materials and components",
    "svc_desc_analytics": "Inventory transparency, decision support and operational reporting improvements",
    # ── goods classification ─────────────────────────────────────────────
    "goods_manufacturer": "Manufacturer",
    "goods_distributor": "Distributor / Wholesaler",
    "goods_held_in_stock": "Stockholder",
    "goods_mixed": "Mixed (Manufacturing + Trading)",
    "goods_unclear": "Business model unclear",
    # ── research tab ─────────────────────────────────────────────────────
    "company_profile": "Company Profile",
    "name": "Name",
    "website": "Website",
    "industry": "Industry",
    "goods_type": "Goods type",
    "products": "Products / Services",
    "description": "Description",
    "economic_signals": "Economic Signals",
    "asset_scope": "Asset Scope",
    "market_industry": "Market & Industry",
    "demand_outlook": "Demand Outlook",
    "repurposing_signals": "Repurposing Signals",
    "analytics_signals": "Analytics Signals",
    "buyer_network": "Buyer & Competitor Network",
    "competitors": "Competitors",
    "downstream_buyers": "Downstream Buyers",
    "monetization_paths": "Monetization Paths",
    "redeployment_paths": "Redeployment Paths",
    "contact_intelligence": "Contact Intelligence",
    "coverage_quality": "Coverage quality",
    "function": "Function",
    "confidence": "Confidence",
    "relevance": "Relevance",
    "outreach_angle": "Outreach angle",
    "no_contacts_found": "No contacts found.",
    # ── quality tab ──────────────────────────────────────────────────────
    "research_quality": "Research Quality & Evidence",
    "readiness_score": "Readiness Score",
    "evidence_quality": "Evidence Quality",
    "status": "Status",
    "open_gaps": "Open Gaps",
    "task_status": "Task Status",
    "department_packages": "Department Packages (internal)",
    "run_metadata": "Run Metadata",
    # ── follow-up ────────────────────────────────────────────────────────
    "followup_intro": "Ask targeted questions about a completed run. The question router decides which department responds.",
    "run_id": "Run ID",
    "followup_question": "Follow-up question",
    "followup_placeholder": "e.g. 'Which contacts exist at Bosch?' or 'What pressure signals were found in the market analysis?'",
    "submit_question": "Submit question",
    "followup_required": "Run ID and question are required.",
    "followup_routing": "Routing and preparing answer…",
    "followup_not_found": "Run not found.",
    "followup_error": "Error",
    "answered_by": "Answered by",
    "evidence_used": "Evidence used",
    "unresolved_points": "Unresolved points",
    # ── pdf ──────────────────────────────────────────────────────────────
    "download_pdf_de": "Download PDF (DE)",
    "download_pdf_en": "Download PDF (EN)",
}

_BUNDLES: dict[str, Labels] = {"de": _DE, "en": _EN}


def get_labels(lang: str = "de") -> Labels:
    """Return the label bundle for *lang* (falls back to DE)."""
    return _BUNDLES.get(lang, _DE)


# ── lookup helpers used by render functions ──────────────────────────────────

_SERVICE_KEYS: dict[str, str] = {
    "excess_inventory": "svc_excess_inventory",
    "repurposing": "svc_repurposing",
    "analytics": "svc_analytics",
    "further_validation_required": "svc_further_validation",
}
_SERVICE_DESC_KEYS: dict[str, str] = {
    "excess_inventory": "svc_desc_excess_inventory",
    "repurposing": "svc_desc_repurposing",
    "analytics": "svc_desc_analytics",
}
_SERVICE_ICONS: dict[str, str] = {
    "excess_inventory": "📦",
    "repurposing": "♻️",
    "analytics": "📊",
    "further_validation_required": "🔍",
}
_GOODS_KEYS: dict[str, str] = {
    "manufacturer": "goods_manufacturer",
    "distributor": "goods_distributor",
    "held_in_stock": "goods_held_in_stock",
    "mixed": "goods_mixed",
    "unclear": "goods_unclear",
}
_CONFIDENCE_KEYS: dict[str, str] = {
    "high": "confidence_high",
    "medium": "confidence_medium",
    "low": "confidence_low",
}


def service_label(area: str, labels: Labels) -> str:
    key = _SERVICE_KEYS.get(area)
    return labels.get(key, area.replace("_", " ").title()) if key else area.replace("_", " ").title()


def service_desc(area: str, labels: Labels) -> str:
    key = _SERVICE_DESC_KEYS.get(area)
    return labels.get(key, "") if key else ""


def service_icon(area: str) -> str:
    return _SERVICE_ICONS.get(area, "📌")


def goods_label(classification: str, labels: Labels) -> str:
    key = _GOODS_KEYS.get(classification)
    return labels.get(key, "") if key else ""


def confidence_badge(level: str, labels: Labels) -> str:
    key = _CONFIDENCE_KEYS.get(level)
    return labels.get(key, "") if key else ""
