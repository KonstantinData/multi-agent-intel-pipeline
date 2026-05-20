"""Architecture tests for the Synthesis Department input boundary."""
from __future__ import annotations

from src.orchestration.synthesis_inputs import build_synthesis_input_packages


def _envelope(
    *,
    decision: str,
    downstream_visible: bool,
    narrative_summary: str | None,
) -> dict:
    raw_package = {
        "confidence": "medium",
        "report_segment": {
            "narrative_summary": narrative_summary or "n/v",
            "confidence": "medium",
            "key_findings": ["finding"],
            "open_questions": ["gap"],
        },
    }
    return {
        "admission": {
            "decision": decision,
            "reason": "test",
            "downstream_visible": downstream_visible,
        },
        "raw_package": raw_package,
        "admitted_payload": {"section": "payload"} if downstream_visible else None,
    }


def test_synthesis_inputs_include_admitted_packages() -> None:
    packages = {
        "BuyerDepartment": _envelope(
            decision="accepted",
            downstream_visible=True,
            narrative_summary="Buyer segment is complete.",
        )
    }

    result = build_synthesis_input_packages(packages)

    assert list(result) == ["BuyerDepartment"]
    assert result["BuyerDepartment"]["synthesis_visibility"] == {
        "mode": "admitted",
        "reason": "supervisor_admitted_package",
        "admission_decision": "accepted",
        "downstream_visible": True,
    }


def test_synthesis_inputs_include_rejected_report_segments_as_diagnostic() -> None:
    packages = {
        "CompanyDepartment": _envelope(
            decision="rejected",
            downstream_visible=False,
            narrative_summary="Company segment has useful but gate-blocked findings.",
        ),
        "MarketDepartment": _envelope(
            decision="rejected",
            downstream_visible=False,
            narrative_summary="Market segment has useful but gate-blocked findings.",
        ),
        "BuyerDepartment": _envelope(
            decision="accepted",
            downstream_visible=True,
            narrative_summary="Buyer segment is complete.",
        ),
        "ContactDepartment": _envelope(
            decision="rejected",
            downstream_visible=False,
            narrative_summary="Contact segment has useful but gate-blocked findings.",
        ),
    }

    result = build_synthesis_input_packages(packages)

    assert list(result) == [
        "CompanyDepartment",
        "MarketDepartment",
        "BuyerDepartment",
        "ContactDepartment",
    ]
    assert result["CompanyDepartment"]["synthesis_visibility"] == {
        "mode": "diagnostic",
        "reason": "supervisor_rejected_package_with_report_segment",
        "admission_decision": "rejected",
        "downstream_visible": False,
    }
    assert packages["CompanyDepartment"].get("synthesis_visibility") is None


def test_synthesis_inputs_exclude_rejected_packages_without_report_segment() -> None:
    packages = {
        "CompanyDepartment": _envelope(
            decision="rejected",
            downstream_visible=False,
            narrative_summary=None,
        ),
        "BuyerDepartment": _envelope(
            decision="accepted",
            downstream_visible=True,
            narrative_summary="Buyer segment is complete.",
        ),
    }

    result = build_synthesis_input_packages(packages)

    assert list(result) == ["BuyerDepartment"]
