"""Lightweight extraction helpers from website text and search results."""
from __future__ import annotations

import re


# Words that appear in website chrome, not in product descriptions
_STOPWORDS = {
    "home", "homepage", "about", "contact", "career", "careers", "welcome",
    "login", "register", "search", "menu", "navigation", "cookie", "cookies",
    "privacy", "imprint", "impressum", "datenschutz", "startseite",
    "overview", "annual", "report", "online", "news", "press", "media",
    "figures", "facts", "development", "company", "group", "corporate",
    "global", "international", "worldwide", "site", "page", "website",
    "read", "more", "learn", "discover", "explore", "download",
}


def extract_product_keywords(text: str) -> list[str]:
    candidates = re.findall(r"\b[A-Z][a-zA-Z0-9-]{3,}\b", text or "")
    keywords: list[str] = []
    for item in candidates:
        if item.lower() in _STOPWORDS:
            continue
        if item not in keywords:
            keywords.append(item)
        if len(keywords) >= 8:
            break
    return keywords


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


LEGAL_SUFFIXES = ("gmbh", "ag", "se", "inc", "corp", "corporation", "ltd", "llc", "sarl", "spa", "bv")

_TITLE_NOISE_PREFIX = re.compile(
    r"^(homepage|welcome\s+to|about|official\s+site|home\s+-\s+|startseite)\s*",
    re.IGNORECASE,
)


def _clean_title_chunk(chunk: str) -> str:
    """Strip common navigation prefixes that are not part of a company name."""
    return _TITLE_NOISE_PREFIX.sub("", chunk).strip(" -:,")


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
    elif any(verified_company_name.lower().endswith(suffix) for suffix in LEGAL_SUFFIXES):
        verified_legal_name = verified_company_name
        name_confidence = "high" if verified_company_name.lower() == submitted.lower() else "medium"

    return {
        "verified_company_name": verified_company_name or "n/v",
        "verified_legal_name": verified_legal_name,
        "name_confidence": name_confidence,
    }
