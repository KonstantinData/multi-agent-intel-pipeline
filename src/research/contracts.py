"""Typed contracts for Step-1 intake research."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

RESEARCH_SCHEMA_VERSION = "2026-05-12.1"
OWNED_WEBSITE_SOURCE = "owned_website"
REGISTER_SOURCE = "register"
LINKEDIN_SOURCE = "linkedin"
WIKIDATA_SOURCE = "wikidata"

MAX_RAW_RESPONSE_BYTES = 800_000
MAX_VISIBLE_TEXT_CHARS = 4_000
MAX_SUMMARY_CHARS = 320
DEFAULT_HOMEPAGE_FETCH_TIMEOUT_SECONDS = 8


class ResearchSeverity(StrEnum):
    BLOCKING = "blocking"
    DEGRADED = "degraded"
    WARNING = "warning"


class ResearchCode(StrEnum):
    FETCH_TIMEOUT = "fetch_timeout"
    DNS_FAILED = "dns_failed"
    TLS_FAILED = "tls_failed"
    BLOCKED_PRIVATE_HOST = "blocked_private_host"
    REDIRECT_BLOCKED = "redirect_blocked"
    UNSUPPORTED_CONTENT_TYPE = "unsupported_content_type"
    TEXT_EXTRACTION_EMPTY = "text_extraction_empty"
    TEXT_EXTRACTION_WEAK = "text_extraction_weak"
    IDENTITY_CONFLICT = "identity_conflict"
    INDUSTRY_UNKNOWN = "industry_unknown"
    FETCH_BLOCKED_BOT_PROTECTION = "fetch_blocked_bot_protection"
    FETCH_RATE_LIMITED = "fetch_rate_limited"
    FETCH_ACCESS_DENIED = "fetch_access_denied"
    JS_CONTENT_DETECTED = "js_content_detected"
    SOURCE_GAP = "source_gap"


@dataclass(frozen=True, slots=True)
class ResearchIssue:
    code: str
    severity: str
    message: str
    source_type: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class IdentitySource:
    source_type: str
    enabled: bool
    phase: str
    priority: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


IDENTITY_SOURCE_REGISTRY: tuple[IdentitySource, ...] = (
    IdentitySource(OWNED_WEBSITE_SOURCE, True, "mvp", 1),
    IdentitySource(REGISTER_SOURCE, False, "phase2", 2),
    IdentitySource(LINKEDIN_SOURCE, False, "phase2", 3),
    IdentitySource(WIKIDATA_SOURCE, False, "phase2", 4),
)


@dataclass(frozen=True, slots=True)
class WebsiteSnapshot:
    requested_url: str
    final_url: str
    reachable: bool
    http_status: int = 0
    content_type: str = ""
    title: str = ""
    meta_description: str = ""
    og_title: str = ""
    og_description: str = ""
    h1: tuple[str, ...] = ()
    h2: tuple[str, ...] = ()
    visible_text: str = ""
    language: str = ""
    redirect_chain: tuple[str, ...] = ()
    fetch_error_type: str = ""
    fetch_error_message: str = ""
    retrieved_at: str = ""
    content_hash: str = ""
    content_length: int = 0
    is_pdf: bool = False
    blocked_reason: str = ""
    extraction_quality: str = "unknown"
    js_content_detected: bool = False
    about_url: str = ""
    imprint_url: str = ""

    def __post_init__(self) -> None:
        if len(self.visible_text) > MAX_VISIBLE_TEXT_CHARS:
            object.__setattr__(self, "visible_text", self.visible_text[:MAX_VISIBLE_TEXT_CHARS])
        if not self.content_hash and self.visible_text:
            digest = hashlib.sha256(self.visible_text.encode("utf-8", errors="ignore")).hexdigest()
            object.__setattr__(self, "content_hash", digest)

    def get(self, key: str, default: Any = None) -> Any:
        legacy = {
            "url": "requested_url",
            "content_language": "language",
            "error_type": "fetch_error_type",
            "error_message": "fetch_error_message",
            "fetched_at": "retrieved_at",
        }
        attr = legacy.get(key, key)
        return getattr(self, attr, default)

    def __getitem__(self, key: str) -> Any:
        value = self.get(key, None)
        if value is None and not hasattr(self, key):
            raise KeyError(key)
        return value

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update({
            "url": self.requested_url,
            "content_language": self.language,
            "error_type": self.fetch_error_type,
            "error_message": self.fetch_error_message,
            "fetched_at": self.retrieved_at,
        })
        return payload

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> WebsiteSnapshot:
        return cls(
            requested_url=str(payload.get("requested_url") or payload.get("url") or ""),
            final_url=str(payload.get("final_url") or payload.get("url") or ""),
            reachable=bool(payload.get("reachable")),
            http_status=int(payload.get("http_status", 0) or 0),
            content_type=str(payload.get("content_type", "")),
            title=str(payload.get("title", "")),
            meta_description=str(payload.get("meta_description", "")),
            visible_text=str(payload.get("visible_text", "")),
            language=str(payload.get("language") or payload.get("content_language") or ""),
            redirect_chain=tuple(payload.get("redirect_chain", ()) or ()),
            fetch_error_type=str(payload.get("fetch_error_type") or payload.get("error_type") or ""),
            fetch_error_message=str(payload.get("fetch_error_message") or payload.get("error_message") or ""),
            retrieved_at=str(payload.get("retrieved_at") or payload.get("fetched_at") or ""),
            content_hash=str(payload.get("content_hash", "")),
            content_length=int(payload.get("content_length", 0) or 0),
            is_pdf=bool(payload.get("is_pdf", False)),
            blocked_reason=str(payload.get("blocked_reason", "")),
            extraction_quality=str(payload.get("extraction_quality", "unknown")),
            js_content_detected=bool(payload.get("js_content_detected", False)),
        )


@dataclass(frozen=True, slots=True)
class IdentityResolutionResult:
    submitted_name: str
    verified_company_name: str
    verified_legal_name: str = ""
    brand_name: str = ""
    name_confidence: str = "low"
    confidence_reason: str = ""
    homepage_name_match: bool = False
    source_gaps: tuple[ResearchIssue, ...] = ()

    def get(self, key: str, default: Any = None) -> Any:
        legacy = {"name_confidence_reason": "confidence_reason"}
        return getattr(self, legacy.get(key, key), default)

    def __getitem__(self, key: str) -> Any:
        value = self.get(key, None)
        if value is None and not hasattr(self, key):
            raise KeyError(key)
        return value

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_gaps"] = [issue.as_dict() for issue in self.source_gaps]
        return payload


@dataclass(frozen=True, slots=True)
class IndustryInferenceResult:
    industry_hint: str
    confidence: str
    confidence_reason: str
    evidence_fields: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CompanyResearchResult:
    normalized_domain: str
    homepage_url: str
    snapshot: WebsiteSnapshot
    identity: IdentityResolutionResult
    industry: IndustryInferenceResult
    summary: str
    evidence: tuple[dict[str, Any], ...] = ()
    warnings: tuple[ResearchIssue, ...] = ()
    errors: tuple[ResearchIssue, ...] = ()
    source_registry: tuple[IdentitySource, ...] = IDENTITY_SOURCE_REGISTRY
    schema_version: str = RESEARCH_SCHEMA_VERSION
    timings_ms: dict[str, int] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        if key == "verified_company_name":
            return self.identity.verified_company_name
        if key == "verified_legal_name":
            return self.identity.verified_legal_name
        if key == "name_confidence":
            return self.identity.name_confidence
        if key == "industry_hint":
            return self.industry.industry_hint
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        value = self.get(key, None)
        if value is None and not hasattr(self, key):
            raise KeyError(key)
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "normalized_domain": self.normalized_domain,
            "homepage_url": self.homepage_url,
            "snapshot": self.snapshot.as_dict(),
            "identity": self.identity.as_dict(),
            "industry": self.industry.as_dict(),
            "summary": self.summary,
            "evidence": list(self.evidence),
            "warnings": [issue.as_dict() for issue in self.warnings],
            "errors": [issue.as_dict() for issue in self.errors],
            "source_registry": [source.as_dict() for source in self.source_registry],
            "timings_ms": dict(self.timings_ms),
            # legacy compatibility
            "verified_company_name": self.identity.verified_company_name,
            "verified_legal_name": self.identity.verified_legal_name,
            "name_confidence": self.identity.name_confidence,
        }

