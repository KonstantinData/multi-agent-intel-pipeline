"""Higher-level research helpers used by workers."""
from __future__ import annotations

from src.research.extract import infer_company_identity, summarize_visible_text
from src.research.fetch import fetch_website_snapshot
from src.research.normalize import homepage_url, normalize_domain
from src.research.search import (
    build_buyer_queries,
    build_company_queries,
    build_market_queries,
    perform_search,
)


def build_company_research(domain: str, company_name: str) -> dict:
    normalized_domain = normalize_domain(domain)
    url = homepage_url(normalized_domain)
    snapshot = fetch_website_snapshot(url)
    identity = infer_company_identity(
        company_name,
        str(snapshot.get("title", "")),
        str(snapshot.get("meta_description", "")),
        str(snapshot.get("visible_text", "")),
    )
    return {
        "normalized_domain": normalized_domain,
        "homepage_url": url,
        "snapshot": snapshot,
        "summary": summarize_visible_text(str(snapshot.get("visible_text", ""))),
        **identity,
    }


__all__ = [
    "build_buyer_queries",
    "build_company_queries",
    "build_company_research",
    "build_market_queries",
    "perform_search",
]
