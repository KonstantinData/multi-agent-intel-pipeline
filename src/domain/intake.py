"""Intake-side domain models."""
from __future__ import annotations

from dataclasses import dataclass, field


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
            raise ValueError("Intake validation failed: company_name is required.")
        if not self.web_domain:
            raise ValueError("Intake validation failed: web_domain is required.")


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
