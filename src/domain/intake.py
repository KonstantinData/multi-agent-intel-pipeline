"""Intake-side domain models."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.research.normalize import IntakeErrorCode

# Placeholder values that indicate the caller did not supply a real company name.
# web_domain placeholders are handled in normalize_domain_result() in src/research/normalize.py.
_COMPANY_NAME_PLACEHOLDERS: frozenset[str] = frozenset({
    "n/v", "n/a", "unknown", "none", "null", "na", "tbd",
})

_MAX_COMPANY_NAME_LENGTH = 200
_MAX_WEB_DOMAIN_INPUT_LENGTH = 2048  # generous; normalize_domain_result() enforces hostname limits


class IntakeValidationError(ValueError):
    """Structured intake-validation failure with machine-readable field + code.

    Raised by `IntakeRequest.__post_init__()` when a required field is missing,
    a placeholder value is supplied, or a length limit is exceeded. Caught by
    `run_pipeline()` to build a structured failed-run result.
    """

    def __init__(self, *, field: str, code: str, reason: str) -> None:
        super().__init__(reason)
        self.field = field
        self.code = code
        self.reason = reason


def _present(value: str) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"", "n/v", "n/a", "unknown"} else text


@dataclass(slots=True)
class IntakeRequest:
    company_name: str
    web_domain: str
    language: str = "de"

    def __post_init__(self) -> None:
        self.company_name = " ".join(str(self.company_name or "").split())
        self.web_domain = str(self.web_domain or "").strip()
        self.language = str(self.language or "de").strip() or "de"

        if not self.company_name:
            raise IntakeValidationError(
                field="company_name",
                code=IntakeErrorCode.COMPANY_NAME_REQUIRED,
                reason="company_name is required.",
            )
        if len(self.company_name) > _MAX_COMPANY_NAME_LENGTH:
            raise IntakeValidationError(
                field="company_name",
                code=IntakeErrorCode.COMPANY_NAME_TOO_LONG,
                reason=(
                    f"company_name must not exceed {_MAX_COMPANY_NAME_LENGTH} characters."
                ),
            )
        if self.company_name.lower() in _COMPANY_NAME_PLACEHOLDERS:
            raise IntakeValidationError(
                field="company_name",
                code=IntakeErrorCode.COMPANY_NAME_PLACEHOLDER,
                reason=(
                    f"company_name '{self.company_name}' is a placeholder value."
                ),
            )

        if not self.web_domain:
            raise IntakeValidationError(
                field="web_domain",
                code=IntakeErrorCode.WEB_DOMAIN_REQUIRED,
                reason="web_domain is required.",
            )
        if len(self.web_domain) > _MAX_WEB_DOMAIN_INPUT_LENGTH:
            raise IntakeValidationError(
                field="web_domain",
                code=IntakeErrorCode.WEB_DOMAIN_TOO_LONG,
                reason=(
                    f"web_domain must not exceed {_MAX_WEB_DOMAIN_INPUT_LENGTH} characters."
                ),
            )


@dataclass(slots=True)
class SupervisorBrief:
    submitted_company_name: str
    submitted_web_domain: str
    verified_company_name: str
    verified_legal_name: str
    name_confidence: str
    website_reachable: bool
    homepage_url: str
    page_title: str
    meta_description: str
    raw_homepage_excerpt: str
    normalized_domain: str
    industry_hint: str = "n/v"
    observations: list[str] = field(default_factory=list)
    sources: list[dict[str, str]] = field(default_factory=list)
    fetch_error_type: str = ""
    fetch_error_message: str = ""
    # ── Punkt 5: evidence-backed briefing contract ──
    # All new fields have safe defaults so legacy fixtures keep working.
    schema_version: str = ""
    name_confidence_reason: str = ""
    industry_confidence: str = "unknown"
    industry_confidence_reason: str = ""
    evidence_items: list[dict[str, str]] = field(default_factory=list)
    missing_evidence: list[dict[str, str]] = field(default_factory=list)
    fetch_audit: dict = field(default_factory=dict)
    briefing_readiness: str = "ready"
    routing_gaps: list[str] = field(default_factory=list)
    identity_conflict: bool = False

    @property
    def company_name(self) -> str:
        return (
            _present(self.verified_legal_name)
            or _present(self.verified_company_name)
            or _present(self.submitted_company_name)
            or "n/v"
        )

    @property
    def web_domain(self) -> str:
        return self.normalized_domain or self.submitted_web_domain
