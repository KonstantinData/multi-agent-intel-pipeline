"""Higher-level research helpers used by workers."""
from __future__ import annotations

from time import perf_counter
from warnings import warn

from src.research.contracts import (
    CompanyResearchResult,
    IndustryInferenceResult,
    ResearchCode,
    ResearchIssue,
    ResearchSeverity,
    WebsiteSnapshot,
)
from src.research.extract import (
    infer_company_identity,
    infer_industry_result,
    summarize_visible_text,
)
from src.research.fetch import fetch_website_snapshot
from src.research.normalize import NormalizedDomainResult, normalize_domain_result
from src.research.search import (
    build_buyer_queries,
    build_company_queries,
    build_market_queries,
    perform_search,
)


def _coerce_domain_contract(domain: NormalizedDomainResult | str) -> NormalizedDomainResult:
    if isinstance(domain, NormalizedDomainResult):
        if not domain.is_valid:
            raise ValueError(f"invalid normalized domain contract: {domain.rejection_code}")
        return domain
    warn(
        "build_company_research(str, ...) is deprecated; pass NormalizedDomainResult.",
        DeprecationWarning,
        stacklevel=2,
    )
    result = normalize_domain_result(domain)
    if not result.is_valid:
        raise ValueError(f"invalid domain: {result.rejection_code}")
    return result


def _research_issues(snapshot: WebsiteSnapshot, industry: IndustryInferenceResult) -> tuple[tuple[ResearchIssue, ...], tuple[ResearchIssue, ...]]:
    warnings: list[ResearchIssue] = []
    errors: list[ResearchIssue] = []
    if snapshot.fetch_error_type:
        severity = ResearchSeverity.BLOCKING if snapshot.blocked_reason else ResearchSeverity.DEGRADED
        target = errors if severity == ResearchSeverity.BLOCKING else warnings
        target.append(ResearchIssue(
            code=snapshot.fetch_error_type,
            severity=severity,
            message=snapshot.fetch_error_message or snapshot.fetch_error_type,
        ))
    if snapshot.extraction_quality == "empty":
        warnings.append(ResearchIssue(
            code=ResearchCode.TEXT_EXTRACTION_EMPTY,
            severity=ResearchSeverity.DEGRADED,
            message="homepage fetch succeeded but visible text extraction returned no useful content",
        ))
    elif snapshot.extraction_quality in {"weak", "js_limited"}:
        warnings.append(ResearchIssue(
            code=ResearchCode.TEXT_EXTRACTION_WEAK,
            severity=ResearchSeverity.WARNING,
            message=f"homepage text extraction quality is {snapshot.extraction_quality}",
        ))
    if snapshot.js_content_detected:
        warnings.append(ResearchIssue(
            code=ResearchCode.JS_CONTENT_DETECTED,
            severity=ResearchSeverity.WARNING,
            message="homepage appears to require JavaScript rendering; browser rendering is backlog, not MVP",
        ))
    if industry.confidence == "unknown":
        warnings.append(ResearchIssue(
            code=ResearchCode.INDUSTRY_UNKNOWN,
            severity=ResearchSeverity.WARNING,
            message="industry hint could not be inferred from homepage snapshot",
        ))
    return tuple(warnings), tuple(errors)


def build_company_research(
    normalized_domain: NormalizedDomainResult | str,
    company_name: str,
    *,
    language: str = "de",
) -> CompanyResearchResult:
    domain = _coerce_domain_contract(normalized_domain)
    url = domain.canonical_url
    t0 = perf_counter()
    snapshot = fetch_website_snapshot(url, accept_language=f"{language},en;q=0.8")
    fetch_ms = int((perf_counter() - t0) * 1000)
    t1 = perf_counter()
    identity = infer_company_identity(
        company_name,
        str(snapshot.get("title", "")),
        str(snapshot.get("meta_description", "")),
        str(snapshot.get("visible_text", "")),
    )
    identity_ms = int((perf_counter() - t1) * 1000)
    t2 = perf_counter()
    summary = summarize_visible_text(str(snapshot.get("visible_text", "")))
    industry = infer_industry_result(
        title=str(snapshot.get("title", "")),
        description=str(snapshot.get("meta_description", "")),
        text=summary,
    )
    warnings, errors = _research_issues(snapshot, industry)
    warnings = (*warnings, *identity.source_gaps)
    return CompanyResearchResult(
        normalized_domain=domain.canonical_domain,
        homepage_url=url,
        snapshot=snapshot,
        identity=identity,
        industry=industry,
        summary=summary,
        evidence=(
            {
                "source_type": "owned_website",
                "url": url,
                "supports": ["verified_company_name", "industry_hint", "website_reachable"],
                "content_hash": snapshot.content_hash,
                "retrieved_at": snapshot.retrieved_at,
            },
        ),
        warnings=warnings,
        errors=errors,
        timings_ms={
            "homepage_fetch": fetch_ms,
            "identity_resolution": identity_ms,
            "industry_and_summary": int((perf_counter() - t2) * 1000),
        },
    )


__all__ = [
    "build_buyer_queries",
    "build_company_queries",
    "build_company_research",
    "build_market_queries",
    "perform_search",
]
