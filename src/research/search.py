"""Search helpers — powered by OpenAI web_search_preview."""
from __future__ import annotations

from src.config.settings import (
    get_openai_api_key,
    get_openai_max_retries,
    get_openai_timeout_seconds,
    get_search_model,
)


def perform_search(query: str, *, max_results: int = 5, timeout: int = 20) -> list[dict[str, str]]:
    """Run a web search via OpenAI Responses API (web_search_preview tool).

    Returns a list of {title, url, source_type, summary} dicts.
    The first result carries the synthesised answer text as its summary;
    subsequent results carry the individual citation titles and URLs.
    Falls back to [] on any error so callers never see an exception.
    """
    if not query.strip():
        return []
    try:
        from openai import OpenAI

        api_key = get_openai_api_key()
        if not api_key:
            return []

        resolved_timeout = float(timeout) if timeout and timeout > 0 else get_openai_timeout_seconds()
        client = OpenAI(
            api_key=api_key,
            timeout=resolved_timeout,
            max_retries=get_openai_max_retries(),
        )
        response = client.responses.create(
            model=get_search_model(),
            tools=[{"type": "web_search_preview"}],
            input=query,
        )

        results: list[dict[str, str]] = []
        seen_urls: set[str] = set()

        for item in response.output:
            if item.type != "message":
                continue
            for content in item.content:
                if content.type != "output_text":
                    continue
                full_text: str = content.text or ""
                for ann in content.annotations:
                    if ann.type != "url_citation":
                        continue
                    url = (ann.url or "").split("?utm_source=")[0]  # strip tracking param
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    # First result gets the full synthesised answer as summary
                    summary = full_text[:600] if not results else ""
                    results.append({
                        "title": ann.title or url,
                        "url": url,
                        "source_type": "secondary",
                        "summary": summary,
                    })
                    if len(results) >= max_results:
                        return results
        return results
    except Exception:
        return []


def build_company_queries(company_name: str, web_domain: str) -> list[str]:
    """Deprecated: use ``src.research.query_resolver.resolve_queries`` instead.

    Called by ``_build_queries_legacy()`` for ``company_fundamentals`` and
    ``product_asset_scope`` task keys.  Will be removed after parity migration
    is complete (Phase 10).
    """
    return [
        f"\"{company_name}\" revenue",
        f"\"{company_name}\" employees",
        f"\"{company_name}\" umsatz mitarbeiter",
        f"\"{company_name}\" company profile",
        f"site:{web_domain} {company_name} about",
        f"site:{web_domain} {company_name} products",
        f"site:{web_domain} {company_name} pressemitteilung umsatz",
        f"site:{web_domain} {company_name} press release revenue",
        f"site:bundesanzeiger.de \"{company_name}\" Jahresabschluss",
        f"site:unternehmensregister.de \"{company_name}\" Jahresabschluss",
    ]


def build_market_queries(company_name: str, industry_hint: str, product_keywords: list[str]) -> list[str]:
    """Deprecated: imported but not called in the current runtime path.

    Registered in ``tools.py`` but not invoked by ``_build_queries_legacy()``.
    Lowest-risk removal candidate.  Will be removed in Phase 10.
    """
    joined_keywords = " ".join(product_keywords[:3]).strip()
    queries = []
    if industry_hint and industry_hint != "n/v":
        queries.append(f"\"{industry_hint}\" market demand trend")
    if joined_keywords:
        queries.append(f"{joined_keywords} demand trend suppliers buyers")
    queries.append(f"\"{company_name}\" competitors market")
    return queries


def build_buyer_queries(company_name: str, product_keywords: list[str], industry_hint: str) -> list[str]:
    """Deprecated: use ``src.research.query_resolver.resolve_queries`` instead.

    Called by ``_build_queries_legacy()`` for ``peer_companies`` and as fallback
    for ``monetization_redeployment``.  Will be removed in Phase 10.
    """
    joined_keywords = " ".join(product_keywords[:3]).strip()
    queries = []
    if joined_keywords:
        queries.append(f"{joined_keywords} distributors aftermarket buyers")
        queries.append(f"{joined_keywords} spare parts buyers")
    if industry_hint and industry_hint != "n/v":
        queries.append(f"{industry_hint} peer companies buyers")
        if not joined_keywords:
            queries.append(f"{industry_hint} distributors aftermarket buyers")
    queries.append(f"\"{company_name}\" customers")
    if not joined_keywords:
        # No product keywords — add company-name-based peer/buyer queries as fallback
        queries.append(f"\"{company_name}\" competitors peer companies")
        if not industry_hint or industry_hint == "n/v":
            queries.append(f"\"{company_name}\" distributors buyers aftermarket")
    return queries
