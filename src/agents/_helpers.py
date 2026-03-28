"""Pure data-transformation helpers for payload coercion and normalization.

Extracted from ResearchWorker to enable architecture-level testing without
importing openai, AG2, or any runtime-heavy dependency.

All functions are stateless — they operate on plain dicts/lists/strings.
"""
from __future__ import annotations

import json
from typing import Any

from src.models.schemas import (
    CompanyProfile,
    ContactIntelligenceSection,
    IndustryAnalysis,
    MarketNetwork,
)

SECTION_MODELS: dict[str, Any] = {
    "company_profile": CompanyProfile,
    "industry_analysis": IndustryAnalysis,
    "market_network": MarketNetwork,
    "contact_intelligence": ContactIntelligenceSection,
}


# ---------------------------------------------------------------------------
# Scalar coercion
# ---------------------------------------------------------------------------

def coerce_to_string(value: Any) -> str:
    """Coerce any scalar-ish value to a plain string for Pydantic.

    Handles common LLM patterns:
    - dict  → join values  (e.g. {"city": "X", "country": "Y"} → "X, Y")
    - int   → str
    - list  → join elements
    - None  → "n/v"
    """
    if value is None:
        return "n/v"
    if isinstance(value, str):
        return value.strip() or "n/v"
    if isinstance(value, dict):
        parts = [str(v).strip() for v in value.values() if v and str(v).strip()]
        return ", ".join(parts) if parts else "n/v"
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if v and str(v).strip()]
        return ", ".join(parts) if parts else "n/v"
    return str(value).strip() or "n/v"


# ---------------------------------------------------------------------------
# List coercion
# ---------------------------------------------------------------------------

def coerce_string_list(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    values: list[str] = []
    for item in items:
        if isinstance(item, str):
            text = item.strip()
            # Fix Python-dict-repr strings like "{'buyer_type': 'OEM', ...}"
            if text.startswith("{") and "':" in text:
                try:
                    import ast
                    parsed = ast.literal_eval(text)
                    if isinstance(parsed, dict):
                        text = " | ".join(str(v).strip() for v in parsed.values() if str(v).strip())
                except (ValueError, SyntaxError):
                    pass
        elif isinstance(item, dict):
            text = " | ".join(str(v).strip() for v in item.values() if str(v).strip())
        else:
            text = str(item).strip()
        if text:
            values.append(text)
    return values


def coerce_people(items: Any) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    people: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            people.append({
                "name": str(item.get("name", "n/v")).strip() or "n/v",
                "role": str(item.get("role", "n/v")).strip() or "n/v",
            })
        elif isinstance(item, str) and item.strip():
            people.append({"name": item.strip(), "role": "n/v"})
    return people


def coerce_sources(items: Any) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    sources: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            url = str(item.get("url", "")).strip()
            title = str(item.get("title", "")).strip() or url or "n/v"
            if not url:
                continue
            sources.append({
                "title": title,
                "url": url,
                "source_type": str(item.get("source_type", "secondary")).strip() or "secondary",
                "summary": str(item.get("summary", "")).strip(),
            })
        elif isinstance(item, str) and item.strip():
            sources.append({
                "title": item.strip(), "url": item.strip(),
                "source_type": "secondary", "summary": "",
            })
    return sources


# ---------------------------------------------------------------------------
# Record normalization
# ---------------------------------------------------------------------------

def pick_field(item: dict[str, Any], keys: tuple[str, ...], default: str = "n/v") -> str:
    """Return the first non-empty, non-placeholder value from candidate keys."""
    for k in keys:
        v = item.get(k)
        if v and str(v).strip() and str(v).strip() != "n/v":
            return str(v).strip()
    return default


def coerce_company_records(items: Any) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    companies: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            companies.append({
                "name": pick_field(item, ("name", "company_name", "company", "firm", "organisation", "organization")),
                "city": pick_field(item, ("city", "location", "headquarters")),
                "country": pick_field(item, ("country",)),
                "relevance": pick_field(item, ("relevance", "relevance_reason", "reason")),
            })
        elif isinstance(item, str) and item.strip():
            companies.append({"name": item.strip(), "city": "n/v", "country": "n/v", "relevance": "n/v"})
    return companies


def normalize_contact_fields(item: dict[str, Any]) -> dict[str, str]:
    """Map common LLM field-name variants to the ContactPerson schema."""
    def _pick(keys: tuple[str, ...], default: str = "n/v") -> str:
        for k in keys:
            v = item.get(k)
            if v and str(v).strip() and str(v).strip() != "n/v":
                return str(v).strip()
        return default

    return {
        "name": _pick(("name", "full_name", "person_name", "contact_name")),
        "firma": _pick(("firma", "company", "company_name", "organization", "firm")),
        "rolle_titel": _pick(("rolle_titel", "title", "job_title", "role", "position")),
        "funktion": _pick(("funktion", "function", "department", "area")),
        "senioritaet": _pick(("senioritaet", "seniority", "level", "seniority_level")),
        "standort": _pick(("standort", "location", "city", "office")),
        "quelle": _pick(("quelle", "source_url", "source", "url", "link")),
        "confidence": _pick(("confidence",), "inferred"),
        "relevance_reason": _pick(("relevance_reason", "relevance", "reason")),
        "suggested_outreach_angle": _pick(("suggested_outreach_angle", "outreach_angle", "outreach")),
    }


def coerce_contact_records(items: Any) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    contacts: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            contacts.append(normalize_contact_fields(item))
        elif isinstance(item, str) and item.strip():
            contacts.append({
                "name": item.strip(), "firma": "n/v", "rolle_titel": "n/v",
                "funktion": "n/v", "senioritaet": "n/v", "standort": "n/v",
                "quelle": "n/v", "confidence": "inferred",
                "relevance_reason": "n/v", "suggested_outreach_angle": "n/v",
            })
    return contacts


# ---------------------------------------------------------------------------
# Section-level sanitization
# ---------------------------------------------------------------------------

def sanitize_for_section(section: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Coerce payload fields to match the Pydantic schema for a section."""
    cleaned = deep_merge({}, payload)
    if section == "company_profile":
        for str_field in ("headquarters", "founded", "employees", "revenue",
                          "legal_form", "goods_classification", "company_name",
                          "website", "industry", "description"):
            if str_field in cleaned:
                cleaned[str_field] = coerce_to_string(cleaned[str_field])
        for key in ("products_and_services", "product_asset_scope"):
            cleaned[key] = coerce_string_list(cleaned.get(key, []))
        cleaned["key_people"] = coerce_people(cleaned.get("key_people", []))
        cleaned["sources"] = coerce_sources(cleaned.get("sources", []))
        economic = cleaned.get("economic_situation", {})
        if isinstance(economic, dict):
            for econ_str in ("revenue_trend", "profitability", "financial_pressure", "assessment"):
                if econ_str in economic:
                    economic[econ_str] = coerce_to_string(economic[econ_str])
            economic["recent_events"] = coerce_string_list(economic.get("recent_events", []))
            economic["inventory_signals"] = coerce_string_list(economic.get("inventory_signals", []))
            cleaned["economic_situation"] = economic
    elif section == "industry_analysis":
        for key in ("key_trends", "overcapacity_signals", "repurposing_signals", "analytics_signals"):
            cleaned[key] = coerce_string_list(cleaned.get(key, []))
        cleaned["sources"] = coerce_sources(cleaned.get("sources", []))
    elif section == "market_network":
        for tier_key in ("peer_competitors", "downstream_buyers", "service_providers", "cross_industry_buyers"):
            tier = cleaned.get(tier_key, {})
            if isinstance(tier, list):
                tier = {"companies": tier, "assessment": "n/v", "sources": []}
            if isinstance(tier, dict):
                tier["companies"] = coerce_company_records(tier.get("companies", []))
                tier["sources"] = coerce_sources(tier.get("sources", []))
                cleaned[tier_key] = tier
        cleaned["monetization_paths"] = coerce_string_list(cleaned.get("monetization_paths", []))
        cleaned["redeployment_paths"] = coerce_string_list(cleaned.get("redeployment_paths", []))
    elif section == "contact_intelligence":
        cleaned["contacts"] = coerce_contact_records(cleaned.get("contacts", []))
        cleaned["prioritized_contacts"] = coerce_contact_records(cleaned.get("prioritized_contacts", []))
        cleaned["open_questions"] = coerce_string_list(cleaned.get("open_questions", []))
        cleaned["sources"] = coerce_sources(cleaned.get("sources", []))
    return cleaned


# ---------------------------------------------------------------------------
# Salvage valid fields from a failed payload
# ---------------------------------------------------------------------------

def salvage_valid_fields(section: str, payload_updates: dict[str, Any]) -> dict[str, Any]:
    """Extract individually valid fields from a payload that failed bulk validation."""
    model_cls = SECTION_MODELS.get(section)
    if not model_cls or not isinstance(payload_updates, dict):
        return {}
    salvaged: dict[str, Any] = {}
    for key, value in payload_updates.items():
        if value is None or value == "n/v":
            continue
        field_info = model_cls.model_fields.get(key)
        if field_info is not None:
            annotation = field_info.annotation
            if annotation is str:
                value = coerce_to_string(value)
        try:
            model_cls.model_validate({key: value})
            salvaged[key] = value
        except Exception:
            coerced = coerce_to_string(value) if isinstance(value, (dict, list, int, float)) else value
            try:
                model_cls.model_validate({key: coerced})
                salvaged[key] = coerced
            except Exception:
                pass
    return salvaged


# ---------------------------------------------------------------------------
# Memory context builder
# ---------------------------------------------------------------------------

def build_memory_context(
    *,
    task_key: str,
    target_section: str,
    current_sections: dict[str, Any],
    role_memory: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build cross-task memory context for the LLM (pure dict logic)."""
    ctx: dict[str, Any] = {}

    if task_key in {"peer_companies", "monetization_redeployment"}:
        company = current_sections.get("company_profile", {})
        if company:
            ctx["known_products"] = company.get("products_and_services", [])
            ctx["known_industry"] = company.get("industry", "n/v")
            ctx["known_description"] = (company.get("description") or "")[:300]

    if task_key == "contact_qualification":
        contacts_section = current_sections.get("contact_intelligence", {})
        if contacts_section:
            ctx["discovered_contacts"] = [
                {k: v for k, v in c.items() if v != "n/v"}
                for c in contacts_section.get("contacts", [])[:10]
            ]

    if task_key == "market_situation":
        industry = current_sections.get("industry_analysis", {})
        if industry:
            ctx["existing_trends"] = industry.get("key_trends", [])
            ctx["existing_assessment"] = industry.get("assessment", "")
            ctx["existing_growth_rate"] = industry.get("growth_rate", "")
        company = current_sections.get("company_profile", {})
        if company:
            ctx["company_industry"] = company.get("industry", "n/v")
            ctx["company_products"] = company.get("products_and_services", [])[:5]
            ctx["company_description"] = (company.get("description") or "")[:300]

    if role_memory:
        successful_queries = []
        for mem in role_memory[:3]:
            # Prefer structural_queries (scrubbed); fall back to successful_queries
            # only for legacy compat, but skip entries that contain company names
            queries = mem.get("structural_queries") or mem.get("successful_queries", [])
            successful_queries.extend(queries[:5])
        if successful_queries:
            ctx["prior_successful_queries"] = dedup_list(successful_queries)[:10]

    return ctx


# ---------------------------------------------------------------------------
# Generic utilities
# ---------------------------------------------------------------------------

def normalize_payload_updates(section: str, payload_updates: Any) -> dict[str, Any]:
    if not isinstance(payload_updates, dict):
        return {}
    nested = payload_updates.get(section)
    if isinstance(nested, dict):
        return nested
    return payload_updates


def deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def dedup_list(items: list) -> list:
    """Deduplicate a list whose items may be dicts (unhashable)."""
    seen: set[str] = set()
    result = []
    for item in items:
        key = (
            json.dumps(item, sort_keys=True, ensure_ascii=False)
            if isinstance(item, (dict, list))
            else str(item)
        )
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


# RF-2: Blacklist for parse_contact_from_title — generic terms that are not person names
_CONTACT_NAME_BLACKLIST = (
    "update", "outlook", "report", "description", "job",
    "homepage", "press", "news", "credit", "opinion",
    "automotive", "industry", "market", "forecast",
    "supply chain", "annual report", "press release", "product portfolio",
    "global technology", "procurement group", "purchasing group",
    "battery management", "market report", "presse-information",
    "reviced", "revised", "predictions", "insights",
)


def _looks_like_person_name(name: str) -> bool:
    """RF-2: Heuristic check — does this string look like a real person name?"""
    words = name.split()
    if len(words) < 2 or len(name) > 50:
        return False
    # At least 2 words must start with uppercase (Title Case)
    title_case_words = sum(1 for w in words if w[0].isupper())
    if title_case_words < 2:
        return False
    # Must not contain blacklisted terms
    name_lower = name.lower()
    if any(kw in name_lower for kw in _CONTACT_NAME_BLACKLIST):
        return False
    # Must not be all-caps (acronyms like "GF GTC 2020")
    if name == name.upper():
        return False
    # Must not contain digits (years, version numbers)
    if any(c.isdigit() for c in name):
        return False
    return True


def parse_contact_from_title(
    title: str,
    url: str,
    buyer_candidates: list[str] | None = None,
) -> dict[str, str] | None:
    """Extract a contact from a search result title.

    RF-2: Strengthened validation — rejects page titles, conference names,
    and generic terms that are not real person names.
    Returns None if no real person name is detected.
    """
    for sep in (" \u2013 ", " - ", " | "):
        if sep in title:
            parts = title.split(sep, 1)
            candidate_name = parts[0].strip()
            rest = parts[1].strip() if len(parts) > 1 else ""
            if not _looks_like_person_name(candidate_name):
                continue
            rolle = rest
            firma = "n/v"
            for role_sep in (" | ", " at ", ", "):
                if role_sep in rest:
                    role_parts = rest.split(role_sep, 1)
                    rolle = role_parts[0].strip()
                    firma = role_parts[1].strip()
                    break
            if buyer_candidates and firma and firma != "n/v":
                firma_lower = firma.lower()
                if not any(
                    bc.lower() in firma_lower or firma_lower in bc.lower()
                    for bc in buyer_candidates
                ):
                    return None
            return {
                "name": candidate_name,
                "firma": firma if firma else "n/v",
                "rolle_titel": rolle if rolle else "n/v",
                "funktion": "n/v", "senioritaet": "n/v", "standort": "n/v",
                "quelle": url, "confidence": "inferred",
                "relevance_reason": "Extracted from public search result.",
                "suggested_outreach_angle": "n/v",
            }
    return None


def extract_contacts_from_facts(facts: list, buyer_hypotheses: list) -> list[dict[str, str]]:
    """RF-2: Extract structured contacts from LLM facts/buyer_hypotheses.

    Looks for patterns like:
    - "Dr. Arne Flemming serves as SVP Supply Chain at Robert Bosch GmbH"
    - "Jiro Ebihara is Head of the Purchasing Group at Denso Corporation"
    """
    import re
    contacts: list[dict[str, str]] = []
    seen_names: set[str] = set()
    # Patterns: "Name serves as/is/was Role at Company"
    _ROLE_PATTERNS = [
        re.compile(r"([A-Z][\w.]+(?:\s+[A-Z][\w.]+)+)\s+(?:serves? as|is|was)\s+(?:the\s+)?(.+?)\s+at\s+(.+?)(?:\.|,|$)", re.IGNORECASE),
        re.compile(r"([A-Z][\w.]+(?:\s+[A-Z][\w.]+)+),\s+(.+?)\s+at\s+(.+?)(?:\.|,|$)", re.IGNORECASE),
    ]
    all_texts = [str(f) for f in facts] + [str(h) for h in buyer_hypotheses if isinstance(h, str)]
    for text in all_texts:
        for pattern in _ROLE_PATTERNS:
            for match in pattern.finditer(text):
                name = match.group(1).strip()
                role = match.group(2).strip()
                company = match.group(3).strip()
                if name in seen_names or len(name) < 5 or len(name) > 60:
                    continue
                if not _looks_like_person_name(name):
                    continue
                seen_names.add(name)
                contacts.append({
                    "name": name,
                    "firma": company[:80],
                    "rolle_titel": role[:100],
                    "funktion": "n/v", "senioritaet": "n/v", "standort": "n/v",
                    "quelle": "n/v", "confidence": "inferred",
                    "relevance_reason": "Extracted from LLM research facts.",
                    "suggested_outreach_angle": "n/v",
                })
    return contacts
