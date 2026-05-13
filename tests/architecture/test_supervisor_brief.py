"""Architecture tests for the evidence-backed Supervisor Briefing (Punkt 5).

Exercises the typed contracts in `src/domain/briefing.py` and the
`SupervisorAgent.build_intake_brief()` flow with mocked `build_company_research`.
No AG2 dependency — fully exercisable in `tests/architecture/`.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import pytest

from src.agents import supervisor as supervisor_module
from src.agents.supervisor import SupervisorAgent
from src.domain.briefing import (
    ALLOWED_SOURCE_TYPES,
    BRIEFING_REDIRECT_DOMAIN_MISMATCH,
    BRIEFING_SCHEMA_VERSION,
    SOURCE_TYPE_OWNED_WEBSITE,
    BriefingReadiness,
    EvidenceSummary,
    EvidenceItem,
    IdentityConfidence,
    IndustryConfidence,
    SupervisorBriefMessage,
    classify_briefing_readiness,
    classify_identity_confidence,
    classify_industry_confidence,
    detect_identity_conflict,
    validate_supervisor_brief_message,
)
from src.domain.intake import IntakeRequest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_research(
    *,
    reachable: bool = True,
    title: str = "Example AG",
    meta: str = "Industrial automation supplier",
    verified_company_name: str = "Example AG",
    verified_legal_name: str = "",
    error_type: str = "",
    final_url: str = "https://example.com",
    http_status: int = 200,
    content_language: str = "de",
    fetched_at: str = "2026-05-12T10:00:00Z",
) -> dict[str, Any]:
    """Mock factory matching the shape of `build_company_research()`."""
    return {
        "normalized_domain": "example.com",
        "homepage_url": "https://example.com",
        "snapshot": {
            "reachable": reachable,
            "url": "https://example.com",
            "title": title,
            "meta_description": meta,
            "visible_text": "Example AG manufactures industrial automation systems.",
            "content_type": "text/html; charset=utf-8",
            "is_pdf": False,
            "error_type": error_type,
            "error_message": "network timed out" if error_type else "",
            "final_url": final_url,
            "http_status": http_status,
            "content_length": 12345,
            "content_language": content_language,
            "fetched_at": fetched_at,
            "redirect_chain": [],
        },
        "summary": "Example AG manufactures industrial automation systems.",
        "verified_company_name": verified_company_name,
        "verified_legal_name": verified_legal_name,
        "name_confidence": "high",
    }


def _supervisor_with_mock(monkeypatch: pytest.MonkeyPatch, **research_kw: Any) -> SupervisorAgent:
    research = _make_research(**research_kw)
    monkeypatch.setattr(
        supervisor_module, "build_company_research", lambda *a, **kw: research
    )
    return SupervisorAgent.__new__(SupervisorAgent)


# ── 5.4 Identity confidence (token-overlap heuristic) ─────────────────────────

def test_identity_confidence_high_when_homepage_contains_all_tokens() -> None:
    confidence, reason = classify_identity_confidence(
        website_reachable=True,
        submitted_name="Example AG",
        homepage_title="Example AG — Industrial Automation",
        verified_legal_name="",
    )
    assert confidence == IdentityConfidence.HIGH
    assert "all submitted-name tokens" in reason


def test_identity_confidence_medium_on_partial_overlap() -> None:
    confidence, reason = classify_identity_confidence(
        website_reachable=True,
        submitted_name="Example AG Solutions",
        homepage_title="Example — Solutions Provider",
        verified_legal_name="",
    )
    assert confidence == IdentityConfidence.MEDIUM
    assert "partial overlap" in reason


def test_identity_confidence_low_when_no_overlap() -> None:
    confidence, reason = classify_identity_confidence(
        website_reachable=True,
        submitted_name="Example AG",
        homepage_title="Totally Different Brand",
        verified_legal_name="",
    )
    assert confidence == IdentityConfidence.LOW
    assert "no token overlap" in reason


def test_identity_confidence_unverified_when_homepage_not_reachable() -> None:
    confidence, reason = classify_identity_confidence(
        website_reachable=False,
        submitted_name="Example AG",
        homepage_title="",
        verified_legal_name="",
    )
    assert confidence == IdentityConfidence.UNVERIFIED
    assert "not reachable" in reason


# ── 5.4 Industry confidence ───────────────────────────────────────────────────

def test_industry_confidence_unknown_when_no_hint() -> None:
    confidence, _ = classify_industry_confidence(
        industry_hint="",
        has_title_signal=True,
        has_meta_signal=True,
    )
    assert confidence == IndustryConfidence.UNKNOWN


def test_industry_confidence_high_when_both_signals_present() -> None:
    confidence, _ = classify_industry_confidence(
        industry_hint="industrial-automation",
        has_title_signal=True,
        has_meta_signal=True,
    )
    assert confidence == IndustryConfidence.HIGH


def test_industry_confidence_low_when_only_text_heuristic() -> None:
    confidence, _ = classify_industry_confidence(
        industry_hint="industrial-automation",
        has_title_signal=False,
        has_meta_signal=False,
    )
    assert confidence == IndustryConfidence.LOW


# ── 5.2 Identity conflict (submitted vs homepage) ─────────────────────────────

def test_detect_identity_conflict_when_homepage_names_different_company() -> None:
    assert detect_identity_conflict(
        submitted_name="Example AG",
        homepage_title="Totally Different Brand",
        confidence=IdentityConfidence.LOW,
    ) is True


def test_no_identity_conflict_when_homepage_unreachable() -> None:
    # Unreachable homepage is a website gap, not an identity conflict.
    assert detect_identity_conflict(
        submitted_name="Example AG",
        homepage_title="",
        confidence=IdentityConfidence.UNVERIFIED,
    ) is False


def test_no_identity_conflict_when_homepage_matches() -> None:
    assert detect_identity_conflict(
        submitted_name="Example AG",
        homepage_title="Example AG — Industrial Automation",
        confidence=IdentityConfidence.HIGH,
    ) is False


# ── 5.6 Briefing readiness classifier ─────────────────────────────────────────

def test_briefing_readiness_ready_when_homepage_and_identity_high() -> None:
    readiness, gaps = classify_briefing_readiness(
        website_reachable=True,
        identity_conflict=False,
        identity_confidence=IdentityConfidence.HIGH,
    )
    assert readiness == BriefingReadiness.READY
    assert gaps == ()


def test_briefing_readiness_blocked_on_conflict() -> None:
    readiness, gaps = classify_briefing_readiness(
        website_reachable=True,
        identity_conflict=True,
        identity_confidence=IdentityConfidence.LOW,
    )
    assert readiness == BriefingReadiness.BLOCKED_IDENTITY_CONFLICT
    assert "identity_conflict" in gaps


def test_briefing_readiness_blocked_when_homepage_unreachable() -> None:
    readiness, gaps = classify_briefing_readiness(
        website_reachable=False,
        identity_conflict=False,
        identity_confidence=IdentityConfidence.UNVERIFIED,
    )
    assert readiness == BriefingReadiness.BLOCKED_WEBSITE_UNREACHABLE
    assert "homepage_unreachable" in gaps
    assert "identity_unverified" in gaps


# ── 5.1 + 5.3 + 5.7: full build_intake_brief flow ─────────────────────────────

def test_build_intake_brief_evidence_contract_on_reachable_homepage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = _supervisor_with_mock(monkeypatch)
    intake = IntakeRequest(company_name="Example AG", web_domain="https://www.example.com")

    brief, message = supervisor.build_intake_brief(intake, normalized_domain="example.com")

    # 5.3: structured evidence items present, all from owned_website
    assert brief.evidence_items
    for item in brief.evidence_items:
        assert item["source_type"] == SOURCE_TYPE_OWNED_WEBSITE
        assert item["source_type"] in ALLOWED_SOURCE_TYPES
        assert item["retrieved_at"]  # ISO timestamp must be non-empty
    supports_fields = {item["supports_field"] for item in brief.evidence_items}
    assert {"verified_company_name", "industry_hint", "website_reachable"}.issubset(supports_fields)

    # 5.3: legal name is recorded as missing (Phase 2 source)
    missing_fields = {item["supports_field"] for item in brief.missing_evidence}
    assert "verified_legal_name" in missing_fields

    # 5.4: identity + industry confidence with reasons
    assert brief.name_confidence == IdentityConfidence.HIGH
    assert brief.name_confidence_reason
    assert brief.industry_confidence in {IndustryConfidence.HIGH, IndustryConfidence.LOW}
    assert brief.industry_confidence_reason

    # 5.6: readiness ready, no routing gaps
    assert brief.briefing_readiness == BriefingReadiness.READY
    assert brief.routing_gaps == []
    assert brief.identity_conflict is False

    # 5.7: versioned message envelope
    assert message["schema_version"] == BRIEFING_SCHEMA_VERSION
    assert message["section"] == "supervisor_brief"
    assert message["status"] == "ready_for_department_routing"
    assert message["briefing_readiness"] == "ready"
    assert message["identity_confidence"] == "high"
    assert isinstance(message["evidence_summary"], dict)
    assert message["evidence_summary"]["item_count"] >= 3


def test_build_intake_brief_blocks_on_unreachable_homepage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = _supervisor_with_mock(
        monkeypatch, reachable=False, title="", meta="", error_type="TimeoutError"
    )
    intake = IntakeRequest(company_name="Example AG", web_domain="https://www.example.com")

    brief, message = supervisor.build_intake_brief(intake, normalized_domain="example.com")

    assert brief.briefing_readiness == BriefingReadiness.BLOCKED_WEBSITE_UNREACHABLE
    assert "homepage_unreachable" in brief.routing_gaps
    assert brief.name_confidence == IdentityConfidence.UNVERIFIED
    assert brief.industry_confidence == IndustryConfidence.UNKNOWN
    assert message["status"] == "blocked_for_department_routing"

    # 5.3: every missing evidence item must have a reason
    for item in brief.missing_evidence:
        assert item["reason"]


def test_build_intake_brief_marks_identity_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    # Homepage clearly names a different company than what the user submitted.
    supervisor = _supervisor_with_mock(
        monkeypatch, title="Totally Different Brand", verified_company_name="Example AG"
    )
    intake = IntakeRequest(company_name="Example AG", web_domain="https://www.example.com")

    brief, message = supervisor.build_intake_brief(intake, normalized_domain="example.com")

    assert brief.identity_conflict is True
    assert brief.briefing_readiness == BriefingReadiness.BLOCKED_IDENTITY_CONFLICT
    assert "identity_conflict" in brief.routing_gaps
    # Submitted name MUST NOT be silently overwritten by the conflicting homepage title.
    assert brief.submitted_company_name == "Example AG"
    assert message["briefing_readiness"] == "blocked_identity_conflict"


def test_build_intake_brief_preserves_brand_vs_legal_separation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """5.2 MVP: verified_legal_name stays empty when register lookup is Phase 2."""
    supervisor = _supervisor_with_mock(monkeypatch, verified_legal_name="")
    intake = IntakeRequest(company_name="Example AG", web_domain="https://www.example.com")

    brief, _ = supervisor.build_intake_brief(intake, normalized_domain="example.com")

    assert brief.verified_legal_name == ""
    # Brand/verified name still comes from the homepage signal.
    assert brief.verified_company_name == "Example AG"
    # Missing evidence must be explicit so the CompanyDepartment knows to clarify.
    missing = {item["supports_field"]: item["reason"] for item in brief.missing_evidence}
    assert "verified_legal_name" in missing
    assert "Phase 2" in missing["verified_legal_name"]


def test_build_intake_brief_does_not_renormalize_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """5.1: build_intake_brief must use the validated canonical domain.

    The mock returns `normalized_domain = "example.com"`. The brief must adopt
    that value without re-running normalization on the raw `intake.web_domain`.
    """
    supervisor = _supervisor_with_mock(monkeypatch)
    intake = IntakeRequest(
        company_name="Example AG",
        web_domain="https://www.example.com/about?ref=test",
    )

    brief, _ = supervisor.build_intake_brief(intake, normalized_domain="example.com")

    assert brief.normalized_domain == "example.com"
    assert brief.submitted_web_domain == "https://www.example.com/about?ref=test"


# ── 5.5 Fetch audit ───────────────────────────────────────────────────────────

def test_build_intake_brief_populates_fetch_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    supervisor = _supervisor_with_mock(
        monkeypatch,
        final_url="https://example.com/",
        http_status=200,
        content_language="de",
    )
    intake = IntakeRequest(company_name="Example AG", web_domain="https://www.example.com")

    brief, _ = supervisor.build_intake_brief(intake, normalized_domain="example.com")

    audit = brief.fetch_audit
    assert audit["reachable"] is True
    assert audit["http_status"] == 200
    assert audit["final_url"] == "https://example.com/"
    assert audit["content_language"] == "de"
    assert audit["fetched_at"]
    assert audit["content_length"] > 0


def test_build_intake_brief_flags_final_url_domain_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = _supervisor_with_mock(
        monkeypatch,
        final_url="https://other-example.com/",
        title="Example AG",
    )
    intake = IntakeRequest(company_name="Example AG", web_domain="https://www.example.com")

    brief, message = supervisor.build_intake_brief(intake, normalized_domain="example.com")

    assert BRIEFING_REDIRECT_DOMAIN_MISMATCH in brief.routing_gaps
    assert brief.briefing_readiness == BriefingReadiness.READY_WITH_WEBSITE_GAPS
    assert message["status"] == "ready_for_department_routing"
    missing = {item["supports_field"]: item["reason"] for item in brief.missing_evidence}
    assert "normalized_domain" in missing
    reason = missing["normalized_domain"]
    url_tokens = [
        token.strip(".,;:()[]{}<>\"'")
        for token in reason.split()
        if token.startswith(("http://", "https://"))
    ]
    parsed_hostnames = [
        hostname.rstrip(".").lower()
        for token in url_tokens
        if (hostname := urlparse(token).hostname)
    ]
    assert any(hostname == "other-example.com" for hostname in parsed_hostnames)


def test_supervisor_brief_message_contract_validator_accepts_valid_message() -> None:
    message = SupervisorBriefMessage(
        schema_version=BRIEFING_SCHEMA_VERSION,
        section="supervisor_brief",
        status="ready_for_department_routing",
        briefing_readiness="ready",
        identity_confidence="high",
        industry_confidence="high",
        routing_gaps=(),
        evidence_summary=EvidenceSummary(
            item_count=1,
            source_types=("owned_website",),
            missing_fields=(),
        ),
        payload={"normalized_domain": "example.com"},
    )

    is_valid, errors = validate_supervisor_brief_message(message.as_dict())

    assert is_valid is True
    assert errors == ()


def test_supervisor_brief_message_contract_validator_rejects_incomplete_message() -> None:
    is_valid, errors = validate_supervisor_brief_message(
        {
            "schema_version": BRIEFING_SCHEMA_VERSION,
            "section": "supervisor_brief",
            "status": "ready_for_department_routing",
        }
    )

    assert is_valid is False
    assert "missing:payload" in errors


# ── 5.11 Logging ──────────────────────────────────────────────────────────────

def test_supervisor_logging_emits_structured_event() -> None:
    import logging as _logging

    from src.orchestration.supervisor_logging import log_supervisor_brief_event

    captured: list[_logging.LogRecord] = []

    class _Collector(_logging.Handler):
        def emit(self, record): captured.append(record)

    logger = _logging.getLogger("liquisto.supervisor_brief")
    handler = _Collector(level=_logging.DEBUG)
    logger.addHandler(handler)
    try:
        log_supervisor_brief_event(
            run_id="20260512T120000Z",
            status="ok",
            duration_ms=120,
            briefing_readiness="ready",
            identity_confidence="high",
            industry_confidence="high",
            fetch_status="reachable",
            evidence_item_count=3,
        )
    finally:
        logger.removeHandler(handler)

    assert captured
    payload = captured[-1].payload  # type: ignore[attr-defined]
    assert payload["component"] == "supervisor_brief"
    assert payload["phase"] == "supervisor_brief"
    assert payload["status"] == "ok"
    assert payload["briefing_readiness"] == "ready"
    assert payload["identity_confidence"] == "high"
    assert payload["fetch_status"] == "reachable"
    assert payload["evidence_item_count"] == 3


# ── 5.8 RunContext snapshot ───────────────────────────────────────────────────

def test_build_supervisor_brief_persists_snapshot_in_resolution_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """5.8: pipeline_runner._build_supervisor_brief() writes a non-sensitive snapshot."""
    from src import pipeline_runner
    from src.agents.runtime_factory import _build_specs
    from src.orchestration.runtime_agents import (
        DOMAIN_DEPARTMENT_NAMES,
        RuntimeAgents,
        RuntimeFactoryConfig,
        SearchCache,
    )

    # Build a stub agents bundle whose supervisor returns a controlled brief.
    class _StubSupervisor:
        def build_intake_brief(self, intake, normalized_domain):
            from src.domain.briefing import (
                BRIEFING_SCHEMA_VERSION,
                BriefingReadiness,
                IdentityConfidence,
                IndustryConfidence,
            )
            from src.domain.intake import SupervisorBrief

            brief = SupervisorBrief(
                submitted_company_name=intake.company_name,
                submitted_web_domain=intake.web_domain,
                verified_company_name="Example AG",
                verified_legal_name="",
                name_confidence=IdentityConfidence.HIGH,
                website_reachable=True,
                homepage_url=f"https://{normalized_domain}",
                page_title="Example AG",
                meta_description="Industrial automation",
                raw_homepage_excerpt="",
                normalized_domain=normalized_domain,
                industry_hint="industrial-automation",
                schema_version=BRIEFING_SCHEMA_VERSION,
                name_confidence_reason="full token match",
                industry_confidence=IndustryConfidence.HIGH,
                industry_confidence_reason="title + meta",
                evidence_items=[
                    {
                        "source_type": "owned_website",
                        "url": f"https://{normalized_domain}",
                        "claim": "Example AG",
                        "supports_field": "verified_company_name",
                        "retrieved_at": "2026-05-12T10:00:00Z",
                    }
                ],
                missing_evidence=[],
                fetch_audit={
                    "reachable": True,
                    "http_status": 200,
                    "final_url": f"https://{normalized_domain}",
                    "content_language": "de",
                },
                briefing_readiness=BriefingReadiness.READY,
                routing_gaps=[],
                identity_conflict=False,
            )
            message = {
                "schema_version": BRIEFING_SCHEMA_VERSION,
                "section": "supervisor_brief",
                "status": "ready_for_department_routing",
                "briefing_readiness": "ready",
                "identity_confidence": "high",
                "industry_confidence": "high",
                "routing_gaps": [],
                "evidence_summary": {
                    "item_count": 1,
                    "source_types": ["owned_website"],
                    "missing_fields": [],
                },
                "payload": {"normalized_domain": normalized_domain},
            }
            return brief, message

    class _StubRole:
        def run(self, *a, **kw): return None

    departments = {name: _StubRole() for name in DOMAIN_DEPARTMENT_NAMES}
    agents = RuntimeAgents(
        supervisor=_StubSupervisor(),
        departments=departments,
        synthesis=_StubRole(),
        report_writer=_StubRole(),
        search_cache=SearchCache(),
        config=RuntimeFactoryConfig(),
        specs=_build_specs(),
    )

    monkeypatch.setattr(pipeline_runner, "create_runtime_agents", lambda config=None: agents)

    state = pipeline_runner._initialize_run(
        start_time=0.0,
        run_id="20260512T120000Z",
        run_dir=tmp_path,
        company_name="Example AG",
        web_domain="https://www.example.com",
    )

    pipeline_runner._build_supervisor_brief(state, on_message=None)

    snap = state.run_context.resolution_state["supervisor_brief"]
    assert snap["schema_version"] == BRIEFING_SCHEMA_VERSION
    assert snap["briefing_readiness"] == "ready"
    assert snap["identity_confidence"] == "high"
    assert snap["industry_confidence"] == "high"
    assert snap["fetch_status"] == "reachable"
    assert snap["evidence_item_count"] == 1
    assert snap["identity_conflict"] is False
    assert "duration_ms" in snap
    # No raw text in snapshot
    snap_repr = repr(snap)
    assert "Industrial automation" not in snap_repr  # meta description excluded
