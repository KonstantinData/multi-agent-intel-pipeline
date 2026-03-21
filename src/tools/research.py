"""Lightweight web research tools for AG2 agents."""
from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import os
import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import base64


REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.8,de;q=0.7",
}
REQUEST_TIMEOUT = 10
MAX_HTML_BYTES = 512_000


def _env_int_with_min(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw is not None else int(default)
    except (TypeError, ValueError):
        value = int(default)
    return max(int(minimum), value)


MAX_TOOL_CALLS = _env_int_with_min("PIPELINE_MAX_TOOL_CALLS", 48, 12)
LOW_VALUE_RESULT_HOSTS = {
    "zhihu.com",
    "www.zhihu.com",
    "baidu.com",
    "www.baidu.com",
    "zhidao.baidu.com",
    "convertio.co",
    "www.convertio.co",
    "convertio.com",
    "www.convertio.com",
    "convert.io",
    "www.convert.io",
    "reddit.com",
    "www.reddit.com",
    "github.com",
    "www.github.com",
    "chatgpt.com",
    "www.chatgpt.com",
}
QUERY_STOPWORDS = {
    "site",
    "www",
    "com",
    "company",
    "official",
    "website",
    "report",
    "reports",
    "market",
    "industry",
    "pdf",
    "and",
    "the",
    "for",
    "with",
    "from",
    "und",
    "der",
    "die",
    "das",
    "von",
    "mit",
    "ein",
    "eine",
    "customers",
    "customer",
    "competitors",
    "competitor",
    "applications",
    "application",
    "service",
    "services",
    "aftermarket",
    "oem",
    "demand",
    "outlook",
    "growth",
    "inventory",
    "levels",
    "capacity",
    "overcapacity",
    "excess",
    "founded",
    "headquarters",
    "management",
    "board",
    "legal",
    "form",
    "rechtsform",
    "hauptsitz",
    "gegründet",
    "gegruendet",
}


def register_research_tools(agent: Any, tool_names: list[str] | None = None) -> None:
    """Register shared research tools on an AG2 agent."""
    tool_registry = {
        "check_domain": (
            "Fetch a company domain homepage and return reachability, page title, and a conservative visible-language guess.",
            check_domain,
        ),
        "web_search": (
            "Search the public web for recent sources. Optionally restrict to a site/domain and keep results compact.",
            web_search,
        ),
        "fetch_page": (
            "Fetch a webpage and return normalized title, final URL, excerpt, and language hints for grounding claims.",
            fetch_page,
        ),
        "company_source_pack": (
            "Run a small curated batch of company-profile searches across official and registry-style sources, returning deduplicated candidate links.",
            company_source_pack,
        ),
        "industry_source_pack": (
            "Run a small curated batch of industry searches derived from company name, industry hint, and product keywords.",
            industry_source_pack,
        ),
        "buyer_source_pack": (
            "Run a small curated batch of competitor, customer, service, and aftermarket searches derived from company name and product keywords.",
            buyer_source_pack,
        ),
    }

    selected_names = tool_names or list(tool_registry.keys())

    for name in selected_names:
        description, func = tool_registry[name]
        llm_tool = agent.register_for_llm(name=name, description=description)(func)
        agent.register_for_execution(name=name, description=description)(llm_tool)


def check_domain(domain: str, context_variables: Any = None) -> dict[str, Any]:
    """Check whether a domain is reachable and summarize the homepage conservatively."""
    budget_error = _consume_tool_budget(context_variables, "check_domain")
    if budget_error:
        return budget_error
    normalized = _normalize_domain(domain)
    fetch = _fetch_page_impl(normalized, max_chars=1200)
    return {
        "requested_domain": domain,
        "resolved_url": fetch.get("final_url", normalized),
        "reachable": fetch.get("ok", False),
        "status": fetch.get("status"),
        "title": fetch.get("title", ""),
        "language_guess": fetch.get("language_guess", "unknown"),
        "excerpt": fetch.get("excerpt", ""),
    }


def web_search(query: str, site: str = "", max_results: int = 5, context_variables: Any = None) -> dict[str, Any]:
    """Search the public web via DuckDuckGo's HTML endpoint."""
    budget_error = _consume_tool_budget(context_variables, "web_search")
    if budget_error:
        return budget_error
    return _web_search_impl(query=query, site=site, max_results=max_results)


def _web_search_impl(query: str, site: str = "", max_results: int = 5) -> dict[str, Any]:
    """Search backend implementation without consuming budget a second time."""
    max_results = max(1, min(int(max_results), 8))
    scoped_query = query.strip()
    if site.strip():
        scoped_query = f"site:{site.strip()} {scoped_query}".strip()
    if not scoped_query:
        return {"query": query, "results": [], "error": "empty query"}

    search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(scoped_query)}"
    try:
        html_text, _final_url, _status = _http_get_text(search_url)
    except Exception as exc:
        fallback_results = _filter_search_results(
            scoped_query,
            _bing_html_search(scoped_query, max_results=max_results),
            site=site.strip(),
        )
        backend = "bing_html_fallback"
        if not fallback_results:
            fallback_results = _filter_search_results(
                scoped_query,
                _google_news_rss_search(scoped_query, max_results=max_results),
                site=site.strip(),
            )
            backend = "google_news_rss_fallback"
        return {
            "query": scoped_query,
            "site": site.strip(),
            "results": fallback_results,
            "error": str(exc),
            "search_backend": backend,
        }

    results = _filter_search_results(
        scoped_query,
        _parse_duckduckgo_results(html_text, max_results=max_results),
        site=site.strip(),
    )
    if not results:
        results = _filter_search_results(
            scoped_query,
            _bing_html_search(scoped_query, max_results=max_results),
            site=site.strip(),
        )
        backend = "bing_html_fallback"
        if not results:
            results = _filter_search_results(
                scoped_query,
                _google_news_rss_search(scoped_query, max_results=max_results),
                site=site.strip(),
            )
            backend = "google_news_rss_fallback"
    else:
        backend = "duckduckgo_html"
    return {
        "query": scoped_query,
        "site": site.strip(),
        "results": results,
        "search_backend": backend,
    }


def fetch_page(url: str, max_chars: int = 4000, context_variables: Any = None) -> dict[str, Any]:
    """Fetch a webpage and return compact normalized content."""
    budget_error = _consume_tool_budget(context_variables, "fetch_page")
    if budget_error:
        return budget_error
    return _fetch_page_impl(url=url, max_chars=max_chars)


def _fetch_page_impl(url: str, max_chars: int = 4000) -> dict[str, Any]:
    """Fetch implementation without consuming budget a second time."""
    normalized_url = _normalize_url(url)
    try:
        html_text, final_url, status = _http_get_text(normalized_url)
    except Exception as exc:
        return {
            "ok": False,
            "url": normalized_url,
            "final_url": normalized_url,
            "status": None,
            "title": "",
            "language_guess": "unknown",
            "excerpt": "",
            "error": str(exc),
        }

    if _is_google_news_wrapper_url(final_url) or _looks_like_google_news_shell(html_text):
        return {
            "ok": False,
            "url": normalized_url,
            "final_url": final_url,
            "status": status,
            "title": "",
            "language_guess": "unknown",
            "excerpt": "",
            "error": "google news wrapper page is not a grounded publisher page; fetch the original publisher URL instead",
        }

    title_match = re.search(r"<title[^>]*>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
    title = _normalize_whitespace(unescape(title_match.group(1))) if title_match else ""
    text = _html_to_text(html_text)
    excerpt = text[: max(200, min(int(max_chars), 6000))]
    return {
        "ok": True,
        "url": normalized_url,
        "final_url": final_url,
        "status": status,
        "title": title,
        "language_guess": _detect_language(html_text, text),
        "excerpt": excerpt,
    }


def company_source_pack(
    company_name: str,
    domain: str = "",
    max_results: int = 10,
    context_variables: Any = None,
) -> dict[str, Any]:
    """Search a curated set of company-profile queries in one tool call."""
    budget_error = _consume_tool_budget(context_variables, "company_source_pack")
    if budget_error:
        return budget_error
    queries = _build_company_queries(company_name, domain)
    result = _run_query_pack(queries, max_results=max_results, context_variables=context_variables)
    wikipedia_candidate = _find_wikipedia_candidate(company_name)
    if (
        wikipedia_candidate
        and len(result.get("results", [])) < max_results
        and all(item.get("url") != wikipedia_candidate["url"] for item in result.get("results", []))
    ):
        result.setdefault("results", []).append(wikipedia_candidate)
    bare_domain = _bare_domain(domain)
    if bare_domain:
        existing_urls = {
            _normalize_url(item.get("url", ""))
            for item in result.get("results", [])
            if isinstance(item, dict)
        }
        for seed in _official_company_page_seeds(company_name, domain):
            if len(result.get("results", [])) >= max_results:
                break
            if _normalize_url(seed["url"]) in existing_urls:
                continue
            result.setdefault("results", []).append(seed)
            existing_urls.add(_normalize_url(seed["url"]))
    result["results"] = list(result.get("results", []))[:max_results]
    return result


def industry_source_pack(
    company_name: str,
    industry_hint: str = "",
    product_keywords: str = "",
    max_results: int = 10,
    context_variables: Any = None,
) -> dict[str, Any]:
    """Search a curated set of industry-signal queries in one tool call."""
    budget_error = _consume_tool_budget(context_variables, "industry_source_pack")
    if budget_error:
        return budget_error
    queries = _build_industry_queries(company_name, industry_hint, product_keywords)
    return _run_query_pack(queries, max_results=max_results, context_variables=context_variables)


def buyer_source_pack(
    company_name: str,
    product_keywords: str = "",
    domain: str = "",
    max_results: int = 10,
    context_variables: Any = None,
) -> dict[str, Any]:
    """Search a curated set of buyer-network queries in one tool call."""
    budget_error = _consume_tool_budget(context_variables, "buyer_source_pack")
    if budget_error:
        return budget_error
    queries = _build_buyer_queries(company_name, product_keywords, domain)
    return _run_query_pack(queries, max_results=max_results, context_variables=context_variables)


def _consume_tool_budget(context_variables: Any, tool_name: str) -> dict[str, Any] | None:
    if context_variables is None:
        return None

    used = int(context_variables.get("tool_calls_used", 0) or 0)
    if used >= MAX_TOOL_CALLS:
        return {
            "error": "tool budget exhausted",
            "tool_name": tool_name,
            "tool_calls_used": used,
            "max_tool_calls": MAX_TOOL_CALLS,
        }

    context_variables.set("tool_calls_used", used + 1)
    return None


def _run_query_pack(queries: list[str], max_results: int, context_variables: Any = None) -> dict[str, Any]:
    deduped_results: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for query in queries[:6]:
        result = _web_search_impl(query=query, max_results=3)
        for item in result.get("results", []):
            url = item.get("url", "")
            if (
                not url
                or url in seen_urls
                or _is_unusable_search_result_url(url)
                or _is_low_value_search_result(item)
                or not _result_matches_query_focus(query, item)
            ):
                continue
            seen_urls.add(url)
            deduped_results.append(
                {
                    "query": query,
                    "title": item.get("title", ""),
                    "url": url,
                    "snippet": item.get("snippet", ""),
                }
            )
            if len(deduped_results) >= max_results:
                break
        if len(deduped_results) >= max_results:
            break

    return {
        "queries": queries,
        "results": deduped_results,
    }


def _filter_search_results(query: str, results: list[dict[str, str]], site: str = "") -> list[dict[str, str]]:
    filtered: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        url = item.get("url", "")
        if (
            not url
            or url in seen_urls
            or _is_unusable_search_result_url(url)
            or _is_low_value_search_result(item)
            or not _result_matches_query_focus(query, item)
        ):
            continue
        if site.strip():
            site_domain = _bare_domain(site)
            if site_domain and "site:" in str(query).lower() and not _url_matches_domain(url, site_domain):
                continue
        seen_urls.add(url)
        filtered.append(item)
    return filtered


def _build_company_queries(company_name: str, domain: str) -> list[str]:
    clean_name = _normalize_whitespace(company_name)
    bare_domain = _bare_domain(domain)
    official_scope = f'site:{bare_domain} ' if bare_domain else ""
    queries = [
        f'{official_scope}"{clean_name}"',
        f'{official_scope}"{clean_name}" impressum OR unternehmen',
        f'{official_scope}"{clean_name}" rechtsform hauptsitz',
        f'{official_scope}"{clean_name}" gegründet hauptsitz',
        f'{official_scope}"{clean_name}" vorstand geschäftsführung',
        f'{official_scope}"{clean_name}" geschäftsbericht OR annual report pdf',
        f'{official_scope}"{clean_name}" investor relations OR unternehmensprofil',
        f'{official_scope}"{clean_name}" sustainability report OR nachhaltigkeitsbericht',
        f'"{clean_name}" North Data',
        f'"{clean_name}" Wikipedia',
    ]
    return _dedupe_queries(queries)


def _build_industry_queries(company_name: str, industry_hint: str, product_keywords: str) -> list[str]:
    clean_name = _normalize_whitespace(company_name)
    industry_terms = _industry_focus_terms(industry_hint, product_keywords)
    focus = industry_terms[0] if industry_terms else "gearbox market"
    recent_years = _recent_year_query_clause()
    queries = [
        f'"{clean_name}" "{focus}"',
        f'"{focus}" market size growth CAGR {recent_years}',
        f'"{focus}" demand outlook market report {recent_years}',
        f'"{focus}" overcapacity excess capacity {recent_years}',
        f'"{focus}" excess inventory inventory levels {recent_years}',
        f'"{focus}" marktgröße wachstum nachfrage {recent_years}',
    ]
    for term in industry_terms[1:3]:
        queries.append(f'"{term}" market size growth {recent_years}')
        queries.append(f'"{term}" demand outlook {recent_years}')
        queries.append(f'"{term}" overcapacity inventory {recent_years}')
    return _dedupe_queries(queries)


def _recent_year_query_clause() -> str:
    current_year = datetime.now(timezone.utc).year
    return f"({current_year} OR {current_year - 1})"


def _build_buyer_queries(company_name: str, product_keywords: str, domain: str) -> list[str]:
    clean_name = _normalize_whitespace(company_name)
    bare_domain = _bare_domain(domain)
    keywords = _industry_focus_terms("", product_keywords)[:4]
    anchor_keyword = keywords[0] if keywords else clean_name
    queries = [
        f'"{clean_name}" applications industries served',
        f'"{clean_name}" customer reference case study',
        f'"{clean_name}" aftermarket service spare parts',
        f'"{anchor_keyword}" OEM application',
        f'"{anchor_keyword}" OEM',
        f'"{anchor_keyword}" competitors',
        f'"{anchor_keyword}" aftermarket spare parts',
        f'"{anchor_keyword}" repair service distributor',
        f'"{anchor_keyword}" applications buyers',
    ]
    if bare_domain:
        queries.extend(
            [
                f'site:{bare_domain} application OR branche',
                f'site:{bare_domain} customer OR referenz',
                f'site:{bare_domain} aftermarket OR service',
                f'site:{bare_domain} industries OR solutions',
                f'site:{bare_domain} e-bike OR automotive',
            ]
        )
    for keyword in keywords[1:]:
        queries.append(f'"{keyword}" competitors buyers')
        queries.append(f'"{keyword}" spare parts service')
    return _dedupe_queries(queries)


def _industry_focus_terms(industry_hint: str, product_keywords: str) -> list[str]:
    raw_terms = _keyword_list(product_keywords, limit=6)
    if industry_hint:
        raw_terms.extend(_keyword_list(industry_hint, limit=4))
        raw_terms.append(_normalize_whitespace(industry_hint))

    normalized_terms: list[str] = []
    for term in raw_terms:
        normalized = _normalize_whitespace(term)
        if not normalized:
            continue
        normalized_terms.append(normalized)
        lowered = normalized.lower()
        if "planetary" in lowered and "gear" in lowered:
            normalized_terms.append("planetary gearbox")
        if "transmission" in lowered or "gearbox" in lowered or "getriebe" in lowered:
            normalized_terms.append("gearbox")
            normalized_terms.append("power transmission")
        if "gear" in lowered or "zahnrad" in lowered:
            normalized_terms.append("gear manufacturing")
        if "e-bike" in lowered or "ebike" in lowered:
            normalized_terms.append("e-bike drive system")
    return _dedupe_queries(normalized_terms)


def _google_news_rss_search(query: str, max_results: int) -> list[dict[str, str]]:
    rss_url = (
        "https://news.google.com/rss/search?q="
        f"{quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        xml_text, _final_url, _status = _http_get_text(rss_url)
    except Exception:
        return []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in root.findall("./channel/item"):
        link = str(item.findtext("link", "") or "").strip()
        title = _normalize_whitespace(item.findtext("title", ""))
        description = _html_to_text(item.findtext("description", ""))
        if not link or link in seen_urls:
            continue
        seen_urls.add(link)
        results.append(
            {
                "title": title,
                "url": link,
                "snippet": description[:280],
            }
        )
        if len(results) >= max_results:
            break
    return results


def _bing_html_search(query: str, max_results: int) -> list[dict[str, str]]:
    rss_search_url = f"https://www.bing.com/search?format=rss&q={quote_plus(query)}"
    try:
        rss_text, _final_url, _status = _http_get_text(rss_search_url)
    except Exception:
        rss_text = ""
    else:
        rss_results = _parse_bing_rss_results(rss_text, max_results=max_results)
        if rss_results:
            return rss_results

    search_url = f"https://www.bing.com/search?q={quote_plus(query)}"
    try:
        html_text, _final_url, _status = _http_get_text(search_url)
    except Exception:
        return []
    return _parse_bing_results(html_text, max_results=max_results)


def _parse_bing_results(html_text: str, max_results: int) -> list[dict[str, str]]:
    block_pattern = re.compile(
        r'<li[^>]*class=\"[^\"]*b_algo[^\"]*\"[^>]*>(.*?)</li>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    anchor_pattern = re.compile(
        r'<h2[^>]*>\s*<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<p[^>]*>(.*?)</p>',
        flags=re.IGNORECASE | re.DOTALL,
    )

    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for block in block_pattern.findall(html_text):
        anchor = anchor_pattern.search(block)
        if not anchor:
            continue
        resolved_url = _resolve_bing_url(anchor.group(1))
        if not resolved_url or resolved_url in seen_urls or _is_unusable_search_result_url(resolved_url):
            continue
        seen_urls.add(resolved_url)
        title = _html_to_text(anchor.group(2))
        snippet_match = snippet_pattern.search(block)
        snippet = _html_to_text(snippet_match.group(1)) if snippet_match else ""
        results.append(
            {
                "title": title,
                "url": resolved_url,
                "snippet": snippet,
            }
        )
        if len(results) >= max_results:
            break
    return results


def _parse_bing_rss_results(xml_text: str, max_results: int) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in root.findall("./channel/item"):
        link = _normalize_url(item.findtext("link", ""))
        if not link or link in seen_urls or _is_unusable_search_result_url(link):
            continue
        seen_urls.add(link)
        results.append(
            {
                "title": _normalize_whitespace(item.findtext("title", "")),
                "url": link,
                "snippet": _normalize_whitespace(item.findtext("description", "")),
            }
        )
        if len(results) >= max_results:
            break
    return results


def _resolve_bing_url(url: str) -> str:
    normalized = _normalize_url(url)
    parsed = urlparse(normalized)
    if parsed.netloc.lower() not in {"www.bing.com", "bing.com"}:
        return normalized
    encoded = parse_qs(parsed.query).get("u", [""])[0]
    if not encoded:
        return normalized
    if encoded.startswith("a1"):
        raw = encoded[2:]
        padding = "=" * ((4 - len(raw) % 4) % 4)
        try:
            return base64.urlsafe_b64decode(raw + padding).decode("utf-8", errors="replace")
        except Exception:
            return normalized
    return normalized


def _is_unusable_search_result_url(url: str) -> bool:
    normalized = _normalize_url(url)
    parsed = urlparse(normalized)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if host in {"duckduckgo.com", "www.duckduckgo.com"}:
        return True
    if host in {"www.bing.com", "bing.com"} and path.startswith("/ck/a"):
        return True
    if host in {"www.google.com", "google.com"} and path.startswith("/url"):
        return True
    if _is_google_news_wrapper_url(normalized):
        return True
    return False


def _is_low_value_search_result(item: dict[str, str]) -> bool:
    url = _normalize_url(item.get("url", ""))
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return host in LOW_VALUE_RESULT_HOSTS


def _result_matches_query_focus(query: str, item: dict[str, str]) -> bool:
    text = " ".join(
        [
            _normalize_whitespace(item.get("title", "")).lower(),
            _normalize_whitespace(item.get("snippet", "")).lower(),
            _normalize_whitespace(item.get("url", "")).lower(),
        ]
    )
    if not text:
        return False

    site_domain = _extract_site_domain(query)
    if site_domain and _url_matches_domain(item.get("url", ""), site_domain):
        return True

    phrases = _quoted_query_phrases(query)
    for phrase in phrases:
        tokens = [token for token in _tokenize_text(phrase) if token not in QUERY_STOPWORDS]
        if tokens and all(token in text for token in tokens):
            return True

    terms = [token for token in _tokenize_text(query) if token not in QUERY_STOPWORDS]
    if not terms:
        return True

    matches = sum(1 for token in terms if token in text)
    required_matches = 1 if len(terms) <= 2 else 2
    return matches >= required_matches


def _extract_site_domain(query: str) -> str:
    match = re.search(r"\bsite:([^\s]+)", str(query or ""), flags=re.IGNORECASE)
    return _bare_domain(match.group(1)) if match else ""


def _quoted_query_phrases(query: str) -> list[str]:
    return [phrase.strip() for phrase in re.findall(r'"([^"]+)"', str(query or "")) if phrase.strip()]


def _tokenize_text(value: str) -> list[str]:
    tokens = []
    for token in re.findall(r"[a-zA-Z0-9äöüÄÖÜß-]+", str(value or "").lower()):
        normalized = token.strip("-")
        if len(normalized) < 3:
            continue
        if normalized.isdigit():
            continue
        if normalized.endswith("s") and len(normalized) > 4:
            normalized = normalized[:-1]
        tokens.append(normalized)
    return tokens


def _is_google_news_wrapper_url(url: str) -> bool:
    normalized = _normalize_url(url)
    parsed = urlparse(normalized)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    return host == "news.google.com" and (
        path.startswith("/rss/articles") or path.startswith("/articles") or path.startswith("/read")
    )


def _looks_like_google_news_shell(html_text: str) -> bool:
    lowered = str(html_text or "").lower()
    if "dotssplashui" not in lowered:
        return False
    return "news.google.com" in lowered or "google news" in lowered


def _url_matches_domain(url: str, bare_domain: str) -> bool:
    normalized = _normalize_url(url)
    host = urlparse(normalized).netloc.lower().removeprefix("www.")
    bare = str(bare_domain or "").strip().lower().removeprefix("www.")
    if not host or not bare:
        return False
    return host == bare or host.endswith(f".{bare}")


def _find_wikipedia_candidate(company_name: str) -> dict[str, str] | None:
    query = _normalize_whitespace(company_name)
    if not query:
        return None
    search_url = (
        "https://en.wikipedia.org/w/index.php?search="
        f"{quote_plus(query)}&title=Special:Search&ns0=1"
    )
    try:
        _html_text, final_url, _status = _http_get_text(search_url)
    except Exception:
        return None
    normalized_final = _normalize_url(final_url)
    parsed = urlparse(normalized_final)
    if parsed.netloc != "en.wikipedia.org" or not parsed.path.startswith("/wiki/"):
        return None
    page_title = unescape(parsed.path.split("/wiki/", 1)[1]).replace("_", " ")
    return {
        "query": "wikipedia_search_seed",
        "title": page_title,
        "url": normalized_final,
        "snippet": "Wikipedia page candidate discovered via deterministic title search.",
    }


def _official_company_page_seeds(company_name: str, domain: str) -> list[dict[str, str]]:
    homepage = _normalize_domain(domain)
    if not homepage:
        return []
    seeds = [
        {
            "query": "domain_homepage_seed",
            "title": f"{company_name} official homepage",
            "url": homepage,
            "snippet": "Deterministic official homepage seed.",
        },
        {
            "query": "domain_impressum_seed",
            "title": f"{company_name} impressum",
            "url": f"{homepage.rstrip('/')}/impressum",
            "snippet": "Likely official legal/imprint page seed for company facts such as legal form and headquarters.",
        },
        {
            "query": "domain_company_seed",
            "title": f"{company_name} company page",
            "url": f"{homepage.rstrip('/')}/unternehmen",
            "snippet": "Likely official company/about page seed for foundational company facts.",
        },
        {
            "query": "domain_company_en_seed",
            "title": f"{company_name} company page",
            "url": f"{homepage.rstrip('/')}/company",
            "snippet": "Likely official company/about page seed for foundational company facts.",
        },
    ]
    return seeds


def _http_get_text(url: str) -> tuple[str, str, int | None]:
    request = Request(url, headers=REQUEST_HEADERS)
    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        raw = response.read(MAX_HTML_BYTES)
        charset = response.headers.get_content_charset() or "utf-8"
        text = raw.decode(charset, errors="replace")
        final_url = response.geturl()
        status = getattr(response, "status", None)
        return text, final_url, status


def _parse_duckduckgo_results(html_text: str, max_results: int) -> list[dict[str, str]]:
    anchor_pattern = re.compile(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*>.*?</a>.*?<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|'
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*>.*?</a>.*?<div[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>',
        flags=re.IGNORECASE | re.DOTALL,
    )

    anchors = list(anchor_pattern.finditer(html_text))
    snippets = list(snippet_pattern.finditer(html_text))
    results: list[dict[str, str]] = []
    seen: set[str] = set()

    for index, anchor in enumerate(anchors):
        raw_url, raw_title = anchor.groups()
        resolved_url = _resolve_duckduckgo_url(raw_url)
        if not resolved_url or resolved_url in seen:
            continue
        seen.add(resolved_url)
        title = _html_to_text(raw_title)
        snippet = ""
        if index < len(snippets):
            snippet = _html_to_text(next(group for group in snippets[index].groups() if group))
        results.append(
            {
                "title": title,
                "url": resolved_url,
                "snippet": snippet,
            }
        )
        if len(results) >= max_results:
            break
    return results


def _resolve_duckduckgo_url(url: str) -> str:
    if url.startswith("//"):
        url = f"https:{url}"
    parsed = urlparse(url)
    if "duckduckgo.com" not in parsed.netloc:
        return url
    if parsed.path.startswith("/l/"):
        encoded = parse_qs(parsed.query).get("uddg", [""])[0]
        if encoded:
            return encoded
    return url


def _normalize_domain(domain: str) -> str:
    text = str(domain or "").strip()
    if not text:
        return ""
    if "://" not in text:
        return f"https://{text}"
    return text


def _normalize_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if not parsed.scheme:
        return f"https://{text}"
    return text


def _html_to_text(html_text: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html_text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    return _normalize_whitespace(text)


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _bare_domain(value: str) -> str:
    text = _normalize_whitespace(value)
    if not text:
        return ""
    parsed = urlparse(_normalize_url(text))
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _keyword_list(value: str, limit: int = 4) -> list[str]:
    raw = [part.strip() for part in str(value or "").split(",")]
    return [item for item in raw if item][:limit]


def _dedupe_queries(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for query in queries:
        normalized = _normalize_whitespace(query)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _detect_language(html_text: str, text: str) -> str:
    lang_match = re.search(r'\blang=["\']([a-zA-Z-]+)["\']', html_text, flags=re.IGNORECASE)
    if lang_match:
        lang = lang_match.group(1).lower()
        if lang.startswith("de"):
            return "de"
        if lang.startswith("en"):
            return "en"

    sample = f"{html_text[:1500]} {text[:1500]}".lower()
    german_markers = (" und ", " der ", " die ", " das ", " mit ", " impressum ", " datenschutz ")
    english_markers = (" and ", " the ", " with ", " privacy ", " contact ", " solutions ")
    german_hits = sum(marker in sample for marker in german_markers)
    english_hits = sum(marker in sample for marker in english_markers)
    if german_hits > english_hits:
        return "de"
    if english_hits > german_hits:
        return "en"
    return "unknown"
