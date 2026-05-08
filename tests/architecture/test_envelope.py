"""P0-4: Regression tests for envelope resolvers and canonical shape access."""
from __future__ import annotations

from src.orchestration.envelope import (
    is_envelope,
    resolve_admission,
    resolve_admitted_payload,
    resolve_confidence,
    resolve_open_questions,
    resolve_raw_package,
    resolve_report_segment,
    resolve_visual_focus,
)


def _make_raw_package(**overrides):
    base = {
        "department": "CompanyDepartment",
        "target_section": "company_profile",
        "summary": "Test summary",
        "section_payload": {"company_name": "TestCo"},
        "completed_tasks": [],
        "accepted_points": ["point_a"],
        "open_questions": ["q1"],
        "visual_focus": ["focus_a", "focus_b"],
        "sources": [],
        "report_segment": {
            "department": "CompanyDepartment",
            "narrative_summary": "Test narrative",
            "confidence": "high",
            "key_findings": ["finding_1"],
            "open_questions": ["open_q"],
            "sources": [],
        },
        "confidence": "high",
    }
    base.update(overrides)
    return base


def _make_envelope(raw_package=None, decision="accepted"):
    raw = raw_package or _make_raw_package()
    return {
        "admission": {
            "decision": decision,
            "reason": f"Test {decision}",
            "downstream_visible": decision != "rejected",
        },
        "raw_package": raw,
        "admitted_payload": raw.get("section_payload") if decision != "rejected" else None,
    }


class TestIsEnvelope:
    def test_envelope_detected(self):
        assert is_envelope(_make_envelope()) is True

    def test_raw_package_not_envelope(self):
        assert is_envelope(_make_raw_package()) is False

    def test_empty_dict_not_envelope(self):
        assert is_envelope({}) is False


class TestResolveRawPackage:
    def test_from_envelope(self):
        raw = _make_raw_package()
        env = _make_envelope(raw)
        assert resolve_raw_package(env) is raw

    def test_from_raw_passthrough(self):
        raw = _make_raw_package()
        assert resolve_raw_package(raw) is raw


class TestResolveAdmittedPayload:
    def test_accepted_envelope(self):
        env = _make_envelope(decision="accepted")
        assert resolve_admitted_payload(env) == {"company_name": "TestCo"}

    def test_rejected_envelope(self):
        env = _make_envelope(decision="rejected")
        assert resolve_admitted_payload(env) is None

    def test_raw_package_fallback(self):
        raw = _make_raw_package()
        assert resolve_admitted_payload(raw) == {"company_name": "TestCo"}


class TestResolveAdmission:
    def test_from_envelope(self):
        env = _make_envelope(decision="accepted_with_gaps")
        adm = resolve_admission(env)
        assert adm["decision"] == "accepted_with_gaps"
        assert adm["downstream_visible"] is True

    def test_from_raw_returns_unknown(self):
        adm = resolve_admission(_make_raw_package())
        assert adm["decision"] == "unknown"


class TestResolveReportSegment:
    def test_from_envelope(self):
        env = _make_envelope()
        seg = resolve_report_segment(env)
        assert seg["narrative_summary"] == "Test narrative"
        assert seg["confidence"] == "high"

    def test_from_raw(self):
        raw = _make_raw_package()
        seg = resolve_report_segment(raw)
        assert seg["narrative_summary"] == "Test narrative"

    def test_missing_segment(self):
        env = _make_envelope(_make_raw_package(report_segment={}))
        assert resolve_report_segment(env) == {}


class TestResolveVisualFocus:
    def test_from_envelope(self):
        assert resolve_visual_focus(_make_envelope()) == ["focus_a", "focus_b"]

    def test_from_raw(self):
        assert resolve_visual_focus(_make_raw_package()) == ["focus_a", "focus_b"]

    def test_missing(self):
        env = _make_envelope(_make_raw_package(visual_focus=[]))
        assert resolve_visual_focus(env) == []


class TestResolveConfidence:
    def test_from_envelope(self):
        assert resolve_confidence(_make_envelope()) == "high"

    def test_from_raw(self):
        assert resolve_confidence(_make_raw_package()) == "high"

    def test_default(self):
        assert resolve_confidence({}) == "low"


class TestResolveOpenQuestions:
    def test_from_envelope(self):
        assert resolve_open_questions(_make_envelope()) == ["q1"]

    def test_from_raw(self):
        assert resolve_open_questions(_make_raw_package()) == ["q1"]


class TestEnvelopeShapeMismatchDetection:
    """Negative tests: wrong shape must not silently succeed."""

    def test_direct_report_segment_on_envelope_root_returns_empty(self):
        """Pre-P0 bug: code did pkg.get('report_segment') on envelope root."""
        env = _make_envelope()
        # Direct access (the old broken pattern) returns nothing
        assert env.get("report_segment") is None
        # Resolver returns the correct segment
        assert resolve_report_segment(env)["narrative_summary"] == "Test narrative"

    def test_direct_visual_focus_on_envelope_root_returns_none(self):
        env = _make_envelope()
        assert env.get("visual_focus") is None
        assert resolve_visual_focus(env) == ["focus_a", "focus_b"]


# ---------------------------------------------------------------------------
# RF2-1: Synthesis envelope regression tests
# ---------------------------------------------------------------------------

def _make_synthesis_envelope(decision="accepted"):
    """Build a canonical Synthesis envelope (post-RF2-1 fix)."""
    raw = {
        "target_company": "TestCo",
        "executive_summary": "TestCo presents a clear opportunity.",
        "opportunity_assessment": "Excess inventory path is most plausible.",
        "generation_mode": "normal",
        "confidence": "medium",
    }
    return {
        "admission": {
            "decision": decision,
            "reason": f"Test synthesis {decision}",
            "downstream_visible": decision != "rejected",
        },
        "raw_package": raw,
        "admitted_payload": raw if decision != "rejected" else None,
    }


def _make_legacy_synthesis_envelope(decision="accepted"):
    """Build a legacy Synthesis envelope (pre-RF2-1, uses raw_synthesis)."""
    raw = {
        "target_company": "LegacyCo",
        "executive_summary": "Legacy synthesis output.",
        "generation_mode": "normal",
        "confidence": "medium",
    }
    return {
        "admission": {
            "decision": decision,
            "reason": f"Legacy {decision}",
            "downstream_visible": decision != "rejected",
        },
        "raw_synthesis": raw,
        "admitted_synthesis": raw if decision != "rejected" else None,
    }


class TestSynthesisEnvelope:
    """RF2-1: Synthesis envelope must use canonical shape and be resolver-compatible."""

    def test_canonical_synthesis_envelope_is_detected(self):
        env = _make_synthesis_envelope()
        assert is_envelope(env) is True

    def test_canonical_synthesis_resolve_admission(self):
        env = _make_synthesis_envelope(decision="accepted")
        adm = resolve_admission(env)
        assert adm["decision"] == "accepted"

    def test_canonical_synthesis_resolve_raw_package(self):
        env = _make_synthesis_envelope()
        raw = resolve_raw_package(env)
        assert raw["target_company"] == "TestCo"
        assert raw["executive_summary"] == "TestCo presents a clear opportunity."

    def test_canonical_synthesis_rejected(self):
        env = _make_synthesis_envelope(decision="rejected")
        assert resolve_admission(env)["decision"] == "rejected"
        assert resolve_admitted_payload(env) is None

    def test_legacy_synthesis_envelope_is_detected(self):
        """Compat: old runs with raw_synthesis must still be recognised."""
        env = _make_legacy_synthesis_envelope()
        assert is_envelope(env) is True

    def test_legacy_synthesis_resolve_admission(self):
        env = _make_legacy_synthesis_envelope(decision="accepted")
        adm = resolve_admission(env)
        assert adm["decision"] == "accepted"

    def test_legacy_synthesis_resolve_raw_package(self):
        """Compat: resolve_raw_package falls back to raw_synthesis."""
        env = _make_legacy_synthesis_envelope()
        raw = resolve_raw_package(env)
        assert raw["target_company"] == "LegacyCo"

    def test_synthesis_envelope_not_confused_with_department(self):
        """Synthesis envelope must not accidentally resolve department fields."""
        env = _make_synthesis_envelope()
        assert resolve_report_segment(env) == {}
        assert resolve_visual_focus(env) == []
