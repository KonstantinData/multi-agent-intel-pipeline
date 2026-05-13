"""Typed contracts for the evidence-backed Supervisor Briefing (Step 1, Punkt 5).

`SupervisorBrief` (in `src/domain/intake.py`) keeps its existing field shape for
backward compatibility. The contracts in this module add evidence,
confidence-with-reason, fetch-audit and briefing-readiness semantics that
`SupervisorAgent.build_intake_brief()` populates.

MVP scope (per TODO 5.2):
- Only "owned_website" source type is used in Step 1.
- Register/Wikidata/LinkedIn sources are Phase 2 — the contract is shaped so
  those can be added later without breaking consumers.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

BRIEFING_SCHEMA_VERSION = "2026-05-12.1"


# ── Enums ─────────────────────────────────────────────────────────────────────

class IdentityConfidence(StrEnum):
    """Confidence that the verified company name reflects the real target."""

    HIGH = "high"            # homepage title matches submitted name
    MEDIUM = "medium"        # partial overlap (token-level)
    LOW = "low"              # no overlap, but homepage reachable
    UNVERIFIED = "unverified"  # homepage not reachable / fetch blocked


class IndustryConfidence(StrEnum):
    """Confidence that the inferred industry hint is a real signal."""

    HIGH = "high"      # clear title/meta signal
    LOW = "low"        # heuristic, uncertain
    UNKNOWN = "unknown"  # no useful signal


class BriefingReadiness(StrEnum):
    """Routing-decision class for the supervisor message.

    `ready` → Step 2 may run all departments.
    `ready_with_*_gaps` → Step 2 may run, but the gap should be flagged.
    `blocked_*` → Step 2 must not run blindly; CompanyDepartment clarifies first.
    """

    READY = "ready"
    READY_WITH_IDENTITY_GAPS = "ready_with_identity_gaps"
    READY_WITH_WEBSITE_GAPS = "ready_with_website_gaps"
    BLOCKED_IDENTITY_CONFLICT = "blocked_identity_conflict"
    BLOCKED_WEBSITE_UNREACHABLE = "blocked_website_unreachable"


# Source types the evidence contract may carry.
SOURCE_TYPE_OWNED_WEBSITE = "owned_website"
SOURCE_TYPE_IMPRESSUM = "impressum"  # Phase 2
SOURCE_TYPE_REGISTER = "register"    # Phase 2
SOURCE_TYPE_LINKEDIN = "linkedin"    # Phase 2
SOURCE_TYPE_WIKIDATA = "wikidata"    # Phase 2

ALLOWED_SOURCE_TYPES: frozenset[str] = frozenset({
    SOURCE_TYPE_OWNED_WEBSITE,
    SOURCE_TYPE_IMPRESSUM,
    SOURCE_TYPE_REGISTER,
    SOURCE_TYPE_LINKEDIN,
    SOURCE_TYPE_WIKIDATA,
})


# ── Structured fetch + briefing error codes (TODO 5.9) ────────────────────────

BRIEFING_HOMEPAGE_UNREACHABLE = "homepage_unreachable"
BRIEFING_IDENTITY_UNVERIFIED = "identity_unverified"
BRIEFING_IDENTITY_CONFLICT = "identity_conflict"
BRIEFING_INDUSTRY_UNKNOWN = "industry_unknown"
BRIEFING_SOURCE_TIMEOUT = "briefing_source_timeout"
BRIEFING_BLOCKED_FETCH = "blocked_fetch"
BRIEFING_REDIRECT_DOMAIN_MISMATCH = "redirect_domain_mismatch"


# ── EvidenceItem and supporting types ─────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """One source-of-truth claim that supports a briefing field.

    `retrieved_at` is an ISO-8601 UTC timestamp; the supervisor stamps it at
    fetch time so later consumers can audit recency.
    """

    source_type: str
    url: str
    claim: str
    supports_field: str
    retrieved_at: str = ""

    def __post_init__(self) -> None:  # type: ignore[override]
        if self.source_type not in ALLOWED_SOURCE_TYPES:
            # Frozen dataclass: re-set via object.__setattr__
            object.__setattr__(self, "source_type", SOURCE_TYPE_OWNED_WEBSITE)


@dataclass(frozen=True, slots=True)
class MissingEvidence:
    """Explicit marker that an expected supports_field has no source yet."""

    supports_field: str
    reason: str


@dataclass(frozen=True, slots=True)
class BriefingFetchAudit:
    """Structured fetch result for the homepage (TODO 5.5).

    Replaces the loose `website_reachable: bool` + `fetch_error_type` fields
    with a complete audit. Backward-compatible because the SupervisorBrief
    keeps the old `website_reachable` flag in addition to this audit.
    """

    reachable: bool = False
    final_url: str = ""
    redirect_chain: tuple[str, ...] = ()
    http_status: int = 0
    content_type: str = ""
    content_length: int = 0
    content_language: str = ""
    fetched_at: str = ""
    error_type: str = ""
    error_message: str = ""
    blocked_reason: str = ""


def iso_now() -> str:
    """ISO-8601 UTC timestamp helper used by EvidenceItem + BriefingFetchAudit."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Identity helpers (TODO 5.4) ───────────────────────────────────────────────

def _tokenize_for_match(value: str) -> set[str]:
    """Lower-case alphanumeric token set for fuzzy name overlap detection."""
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in (value or ""))
    return {tok for tok in cleaned.split() if len(tok) >= 2}


def classify_identity_confidence(
    *,
    website_reachable: bool,
    submitted_name: str,
    homepage_title: str,
    verified_legal_name: str,
) -> tuple[IdentityConfidence, str]:
    """Derive (confidence, reason) from homepage signal vs. submitted name.

    MVP scope (TODO 5.4):
    - `unverified` when homepage was not reachable
    - `high` when submitted-name tokens all appear in homepage title
    - `medium` when at least one shared token (partial overlap)
    - `low` when no token overlap, but homepage reachable

    `verified_legal_name` is not used here in MVP — register lookup is Phase 2.
    """
    if not website_reachable:
        return IdentityConfidence.UNVERIFIED, "homepage not reachable"

    submitted_tokens = _tokenize_for_match(submitted_name)
    title_tokens = _tokenize_for_match(homepage_title)
    if not submitted_tokens or not title_tokens:
        return IdentityConfidence.LOW, "submitted name or homepage title token-empty"

    overlap = submitted_tokens & title_tokens
    if submitted_tokens.issubset(title_tokens):
        return (
            IdentityConfidence.HIGH,
            "homepage title contains all submitted-name tokens",
        )
    if overlap:
        return (
            IdentityConfidence.MEDIUM,
            f"partial overlap of {len(overlap)} token(s) between submitted name and homepage title",
        )
    return IdentityConfidence.LOW, "no token overlap between submitted name and homepage title"


def classify_industry_confidence(
    *,
    industry_hint: str,
    has_title_signal: bool,
    has_meta_signal: bool,
) -> tuple[IndustryConfidence, str]:
    """Decide industry confidence based on which signals fed the hint."""
    if not industry_hint or industry_hint == "n/v":
        return IndustryConfidence.UNKNOWN, "no industry signal extracted"
    if has_title_signal and has_meta_signal:
        return IndustryConfidence.HIGH, "industry hint backed by both title and meta description"
    if has_title_signal or has_meta_signal:
        return IndustryConfidence.HIGH, "industry hint backed by title or meta description"
    return IndustryConfidence.LOW, "industry hint based on heuristic text scan only"


def detect_identity_conflict(
    *,
    submitted_name: str,
    homepage_title: str,
    confidence: IdentityConfidence,
) -> bool:
    """True if homepage clearly names a different company than the submitted one.

    Conflict is reserved for the case where the homepage title is non-empty AND
    has zero token overlap with the submitted name (low-confidence case).
    Unverified (no homepage) is *not* a conflict — it's a website gap.
    """
    if confidence in (IdentityConfidence.HIGH, IdentityConfidence.MEDIUM):
        return False
    if confidence == IdentityConfidence.UNVERIFIED:
        return False
    submitted_tokens = _tokenize_for_match(submitted_name)
    title_tokens = _tokenize_for_match(homepage_title)
    if not submitted_tokens or not title_tokens:
        return False
    return not (submitted_tokens & title_tokens)


# ── Briefing readiness classifier (TODO 5.6) ──────────────────────────────────

def classify_briefing_readiness(
    *,
    website_reachable: bool,
    identity_conflict: bool,
    identity_confidence: IdentityConfidence,
    website_domain_mismatch: bool = False,
) -> tuple[BriefingReadiness, tuple[str, ...]]:
    """Map briefing signals to a routing-decision class plus structured gaps."""
    gaps: list[str] = []
    if identity_conflict:
        gaps.append("identity_conflict")
        return BriefingReadiness.BLOCKED_IDENTITY_CONFLICT, tuple(gaps)
    if website_domain_mismatch:
        gaps.append(BRIEFING_REDIRECT_DOMAIN_MISMATCH)
        return BriefingReadiness.READY_WITH_WEBSITE_GAPS, tuple(gaps)
    if not website_reachable:
        gaps.append("homepage_unreachable")
        if identity_confidence == IdentityConfidence.UNVERIFIED:
            gaps.append("identity_unverified")
        return BriefingReadiness.BLOCKED_WEBSITE_UNREACHABLE, tuple(gaps)
    if identity_confidence == IdentityConfidence.UNVERIFIED:
        gaps.append("identity_unverified")
        return BriefingReadiness.READY_WITH_IDENTITY_GAPS, tuple(gaps)
    if identity_confidence == IdentityConfidence.LOW:
        gaps.append("identity_low_confidence")
        return BriefingReadiness.READY_WITH_IDENTITY_GAPS, tuple(gaps)
    return BriefingReadiness.READY, ()


# ── Versioned message contract (TODO 5.7) ─────────────────────────────────────

@dataclass(frozen=True, slots=True)
class EvidenceSummary:
    """Compact, non-sensitive evidence rollup for supervisor_message."""

    item_count: int = 0
    source_types: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SupervisorBriefMessage:
    """Versioned supervisor_message envelope for emit_message().

    Wraps the legacy `{"section", "payload", "status"}` shape with
    `schema_version`, structured readiness, confidence and evidence summary
    so consumers can validate against a stable contract instead of fragile
    dict-key strings.
    """

    schema_version: str
    section: str
    status: str
    briefing_readiness: str
    identity_confidence: str
    industry_confidence: str
    routing_gaps: tuple[str, ...]
    evidence_summary: EvidenceSummary
    payload: dict

    def as_dict(self) -> dict:
        """Legacy-compatible dict shape: `{section, payload, status, ...}`."""
        return {
            "schema_version": self.schema_version,
            "section": self.section,
            "status": self.status,
            "briefing_readiness": self.briefing_readiness,
            "identity_confidence": self.identity_confidence,
            "industry_confidence": self.industry_confidence,
            "routing_gaps": list(self.routing_gaps),
            "evidence_summary": {
                "item_count": self.evidence_summary.item_count,
                "source_types": list(self.evidence_summary.source_types),
                "missing_fields": list(self.evidence_summary.missing_fields),
            },
            "payload": self.payload,
        }


def validate_supervisor_brief_message(payload: dict) -> tuple[bool, tuple[str, ...]]:
    """Validate the versioned supervisor brief message envelope.

    This is intentionally dependency-light for architecture tests. It enforces
    the same stable shape a Pydantic model would enforce without importing
    runtime-heavy validation code into the pure contract layer.
    """
    required = {
        "schema_version",
        "section",
        "status",
        "briefing_readiness",
        "identity_confidence",
        "industry_confidence",
        "evidence_summary",
        "payload",
    }
    errors: list[str] = []
    missing = sorted(required - set(payload))
    errors.extend(f"missing:{key}" for key in missing)
    if payload.get("schema_version") != BRIEFING_SCHEMA_VERSION:
        errors.append("invalid:schema_version")
    if payload.get("section") != "supervisor_brief":
        errors.append("invalid:section")
    if payload.get("status") not in {
        "ready_for_department_routing",
        "blocked_for_department_routing",
    }:
        errors.append("invalid:status")
    if not isinstance(payload.get("payload"), dict):
        errors.append("invalid:payload")
    evidence_summary = payload.get("evidence_summary")
    if not isinstance(evidence_summary, dict):
        errors.append("invalid:evidence_summary")
    else:
        for key in ("item_count", "source_types", "missing_fields"):
            if key not in evidence_summary:
                errors.append(f"missing:evidence_summary.{key}")
    return not errors, tuple(errors)


__all__ = [
    "ALLOWED_SOURCE_TYPES",
    "BRIEFING_BLOCKED_FETCH",
    "BRIEFING_HOMEPAGE_UNREACHABLE",
    "BRIEFING_IDENTITY_CONFLICT",
    "BRIEFING_IDENTITY_UNVERIFIED",
    "BRIEFING_INDUSTRY_UNKNOWN",
    "BRIEFING_REDIRECT_DOMAIN_MISMATCH",
    "BRIEFING_SCHEMA_VERSION",
    "BRIEFING_SOURCE_TIMEOUT",
    "BriefingFetchAudit",
    "BriefingReadiness",
    "EvidenceItem",
    "EvidenceSummary",
    "IdentityConfidence",
    "IndustryConfidence",
    "MissingEvidence",
    "SOURCE_TYPE_IMPRESSUM",
    "SOURCE_TYPE_LINKEDIN",
    "SOURCE_TYPE_OWNED_WEBSITE",
    "SOURCE_TYPE_REGISTER",
    "SOURCE_TYPE_WIKIDATA",
    "SupervisorBriefMessage",
    "classify_briefing_readiness",
    "classify_identity_confidence",
    "classify_industry_confidence",
    "detect_identity_conflict",
    "iso_now",
    "validate_supervisor_brief_message",
]
