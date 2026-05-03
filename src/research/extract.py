"""Lightweight extraction helpers from website text and search results."""
from __future__ import annotations

import json
import logging
import os
import re

from src.config.settings import (
    get_extraction_model,
    get_openai_api_key,
    get_openai_max_retries,
    get_openai_timeout_seconds,
    temperature_param,
)


# Words that appear in website chrome, not in product descriptions
_STOPWORDS = {
    "home", "homepage", "about", "contact", "career", "careers", "welcome",
    "login", "register", "search", "menu", "navigation", "cookie", "cookies",
    "privacy", "imprint", "impressum", "datenschutz", "startseite",
    "overview", "annual", "report", "online", "news", "press", "media",
    "figures", "facts", "development", "company", "group", "corporate",
    "global", "international", "worldwide", "site", "page", "website",
    "read", "more", "learn", "discover", "explore", "download",
    # Location / legal noise
    "friedrichshafen", "stuttgart", "munich", "berlin", "hamburg",
    "deutschland", "germany", "europe", "business", "services",
    "solutions", "management", "information", "technology",
}

# Technical / product-relevant patterns (multi-word and lowercase)
_PRODUCT_PATTERNS = [
    r"\b(?:electric|e-)\s*(?:drive|motor|powertrain|mobility)s?\b",
    r"\b(?:wind|solar|hydro)\s*(?:power|turbine|energy)s?\b",
    r"\b(?:chassis|transmission|axle|driveline|steering|brake|suspension)s?\b",
    r"\b(?:spare\s+parts?|aftermarket|components?|modules?)\b",
    r"\b(?:sensor|actuator|controller|inverter|converter)s?\b",
    r"\b(?:bearing|gear|clutch|coupling|shaft|seal)s?\b",
    r"\b(?:autonomous\s+driving|adas|lidar|radar)\b",
    r"\b(?:commercial\s+vehicle|truck|bus|off-highway|marine)s?\b",
    r"\b(?:industrial\s+technology|test\s+system|automation)s?\b",
]


def extract_product_keywords(text: str, *, company_name: str = "") -> list[str]:
    """Extract product/service keywords from visible website text.

    Strategy:
    1. Try LLM extraction (fast, cheap call) if API key available and not in test.
    2. Fall back to pattern + regex extraction.
    """
    if not (text or "").strip():
        return []
    # Try LLM-based extraction first
    if not os.getenv("PYTEST_CURRENT_TEST"):
        llm_keywords = _llm_extract_keywords(text, company_name=company_name)
        if llm_keywords:
            return llm_keywords[:8]
    return _regex_extract_keywords(text, company_name=company_name)


def _llm_extract_keywords(text: str, *, company_name: str = "") -> list[str]:
    """Use a cheap LLM call to extract product keywords."""
    try:
        from openai import OpenAI
        api_key = get_openai_api_key()
        if not api_key:
            return []
        client = OpenAI(
            api_key=api_key,
            timeout=get_openai_timeout_seconds(),
            max_retries=get_openai_max_retries(),
        )
        model_name = get_extraction_model()
        request_payload = {
            "model": model_name,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": (
                    "Extract 4-8 product/service keywords from the company website text. "
                    "Return JSON: {\"keywords\": [\"keyword1\", ...]}. "
                    "Focus on: products manufactured, goods traded, services offered, "
                    "technology domains, material categories. "
                    "Exclude: city names, legal suffixes, generic business terms."
                )},
                {"role": "user", "content": f"Company: {company_name}\nText: {text[:800]}"},
            ],
        }
        request_payload.update(temperature_param(model_name, 0.0))
        response = client.chat.completions.create(
            **request_payload,
        )
        raw = json.loads(response.choices[0].message.content or "{}")
        keywords = raw.get("keywords", [])
        return [str(k).strip() for k in keywords if isinstance(k, str) and k.strip()][:8]
    except Exception as exc:
        logging.debug("LLM keyword extraction failed: %s", exc)
        return []


def _regex_extract_keywords(text: str, *, company_name: str = "") -> list[str]:
    """Pattern + regex fallback for keyword extraction."""
    keywords: list[str] = []
    seen_lower: set[str] = set()
    company_tokens = {t.lower() for t in re.findall(r"[A-Za-z0-9]+", company_name)} if company_name else set()

    # Phase 1: domain-specific multi-word patterns
    for pattern in _PRODUCT_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            term = match.group(0).strip()
            if term.lower() not in seen_lower:
                seen_lower.add(term.lower())
                keywords.append(term)

    # Phase 2: capitalized terms (original approach, but with better filtering)
    for match in re.findall(r"\b[A-Z][a-zA-Z0-9-]{2,}(?:\s+[A-Z][a-zA-Z0-9-]{2,}){0,2}\b", text or ""):
        term = match.strip()
        if term.lower() in _STOPWORDS or term.lower() in seen_lower:
            continue
        if term.lower() in company_tokens:
            continue
        seen_lower.add(term.lower())
        keywords.append(term)
        if len(keywords) >= 8:
            break

    return keywords[:8]


def infer_industry(title: str, description: str, text: str) -> str:
    haystack = " ".join([title or "", description or "", text or ""]).lower()
    # Ordered from most specific to most general to avoid false positives
    if any(token in haystack for token in ["aerospace", "aviation", "defense", "rüstung", "luft- und raumfahrt"]):
        return "Aerospace & Defense"
    if any(token in haystack for token in ["pharma", "pharmaceutical", "biotechnology", "biotech", "medizintechnik", "medical device"]):
        return "Life Sciences & Pharma"
    if any(token in haystack for token in ["medical", "health", "hospital", "clinic", "gesundheit", "klinik"]):
        return "Healthcare"
    if any(token in haystack for token in ["semiconductor", "chip", "microelectronics", "pcb", "halbleiter", "elektronik", "electronics"]):
        return "Electronics & Semiconductors"
    if any(token in haystack for token in ["automotive", "vehicle", "car manufacturer", "tier 1", "fahrzeug", "kraftfahrzeug", "automobil"]):
        return "Automotive"
    if any(token in haystack for token in ["machinery", "gear", "transmission", "mechanical engineering", "maschinenbau", "getriebe", "antrieb"]):
        return "Mechanical Engineering"
    if any(token in haystack for token in ["automation", "robotics", "robot", "plc", "scada", "motion control", "automatisierung", "roboter"]):
        return "Industrial Automation"
    if any(token in haystack for token in ["chemical", "coating", "adhesive", "lubricant", "polymer", "chemie", "beschichtung", "klebstoff"]):
        return "Chemicals"
    if any(token in haystack for token in ["metal", "steel", "aluminium", "casting", "forging", "stamping", "stahl", "metall", "guss", "schmiede"]):
        return "Metal Manufacturing"
    if any(token in haystack for token in ["construction", "real estate", "infrastructure", "bau", "immobilien", "hochbau", "tiefbau"]):
        return "Construction & Real Estate"
    if any(token in haystack for token in ["energy", "power", "solar", "wind", "utilities", "grid", "energie", "strom", "photovoltaik"]):
        return "Energy & Utilities"
    if any(token in haystack for token in ["logistics", "transport", "freight", "shipping", "supply chain", "logistik", "spedition", "fracht"]):
        return "Logistics & Transport"
    if any(token in haystack for token in ["food", "beverage", "agriculture", "farming", "lebensmittel", "getränk", "landwirtschaft"]):
        return "Food, Beverage & Agriculture"
    if any(token in haystack for token in ["textile", "apparel", "fashion", "garment", "textil", "bekleidung", "mode"]):
        return "Textile & Apparel"
    if any(token in haystack for token in ["printing", "paper", "packaging", "plastics", "druck", "papier", "verpackung", "kunststoff"]):
        return "Packaging & Materials"
    if any(token in haystack for token in ["retail", "e-commerce", "wholesale", "distribution", "handel", "großhandel", "einzelhandel"]):
        return "Retail & Distribution"
    if any(token in haystack for token in ["software", "cloud", "platform", "saas", "it services", "digital", "app", "entwicklung"]):
        return "Software & IT Services"
    if any(token in haystack for token in ["finance", "bank", "insurance", "fintech", "capital", "finanz", "versicherung", "kapital"]):
        return "Financial Services"
    return "n/v"


def summarize_visible_text(text: str, *, limit: int = 320) -> str:
    compact = " ".join((text or "").split())
    return compact[:limit].strip() or "n/v"


LEGAL_SUFFIX_RE = re.compile(
    r"(?:\b(?:GmbH|AG|SE|Inc\.?|Corp\.?|Corporation|Ltd\.?|LLC|SARL|SpA|BV)\.?)$",
    re.IGNORECASE,
)

_TITLE_NOISE_PREFIX = re.compile(
    r"^(homepage|welcome\s+to|about|official\s+site|home\s+-\s+|startseite)\s*",
    re.IGNORECASE,
)


def _clean_title_chunk(chunk: str) -> str:
    """Strip common navigation prefixes that are not part of a company name."""
    return _TITLE_NOISE_PREFIX.sub("", chunk).strip(" -:,")


def _has_legal_suffix(name: str) -> bool:
    return bool(LEGAL_SUFFIX_RE.search(" ".join((name or "").split())))


def infer_company_identity(submitted_name: str, title: str, description: str, text: str) -> dict[str, str]:
    """Infer canonical and legal company names from homepage signals."""
    submitted = " ".join((submitted_name or "").split()).strip()
    title_text = " ".join((title or "").replace("|", " ").split()).strip()
    description_text = " ".join((description or "").split()).strip()
    visible_text = " ".join((text or "").split()).strip()

    candidates: list[str] = []
    if title_text:
        candidates.extend(
            [
                _clean_title_chunk(chunk)
                for chunk in re.split(r"[|:·-]", title_text)
                if _clean_title_chunk(chunk)
            ]
        )
    if submitted:
        candidates.insert(0, submitted)

    verified_company_name = submitted or "n/v"
    verified_legal_name = "n/v"
    name_confidence = "low"

    submitted_tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9]+", submitted)}
    for candidate in candidates:
        candidate_tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9]+", candidate)}
        if submitted_tokens and candidate_tokens and submitted_tokens.intersection(candidate_tokens):
            verified_company_name = candidate
            name_confidence = "medium"
            break

    # Build a cleaned search text: strip noise prefixes from title before regex matching
    clean_title = _clean_title_chunk(title_text)
    legal_match = re.search(
        r"\b([A-Z][A-Za-z0-9&.,' -]{2,}?\s(?:GmbH|AG|SE|Inc\.?|Corp\.?|Corporation|Ltd\.?|LLC|SARL|SpA|BV))\b",
        " ".join(part for part in [clean_title, description_text, visible_text[:500]] if part),
    )
    if legal_match:
        verified_legal_name = " ".join(legal_match.group(1).split())
        verified_company_name = verified_legal_name
        name_confidence = "high"
    elif _has_legal_suffix(verified_company_name):
        verified_legal_name = verified_company_name
        name_confidence = "high" if verified_company_name.lower() == submitted.lower() else "medium"

    return {
        "verified_company_name": verified_company_name or "n/v",
        "verified_legal_name": verified_legal_name,
        "name_confidence": name_confidence,
    }
