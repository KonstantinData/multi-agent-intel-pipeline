"""Cross-domain synthesis and report shaping."""
from __future__ import annotations

from typing import Any

from src.orchestration.envelope import resolve_raw_package
from src.utils import dedup_safe as _dedup_safe

NEGATIVE_PREFIXES = ("no ", "not ", "none", "kein", "keine", "keinen")
UNCERTAIN_SIGNAL_MARKERS = (
    "indicative",
    "requires validation",
    "should be validated",
    "remains open",
    "remains unvalidated",
    "may be plausible",
    "may exist",
    "potential",
    "likely",
    "possible",
    "hypothesis",
)
SYNTHESIS_INCOMPLETE_MARKERS = (
    "did not complete within max_round",
    "synthesis incomplete",
    "conservative output",
    "not accepted by the supervisor gate",
)
TARGET_ROLE_SPECS = [
    {
        "role_name": "Head of Supply Chain / Material Management DACH / EU",
        "tokens": ("supply chain", "material", "logistics"),
        "why_critical": "Owns slow-moving inventory, stock transfers, and release of operational detail for a working-capital case.",
        "likely_org_area": "Supply Chain / Material Management",
        "best_search_channel": "LinkedIn Sales Navigator and company leadership pages",
        "next_search_action": "Search for European or DACH supply-chain leadership tied to plants, logistics, or material management.",
    },
    {
        "role_name": "Head of Procurement / Purchasing",
        "tokens": ("procurement", "purchasing", "einkauf"),
        "why_critical": "Can validate supplier commitments, inbound overhang, and stock locked in purchased components.",
        "likely_org_area": "Procurement / Purchasing",
        "best_search_channel": "LinkedIn, procurement conference mentions, switchboard escalation",
        "next_search_action": "Identify the senior procurement owner below CFO/COO and prepare a direct operational outreach path.",
    },
    {
        "role_name": "Plant or Operations Lead for Europe",
        "tokens": ("plant", "operations", "werk", "production"),
        "why_critical": "Best source for where inventory is stuck: raw material, WIP, or finished goods.",
        "likely_org_area": "Plant Management / Operations",
        "best_search_channel": "Plant press releases, local legal entities, switchboard, local trade-press mentions",
        "next_search_action": "Prioritize the plant leader for the site with the highest likely overhang before the meeting.",
    },
    {
        "role_name": "Plant Lead Poland",
        "tokens": ("poland", "polen", "plant poland", "werk polen"),
        "why_critical": "Likely plant-level owner if inventory, workforce, or output imbalances sit in the Polish footprint.",
        "likely_org_area": "Plant Management / Poland",
        "best_search_channel": "Local legal-entity filings, plant press releases, LinkedIn, switchboard",
        "next_search_action": "Identify the Polish plant manager or operations lead tied to workforce, production, or logistics updates.",
    },
    {
        "role_name": "Plant Lead Kupferzell / Germany",
        "tokens": ("kupferzell", "germany plant", "werk kupferzell"),
        "why_critical": "Critical when German production, inventory, or restructuring signals point to the HQ manufacturing footprint.",
        "likely_org_area": "Plant Management / Germany",
        "best_search_channel": "Company press releases, local registries, trade-press mentions, switchboard",
        "next_search_action": "Map the Kupferzell or Germany plant owner and connect that role to inventory and operational execution.",
    },
    {
        "role_name": "Aftermarket / Service Parts Lead",
        "tokens": ("aftermarket", "service", "spare parts", "retrofit"),
        "why_critical": "Critical to validate whether legacy parts can be monetized through service and retrofit channels instead of discounting.",
        "likely_org_area": "Aftermarket / Service / Retrofit",
        "best_search_channel": "Service pages, aftermarket partner pages, LinkedIn",
        "next_search_action": "Map who owns service-parts monetization and whether spare-parts channels can absorb legacy stock.",
    },
]

_PRIMARY_SOURCE_KEYWORDS = (
    "annual report",
    "geschaeftsbericht",
    "geschäftsbericht",
    "10-k",
    "20-f",
    "sec",
    "bundesanzeiger",
    "filing",
    "handelsregister",
    "companies house",
    "investor relations",
)

_HARD_FINANCIAL_SIGNAL_KEYWORDS = (
    "inventory",
    "bestand",
    "write-down",
    "write down",
    "abschreibung",
    "dio",
    "days inventory",
    "net debt",
    "working capital",
    "ebit",
    "net loss",
    "lager",
)

_DECISION_ROLE_TOKENS = (
    "cfo", "ceo", "coo", "vorstand", "geschaeftsfuehrer", "geschäftsführer",
    "managing director", "head", "leiter", "director", "vp", "vice president",
)

_FUNCTION_RELEVANCE_TOKENS = (
    "procurement", "purchasing", "einkauf", "supply chain", "logistics",
    "operations", "plant", "werk", "finance", "controlling", "aftermarket",
)


def _flatten_sources(*sections: dict[str, Any]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        for item in section.get("sources", []) or []:
            if isinstance(item, dict):
                flat.append(item)
    return flat


def _is_primary_source_record(source: dict[str, Any]) -> bool:
    source_type = str(source.get("source_type", "") or "").strip().lower()
    if source_type == "primary":
        return True
    text = " ".join(
        str(source.get(key, "") or "").strip().lower()
        for key in ("title", "url", "summary")
    )
    return any(token in text for token in _PRIMARY_SOURCE_KEYWORDS)


def _source_family(source: dict[str, Any]) -> str:
    text = " ".join(
        str(source.get(key, "") or "").strip().lower()
        for key in ("title", "url", "summary")
    )
    if any(token in text for token in ("annual report", "geschaeftsbericht", "geschäftsbericht", "10-k", "20-f")):
        return "annual_docs"
    if any(token in text for token in ("sec", "bundesanzeiger", "filing", "ad-hoc")):
        return "filings"
    if any(token in text for token in ("handelsregister", "companies house", "registry")):
        return "registries"
    return "other_primary"


def _collect_hard_financial_inventory_signals(company_profile: dict[str, Any]) -> list[str]:
    financial = (company_profile or {}).get("financial_deep_dive", {}) or {}
    buckets = [
        *list(financial.get("key_financials", []) or []),
        *list(financial.get("inventory_positions", []) or []),
        *list(financial.get("inventory_risks", []) or []),
        *list(financial.get("balance_sheet_signals", []) or []),
    ]
    signals: list[str] = []
    seen: set[str] = set()
    for item in _confident_signals([str(entry) for entry in buckets]):
        low = item.lower()
        if not any(token in low for token in _HARD_FINANCIAL_SIGNAL_KEYWORDS):
            continue
        key = item.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        signals.append(item.strip())
    return signals


def build_primary_source_stage(
    *,
    company_profile: dict[str, Any],
    industry_analysis: dict[str, Any],
    market_network: dict[str, Any],
) -> dict[str, Any]:
    """Dedicated stage before synthesis: validate primary-source grounding."""
    financial = (company_profile or {}).get("financial_deep_dive", {}) or {}
    event_intel = (company_profile or {}).get("transaction_event_intelligence", {}) or {}
    all_sources = _flatten_sources(
        company_profile,
        financial,
        event_intel,
        industry_analysis,
        market_network,
    )
    primary_sources = [src for src in all_sources if _is_primary_source_record(src)]
    families = sorted({_source_family(src) for src in primary_sources})
    hard_signals = _collect_hard_financial_inventory_signals(company_profile)
    return {
        "stage": "primary_source_validation",
        "required_source_families": ["annual_docs", "filings", "registries"],
        "source_families_covered": families,
        "public_primary_sources_available": bool(primary_sources),
        "coverage_quality": (
            "strong"
            if len(families) >= 2 and len(primary_sources) >= 2
            else "partial"
            if primary_sources
            else "weak"
        ),
        "primary_sources_used": primary_sources[:10],
        "hard_financial_inventory_signals": hard_signals,
        "hard_financial_inventory_signal_count": len(hard_signals),
    }


def _contact_confidence_score(contact: dict[str, Any]) -> int:
    role = f"{contact.get('rolle_titel', '')} {contact.get('funktion', '')}".strip().lower()
    source = _non_placeholder(contact.get("quelle"))
    confidence = str(contact.get("confidence", "") or "").strip().lower()
    seniority = str(contact.get("senioritaet", "") or "").strip().lower()
    score = 0
    if any(token in role for token in _DECISION_ROLE_TOKENS):
        score += 35
    if source:
        score += 25
    if confidence in {"high", "verified"}:
        score += 20
    elif confidence in {"medium", "inferred"}:
        score += 10
    if any(token in seniority for token in ("c-level", "executive", "director", "head", "leiter", "senior")):
        score += 10
    if any(token in role for token in _FUNCTION_RELEVANCE_TOKENS):
        score += 10
    return min(score, 100)


def build_contact_enrichment_stage(
    *,
    company_profile: dict[str, Any],
    contact_intelligence: dict[str, Any],
) -> dict[str, Any]:
    """Role-based contact enrichment with DE/EN patterns and confidence scoring."""
    target_contacts = (
        contact_intelligence.get("target_company_prioritized_contacts")
        or contact_intelligence.get("target_company_contacts")
        or []
    )
    role_text = " ".join(
        f"{item.get('rolle_titel', '')} {item.get('funktion', '')}"
        for item in target_contacts
        if isinstance(item, dict)
    ).lower()

    role_patterns: list[dict[str, Any]] = []
    for spec in TARGET_ROLE_SPECS:
        role_name = str(spec.get("role_name", "") or "")
        tokens = [str(token) for token in spec.get("tokens", []) if str(token).strip()]
        role_patterns.append(
            {
                "role_name": role_name,
                "patterns_de": [
                    f"{_non_placeholder(company_profile.get('company_name'))} {token} kontakt"
                    for token in tokens[:2]
                ],
                "patterns_en": [
                    f"{_non_placeholder(company_profile.get('company_name'))} {token} contact"
                    for token in tokens[:2]
                ],
            }
        )

    enriched_contacts: list[dict[str, Any]] = []
    verified_decision_makers: list[dict[str, Any]] = []
    for item in target_contacts:
        if not isinstance(item, dict):
            continue
        score = _contact_confidence_score(item)
        enriched = {
            **item,
            "confidence_score": score,
            "decision_role_match": any(
                token in f"{item.get('rolle_titel', '')} {item.get('funktion', '')}".lower()
                for token in _DECISION_ROLE_TOKENS
            ),
        }
        if not _non_placeholder(item.get("quelle")):
            enriched["source_availability_note"] = "keine freien Quellen"
        enriched_contacts.append(enriched)
        if enriched["decision_role_match"] and score >= 60:
            verified_decision_makers.append(enriched)

    missing_role_specs = [
        spec for spec in TARGET_ROLE_SPECS
        if not any(token in role_text for token in spec.get("tokens", ()))
    ]
    public_search_exhausted = bool(role_patterns) and not verified_decision_makers
    return {
        "stage": "contact_enrichment",
        "role_search_patterns": role_patterns,
        "target_contacts_enriched": enriched_contacts[:12],
        "verified_decision_makers": verified_decision_makers[:5],
        "verified_decision_makers_count": len(verified_decision_makers),
        "missing_critical_roles": [
            {
                "role_name": spec.get("role_name", "n/v"),
                "why_critical": spec.get("why_critical", "n/v"),
            }
            for spec in missing_role_specs[:6]
        ],
        "public_search_exhausted": public_search_exhausted,
    }


def _department_policy_gate_overview(
    department_packages: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(department_packages, dict):
        return {}
    overview: dict[str, Any] = {}
    for department in (
        "CompanyDepartment",
        "MarketDepartment",
        "BuyerDepartment",
        "ContactDepartment",
    ):
        raw = resolve_raw_package(department_packages.get(department, {}))
        policy_gate = raw.get("policy_gate", {}) if isinstance(raw, dict) else {}
        if not isinstance(policy_gate, dict):
            continue
        blockers = [
            item
            for item in policy_gate.get("blockers", [])
            if isinstance(item, dict)
        ]
        overview[department] = {
            "passed": bool(policy_gate.get("passed", True)),
            "blocker_count": len(blockers),
            "missing_required_fields": list(policy_gate.get("missing_required_fields", [])),
        }
    return overview


def _department_policy_gate_blockers(
    department_packages: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(department_packages, dict):
        return []
    blockers: list[dict[str, Any]] = []
    for department in (
        "CompanyDepartment",
        "MarketDepartment",
        "BuyerDepartment",
        "ContactDepartment",
    ):
        raw = resolve_raw_package(department_packages.get(department, {}))
        policy_gate = raw.get("policy_gate", {}) if isinstance(raw, dict) else {}
        if not isinstance(policy_gate, dict):
            continue
        if bool(policy_gate.get("passed", True)):
            continue
        for item in policy_gate.get("blockers", []):
            if not isinstance(item, dict):
                continue
            blockers.append(
                {
                    "blocker_id": str(item.get("blocker_id", f"{department}_policy_gate")).strip() or f"{department}_policy_gate",
                    "field_key": str(item.get("field_key", "department_policy_gate")).strip() or "department_policy_gate",
                    "availability": str(item.get("availability", "public")).strip() or "public",
                    "severity": str(item.get("severity", "hard")).strip() or "hard",
                    "reason": str(item.get("reason", f"{department} policy gate failed.")).strip() or f"{department} policy gate failed.",
                    "owner": str(item.get("owner", department)).strip() or department,
                    "next_step": str(item.get("next_step", "Close mandatory department fields and rerun gate.")).strip()
                    or "Close mandatory department fields and rerun gate.",
                }
            )
    return blockers


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


def _confident_signals(items: list[str]) -> list[str]:
    confident: list[str] = []
    for item in _positive_signals(items):
        lowered = item.lower()
        if any(marker in lowered for marker in UNCERTAIN_SIGNAL_MARKERS):
            continue
        confident.append(item)
    return confident


def _non_placeholder(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"", "n/v", "n/a", "unknown"} else text


def _step_to_text(value: Any) -> str:
    """Normalize synthesis step payloads to a concise string.

    Agents may emit structured step objects (dicts) while the runtime contract
    for ``synthesis.next_steps`` expects ``list[str]``. This helper preserves
    key action semantics and prevents schema failures.
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        action = _non_placeholder(
            value.get("action")
            or value.get("step")
            or value.get("title")
            or value.get("summary")
            or value.get("question")
            or value.get("label")
        )
        detail = _non_placeholder(
            value.get("goal")
            or value.get("expected_output")
            or value.get("output")
            or value.get("reason")
        )
        if action and detail:
            return f"{action} - {detail}"
        if action:
            return action
        scalar_parts: list[str] = []
        for item in value.values():
            if isinstance(item, (str, int, float, bool)):
                text = _non_placeholder(item)
                if text:
                    scalar_parts.append(text)
        return " | ".join(scalar_parts[:2])
    if isinstance(value, (list, tuple)):
        parts = [_step_to_text(item) for item in value]
        return " | ".join(part for part in parts if part)
    return str(value or "").strip()


def _normalize_text_items(values: Any) -> list[str]:
    if isinstance(values, list):
        raw = values
    elif values is None:
        raw = []
    else:
        raw = [values]
    normalized = [_step_to_text(item) for item in raw]
    return [
        str(item).strip()
        for item in _dedup_safe(normalized)
        if str(item).strip()
    ]


def _sentence_has_pressure_signal(text: str) -> bool:
    sentence = text.strip().lower()
    if not sentence:
        return False
    if any(
        marker in sentence
        for marker in (
            "no evidence", "no sign", "no signs", "no public signal", "without distress",
            "avoid excess stock", "prevent excess stock", "prevent write-down", "effective inventory management",
            "no write-down", "no write downs", "no inventory stress", "low financial pressure",
        )
    ):
        return False
    return any(kw in sentence for kw in _ECO_PRESSURE_KEYWORDS)


def _normalize_company_name(value: Any) -> str:
    text = _non_placeholder(value).lower()
    if not text:
        return ""
    text = (
        text.replace("&", " and ")
        .replace("-", " ")
        .replace("_", " ")
        .replace("/", " ")
    )
    for token in (
        " inc", " ltd", " llc", " gmbh", " ag", " se", " sa", " nv",
        " holdings", " holding", " group", " corporation", " corp", " company",
    ):
        text = text.replace(token, " ")
    return " ".join(part for part in text.split() if part)


def _is_specific_company_name(name: Any) -> bool:
    text = _non_placeholder(name)
    if not text:
        return False
    lowered = text.lower()
    if "," in lowered:
        return False
    if any(token in lowered for token in (
        "various", "operators", "customers", "end-users", "end users",
        "oems", "distributors", "service providers", "channels",
        "aftermarket", "industrial automation", "building technology",
        "commercial vehicle", "secondary markets", "fleet operators",
    )):
        return False
    if lowered.endswith(" oem") or lowered.endswith(" distributor") or lowered.endswith(" service provider"):
        return False
    if len(text.split()) < 1:
        return False
    return True


def _collect_validated_buyer_companies(
    market: dict[str, Any],
    *,
    target_company: str,
) -> list[dict[str, Any]]:
    target_norm = _normalize_company_name(target_company)
    buyer_tier = (market.get("downstream_buyers", {}) or {}).get("companies", []) or []
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for company in buyer_tier:
        if not isinstance(company, dict):
            continue
        name = company.get("name", "n/v")
        if not _is_specific_company_name(name):
            continue
        normalized = _normalize_company_name(name)
        if not normalized or normalized == target_norm or normalized in seen:
            continue
        seen.add(normalized)
        validated.append(company)
    return validated


def _synthesis_is_actionable(synthesis: dict[str, Any] | None) -> bool:
    if not isinstance(synthesis, dict):
        return False
    generation_mode = str(synthesis.get("generation_mode", "") or "").strip().lower()
    executive_summary = str(synthesis.get("executive_summary", "") or "").strip().lower()
    opportunity_summary = str(synthesis.get("opportunity_assessment_summary", "") or "").strip().lower()
    if generation_mode == "blocked":
        return False
    if any(marker in executive_summary for marker in SYNTHESIS_INCOMPLETE_MARKERS):
        return False
    if any(marker in opportunity_summary for marker in SYNTHESIS_INCOMPLETE_MARKERS):
        return False
    if generation_mode == "fallback" and not _non_placeholder(opportunity_summary):
        return False
    return bool(
        (synthesis.get("recommended_engagement_paths") or [])
        and _non_placeholder(synthesis.get("executive_summary"))
        and _non_placeholder(synthesis.get("opportunity_assessment_summary"))
    )


def _has_financial_substance(company_profile: dict[str, Any] | None) -> bool:
    profile = company_profile or {}
    financial = profile.get("financial_deep_dive", {}) or {}
    assessment = _non_placeholder(financial.get("assessment"))
    key_financials = _positive_signals(list(financial.get("key_financials", []) or []))
    inventory_positions = _positive_signals(list(financial.get("inventory_positions", []) or []))
    balance_sheet_signals = _positive_signals(list(financial.get("balance_sheet_signals", []) or []))
    inventory_risks = _positive_signals(list(financial.get("inventory_risks", []) or []))
    signal_count = sum(
        1 for bucket in (key_financials, inventory_positions, balance_sheet_signals, inventory_risks) if bucket
    )
    if signal_count >= 3:
        return True
    if assessment and signal_count >= 2:
        return True
    if len(key_financials) >= 2 and (inventory_positions or balance_sheet_signals):
        return True
    return False


def _infer_buying_center(contact: dict[str, Any]) -> str:
    role = f"{contact.get('rolle_titel', '')} {contact.get('funktion', '')}".lower()
    if any(token in role for token in ("cfo", "finance", "working capital", "controlling")):
        return "Economic buyer"
    if any(token in role for token in ("procurement", "purchasing", "einkauf")):
        return "Procurement gatekeeper"
    if any(token in role for token in ("operations", "plant", "werk", "production", "logistics", "supply chain")):
        return "Operational sponsor"
    if any(token in role for token in ("aftermarket", "service", "retrofit")):
        return "Aftermarket owner"
    if any(token in role for token in ("cto", "technology", "product")):
        return "Technical owner"
    if any(token in role for token in ("ceo", "coo", "managing director")):
        return "Executive sponsor"
    return "Stakeholder"


def _channel_type(source: str) -> str:
    src = str(source or "").strip()
    lowered = src.lower()
    if "linkedin.com" in lowered:
        return "linkedin"
    if "xing.com" in lowered:
        return "linkedin"
    if src.startswith("mailto:") or ("@" in src and "http" not in lowered):
        return "email"
    if src.startswith("tel:") or lowered.replace("+", "").replace(" ", "").replace("-", "").isdigit():
        return "phone"
    if lowered.startswith("http"):
        if any(token in lowered for token in ("press", "presse", "newsroom", "media")):
            return "press contact"
        if any(token in lowered for token in ("company", "unternehmen", "leadership", "management", "about")):
            return "company website"
        return "company website"
    return "assistant / switchboard"


def _channel_label(source: str) -> str:
    mapping = {
        "linkedin": "LinkedIn",
        "company website": "Company or public web source",
        "email": "Email",
        "phone": "Phone",
        "assistant / switchboard": "Assistant / switchboard",
        "press contact": "Press contact",
    }
    return mapping.get(_channel_type(source), "Public source")


def _verification_status(contact: dict[str, Any], source: str) -> str:
    confidence = str(contact.get("confidence", "") or "").strip().lower()
    channel_type = _channel_type(source)
    if channel_type in {"email", "phone"} and confidence not in {"high", "verified"}:
        return "unverified_excluded_from_pdf"
    if confidence in {"high", "verified"}:
        return "verified"
    if source:
        return "partially_verified"
    return "role_inferred"


def _contact_objection(contact: dict[str, Any]) -> str:
    buying_center = _infer_buying_center(contact)
    if buying_center == "Economic buyer":
        return "Will ask for quantified working-capital impact and a low-friction first step."
    if buying_center == "Procurement gatekeeper":
        return "May resist outreach without proof that supplier commitments or inbound overhang are affected."
    if buying_center == "Operational sponsor":
        return "Will want operational specificity on where inventory is stuck and what team effort is required."
    if buying_center == "Aftermarket owner":
        return "May question whether service channels can absorb stock without channel conflict."
    return "Will want proof that the topic is commercially material and worth management attention."


def _contact_outreach_rationale(contact: dict[str, Any]) -> str:
    role = _non_placeholder(contact.get("rolle_titel")) or _non_placeholder(contact.get("funktion")) or "the role"
    reason = _non_placeholder(contact.get("relevance_reason")) or "Role is relevant for inventory, working capital, or operational ownership."
    return f"Start with {role} because {reason}"


def _render_profile_channel(source: str, verification_status: str) -> str:
    if verification_status == "unverified_excluded_from_pdf":
        return "Assistant / switchboard route only until direct channel is verified."
    if source:
        return f"{_channel_label(source)}: {source}"
    return "No direct public channel (keine freien Quellen); use switchboard/network intro path."


def _contact_priority_score(contact: dict[str, Any]) -> int:
    role_title = str(
        contact.get("rolle_titel")
        or contact.get("role")
        or contact.get("buying_center_role")
        or ""
    )
    function = str(
        contact.get("funktion")
        or contact.get("relevance_buying_center")
        or ""
    )
    normalized = {
        "rolle_titel": role_title,
        "funktion": function,
    }
    buying_center = _infer_buying_center(normalized)
    role_text = f"{role_title} {function}".lower()
    score = 0
    if buying_center == "Economic buyer":
        score += 7
    elif buying_center == "Operational sponsor":
        score += 6
    elif buying_center == "Procurement gatekeeper":
        score += 5
    elif buying_center == "Aftermarket owner":
        score += 4
    elif buying_center == "Executive sponsor":
        score += 3
    elif buying_center == "Technical owner":
        score += 2
    if any(token in role_text for token in ("cfo", "finance", "controlling", "working capital")):
        score += 3
    if any(token in role_text for token in ("plant", "operations", "production", "logistics", "supply chain", "procurement")):
        score += 2
    if any(token in role_text for token in ("aftermarket", "service", "parts", "retrofit")):
        score += 1
    return score


def _preferred_contact_name(contact_cards: list[dict[str, Any]], *, top_path: str) -> str:
    if not contact_cards:
        return "CEO / CFO sponsor"
    best = sorted(
        contact_cards,
        key=lambda item: (-_contact_priority_score(item), str(item.get("name", ""))),
    )[0]
    return _non_placeholder(best.get("name")) or "CEO / CFO sponsor"


def _company_signal_text(
    company_profile: dict[str, Any],
    market_network: dict[str, Any],
) -> str:
    economic = company_profile.get("economic_situation", {}) or {}
    event_intel = company_profile.get("transaction_event_intelligence", {}) or {}
    financial = company_profile.get("financial_deep_dive", {}) or {}
    texts = [
        company_profile.get("description", ""),
        economic.get("assessment", ""),
        economic.get("financial_pressure", ""),
        event_intel.get("assessment", ""),
        financial.get("assessment", ""),
        (market_network.get("downstream_buyers") or {}).get("assessment", ""),
        (market_network.get("peer_competitors") or {}).get("assessment", ""),
    ]
    for key in ("recent_events", "inventory_signals"):
        texts.extend(economic.get(key, []) or [])
    for key in ("strategic_events", "carve_out_signals", "regulatory_signals"):
        texts.extend(event_intel.get(key, []) or [])
    for key in ("key_financials", "inventory_positions", "inventory_risks", "balance_sheet_signals"):
        texts.extend(financial.get(key, []) or [])
    return " ".join(str(item) for item in texts if item).lower()


def _site_focus_hint(
    company_profile: dict[str, Any],
    market_network: dict[str, Any],
) -> str:
    text = _company_signal_text(company_profile, market_network)
    if any(token in text for token in ("poland", "polen")):
        return "Poland"
    if "kupferzell" in text:
        return "Kupferzell"
    if any(token in text for token in ("winston-salem", "north carolina")):
        return "Winston-Salem"
    if any(token in text for token in ("europe", "europa", "dach", "germany", "deutschland")):
        return "European footprint"
    return "core plant footprint"


def _preferred_missing_role(
    missing_roles: list[dict[str, Any]],
    *,
    company_profile: dict[str, Any],
    market_network: dict[str, Any],
    top_path: str,
) -> str:
    if not missing_roles:
        return "Operational inventory owner"
    site_hint = _site_focus_hint(company_profile, market_network).lower()
    role_names = [str(role.get("role_name", "")) for role in missing_roles]
    if site_hint != "core plant footprint":
        for role_name in role_names:
            if site_hint in role_name.lower():
                return role_name
    if top_path == "excess_inventory":
        for token in ("procurement", "plant", "aftermarket"):
            for role_name in role_names:
                if token in role_name.lower():
                    return role_name
    return role_names[0]


def _secondary_missing_role(
    missing_roles: list[dict[str, Any]],
    primary_role: str,
) -> str:
    for role in missing_roles:
        role_name = str(role.get("role_name", "") or "")
        if role_name and role_name != primary_role:
            return role_name
    return primary_role


def build_contact_briefing_assets(
    *,
    company_profile: dict[str, Any],
    contact_intelligence: dict[str, Any],
) -> dict[str, Any]:
    target_contacts = (
        contact_intelligence.get("target_company_prioritized_contacts")
        or contact_intelligence.get("target_company_contacts")
        or []
    )
    normalized_target_contacts: list[dict[str, Any]] = []
    cards: list[dict[str, str]] = []
    target_text = " ".join(
        [
            str(contact.get("rolle_titel", ""))
            for contact in target_contacts
            if isinstance(contact, dict)
        ] + [
            str(contact.get("funktion", ""))
            for contact in target_contacts
            if isinstance(contact, dict)
        ]
    ).lower()

    hq = _non_placeholder(company_profile.get("headquarters")) or "n/v"
    for contact in target_contacts[:5]:
        if not isinstance(contact, dict):
            continue
        source = _non_placeholder(contact.get("quelle"))
        buying_center = _infer_buying_center(contact)
        channel_type = _channel_type(source)
        verification_status = _verification_status(contact, source)
        normalized_contact = {
            **contact,
            "buying_center_role": contact.get("buying_center_role") or buying_center.lower().replace(" ", "_"),
            "verified_channel_type": contact.get("verified_channel_type") or channel_type,
            "verification_status": contact.get("verification_status") or verification_status,
        }
        normalized_target_contacts.append(normalized_contact)
        if verification_status == "unverified_excluded_from_pdf":
            continue
        company = _non_placeholder(contact.get("firma")) or _non_placeholder(company_profile.get("company_name")) or "n/v"
        location = _non_placeholder(contact.get("standort")) or hq
        cards.append({
            "name": _non_placeholder(contact.get("name")) or "n/v",
            "role": _non_placeholder(contact.get("rolle_titel")) or _non_placeholder(contact.get("funktion")) or "n/v",
            "organization_location": (
                f"{company} ({location})" if location != "n/v" else company
            ),
            "relevance_buying_center": (
                f"{buying_center}. "
                f"{_non_placeholder(contact.get('relevance_reason')) or 'Relevant for inventory, working capital, or operating-model validation.'}"
            ).strip(),
            "profile_contact_channel": _render_profile_channel(source, verification_status),
            "source_verification": (
                f"{'Verified' if str(contact.get('confidence', '')).lower() == 'high' else 'Partially verified'} via {source}"
                if source else
                "No public sources for direct channel (keine freien Quellen); role inferred from public evidence."
            ),
            "verified_channel_type": channel_type,
            "verification_status": verification_status,
            "buying_center_role": normalized_contact["buying_center_role"],
            "outreach_rationale": _contact_outreach_rationale(contact),
            "likely_objection": _contact_objection(contact),
            "confidence": _non_placeholder(contact.get("confidence")) or "inferred",
        })

    missing_roles: list[dict[str, str]] = []
    for spec in TARGET_ROLE_SPECS:
        if any(token in target_text for token in spec["tokens"]):
            continue
        missing_roles.append({
            "role_name": spec["role_name"],
            "why_critical": spec["why_critical"],
            "likely_org_area": spec["likely_org_area"],
            "best_search_channel": spec["best_search_channel"],
            "next_search_action": spec["next_search_action"],
        })

    cards.sort(key=lambda item: (-_contact_priority_score(item), item.get("name", "")))

    access_path = []
    if cards:
        first_name = cards[0]["name"]
        access_path.append(
            f"Open top-down with {first_name}, then request handoff to the operational owner for inventory, procurement, or plant execution."
        )
    if missing_roles:
        access_path.append(
            f"Close the remaining stakeholder gap before outreach by identifying: {', '.join(role['role_name'] for role in missing_roles[:3])}."
        )
    access_path.append(
        "Keep buyer/partner contacts separate from target-company stakeholders; do not mix them in the target-contact section."
    )
    if missing_roles:
        access_path.append(
            "Do not invent direct email addresses or phone numbers; close the remaining role gap first via Sales Navigator, assistant, or switchboard routes."
        )

    named_contacts = ", ".join(card["name"] for card in cards[:3]) if cards else "no named stakeholders"
    missing_role_text = ", ".join(role["role_name"] for role in missing_roles[:3]) if missing_roles else "no critical role gaps"
    target_company_summary = (
        "Only publicly evidenced named stakeholders are listed; no placeholder email addresses or phone numbers are generated. "
        f"The current map is strongest at the executive level around {named_contacts}. "
        f"The remaining operational gaps are: {missing_role_text}. "
        "Close these roles before any cold outreach sequence is written."
    )

    return {
        "target_company_contacts": normalized_target_contacts or target_contacts,
        "target_company_prioritized_contacts": (normalized_target_contacts or target_contacts)[:5],
        "target_company_contact_cards": cards,
        "target_company_missing_roles": missing_roles,
        "target_company_access_path": access_path,
        "target_company_summary": target_company_summary,
    }


def build_playbook_assets(
    *,
    company_profile: dict[str, Any],
    market_network: dict[str, Any],
    contact_intelligence: dict[str, Any],
    synthesis: dict[str, Any],
) -> dict[str, Any]:
    company_name = _non_placeholder(company_profile.get("company_name")) or "the target company"
    top_path = ((synthesis.get("recommended_engagement_paths") or [])[:1] or ["further_validation_required"])[0]
    contact_cards = contact_intelligence.get("target_company_contact_cards") or []
    missing_roles = contact_intelligence.get("target_company_missing_roles") or []
    top_contact = _preferred_contact_name(contact_cards, top_path=top_path)
    top_role_gap = _preferred_missing_role(
        missing_roles,
        company_profile=company_profile,
        market_network=market_network,
        top_path=top_path,
    )
    secondary_role_gap = _secondary_missing_role(missing_roles, top_role_gap)
    buyer_count = len((market_network.get("downstream_buyers") or {}).get("companies", []) or [])
    site_hint = _site_focus_hint(company_profile, market_network)
    site_phrase = {
        "Poland": "especially in the Polish plant footprint",
        "Kupferzell": "especially in Kupferzell and adjacent German production",
        "Winston-Salem": "especially in the Winston-Salem ramp-up and adjacent reporting lines",
        "European footprint": "especially across the European footprint",
    }.get(site_hint, "across the core plant footprint")
    open_questions = [
        {
            "label": "Bestandsvolumen",
            "question": f"What is the current book-value and physical volume of slow-moving or excess inventory at {company_name}, split by site and business line {site_phrase}?",
            "why_critical": "This determines whether the excess-inventory case is commercially material enough for immediate action.",
            "hypothesis_tested": "There is enough trapped working capital to justify a monetization mandate.",
            "owner": top_contact,
            "timing": "during_meeting",
            "meeting_criticality": "must-answer-in-meeting",
            "decision_impact": "Confirms whether Liquisto should lead with inventory-to-cash positioning.",
        },
        {
            "label": "Standardisierungsgrad",
            "question": "What share of the overhang is standard, resale-capable inventory versus customer-specific OEM configuration, and which share can move without engineering change?",
            "why_critical": "This decides whether redeployment can happen quickly or only via selective channels.",
            "hypothesis_tested": "A meaningful portion of stock is transferable to secondary OEM or aftermarket demand.",
            "owner": top_role_gap,
            "timing": "during_meeting",
            "meeting_criticality": "must-answer-in-meeting",
            "decision_impact": "Changes buyer targeting, discount logic, and expected conversion speed.",
        },
        {
            "label": "WIP-Stufe",
            "question": f"Where is inventory currently stuck most heavily {site_phrase}: raw materials, purchased electronics, WIP, service parts, or finished goods?",
            "why_critical": "The optimal monetization path differs completely by asset maturity and material state.",
            "hypothesis_tested": "The overhang can be segmented into discrete pools with different liquidation routes.",
            "owner": top_role_gap,
            "timing": "during_meeting",
            "meeting_criticality": "must-answer-in-meeting",
            "decision_impact": "Determines whether Liquisto pitches finished-goods redeployment or component brokerage first.",
        },
        {
            "label": "Obsoleszenz-Management",
            "question": "How much of the inventory overhang is already at risk of obsolescence, aging, or write-down if no action is taken in the next two quarters?",
            "why_critical": "The urgency, discount logic, and likely value-recovery path depend on how much stock is already drifting into obsolescence.",
            "hypothesis_tested": "A meaningful portion of the stock requires immediate action before further value erosion occurs.",
            "owner": top_contact,
            "timing": "during_meeting",
            "meeting_criticality": "must-answer-in-meeting",
            "decision_impact": "Determines urgency, pricing posture, and whether Liquisto leads with rapid stock release versus structured diagnostics.",
        },
        {
            "label": "Compliance / Brand Protection",
            "question": "Which brand, channel, compliance, or customer-conflict rules limit secondary sales, aftermarket resale, or discreet buyer matching?",
            "why_critical": "Commercial feasibility depends on whether management allows controlled external monetization.",
            "hypothesis_tested": "The company can monetize excess stock without damaging premium positioning or OEM relationships.",
            "owner": top_contact,
            "timing": "during_meeting",
            "meeting_criticality": "must-answer-in-meeting",
            "decision_impact": "Defines which buyer categories and go-to-market mechanics are viable.",
        },
        {
            "label": "Entscheider / NDA",
            "question": f"Who owns the release decision for excess inventory in Europe, and who can sponsor NDA-based data sharing after the meeting with support from {secondary_role_gap} if needed?",
            "why_critical": "Without a named operational sponsor, the opportunity will stall after an encouraging first discussion.",
            "hypothesis_tested": "A reachable owner exists who can move from discussion to data room and pilot scope.",
            "owner": top_contact,
            "timing": "during_meeting",
            "meeting_criticality": "can-be-validated-after-meeting" if missing_roles else "must-answer-in-meeting",
            "decision_impact": "Determines whether Liquisto can progress directly to post-meeting data collection.",
        },
    ]

    angle_step = {
        "phase": "pre_meeting",
        "owner": "Liquisto Account Lead",
        "action": f"Prepare a hypothesis-led executive outreach for {top_contact} that frames Liquisto as a stock monetization and redeployment partner tied to trapped working capital.",
        "target_person": top_contact,
        "asset_hypothesis": "There is a commercially material inventory-to-cash or redeployment case tied to trapped working capital and site-specific ownership.",
        "goal": "Enter the meeting with a sharp commercial angle around trapped stock, redeployment routes, and value release.",
        "expected_output": "One tailored opening message, one meeting hypothesis, and a 3-point narrative for the first call.",
        "success_criterion": "The opening clearly links Liquisto's offer to the stakeholder's agenda and the likely ownership structure.",
        "definition_of_done": "A tailored outreach note and a concise opening narrative are ready for the first conversation.",
        "dependency": "Target-company sponsor identified",
    }
    channel_step = {
        "phase": "pre_meeting",
        "owner": "Liquisto SDR / Research",
        "action": f"Close the operational contact gap around `{top_role_gap}` via Sales Navigator, assistant, and switchboard routes before or immediately after first response.",
        "target_person": top_role_gap,
        "asset_hypothesis": "The opportunity will stall if Liquisto reaches only CFO / CEO level and cannot hand off into plant, supply-chain, or procurement ownership.",
        "goal": "Prioritize contact channels before any cold-outreach sequence scales.",
        "expected_output": "Named operational stakeholder or a callable escalation path tied to the missing role.",
        "success_criterion": "At least one operational owner or named escalation route is documented for follow-up.",
        "definition_of_done": "A named operational owner or an explicit escalation route is documented for follow-up.",
        "dependency": "Missing target role remains unresolved after public-web search",
    }
    next_steps = [
        channel_step,
        angle_step,
        {
            "phase": "during_meeting",
            "owner": "Liquisto Account Lead",
            "action": (
                f"Validate the five critical questions in sequence: visibility gap, steering rhythm, data access, segmentation, and decision ownership {site_phrase}."
                if top_path == "analytics"
                else f"Validate the five critical questions in sequence: inventory volume, standardization, WIP stage, governance constraints, and decision ownership {site_phrase}."
            ),
            "target_person": top_contact,
            "asset_hypothesis": "The first meeting can convert the case from directional interest into a qualified monetization or analytics opportunity.",
            "goal": (
                "Convert the first meeting into a qualification gate for a real analytics pilot or visibility diagnostic."
                if top_path == "analytics"
                else "Convert the first meeting into a qualification gate for a real inventory monetization or analytics project."
            ),
            "expected_output": "Structured answers, owner names, and one concrete post-meeting work package that confirm or disprove the lead hypothesis.",
            "success_criterion": "At least three of the five questions are answered with concrete operational detail.",
            "definition_of_done": "The meeting yields enough operational detail to confirm, downgrade, or redirect the lead path.",
            "dependency": "Meeting secured",
        },
        {
            "phase": "post_meeting",
            "owner": "Liquisto Account Lead",
            "action": "Send a 24-hour recap with the validated opportunity path, named sponsor, and explicit request for the next operational working session.",
            "target_person": top_contact,
            "asset_hypothesis": "Momentum from the first meeting will decay unless Liquisto anchors the path, owner, and next work package immediately.",
            "goal": "Turn meeting momentum into a committed follow-up step.",
            "expected_output": "Recap email with agreed next call, stakeholder list, validated questions, and the requested data scope.",
            "success_criterion": "A follow-up meeting or data-review slot is scheduled.",
            "definition_of_done": "A follow-up slot or explicit review cadence is confirmed in writing.",
            "dependency": "Positive first meeting",
        },
        {
            "phase": "post_meeting_under_nda",
            "owner": "Liquisto Account Lead",
            "action": (
                f"Request a lightweight NDA package with plant-level inventory snapshots, slow movers, backlog, demand signals, and reporting exports relevant for a first diagnostic {site_phrase}."
                if top_path == "analytics"
                else f"Request a lightweight NDA package with inventory aging, slow movers, WIP segmentation, and any write-down or working-capital views {site_phrase}."
            ),
            "target_person": top_role_gap,
            "asset_hypothesis": "A quantified deal view requires operational data beyond what public research can provide.",
            "goal": "Move from hypothesis to quantified deal sizing.",
            "expected_output": (
                "Structured data extract suitable for a fast analytics diagnostic and segmentation view, including site and SKU granularity."
                if top_path == "analytics"
                else "Structured data extract suitable for buyer matching or inventory diagnostics, including site and asset-state granularity."
            ),
            "success_criterion": "Data package received or explicitly approved for transfer.",
            "definition_of_done": "The NDA-backed data package is received or the transfer scope is explicitly approved.",
            "dependency": "Named operational owner and NDA approval",
        },
    ]
    if buyer_count and top_path != "analytics":
        next_steps.insert(
            3,
            {
                "phase": "post_meeting",
                "owner": "Liquisto Commercial",
                "action": "Validate the top buyer categories against CRM and existing network fit before any external buyer outreach begins.",
                "target_person": f"{buyer_count} buyer categories already identified",
                "asset_hypothesis": "Only a subset of buyer lanes will remain viable after CRM, channel, and asset-fit validation.",
                "goal": "Keep redeployment outreach tightly matched to asset fit and channel constraints.",
                "expected_output": "Shortlisted buyer lanes with CRM overlap and exclusion rules.",
                "success_criterion": "Only buyer categories with verified asset-fit remain in the plan.",
                "definition_of_done": "The buyer list is reduced to validated lanes with explicit exclusions before outreach starts.",
                "dependency": "Meeting confirms monetizable stock exists",
            },
        )
    visible_steps = next_steps[:]
    if len(visible_steps) > 6:
        required_phases = {"pre_meeting", "during_meeting", "post_meeting", "post_meeting_under_nda"}
        selected: list[dict[str, Any]] = []
        covered: set[str] = set()
        for step in visible_steps:
            phase = str(step.get("phase", "")).strip()
            if phase in required_phases and phase not in covered:
                selected.append(step)
                covered.add(phase)
        for step in visible_steps:
            if len(selected) >= 6:
                break
            if step not in selected:
                selected.append(step)
        visible_steps = selected[:6]

    return {
        "critical_open_questions": open_questions[:5],
        "recommended_next_steps": visible_steps,
    }


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
    contact_intelligence: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    monetization = _confident_signals(market.get("monetization_paths", []))
    target_company = (company_profile or {}).get("company_name", "")
    downstream_buyers = _collect_validated_buyer_companies(market, target_company=target_company)
    financial = (company_profile or {}).get("financial_deep_dive", {})
    event_intel = (company_profile or {}).get("transaction_event_intelligence", {})
    inventory_positions = _positive_signals(financial.get("inventory_positions", []))
    inventory_risks = _positive_signals(financial.get("inventory_risks", []))
    balance_sheet_signals = _positive_signals(financial.get("balance_sheet_signals", []))
    carve_out_signals = _positive_signals(event_intel.get("carve_out_signals", []))

    # Check economic_situation for restructuring / inventory pressure signals
    eco = (company_profile or {}).get("economic_situation", {})
    eco_sentences = list(eco.get("recent_events", [])) + [
        str(eco.get("assessment", "")),
        str(eco.get("financial_pressure", "")),
        *list(eco.get("inventory_signals", []) or []),
    ]
    has_eco_pressure = any(_sentence_has_pressure_signal(str(sentence)) for sentence in eco_sentences)
    buyer_contacts = (
        (contact_intelligence or {}).get("prioritized_contacts", [])
        or (contact_intelligence or {}).get("contacts", [])
    )
    has_named_buyer_coverage = len(buyer_contacts) >= 2

    has_financial_signals = bool(inventory_positions or inventory_risks or balance_sheet_signals)
    buyer_route_strength = 0
    if len(downstream_buyers) >= 2:
        buyer_route_strength += 2
    elif len(downstream_buyers) == 1:
        buyer_route_strength += 1
    if len(buyer_contacts) >= 2:
        buyer_route_strength += 2
    elif buyer_contacts:
        buyer_route_strength += 1
    if monetization:
        buyer_route_strength += 1
    has_buyer_routes = buyer_route_strength >= 4 and has_named_buyer_coverage

    excess_score = 0
    if has_buyer_routes:
        excess_score += 2 + min(1, buyer_route_strength - 4)
    if has_eco_pressure:
        excess_score += 2 if has_financial_signals or has_buyer_routes else 1
    if inventory_positions:
        excess_score += 3
    if inventory_risks or balance_sheet_signals:
        excess_score += 2
    if carve_out_signals:
        excess_score += 1
    if not has_financial_signals and (buyer_route_strength < 4 or not has_named_buyer_coverage):
        excess_score = min(excess_score, 1)
    return [{
        "service_area": "excess_inventory",
        "relevance": "high" if excess_score >= 5 else "medium" if excess_score >= 2 else "unclear",
        "reasoning": (
            "Primary-source inventory and balance-sheet signals support an inventory-to-cash angle."
            if has_financial_signals
            else "Economic pressure signals and buyer-path evidence indicate potential excess asset disposition needs."
            if has_buyer_routes or has_eco_pressure or carve_out_signals
            else "No validated monetization route with buyer or financial evidence is available yet."
        ),
    }]


def build_synthesis_context(
    *,
    company_profile: dict[str, Any],
    industry_analysis: dict[str, Any],
    market_network: dict[str, Any],
    contact_intelligence: dict[str, Any],
    quality_review: dict[str, Any],
    memory_snapshot: dict[str, Any],
    primary_source_stage: dict[str, Any] | None = None,
    contact_enrichment_stage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare a synthesis context payload from department outputs.

    This is pre-processing input for the AG2 SynthesisDepartment, not a
    parallel synthesis author.  When AG2 succeeds, the AG2 output takes
    authority (generation_mode="normal").  When AG2 times out or fails,
    this context is promoted to the final synthesis with
    generation_mode="fallback".  Confidence is derived from input package
    quality — fallback does NOT automatically mean low confidence.
    """
    service_relevance = _service_relevance(
        industry_analysis,
        market_network,
        company_profile,
        contact_intelligence,
    )
    primary_stage = primary_source_stage or build_primary_source_stage(
        company_profile=company_profile,
        industry_analysis=industry_analysis,
        market_network=market_network,
    )
    contact_stage = contact_enrichment_stage or build_contact_enrichment_stage(
        company_profile=company_profile,
        contact_intelligence=contact_intelligence,
    )
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
    research_backlog = _normalize_text_items(memory_snapshot.get("next_actions", [])) or [
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
        "next_steps": research_backlog,
        "research_backlog": research_backlog + (
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
        "primary_source_stage": primary_stage,
        "contact_enrichment_stage": contact_stage,
    }


def harmonize_synthesis_output(
    *,
    synthesis: dict[str, Any],
    company_profile: dict[str, Any],
    industry_analysis: dict[str, Any],
    market_network: dict[str, Any],
    contact_intelligence: dict[str, Any],
    quality_review: dict[str, Any],
) -> dict[str, Any]:
    """Normalize synthesis path ordering against validated runtime evidence."""
    merged = dict(synthesis or {})
    service_relevance = _service_relevance(
        industry_analysis,
        market_network,
        company_profile,
        contact_intelligence,
    )
    recommended_paths = [
        item["service_area"]
        for item in service_relevance
        if item.get("relevance") != "unclear"
    ] or ["further_validation_required"]
    top_path = recommended_paths[0]
    previous_paths = merged.get("recommended_engagement_paths", []) or []
    previous_top = str(previous_paths[0]).strip().lower() if previous_paths else ""
    merged["liquisto_service_relevance"] = service_relevance
    merged["recommended_engagement_paths"] = recommended_paths

    if top_path != previous_top:
        company_name = _non_placeholder(company_profile.get("company_name")) or "the target company"
        if top_path == "excess_inventory":
            merged["opportunity_assessment_summary"] = (
                f"Excess inventory remains the primary path for {company_name} because validated buyer-route and "
                "financial pressure signals are strong enough to support an inventory-to-cash conversation."
            )

    merged["key_risks"] = _normalize_text_items(merged.get("key_risks", []))
    merged["next_steps"] = _normalize_text_items(merged.get("next_steps", []))
    merged["research_backlog"] = _normalize_text_items(
        merged.get("research_backlog", merged.get("next_steps", []))
    )

    if top_path == "excess_inventory" and quality_review.get("evidence_health") in {"medium", "high"}:
        merged["confidence"] = quality_review.get("evidence_health", merged.get("confidence", "medium"))
    return merged


def _build_data_request_sheet(
    *,
    company_name: str,
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    internal_hard = [
        item for item in blockers
        if str(item.get("availability", "")) == "internal_customer"
        and str(item.get("severity", "")) == "hard"
    ]
    required_fields: list[dict[str, Any]] = []
    if any(item.get("field_key") == "minimum_package.hard_financial_inventory_signals" for item in internal_hard):
        required_fields.extend(
            [
                {
                    "field_key": "inventory_aging_by_site_sku",
                    "label": "Lageralterung je Standort/SKU",
                    "why_needed": "Belegt, ob ein materialer Excess-Inventory-Fall vorliegt.",
                    "owner": "Customer Controlling / Finance",
                    "nda_required": True,
                    "availability": "internal_customer",
                },
                {
                    "field_key": "dio_by_division",
                    "label": "DIO (Days Inventory Outstanding) je Division",
                    "why_needed": "Ermoeglicht Working-Capital-basierte Priorisierung.",
                    "owner": "Customer Finance",
                    "nda_required": True,
                    "availability": "internal_customer",
                },
                {
                    "field_key": "write_down_history",
                    "label": "Write-downs / Abschreibungen der letzten 8 Quartale",
                    "why_needed": "Zeigt Dringlichkeit und wirtschaftlichen Druck auf den Bestand.",
                    "owner": "Customer Finance",
                    "nda_required": True,
                    "availability": "internal_customer",
                },
            ]
        )
    if any(item.get("field_key") == "minimum_package.verified_decision_makers" for item in internal_hard):
        required_fields.append(
            {
                "field_key": "target_stakeholder_map",
                "label": "Ansprechpartnerliste mit Rolle, Verantwortungsbereich, Intro-Pfad",
                "why_needed": "Ohne verifizierten Entscheider bleibt das Briefing nur Discovery-ready.",
                "owner": "Customer Sponsor / Sales Owner",
                "nda_required": False,
                "availability": "internal_customer",
            }
        )

    return {
        "status": "required" if required_fields else "not_required",
        "company_name": company_name or "n/v",
        "scope": "Disambiguate internal-only evidence gaps that cannot be validated from public sources.",
        "request_fields": required_fields,
        "submission_format": [
            "CSV/Excel export for inventory and finance fields",
            "Named stakeholder list (Name, Role, Function, Intro path)",
        ],
        "owner": "Liquisto Account Lead",
    }


def _build_outreach_playbook(
    *,
    company_name: str,
    contact_enrichment_stage: dict[str, Any],
) -> dict[str, Any]:
    verified = contact_enrichment_stage.get("verified_decision_makers", []) or []
    role_gaps = contact_enrichment_stage.get("missing_critical_roles", []) or []
    primary_contact = verified[0] if verified else {}
    if verified:
        contact_label = _non_placeholder(primary_contact.get("name")) or _non_placeholder(primary_contact.get("rolle_titel")) or "n/v"
        status = "ready"
        steps = [
            {
                "step": 1,
                "action": f"Open with {contact_label} on inventory-to-cash hypothesis and validate decision ownership.",
                "owner": "Liquisto Account Lead",
                "depends_on": "Publicly verifiable contact confirmed",
            },
            {
                "step": 2,
                "action": "Secure handoff to operational owner (procurement/supply chain/plant) within first meeting.",
                "owner": "Liquisto Account Lead",
                "depends_on": "Initial sponsor response",
            },
        ]
    else:
        missing_role = _non_placeholder((role_gaps[:1] or [{}])[0].get("role_name")) or "operational inventory owner"
        status = "blocked_by_contact_gap"
        steps = [
            {
                "step": 1,
                "action": f"No public decision-maker could be verified (keine freien Quellen). Request customer intro to {missing_role}.",
                "owner": "Customer Sponsor",
                "depends_on": "Customer-side stakeholder mapping",
            },
            {
                "step": 2,
                "action": "Use role-based DE/EN search patterns to validate title and channel before outbound.",
                "owner": "Contact Department",
                "depends_on": "Stakeholder hint received",
            },
        ]
    return {
        "status": status,
        "company_name": company_name or "n/v",
        "entry_contact": primary_contact,
        "steps": steps,
    }


def assess_research_readiness(
    *,
    company_profile: dict[str, Any],
    industry_analysis: dict[str, Any],
    market_network: dict[str, Any],
    contact_intelligence: dict[str, Any],
    quality_review: dict[str, Any],
    synthesis: dict[str, Any] | None = None,
    primary_source_stage: dict[str, Any] | None = None,
    contact_enrichment_stage: dict[str, Any] | None = None,
    department_packages: dict[str, Any] | None = None,
) -> dict[str, Any]:
    primary_stage = primary_source_stage or build_primary_source_stage(
        company_profile=company_profile,
        industry_analysis=industry_analysis,
        market_network=market_network,
    )
    contact_stage = contact_enrichment_stage or build_contact_enrichment_stage(
        company_profile=company_profile,
        contact_intelligence=contact_intelligence,
    )
    score = 0
    reasons: list[str] = []
    financial_substance = _has_financial_substance(company_profile)
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
        or contact_intelligence.get("target_company_contacts")
        or contact_intelligence.get("target_company_prioritized_contacts")
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
    curated_open_questions = []
    if isinstance(synthesis, dict):
        curated_open_questions = synthesis.get("critical_open_questions", []) or []
    open_gap_count = len(curated_open_questions) or len(quality_review.get("open_gaps", []) or [])
    if open_gap_count > 12:
        score = max(0, score - 8)
        reasons.append("Open critic gaps remain too numerous for a concise executive brief.")
    elif open_gap_count:
        reasons.append("Some critic gaps remain unresolved.")
    synthesis_ready = True
    top_path = ""
    if isinstance(synthesis, dict):
        top_path = str(((synthesis.get("recommended_engagement_paths") or [])[:1] or [""])[0]).strip().lower()
    if synthesis is not None and not _synthesis_is_actionable(synthesis):
        synthesis_ready = False
        score = max(0, score - 20)
        reasons.append("Synthesis is incomplete and cannot support a meeting-ready brief.")
    financially_grounded_paths = {"excess_inventory"}
    if top_path in financially_grounded_paths and not financial_substance:
        score = max(0, score - 15)
        reasons.append(
            "Financial deep dive is too thin for a financially grounded primary path."
        )
    # Core sections (company + market) determine usability; contact is optional
    core_score = (30 if company_profile.get("company_name") != "n/v" else 0) + (15 if market_network.get("target_company") != "n/v" else 0)
    min_target_contacts = len(contact_intelligence.get("target_company_prioritized_contacts", []) or []) or len(
        contact_intelligence.get("target_company_contacts", []) or []
    )
    has_min_target_coverage = min_target_contacts >= 2 or (
        min_target_contacts >= 1 and contact_coverage in {"high", "medium"}
    )
    if not has_min_target_coverage:
        score = max(0, score - 10)
        reasons.append("Target-company stakeholder coverage is too thin for meeting readiness.")

    hard_signal_count = int(primary_stage.get("hard_financial_inventory_signal_count", 0) or 0)
    verified_decision_makers = int(contact_stage.get("verified_decision_makers_count", 0) or 0)
    minimum_package = {
        "required_verified_decision_makers": 1,
        "verified_decision_makers": verified_decision_makers,
        "required_hard_financial_inventory_signals": 2,
        "hard_financial_inventory_signals": hard_signal_count,
        "met": verified_decision_makers >= 1 and hard_signal_count >= 2,
    }

    readiness_blockers: list[dict[str, Any]] = []
    if verified_decision_makers < 1:
        availability = (
            "internal_customer"
            if contact_stage.get("public_search_exhausted")
            else "public"
        )
        reason = (
            "No publicly verifiable decision-maker was found (keine freien Quellen)."
            if availability == "internal_customer"
            else "No verified decision-maker is currently available from public evidence."
        )
        readiness_blockers.append(
            {
                "blocker_id": "missing_verified_decision_maker",
                "field_key": "minimum_package.verified_decision_makers",
                "availability": availability,
                "severity": "hard",
                "reason": reason,
                "owner": "Customer Sponsor" if availability == "internal_customer" else "Contact Department",
                "next_step": (
                    "Provide named intro path and role owner from customer-side stakeholder map."
                    if availability == "internal_customer"
                    else "Run additional role-based public contact research."
                ),
            }
        )
    if hard_signal_count < 2:
        availability = (
            "internal_customer"
            if primary_stage.get("public_primary_sources_available")
            else "public"
        )
        reason = (
            "Public primary sources are available but do not contain enough hard financial/inventory signals."
            if availability == "internal_customer"
            else "Primary sources (register/filings/annual docs) are missing from the evidence base."
        )
        readiness_blockers.append(
            {
                "blocker_id": "missing_hard_financial_inventory_signals",
                "field_key": "minimum_package.hard_financial_inventory_signals",
                "availability": availability,
                "severity": "hard",
                "reason": reason,
                "owner": "Customer Finance" if availability == "internal_customer" else "Company Department",
                "next_step": (
                    "Request NDA data package (inventory aging, DIO, write-downs)."
                    if availability == "internal_customer"
                    else "Collect annual docs/filings/registry sources before synthesis finalization."
                ),
            }
        )
    if readiness_blockers and not minimum_package["met"]:
        reasons.append("Minimum package for execution readiness is not met.")

    department_gate_overview = _department_policy_gate_overview(department_packages)
    department_gate_blockers = _department_policy_gate_blockers(department_packages)
    if department_gate_blockers:
        readiness_blockers.extend(department_gate_blockers)
        reasons.append("At least one department acceptance gate reports unresolved mandatory items.")

    component_scores = {
        "synthesis_completeness": 20 if synthesis_ready else 0,
        "contact_quality": 15 if has_min_target_coverage and contact_coverage in {"high", "medium"} else 5 if has_min_target_coverage else 0,
        "financial_depth": 15 if financial_substance else 0,
        "open_question_discipline": 10 if open_gap_count <= 8 else 4 if open_gap_count <= 12 else 0,
    }
    usable = (
        score >= 60
        and quality_review.get("evidence_health") in {"high", "medium"}
        and synthesis_ready
        and (top_path not in financially_grounded_paths or financial_substance)
        and has_min_target_coverage
        and minimum_package["met"]
        and not any(
            item.get("severity") == "hard" and item.get("availability") == "public"
            for item in readiness_blockers
        )
        and not any(
            item.get("severity") == "hard" and item.get("availability") == "internal_customer"
            for item in readiness_blockers
        )
    )
    partial = not usable and core_score >= 30 and quality_review.get("evidence_health") in {"high", "medium", "low"}
    public_hard_blockers = [
        item for item in readiness_blockers
        if item.get("severity") == "hard" and item.get("availability") == "public"
    ]
    internal_hard_blockers = [
        item for item in readiness_blockers
        if item.get("severity") == "hard" and item.get("availability") == "internal_customer"
    ]
    discovery_ready = (
        not usable
        and bool(internal_hard_blockers)
        and not public_hard_blockers
        and core_score >= 30
        and synthesis_ready
    )

    data_request_sheet = _build_data_request_sheet(
        company_name=_non_placeholder(company_profile.get("company_name")) or "n/v",
        blockers=readiness_blockers,
    )
    outreach_playbook = _build_outreach_playbook(
        company_name=_non_placeholder(company_profile.get("company_name")) or "n/v",
        contact_enrichment_stage=contact_stage,
    )

    result = {
        "usable": usable,
        "discovery_ready": discovery_ready,
        "score": score,
        "reasons": reasons,
        "component_scores": component_scores,
        "minimum_package": minimum_package,
        "readiness_blockers": readiness_blockers,
        "department_gate_overview": department_gate_overview,
        "primary_source_stage": primary_stage,
        "contact_enrichment_stage": contact_stage,
        "data_request_sheet": data_request_sheet,
        "outreach_playbook": outreach_playbook,
    }
    if partial:
        result["partial"] = True
    return result
