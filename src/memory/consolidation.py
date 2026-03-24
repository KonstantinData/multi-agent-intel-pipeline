"""Convert finished runs into reusable role-specific process patterns.

CHG-02 / CHG-09 — Memory policy boundary.

**What may enter long-term memory:**
- Query structural patterns (topic + operator combinations — NOT company names)
- Evidence source type effectiveness (e.g. "company registry good for fundamentals")
- Critique heuristics (defect classes, evidence sufficiency thresholds)
- Delegation and completion patterns for the Lead
- Judge decision principles (rule coverage thresholds)
- Coding specialist method patterns (parsing / scraping tactics)

**What must NEVER enter long-term memory:**
- Company names, legal names, or domain names (case-specific facts)
- Customer-specific evidence or findings
- Run-specific outcomes or conclusions
- Contact names, URLs, or revenue figures

Sanitisation is enforced here before any write to ``FileLongTermMemoryStore``.
"""
from __future__ import annotations

import json
import re
from typing import Any


def _dedup_safe(items: list) -> list:
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

# ---------------------------------------------------------------------------
# Company-name scrubbing helpers
# ---------------------------------------------------------------------------

# Regex that broadly matches what looks like a proper-noun company name or
# domain name embedded in a query string.  We replace these with a placeholder
# so the query becomes a structural pattern rather than a company-specific one.
_DOMAIN_RE = re.compile(r'\b[\w\-]+\.(com|de|io|net|org|co\.uk|eu|at|ch)\b', re.IGNORECASE)
_QUOTED_NAME_RE = re.compile(r'"[A-Z][^"]{2,60}"')   # "ACME GmbH"
_GMBH_RE = re.compile(r'\b\w[\w\s\-]{1,30}(GmbH|AG|SE|Inc|Ltd|BV|SAS|SA|NV|KG)\b', re.IGNORECASE)


def _scrub_company_from_query(query: str) -> str:
    """Remove company-name / domain identifiers from a query string.

    Returns a structural query pattern safe for long-term memory.
    """
    q = _DOMAIN_RE.sub("{domain}", query)
    q = _QUOTED_NAME_RE.sub('"{company}"', q)
    q = _GMBH_RE.sub("{company}", q)
    return q.strip()


def _is_process_safe_query(query: str) -> bool:
    """Heuristic: is this query useful as a structural pattern?

    Rejects single-word strings, strings that are just a placeholder, and
    strings that still look company-specific after scrubbing.
    """
    scrubbed = _scrub_company_from_query(query)
    if len(scrubbed) < 12:
        return False
    # Must have at least one non-placeholder word of substance
    words = re.findall(r'[a-z]{4,}', scrubbed.lower())
    non_placeholder = [w for w in words if w not in {"company", "domain", "gmbh"}]
    return len(non_placeholder) >= 1


def _to_structural_patterns(queries: list[str]) -> list[str]:
    """Convert a list of raw queries into scrubbed structural patterns."""
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        scrubbed = _scrub_company_from_query(str(q))
        if _is_process_safe_query(scrubbed) and scrubbed not in seen:
            seen.add(scrubbed)
            out.append(scrubbed)
    return out


# ---------------------------------------------------------------------------
# Role-level brain categories (CHG-09)
# ---------------------------------------------------------------------------

# Which roles get process memory written (and what scope)
ROLE_MEMORY_CATEGORIES: dict[str, str] = {
    "Supervisor": "orchestration",
    "CompanyLead":    "lead_delegation",
    "MarketLead":     "lead_delegation",
    "BuyerLead":      "lead_delegation",
    "ContactLead":    "lead_delegation",
    "CompanyResearcher":  "researcher_strategy",
    "MarketResearcher":   "researcher_strategy",
    "BuyerResearcher":    "researcher_strategy",
    "ContactResearcher":  "researcher_strategy",
    "CompanyCritic":  "critic_heuristics",
    "MarketCritic":   "critic_heuristics",
    "BuyerCritic":    "critic_heuristics",
    "ContactCritic":  "critic_heuristics",
    "CompanyJudge":   "judge_principles",
    "MarketJudge":    "judge_principles",
    "BuyerJudge":     "judge_principles",
    "ContactJudge":   "judge_principles",
    "CompanyCodingSpecialist":  "coding_methods",
    "MarketCodingSpecialist":   "coding_methods",
    "BuyerCodingSpecialist":    "coding_methods",
    "ContactCodingSpecialist":  "coding_methods",
}


# ---------------------------------------------------------------------------
# Main consolidation entry point
# ---------------------------------------------------------------------------

def consolidate_role_patterns(
    *,
    run_context: dict[str, Any],
    pipeline_data: dict[str, Any],
    status: str,
    usable: bool,
) -> list[dict[str, Any]]:
    """Extract reusable process patterns from a completed run.

    Returns a list of pattern dicts suitable for ``FileLongTermMemoryStore.upsert_strategy()``.
    All patterns are scrubbed of company-specific facts before return.

    CHG-09 policy: only process-level guidance is retained. Evidence, findings,
    company profiles, and contact names are explicitly excluded.
    """
    if status != "completed" or not usable:
        return []

    short_term_memory = run_context.get("short_term_memory", {})
    industry_hint = pipeline_data.get("company_profile", {}).get("industry", "n/v")

    # Sanitise industry_hint: keep only generic industry label, strip company refs
    safe_industry = _scrub_company_from_query(str(industry_hint))[:60] if industry_hint else "n/v"

    patterns: list[dict[str, Any]] = []
    worker_reports: list[dict[str, Any]] = short_term_memory.get("worker_reports", [])
    useful_source_types = sorted({
        source.get("source_type", "secondary")
        for source in short_term_memory.get("sources", [])
        if isinstance(source, dict)
    })

    # --- Researcher strategies per role ---
    grouped_queries: dict[str, list[str]] = {}
    for report in worker_reports:
        role = str(report.get("worker", "researcher"))
        raw_queries = list(report.get("queries_used", []))
        grouped_queries.setdefault(role, []).extend(raw_queries)

    for role_name, queries in grouped_queries.items():
        structural_queries = _to_structural_patterns(queries)
        if not structural_queries:
            continue
        scope = ROLE_MEMORY_CATEGORIES.get(role_name, "researcher_strategy")
        patterns.append({
            "name": f"{role_name.lower()}-query-patterns",
            "role": role_name,
            "pattern_scope": scope,
            # CHG-09: no domain/company name in long-term pattern name
            "domain": "",
            "industry_hint": safe_industry,
            "structural_queries": structural_queries,
            "useful_source_types": useful_source_types,
            "rationale": (
                f"{role_name} produced accepted work using {len(structural_queries)} "
                "structural query patterns (company identifiers scrubbed)."
            ),
            "score": 1.0,
        })

    # --- Critic heuristics ---
    critic_reviews: dict[str, dict[str, Any]] = short_term_memory.get("critic_reviews", {})
    if critic_reviews:
        for critic_role in ["CompanyCritic", "MarketCritic", "BuyerCritic", "ContactCritic", "SynthesisCritic"]:
            dept_prefix = critic_role.replace("Critic", "").lower()
            dept_reviews = {k: v for k, v in critic_reviews.items() if dept_prefix in k.lower()}
            if not dept_reviews:
                continue
            # Aggregate heuristics: what fraction of core rules typically pass?
            core_pass_rates = [
                v.get("core_passed", 0) / max(v.get("core_total", 1), 1)
                for v in dept_reviews.values()
                if isinstance(v, dict)
            ]
            avg_pass_rate = round(sum(core_pass_rates) / len(core_pass_rates), 2) if core_pass_rates else 0.0
            # Extract defect classes from failed rule messages (no company data)
            defect_classes = []
            for v in dept_reviews.values():
                if isinstance(v, dict):
                    for msg in v.get("failed_rule_messages", []):
                        scrubbed_msg = _scrub_company_from_query(str(msg))
                        if len(scrubbed_msg) > 8:
                            defect_classes.append(scrubbed_msg)
            patterns.append({
                "name": f"{dept_prefix}-critic-heuristics",
                "role": critic_role,
                "pattern_scope": "critic_heuristics",
                "domain": "",
                "industry_hint": safe_industry,
                "avg_core_pass_rate": avg_pass_rate,
                "common_defect_classes": _dedup_safe(defect_classes)[:8],
                "useful_source_types": useful_source_types,
                "rationale": (
                    f"{critic_role} reviewed {len(dept_reviews)} tasks. "
                    f"Average core pass rate: {avg_pass_rate:.0%}."
                ),
                "score": 1.0,
            })

    # --- Department run state patterns (CHG-09: from DepartmentRunState artifacts) ---
    department_run_states: dict[str, dict[str, Any]] = short_term_memory.get("department_run_states", {})
    for dept_name, run_state in department_run_states.items():
        # Judge escalation patterns
        escalations = run_state.get("judge_escalations", [])
        if escalations:
            outcomes = [e.get("outcome", "unknown") for e in escalations]
            patterns.append({
                "name": f"{dept_name.lower()}-judge-patterns",
                "role": f"{dept_name.replace('Department', '')}Judge",
                "pattern_scope": "judge_principles",
                "domain": "",
                "industry_hint": safe_industry,
                "escalation_count": len(escalations),
                "outcome_distribution": {o: outcomes.count(o) for o in set(outcomes)},
                "rationale": (
                    f"Judge escalation patterns from {dept_name}: "
                    f"{len(escalations)} escalations with outcomes: {set(outcomes)}."
                ),
                "score": 0.9,
            })
        # Coding support patterns
        coding_support = run_state.get("coding_support_used", [])
        if coding_support:
            patterns.append({
                "name": f"{dept_name.lower()}-coding-patterns",
                "role": f"{dept_name.replace('Department', '')}CodingSpecialist",
                "pattern_scope": "coding_methods",
                "domain": "",
                "industry_hint": safe_industry,
                "coding_interventions": len(coding_support),
                "rationale": (
                    f"Coding specialist was used {len(coding_support)} time(s) in {dept_name}."
                ),
                "score": 0.9,
            })
        # Strategy change patterns (what triggered retries)
        strategy_changes = run_state.get("strategy_changes", [])
        if strategy_changes:
            retry_reasons = [
                _scrub_company_from_query(str(c.get("reason", "")))
                for c in strategy_changes
                if c.get("reason")
            ]
            retry_reasons = [r for r in retry_reasons if len(r) > 8]
            if retry_reasons:
                patterns.append({
                    "name": f"{dept_name.lower()}-retry-patterns",
                    "role": f"{dept_name.replace('Department', '')}Lead",
                    "pattern_scope": "lead_delegation",
                    "domain": "",
                    "industry_hint": safe_industry,
                    "retry_trigger_patterns": _dedup_safe(retry_reasons)[:6],
                    "rationale": (
                        f"Retry triggers from {dept_name}: {len(strategy_changes)} retries observed."
                    ),
                    "score": 0.85,
                })

    return patterns
