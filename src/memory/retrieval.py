"""Contextual retrieval helpers for long-term process memory."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any

from src.storage.contracts import LongTermMemoryStore

RETRIEVAL_SCHEMA_VERSION = "2026-05-21.1"
SUPPORTED_RETRIEVAL_SCHEMA_VERSIONS = frozenset({"2026-05-12.1", RETRIEVAL_SCHEMA_VERSION})
RETRIEVAL_POLICY_VERSION = "2026-05-21.1"
DEFAULT_GENERAL_RETRIEVAL_LIMIT = 5
DEFAULT_ROLE_RETRIEVAL_LIMIT = 3

ROLE_PATTERN_SCOPES: dict[str, str] = {
    "Supervisor": "orchestration",
    "CompanyLead": "lead_delegation",
    "MarketLead": "lead_delegation",
    "BuyerLead": "lead_delegation",
    "ContactLead": "lead_delegation",
    "CompanyResearcher": "researcher_strategy",
    "MarketResearcher": "researcher_strategy",
    "BuyerResearcher": "researcher_strategy",
    "ContactResearcher": "researcher_strategy",
    "CompanyCritic": "critic_heuristics",
    "MarketCritic": "critic_heuristics",
    "BuyerCritic": "critic_heuristics",
    "ContactCritic": "critic_heuristics",
    "CompanyJudge": "judge_principles",
    "MarketJudge": "judge_principles",
    "BuyerJudge": "judge_principles",
    "ContactJudge": "judge_principles",
    "CompanyCodingSpecialist": "coding_methods",
    "MarketCodingSpecialist": "coding_methods",
    "BuyerCodingSpecialist": "coding_methods",
    "ContactCodingSpecialist": "coding_methods",
}

NON_PERSISTABLE_CONTEXT_FIELDS = ("company_name", "normalized_domain")

_DOMAIN_RE = re.compile(r"\b[\w\-]+\.(com|de|io|net|org|co\.uk|eu|at|ch)\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.\-+]+@[\w.\-]+\.\w+\b", re.IGNORECASE)
_LEGAL_NAME_RE = re.compile(
    r"\b[A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){0,4}\s+"
    r"(GmbH|AG|SE|Inc|Ltd|BV|SAS|SA|NV|KG)\b"
)
_MONEY_RE = re.compile(r"(\$|€|eur|usd|gbp)\s?\d[\d.,]*|\d[\d.,]*\s?(eur|usd|gbp|€|\$)", re.IGNORECASE)
_KNOWN_AUDIT_TARGET_RE = re.compile(r"\b(Tesla|Siemens|ACME)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class RetrievalContext:
    """Non-secret context for process-memory retrieval.

    `company_name` and `normalized_domain` are current-run context only. They
    must never be persisted into long-term memory and must never add ranking
    bonus points.
    """

    run_id: str
    company_name: str = ""
    normalized_domain: str = ""
    language: str = "de"
    industry_hint: str = ""
    phase: str = "memory_retrieval"
    target_scope: str = "run_start"
    role: str = ""
    department: str = ""
    question_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def pattern_scope(self) -> str:
        if self.role:
            return ROLE_PATTERN_SCOPES.get(self.role, self.target_scope)
        if self.target_scope in {"run_start", "brief_context"}:
            return ""
        return self.target_scope

    def role_context(self, role: str, *, department: str = "") -> RetrievalContext:
        return RetrievalContext(
            run_id=self.run_id,
            company_name=self.company_name,
            normalized_domain=self.normalized_domain,
            language=self.language,
            industry_hint=self.industry_hint,
            phase=self.phase,
            target_scope=ROLE_PATTERN_SCOPES.get(role, "role_process"),
            role=role,
            department=department,
            question_ids=self.question_ids,
        )

    def query_summary(self) -> dict[str, Any]:
        """Return a non-sensitive retrieval summary; no company/domain fields."""
        return {
            "language": self.language,
            "industry_hint_present": bool(self.industry_hint),
            "phase": self.phase,
            "target_scope": self.target_scope,
            "role": self.role,
            "department": self.department,
            "question_count": len(self.question_ids),
        }

    def snapshot(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["non_persistable_context_fields"] = list(NON_PERSISTABLE_CONTEXT_FIELDS)
        payload["pattern_scope"] = self.pattern_scope
        return payload


@dataclass(frozen=True, slots=True)
class RetrievalBatch:
    patterns: list[dict[str, Any]]
    snapshot: dict[str, Any]


def _content_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "name",
        "pattern_scope",
        "industry_hint",
        "content_text",
        "pattern_type",
        "best_practice_type",
        "task_key",
        "rationale",
        "structural_queries",
        "source_strategy",
        "evidence_pattern",
        "task_recipe",
        "critic_acceptance_heuristic",
        "common_defect_classes",
        "retry_trigger_patterns",
    ):
        value = item.get(key)
        if isinstance(value, list):
            parts.extend(str(v) for v in value)
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts)


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]{4,}", text.lower()) if token}


def _local_similarity_score(context: RetrievalContext, item: dict[str, Any]) -> float:
    query_text = " ".join(
        str(part)
        for part in (
            context.industry_hint,
            context.phase,
            context.target_scope,
            context.role,
            context.department,
            " ".join(context.question_ids),
        )
        if part
    )
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return 0.0
    item_tokens = _tokens(_content_text(item))
    if not item_tokens:
        return 0.0
    overlap = len(query_tokens & item_tokens) / max(len(query_tokens), 1)
    return round(min(overlap, 1.0), 4)


def _contains_case_specific_data(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {
                "contact",
                "contact_name",
                "person",
                "person_name",
                "url",
                "website",
            } and str(item).strip():
                return True
            if _contains_case_specific_data(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_case_specific_data(item) for item in value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        return bool(
            _URL_RE.search(text)
            or _EMAIL_RE.search(text)
            or _DOMAIN_RE.search(text)
            or _LEGAL_NAME_RE.search(text)
            or _MONEY_RE.search(text)
            or _KNOWN_AUDIT_TARGET_RE.search(text)
        )
    return False


def _stable_pattern_id(item: dict[str, Any]) -> str:
    explicit = str(item.get("id") or item.get("pattern_id") or "").strip()
    if explicit:
        return explicit
    basis = str(item.get("content_hash") or item.get("name") or _content_text(item))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _dedupe_key(item: dict[str, Any]) -> str:
    return str(item.get("content_hash") or item.get("name") or _content_text(item)).strip().lower()


def _policy_rejection(context: RetrievalContext, item: dict[str, Any]) -> str:
    if _contains_case_specific_data(item):
        return "memory_policy_unsafe_pattern"
    item_role = str(item.get("role") or "").strip()
    item_scope = str(item.get("pattern_scope") or "").strip()
    if context.role and item_role and item_role != context.role:
        return "memory_role_mismatch"
    if context.role and item_scope and item_scope != context.pattern_scope:
        return "memory_scope_mismatch"
    schema_version = str(item.get("schema_version") or RETRIEVAL_SCHEMA_VERSION)
    if schema_version not in SUPPORTED_RETRIEVAL_SCHEMA_VERSIONS:
        return "memory_schema_version_mismatch"
    return ""


def _enrich_pattern(
    *,
    context: RetrievalContext,
    item: dict[str, Any],
    rank_score: float,
    rank: int,
    fallback_reason: str,
) -> dict[str, Any]:
    pattern_score = float(item.get("pattern_score", item.get("score", 0.0)) or 0.0)
    similarity_score = _local_similarity_score(context, item)
    enriched = dict(item)
    enriched.update(
        {
            "pattern_id": _stable_pattern_id(item),
            "role": str(item.get("role") or context.role),
            "pattern_scope": str(item.get("pattern_scope") or context.pattern_scope),
            "schema_version": str(item.get("schema_version") or RETRIEVAL_SCHEMA_VERSION),
            "similarity_score": similarity_score,
            "pattern_score": round(pattern_score, 4),
            "combined_score": round(rank_score, 4),
            "rank": rank,
            "retrieval_reason": (
                "matched role/scope/industry filters with local deterministic "
                "score fallback"
            ),
            "retrieval_query_summary": context.query_summary(),
            "retrieval_policy_version": RETRIEVAL_POLICY_VERSION,
            "fallback_reason": fallback_reason,
        }
    )
    return enriched


def _select_diverse_patterns(
    scored: list[tuple[float, str, dict[str, Any]]],
    *,
    limit: int,
) -> list[tuple[float, str, dict[str, Any]]]:
    """Prefer useful type diversity before filling remaining slots by score."""
    selected: list[tuple[float, str, dict[str, Any]]] = []
    selected_ids: set[str] = set()
    seen_types: set[str] = set()

    for row in scored:
        _score, pattern_id, item = row
        pattern_type = str(item.get("pattern_type") or item.get("best_practice_type") or "legacy")
        if pattern_type in seen_types:
            continue
        selected.append(row)
        selected_ids.add(pattern_id)
        seen_types.add(pattern_type)
        if len(selected) >= limit:
            return selected

    for row in scored:
        _score, pattern_id, _item = row
        if pattern_id in selected_ids:
            continue
        selected.append(row)
        if len(selected) >= limit:
            return selected

    return selected


def retrieve_strategy_batch(
    store: LongTermMemoryStore,
    *,
    context: RetrievalContext,
    limit: int,
) -> RetrievalBatch:
    started = perf_counter()
    fallback_reason = "local_score_fallback_no_embedding"
    candidate_limit = max(limit * 10, 25, limit)
    raw_candidates = store.retrieve(
        domain=context.normalized_domain,
        industry_hint=context.industry_hint,
        role=context.role,
        pattern_scope=context.pattern_scope,
        limit=candidate_limit,
    )

    rejected: list[dict[str, str]] = []
    scored: list[tuple[float, str, dict[str, Any]]] = []
    seen: set[str] = set()
    for item in raw_candidates:
        rejection = _policy_rejection(context, item)
        if rejection:
            rejected.append(
                {
                    "pattern_id": _stable_pattern_id(item),
                    "rejection_code": rejection,
                }
            )
            continue
        key = _dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        pattern_score = float(item.get("pattern_score", item.get("score", 0.0)) or 0.0)
        similarity_score = _local_similarity_score(context, item)
        industry_bonus = 0.25 if context.industry_hint and item.get("industry_hint") == context.industry_hint else 0.0
        role_bonus = 0.2 if context.role and item.get("role") == context.role else 0.0
        scope_bonus = 0.2 if item.get("pattern_scope") == context.pattern_scope else 0.0
        language_bonus = 0.05 if str(item.get("language") or context.language) == context.language else 0.0
        combined = pattern_score + similarity_score + industry_bonus + role_bonus + scope_bonus + language_bonus
        scored.append((combined, _stable_pattern_id(item), item))

    scored.sort(key=lambda row: (-row[0], row[1]))
    selected = _select_diverse_patterns(scored, limit=limit)
    patterns = [
        _enrich_pattern(
            context=context,
            item=item,
            rank_score=score,
            rank=index + 1,
            fallback_reason=fallback_reason,
        )
        for index, (score, _pattern_id, item) in enumerate(selected)
    ]
    duration_ms = int((perf_counter() - started) * 1000)
    status = "ok"
    warning_code = ""
    if not raw_candidates:
        status = "empty"
        warning_code = "memory_retrieval_empty"
    elif raw_candidates and not patterns:
        status = "degraded"
        warning_code = "memory_policy_rejected_all"
    snapshot = {
        "schema_version": RETRIEVAL_SCHEMA_VERSION,
        "retrieval_policy_version": RETRIEVAL_POLICY_VERSION,
        "status": status,
        "warning_code": warning_code,
        "context": context.snapshot(),
        "query_summary": context.query_summary(),
        "result_count": len(patterns),
        "candidate_count": len(raw_candidates),
        "candidate_limit": candidate_limit,
        "rejected_count": len(rejected),
        "rejections": rejected[:20],
        "duration_ms": duration_ms,
        "fallback_reason": fallback_reason,
        "selection_strategy": "score_then_pattern_type_diversity",
    }
    return RetrievalBatch(patterns=patterns, snapshot=snapshot)


def retrieve_strategies(
    store: LongTermMemoryStore,
    *,
    domain: str,
    industry_hint: str = "",
    role: str = "",
    limit: int | None = None,
    context: RetrievalContext | None = None,
) -> list[dict[str, Any]]:
    ctx = context or RetrievalContext(
        run_id="",
        normalized_domain=domain,
        industry_hint=industry_hint,
        role=role,
        target_scope=ROLE_PATTERN_SCOPES.get(role, "run_start") if role else "run_start",
    )
    resolved_limit = limit or (DEFAULT_ROLE_RETRIEVAL_LIMIT if role else DEFAULT_GENERAL_RETRIEVAL_LIMIT)
    return retrieve_strategy_batch(store, context=ctx, limit=resolved_limit).patterns
