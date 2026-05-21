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

import re
from collections import Counter
from typing import Any

from src.app.use_cases import BLOCKED_RUN_STATUS, DISCOVERY_READY_RUN_STATUS, SUCCESS_RUN_STATUS
from src.utils import dedup_safe as _dedup_safe

PROCESS_MEMORY_SCHEMA_VERSION = "2026-05-21.1"
FULL_RUN_ADMISSION = "full_run"
TASK_POSITIVE_ADMISSION = "task_positive"

# ---------------------------------------------------------------------------
# Company-name scrubbing helpers
# ---------------------------------------------------------------------------

# Regex that broadly matches what looks like a proper-noun company name or
# domain name embedded in a query string.  We replace these with a placeholder
# so the query becomes a structural pattern rather than a company-specific one.
_DOMAIN_RE = re.compile(r'\b[\w\-]+\.(com|de|io|net|org|co\.uk|eu|at|ch)\b', re.IGNORECASE)
_URL_RE = re.compile(r'https?://\S+|www\.\S+', re.IGNORECASE)
_EMAIL_RE = re.compile(r'\b[\w.\-+]+@[\w.\-]+\.\w+\b', re.IGNORECASE)
_QUOTED_NAME_RE = re.compile(r'"[A-Z][^"]{2,60}"')   # "ACME GmbH"
_GMBH_RE = re.compile(r'\b\w[\w\s\-]{1,30}(GmbH|AG|SE|Inc|Ltd|BV|SAS|SA|NV|KG)\b', re.IGNORECASE)


def _scrub_company_from_query(query: str, extra_terms: set[str] | None = None) -> str:
    """Remove company-name / domain identifiers from a query string.

    Returns a structural query pattern safe for long-term memory.
    """
    q = _URL_RE.sub("{url}", query)
    q = _EMAIL_RE.sub("{contact}", q)
    q = _DOMAIN_RE.sub("{domain}", q)
    q = _QUOTED_NAME_RE.sub('"{company}"', q)
    q = _GMBH_RE.sub("{company}", q)
    for term in sorted(extra_terms or set(), key=len, reverse=True):
        if len(term) >= 3:
            q = re.sub(rf"\b{re.escape(term)}\b", "{company}", q, flags=re.IGNORECASE)
    q = re.sub(
        r"\{company\}\s*(?:&\s*Co\.\s*)?(GmbH|AG|SE|Inc|Ltd|BV|SAS|SA|NV|KG)\b",
        "{company}",
        q,
        flags=re.IGNORECASE,
    )
    return q.strip()


def _scrub_terms_from_context(run_context: dict[str, Any], pipeline_data: dict[str, Any]) -> set[str]:
    terms: set[str] = set()
    intake = run_context.get("intake", {}) if isinstance(run_context, dict) else {}
    profile = pipeline_data.get("company_profile", {}) if isinstance(pipeline_data, dict) else {}
    for value in (
        intake.get("company_name"),
        intake.get("web_domain"),
        profile.get("company_name"),
        profile.get("legal_name"),
        profile.get("website"),
    ):
        text = str(value or "").strip()
        if not text or text == "n/v":
            continue
        terms.add(text)
        normalized = text.lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/", 1)[0]
        if "." in normalized:
            terms.add(normalized)
            terms.update(part for part in re.split(r"[\W_]+", normalized.split(".", 1)[0]) if len(part) >= 3)
        terms.update(part for part in re.split(r"[\W_]+", text) if len(part) >= 3)
    return terms


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


def _to_structural_patterns(queries: list[str], extra_terms: set[str] | None = None) -> list[str]:
    """Convert a list of raw queries into scrubbed structural patterns."""
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        scrubbed = _scrub_company_from_query(str(q), extra_terms)
        if _is_process_safe_query(scrubbed) and scrubbed not in seen:
            seen.add(scrubbed)
            out.append(scrubbed)
    return out


def _safe_text(value: Any, scrub_terms: set[str]) -> str:
    return _scrub_company_from_query(str(value or ""), scrub_terms).strip()


def _lead_role_for_worker(role_name: str) -> str:
    if role_name.endswith("Researcher"):
        return role_name.removesuffix("Researcher") + "Lead"
    if role_name.endswith("Worker"):
        return role_name.removesuffix("Worker") + "Lead"
    return role_name


def _critic_role_for_worker(role_name: str) -> str:
    if role_name.endswith("Researcher"):
        return role_name.removesuffix("Researcher") + "Critic"
    if role_name.endswith("Worker"):
        return role_name.removesuffix("Worker") + "Critic"
    return role_name


def _pattern_base(
    *,
    name: str,
    role: str,
    pattern_scope: str,
    pattern_type: str,
    industry_hint: str,
    admission_level: str,
    score: float,
    source_run_id: str,
    task_key: str = "",
    task_status: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": PROCESS_MEMORY_SCHEMA_VERSION,
        "name": name,
        "role": role,
        "pattern_scope": pattern_scope,
        "pattern_type": pattern_type,
        "best_practice_type": pattern_type,
        "admission_level": admission_level,
        "domain": "",
        "industry_hint": industry_hint,
        "score": score,
    }
    if source_run_id:
        payload["source_run_id"] = source_run_id
    if task_key:
        payload["task_key"] = task_key
    if task_status:
        payload["task_status"] = task_status
    return payload


def _source_type_counts(sources: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(
        str(source.get("source_type") or "secondary")
        for source in sources
        if isinstance(source, dict)
    )
    return dict(sorted(counter.items()))


def _evidence_summary(report: dict[str, Any]) -> dict[str, Any]:
    packages = report.get("evidence_packages", [])
    if not isinstance(packages, list):
        packages = []
    claim_types = Counter()
    confidence = Counter()
    source_quality = Counter()
    for packet in packages:
        if not isinstance(packet, dict):
            continue
        claim_types[str(packet.get("claim_type") or "fact")] += 1
        confidence[str(packet.get("confidence") or "unknown")] += 1
        source_quality[str(packet.get("source_quality") or "unknown")] += 1
    return {
        "evidence_packet_count": len([item for item in packages if isinstance(item, dict)]),
        "claim_type_counts": dict(sorted(claim_types.items())),
        "confidence_counts": dict(sorted(confidence.items())),
        "source_quality_counts": dict(sorted(source_quality.items())),
    }


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
# F6: Canonical role registry for memory retrieval
# ---------------------------------------------------------------------------

# Role memory status: active roles are persisted AND retrieved.
# Pending roles exist in AGENT_SPECS but are not yet in the memory system.
# Excluded roles are deliberately outside the memory system.
MEMORY_ROLE_STATUS: dict[str, str] = {
    # active — persisted and retrieved
    **{role: "active" for role in ROLE_MEMORY_CATEGORIES},
    # pending — exist in AGENT_SPECS, not yet producing/consuming patterns
    "SynthesisLead": "pending",
    "SynthesisCritic": "pending",
    "SynthesisJudge": "pending",
    # excluded — deliberately outside memory system
    "ReportWriter": "excluded",
}

# Retrieval policy: only active roles are loaded at run start.
# This is an explicit policy layer, not just a mirror of ROLE_MEMORY_CATEGORIES.
# A newly persisted role does NOT automatically enter retrieval.
RETRIEVABLE_ROLES: frozenset[str] = frozenset(
    role for role, status in MEMORY_ROLE_STATUS.items() if status == "active"
)

# Deterministic iteration order for reproducible run initialisation.
RETRIEVABLE_ROLE_ORDER: tuple[str, ...] = tuple(sorted(RETRIEVABLE_ROLES))

_MEMORY_SUCCESS_STATUSES = frozenset({"completed", SUCCESS_RUN_STATUS})


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
    short_term_memory = run_context.get("short_term_memory", {})
    industry_hint = pipeline_data.get("company_profile", {}).get("industry", "n/v")
    task_statuses = short_term_memory.get("task_statuses", {})
    scrub_terms = _scrub_terms_from_context(run_context, pipeline_data)
    source_run_id = str(run_context.get("run_id") or pipeline_data.get("run_id") or "")

    # Sanitise industry_hint: keep only generic industry label, strip company refs
    safe_industry = _scrub_company_from_query(str(industry_hint), scrub_terms)[:60] if industry_hint else "n/v"

    patterns: list[dict[str, Any]] = []
    worker_reports: list[dict[str, Any]] = short_term_memory.get("worker_reports", [])
    critic_reviews: dict[str, dict[str, Any]] = short_term_memory.get("critic_reviews", {})
    useful_source_types = sorted({
        source.get("source_type", "secondary")
        for source in short_term_memory.get("sources", [])
        if isinstance(source, dict)
    })

    # Task-level filter: only include patterns from accepted tasks
    accepted_task_keys = {
        k for k, s in task_statuses.items() if s == "accepted"
    }
    full_run_eligible = status in _MEMORY_SUCCESS_STATUSES and usable
    task_positive_eligible = (
        status
        in {
            "completed",
            SUCCESS_RUN_STATUS,
            DISCOVERY_READY_RUN_STATUS,
            BLOCKED_RUN_STATUS,
        }
        and bool(accepted_task_keys)
    )
    if not full_run_eligible and not task_positive_eligible:
        return []

    # --- Full-run Researcher strategies per role ---
    # Only include queries from tasks that were accepted
    grouped_queries: dict[str, list[str]] = {}
    for report in worker_reports:
        task_key = str(report.get("task_key", ""))
        if task_key and task_key not in accepted_task_keys:
            continue
        role = str(report.get("worker", "researcher"))
        raw_queries = list(report.get("queries_used", []))
        grouped_queries.setdefault(role, []).extend(raw_queries)

    for role_name, queries in grouped_queries.items():
        structural_queries = _to_structural_patterns(queries, scrub_terms)
        if not structural_queries:
            continue
        scope = ROLE_MEMORY_CATEGORIES.get(role_name, "researcher_strategy")
        if full_run_eligible:
            pattern = _pattern_base(
                name=f"{role_name.lower()}-query-patterns",
                role=role_name,
                pattern_scope=scope,
                pattern_type="query_strategy",
                industry_hint=safe_industry,
                admission_level=FULL_RUN_ADMISSION,
                score=1.0,
                source_run_id=source_run_id,
            )
            pattern.update(
                {
                    "structural_queries": structural_queries,
                    "useful_source_types": useful_source_types,
                    "rationale": (
                        f"{role_name} produced accepted work using {len(structural_queries)} "
                        "structural query patterns (company identifiers scrubbed)."
                    ),
                }
            )
            patterns.append(pattern)

    # --- Task-level positive best-practice patterns ---
    reports_by_task: dict[str, list[dict[str, Any]]] = {}
    for report in worker_reports:
        task_key = str(report.get("task_key", ""))
        if task_key in accepted_task_keys:
            reports_by_task.setdefault(task_key, []).append(report)

    for task_key, reports in sorted(reports_by_task.items()):
        role_name = str(reports[-1].get("worker") or "researcher")
        researcher_scope = ROLE_MEMORY_CATEGORIES.get(role_name, "researcher_strategy")
        lead_role = _lead_role_for_worker(role_name)
        critic_role = _critic_role_for_worker(role_name)
        all_queries: list[str] = []
        all_sources: list[dict[str, Any]] = []
        all_evidence_packages: list[dict[str, Any]] = []
        objective_pattern = ""
        for report in reports:
            all_queries.extend(str(query) for query in report.get("queries_used", []) if query)
            all_sources.extend(
                source
                for source in report.get("sources", [])
                if isinstance(source, dict)
            )
            all_evidence_packages.extend(
                packet
                for packet in report.get("evidence_packages", [])
                if isinstance(packet, dict)
            )
            if not objective_pattern:
                objective_pattern = _safe_text(report.get("objective"), scrub_terms)

        structural_queries = _to_structural_patterns(all_queries, scrub_terms)
        source_counts = _source_type_counts(all_sources)
        preferred_source_types = list(source_counts.keys())[:6]
        evidence_pattern = _evidence_summary({"evidence_packages": all_evidence_packages})
        review = critic_reviews.get(task_key, {}) if isinstance(critic_reviews, dict) else {}
        accepted_points = [
            _safe_text(point, scrub_terms)
            for point in list(review.get("accepted_points", []))[:12]
            if _safe_text(point, scrub_terms)
        ]
        evidence_strength = str(review.get("evidence_strength") or "unknown")

        if structural_queries:
            pattern = _pattern_base(
                name=f"{role_name.lower()}-{task_key}-query-strategy",
                role=role_name,
                pattern_scope=researcher_scope,
                pattern_type="query_strategy",
                industry_hint=safe_industry,
                admission_level=TASK_POSITIVE_ADMISSION,
                score=0.95,
                source_run_id=source_run_id,
                task_key=task_key,
                task_status="accepted",
            )
            pattern.update(
                {
                    "structural_queries": structural_queries[:12],
                    "rationale": (
                        f"Accepted task '{task_key}' reused as positive query strategy "
                        "with company identifiers scrubbed."
                    ),
                }
            )
            patterns.append(pattern)

        if preferred_source_types:
            pattern = _pattern_base(
                name=f"{role_name.lower()}-{task_key}-source-strategy",
                role=role_name,
                pattern_scope=researcher_scope,
                pattern_type="source_strategy",
                industry_hint=safe_industry,
                admission_level=TASK_POSITIVE_ADMISSION,
                score=0.9,
                source_run_id=source_run_id,
                task_key=task_key,
                task_status="accepted",
            )
            pattern.update(
                {
                    "source_strategy": {
                        "preferred_source_types": preferred_source_types,
                        "source_type_counts": source_counts,
                        "minimum_source_count": min(len(all_sources), 8),
                    },
                    "rationale": (
                        f"Accepted task '{task_key}' used a reusable source-type mix "
                        f"with evidence strength '{evidence_strength}'."
                    ),
                }
            )
            patterns.append(pattern)

        if evidence_pattern["evidence_packet_count"]:
            pattern = _pattern_base(
                name=f"{role_name.lower()}-{task_key}-evidence-pattern",
                role=role_name,
                pattern_scope=researcher_scope,
                pattern_type="evidence_pattern",
                industry_hint=safe_industry,
                admission_level=TASK_POSITIVE_ADMISSION,
                score=0.9,
                source_run_id=source_run_id,
                task_key=task_key,
                task_status="accepted",
            )
            pattern.update(
                {
                    "evidence_pattern": evidence_pattern,
                    "rationale": (
                        f"Accepted task '{task_key}' produced reusable evidence "
                        "coverage metadata without storing claims or URLs."
                    ),
                }
            )
            patterns.append(pattern)

        if objective_pattern or accepted_points or preferred_source_types:
            lead_scope = ROLE_MEMORY_CATEGORIES.get(lead_role, "lead_delegation")
            pattern = _pattern_base(
                name=f"{lead_role.lower()}-{task_key}-task-recipe",
                role=lead_role,
                pattern_scope=lead_scope,
                pattern_type="task_recipe",
                industry_hint=safe_industry,
                admission_level=TASK_POSITIVE_ADMISSION,
                score=0.92,
                source_run_id=source_run_id,
                task_key=task_key,
                task_status="accepted",
            )
            pattern.update(
                {
                    "task_recipe": {
                        "task_key": task_key,
                        "objective_pattern": objective_pattern[:240],
                        "accepted_fields": _dedup_safe(accepted_points)[:10],
                        "preferred_source_types": preferred_source_types,
                        "evidence_expectation": evidence_pattern,
                    },
                    "rationale": f"Accepted task '{task_key}' is reusable as a task recipe.",
                }
            )
            patterns.append(pattern)

        if review and bool(review.get("approved", False)):
            critic_scope = ROLE_MEMORY_CATEGORIES.get(critic_role, "critic_heuristics")
            pattern = _pattern_base(
                name=f"{critic_role.lower()}-{task_key}-acceptance-heuristic",
                role=critic_role,
                pattern_scope=critic_scope,
                pattern_type="critic_acceptance_heuristic",
                industry_hint=safe_industry,
                admission_level=TASK_POSITIVE_ADMISSION,
                score=0.9,
                source_run_id=source_run_id,
                task_key=task_key,
                task_status="accepted",
            )
            pattern.update(
                {
                    "critic_acceptance_heuristic": {
                        "task_key": task_key,
                        "accepted_fields": _dedup_safe(accepted_points)[:12],
                        "core_passed": int(review.get("core_passed", 0) or 0),
                        "core_total": int(review.get("core_total", 0) or 0),
                        "supporting_passed": int(review.get("supporting_passed", 0) or 0),
                        "supporting_total": int(review.get("supporting_total", 0) or 0),
                        "evidence_strength": evidence_strength,
                    },
                    "rationale": (
                        f"Critic approved accepted task '{task_key}' with reusable "
                        "acceptance metadata."
                    ),
                }
            )
            patterns.append(pattern)

    # --- Full-run Critic heuristics (only from accepted tasks) ---
    if full_run_eligible and critic_reviews:
        for critic_role in ["CompanyCritic", "MarketCritic", "BuyerCritic", "ContactCritic", "SynthesisCritic"]:
            dept_prefix = critic_role.replace("Critic", "").lower()
            dept_reviews = {
                k: v for k, v in critic_reviews.items()
                if dept_prefix in k.lower() and k in accepted_task_keys
            }
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
                        scrubbed_msg = _scrub_company_from_query(str(msg), scrub_terms)
                        if len(scrubbed_msg) > 8:
                            defect_classes.append(scrubbed_msg)
            pattern = _pattern_base(
                name=f"{dept_prefix}-critic-heuristics",
                role=critic_role,
                pattern_scope="critic_heuristics",
                pattern_type="critic_acceptance_heuristic",
                industry_hint=safe_industry,
                admission_level=FULL_RUN_ADMISSION,
                score=1.0,
                source_run_id=source_run_id,
            )
            pattern.update(
                {
                    "avg_core_pass_rate": avg_pass_rate,
                    "common_defect_classes": _dedup_safe(defect_classes)[:8],
                    "useful_source_types": useful_source_types,
                    "rationale": (
                        f"{critic_role} reviewed {len(dept_reviews)} tasks. "
                        f"Average core pass rate: {avg_pass_rate:.0%}."
                    ),
                }
            )
            patterns.append(pattern)

    # --- Department run state patterns (CHG-09: from DepartmentRunState artifacts) ---
    department_run_states: dict[str, dict[str, Any]] = short_term_memory.get("department_run_states", {})
    if not full_run_eligible:
        return patterns
    for dept_name, run_state in department_run_states.items():
        # Judge escalation patterns
        escalations = run_state.get("judge_escalations", [])
        if escalations:
            outcomes = [e.get("outcome", "unknown") for e in escalations]
            role_name = f"{dept_name.replace('Department', '')}Judge"
            pattern = _pattern_base(
                name=f"{dept_name.lower()}-judge-patterns",
                role=role_name,
                pattern_scope="judge_principles",
                pattern_type="judge_principle",
                industry_hint=safe_industry,
                admission_level=FULL_RUN_ADMISSION,
                score=0.9,
                source_run_id=source_run_id,
            )
            pattern.update(
                {
                    "escalation_count": len(escalations),
                    "outcome_distribution": {o: outcomes.count(o) for o in set(outcomes)},
                    "rationale": (
                        f"Judge escalation patterns from {dept_name}: "
                        f"{len(escalations)} escalations with outcomes: {set(outcomes)}."
                    ),
                }
            )
            patterns.append(pattern)
        # Coding support patterns
        coding_support = run_state.get("coding_support_used", [])
        if coding_support:
            role_name = f"{dept_name.replace('Department', '')}CodingSpecialist"
            pattern = _pattern_base(
                name=f"{dept_name.lower()}-coding-patterns",
                role=role_name,
                pattern_scope="coding_methods",
                pattern_type="task_recipe",
                industry_hint=safe_industry,
                admission_level=FULL_RUN_ADMISSION,
                score=0.9,
                source_run_id=source_run_id,
            )
            pattern.update(
                {
                    "coding_interventions": len(coding_support),
                    "rationale": (
                        f"Coding specialist was used {len(coding_support)} time(s) in {dept_name}."
                    ),
                }
            )
            patterns.append(pattern)
        # Strategy change patterns (what triggered retries)
        strategy_changes = run_state.get("strategy_changes", [])
        if strategy_changes:
            retry_reasons = [
                _scrub_company_from_query(str(c.get("reason", "")), scrub_terms)
                for c in strategy_changes
                if c.get("reason")
            ]
            retry_reasons = [r for r in retry_reasons if len(r) > 8]
            if retry_reasons:
                role_name = f"{dept_name.replace('Department', '')}Lead"
                pattern = _pattern_base(
                    name=f"{dept_name.lower()}-retry-patterns",
                    role=role_name,
                    pattern_scope="lead_delegation",
                    pattern_type="task_recipe",
                    industry_hint=safe_industry,
                    admission_level=FULL_RUN_ADMISSION,
                    score=0.85,
                    source_run_id=source_run_id,
                )
                pattern.update(
                    {
                        "retry_trigger_patterns": _dedup_safe(retry_reasons)[:6],
                        "rationale": (
                            f"Retry triggers from {dept_name}: {len(strategy_changes)} retries observed."
                        ),
                    }
                )
                patterns.append(pattern)

    return patterns
