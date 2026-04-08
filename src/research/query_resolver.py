"""Central runtime query resolver.

Single authoritative path for query construction at task execution time.
Loads query strategies from ``knowledge/query_strategies/<department>.yaml``,
expands canonical placeholders, and applies task-specific expansion rules.

Error model
-----------
- Missing strategy file  → explicit ``FileNotFoundError``
- Unparsable strategy file → explicit ``ValueError``
- Missing task entry     → explicit ``KeyError``
- Unknown placeholder    → explicit ``ValueError``

Zero silent fallback for this layer.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.config.settings import ROOT
from src.domain.intake import SupervisorBrief

# ---------------------------------------------------------------------------
# Task-to-department mapping
# ---------------------------------------------------------------------------

_TASK_TO_DEPARTMENT: dict[str, str] = {
    "company_fundamentals": "company",
    "economic_commercial_situation": "company",
    "financial_deep_dive": "company",
    "product_asset_scope": "company",
    "transaction_event_intelligence": "company",
    "market_situation": "market",
    "peer_companies": "buyer",
    "monetization_redeployment": "buyer",
    "contact_discovery": "contact",
    "target_company_contacts": "contact",
    "contact_qualification": "contact",
}

# ---------------------------------------------------------------------------
# Canonical placeholder set
# ---------------------------------------------------------------------------

_CANONICAL_PLACEHOLDERS = {"company", "domain", "industry", "keywords", "buyer"}

# Temporary migration alias normalisation — legacy German names from old YAML
# entries that may have been copied accidentally into strategy files.
# This shim is a migration guard only; it must be removed once all strategy
# content is rewritten to canonical form.
_MIGRATION_ALIASES: dict[str, str] = {
    "firma": "company",
    "branche": "industry",
    "produktkategorie": "keywords",
}

# Pattern that detects angle-bracket placeholders (legacy format, forbidden in
# strategy files).
_ANGLE_BRACKET_RE = re.compile(r"<[^>]+>")

# Pattern for curly-brace placeholders
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


# ---------------------------------------------------------------------------
# Strategy file loading
# ---------------------------------------------------------------------------

@lru_cache(maxsize=8)
def _load_strategy(department_slug: str) -> dict[str, Any]:
    """Load and cache a query-strategy file.  Raises on any problem."""
    path = ROOT / "knowledge" / "query_strategies" / f"{department_slug}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"Query strategy file not found: {path}. "
            f"Expected at knowledge/query_strategies/{department_slug}.yaml"
        )
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise FileNotFoundError(f"Cannot read query strategy file {path}: {exc}") from exc
    if not raw:
        raise ValueError(f"Query strategy file is empty: {path}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cannot parse query strategy file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Query strategy file must be a JSON object: {path}")
    tasks = data.get("tasks")
    if not isinstance(tasks, dict):
        raise ValueError(f"Query strategy file missing 'tasks' object: {path}")
    return data


def _get_task_entry(department_slug: str, task_key: str) -> dict[str, Any]:
    """Return the strategy entry for a task.  Raises KeyError if missing."""
    data = _load_strategy(department_slug)
    tasks: dict[str, Any] = data["tasks"]
    if task_key not in tasks:
        raise KeyError(
            f"No query strategy entry for task '{task_key}' in "
            f"knowledge/query_strategies/{department_slug}.yaml. "
            f"Available tasks: {sorted(tasks)}"
        )
    entry = tasks[task_key]
    if not isinstance(entry, dict):
        raise ValueError(
            f"Query strategy entry for task '{task_key}' must be a dict, "
            f"got {type(entry).__name__}"
        )
    return entry


# ---------------------------------------------------------------------------
# Placeholder expansion
# ---------------------------------------------------------------------------

def _normalize_aliases(template: str) -> str:
    """Replace legacy migration aliases with canonical placeholder names."""
    def _replace(m: re.Match) -> str:  # type: ignore[type-arg]
        name = m.group(1).lower()
        canonical = _MIGRATION_ALIASES.get(name)
        return f"{{{canonical}}}" if canonical else m.group(0)
    return _PLACEHOLDER_RE.sub(_replace, template)


def _validate_template(template: str) -> None:
    """Raise ValueError if the template contains forbidden placeholder syntax."""
    if _ANGLE_BRACKET_RE.search(template):
        raise ValueError(
            f"Angle-bracket placeholder found in query template (forbidden): {template!r}. "
            "Rewrite to canonical {{curly_brace}} syntax."
        )
    for name in _PLACEHOLDER_RE.findall(template):
        if name not in _CANONICAL_PLACEHOLDERS:
            raise ValueError(
                f"Unknown placeholder '{{{name}}}' in query template: {template!r}. "
                f"Allowed: {sorted(_CANONICAL_PLACEHOLDERS)}"
            )


def _expand(template: str, *, company: str, domain: str, industry: str, keywords: str, buyer: str = "") -> str:
    """Expand canonical placeholders in a single query template."""
    return (
        template
        .replace("{company}", company)
        .replace("{domain}", domain)
        .replace("{industry}", industry)
        .replace("{keywords}", keywords)
        .replace("{buyer}", buyer)
    )


def _expand_templates(
    templates: list[str],
    *,
    company: str,
    domain: str,
    industry: str,
    keywords: str,
    buyer: str = "",
) -> list[str]:
    result = []
    for t in templates:
        t = _normalize_aliases(t)
        _validate_template(t)
        result.append(_expand(t, company=company, domain=domain, industry=industry, keywords=keywords, buyer=buyer))
    return result


# ---------------------------------------------------------------------------
# Task-specific expansion helpers
# ---------------------------------------------------------------------------

def _resolve_buyer_base_queries(
    buyer_config: dict[str, Any],
    *,
    company: str,
    domain: str,
    industry: str,
    keywords: str,
) -> list[str]:
    """Apply the same conditional logic as build_buyer_queries() but from YAML templates."""
    has_keywords = bool(keywords.strip())
    has_industry = bool(industry.strip()) and industry != "n/v"

    result: list[str] = []

    if has_keywords:
        result.extend(_expand_templates(
            buyer_config.get("queries_if_keywords", []),
            company=company, domain=domain, industry=industry, keywords=keywords,
        ))
    if has_industry:
        result.extend(_expand_templates(
            buyer_config.get("queries_if_industry", []),
            company=company, domain=domain, industry=industry, keywords=keywords,
        ))
        if not has_keywords:
            result.extend(_expand_templates(
                buyer_config.get("queries_if_industry_no_keywords", []),
                company=company, domain=domain, industry=industry, keywords=keywords,
            ))
    result.extend(_expand_templates(
        buyer_config.get("queries_always", []),
        company=company, domain=domain, industry=industry, keywords=keywords,
    ))
    if not has_keywords:
        result.extend(_expand_templates(
            buyer_config.get("queries_if_no_keywords", []),
            company=company, domain=domain, industry=industry, keywords=keywords,
        ))
        if not has_industry:
            result.extend(_expand_templates(
                buyer_config.get("queries_if_no_keywords_no_industry", []),
                company=company, domain=domain, industry=industry, keywords=keywords,
            ))
    return result


def _resolve_contact_queries(
    entry: dict[str, Any],
    *,
    company: str,
    domain: str,
    industry: str,
    keywords: str,
    buyer_candidates: list[str],
) -> list[str]:
    """Expand per-buyer queries; fall back to industry queries when no candidates."""
    per_buyer_templates: list[str] = entry.get("queries_per_buyer", [])
    buyer_limit: int = int(entry.get("buyer_limit", 5))
    fallback_templates: list[str] = entry.get("queries_fallback", [])
    result_limit: int = int(entry.get("result_limit", 10))

    queries: list[str] = []
    for firm in buyer_candidates[:buyer_limit]:
        queries.extend(_expand_templates(
            per_buyer_templates,
            company=company, domain=domain, industry=industry, keywords=keywords, buyer=firm,
        ))

    if not queries:
        queries = _expand_templates(
            fallback_templates,
            company=company, domain=domain, industry=industry, keywords=keywords,
        )

    return queries[:result_limit]


# ---------------------------------------------------------------------------
# Dedup helper (preserves order)
# ---------------------------------------------------------------------------

def _dedup(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            result.append(q)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_queries(
    task_key: str,
    brief: SupervisorBrief,
    *,
    query_overrides: list[str] | None = None,
    current_section: dict[str, Any] | None = None,
) -> list[str]:
    """Resolve the query list for a research task.

    Preserves existing ``query_overrides`` semantics exactly:
    - ``None``           → standard path (resolve from strategy)
    - ``[]``             → standard path (falsy, treated like None)
    - non-empty list     → override path (returned directly)

    Parameters
    ----------
    task_key:
        One of the 11 standard research task keys.
    brief:
        Supervisor brief providing company_name and normalized_domain.
    query_overrides:
        When non-empty, returned as-is without strategy lookup.
    current_section:
        Section payload from current pipeline state; used for contact tasks
        that expand per buyer candidate.

    Returns
    -------
    list[str]
        Resolved query strings ready for search execution.

    Raises
    ------
    KeyError
        When ``task_key`` has no strategy entry.
    FileNotFoundError
        When the strategy file for the owning department is missing.
    ValueError
        When the strategy file is unparsable or contains invalid placeholders.
    """
    # Preserve current query_overrides or-idiom exactly (Option A)
    if query_overrides:
        return list(query_overrides)

    if task_key not in _TASK_TO_DEPARTMENT:
        raise KeyError(
            f"Unknown task key: '{task_key}'. "
            f"Known tasks: {sorted(_TASK_TO_DEPARTMENT)}"
        )

    department_slug = _TASK_TO_DEPARTMENT[task_key]
    entry = _get_task_entry(department_slug, task_key)

    # Derive expansion values from brief + research helpers
    from src.research.extract import extract_product_keywords, infer_industry  # local import avoids circular

    company = brief.company_name
    domain = brief.normalized_domain
    industry = infer_industry(
        brief.page_title, brief.meta_description, brief.raw_homepage_excerpt
    ) or "n/v"
    product_keywords = extract_product_keywords(brief.raw_homepage_excerpt, company_name=company)
    keywords = " ".join(product_keywords[:3]).strip()

    # --- company tasks ---------------------------------------------------------
    if task_key in {"economic_commercial_situation", "financial_deep_dive",
                     "company_fundamentals", "transaction_event_intelligence"}:
        return _expand_templates(entry["queries"], company=company, domain=domain, industry=industry, keywords=keywords)

    if task_key == "product_asset_scope":
        queries = _expand_templates(entry["queries"], company=company, domain=domain, industry=industry, keywords=keywords)
        queries.extend(_expand_templates(entry.get("queries_extra", []), company=company, domain=domain, industry=industry, keywords=keywords))
        return queries

    # --- market tasks ----------------------------------------------------------
    if task_key == "market_situation":
        return _expand_templates(entry["queries"], company=company, domain=domain, industry=industry, keywords=keywords)

    # --- buyer tasks -----------------------------------------------------------
    if task_key == "peer_companies":
        peer_queries = _expand_templates(
            entry.get("queries_peer_prefix", []),
            company=company, domain=domain, industry=industry, keywords=keywords,
        )
        buyer_base = _resolve_buyer_base_queries(
            entry.get("queries_buyer_base", {}),
            company=company, domain=domain, industry=industry, keywords=keywords,
        )
        if entry.get("dedup", False):
            return _dedup([*peer_queries, *buyer_base])
        return [*peer_queries, *buyer_base]

    if task_key == "monetization_redeployment":
        return _expand_templates(entry["queries"], company=company, domain=domain, industry=industry, keywords=keywords)

    # --- contact tasks ---------------------------------------------------------
    if task_key in {"contact_discovery", "contact_qualification"}:
        raw_candidates = (current_section or {}).get("buyer_candidates") or []
        buyer_candidates: list[str] = []
        for candidate in raw_candidates:
            firm = ""
            if isinstance(candidate, str):
                firm = candidate.strip()
            elif isinstance(candidate, dict):
                firm = (candidate.get("company_name") or candidate.get("name") or "").strip()
            if firm and firm not in {"n/v", "n/a", "target_company"} and "." not in firm:
                buyer_candidates.append(firm)
        return _resolve_contact_queries(
            entry,
            company=company, domain=domain, industry=industry, keywords=keywords,
            buyer_candidates=buyer_candidates,
        )

    if task_key == "target_company_contacts":
        return _expand_templates(entry["queries"], company=company, domain=domain, industry=industry, keywords=keywords)

    # Unreachable given the _TASK_TO_DEPARTMENT guard above, but be explicit
    raise KeyError(f"Unhandled task key in resolver: '{task_key}'")


def clear_strategy_cache() -> None:
    """Clear the LRU cache for strategy files (useful in tests)."""
    _load_strategy.cache_clear()


# ---------------------------------------------------------------------------
# Validation helper (used by preflight and consistency tests)
# ---------------------------------------------------------------------------

def validate_strategy_file(department_slug: str) -> list[str]:
    """Validate a strategy file and return a list of error strings (empty = OK)."""
    errors: list[str] = []
    try:
        data = _load_strategy(department_slug)
    except (FileNotFoundError, ValueError) as exc:
        return [str(exc)]

    tasks: dict[str, Any] = data.get("tasks", {})
    expected_tasks = {k for k, v in _TASK_TO_DEPARTMENT.items() if v == department_slug}

    for task_key in expected_tasks:
        if task_key not in tasks:
            errors.append(f"Missing task entry: '{task_key}' in {department_slug}.yaml")
            continue
        entry = tasks[task_key]
        if not isinstance(entry, dict):
            errors.append(f"Task entry '{task_key}' must be a dict in {department_slug}.yaml")
            continue

        # Collect all template strings from this entry
        all_templates = _collect_all_templates(entry)
        if not all_templates:
            errors.append(f"Task entry '{task_key}' has no query templates in {department_slug}.yaml")

        for tmpl in all_templates:
            if _ANGLE_BRACKET_RE.search(tmpl):
                errors.append(
                    f"Angle-bracket placeholder in '{task_key}' template: {tmpl!r}"
                )
            for name in _PLACEHOLDER_RE.findall(tmpl):
                if name not in _CANONICAL_PLACEHOLDERS:
                    errors.append(
                        f"Unknown placeholder '{{{name}}}' in '{task_key}' template: {tmpl!r}"
                    )

    return errors


def _collect_all_templates(obj: Any) -> list[str]:
    """Recursively collect all string values from a nested dict/list."""
    results: list[str] = []
    if isinstance(obj, str):
        results.append(obj)
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_collect_all_templates(item))
    elif isinstance(obj, dict):
        for key, val in obj.items():
            # Skip non-template metadata keys
            if key in {"dedup", "buyer_limit", "result_limit", "department"}:
                continue
            results.extend(_collect_all_templates(val))
    return results


def validate_all_strategies() -> dict[str, list[str]]:
    """Validate all department strategy files. Returns {slug: [errors]}."""
    results: dict[str, list[str]] = {}
    for slug in ("company", "market", "buyer", "contact"):
        errs = validate_strategy_file(slug)
        if errs:
            results[slug] = errs
    return results


# ---------------------------------------------------------------------------
# Verify mode (Phase 4 — parallel run)
# ---------------------------------------------------------------------------

_VERIFY_ENV_VAR = "LIQUISTO_QUERY_RESOLVER_VERIFY"


def is_verify_mode() -> bool:
    return os.getenv(_VERIFY_ENV_VAR, "").strip() == "1"
