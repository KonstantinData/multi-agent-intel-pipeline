"""Build the package view consumed by the Synthesis Department."""
from __future__ import annotations

from typing import Any

from src.orchestration.envelope import resolve_admission, resolve_report_segment

SYNTHESIS_DOMAIN_DEPARTMENTS = (
    "CompanyDepartment",
    "MarketDepartment",
    "BuyerDepartment",
    "ContactDepartment",
)


def _has_usable_report_segment(segment: dict[str, Any]) -> bool:
    summary = str(segment.get("narrative_summary", "") or "").strip()
    return bool(summary and summary.lower() != "n/v")


def _with_synthesis_visibility(
    *,
    package: dict[str, Any],
    mode: str,
    reason: str,
    admission: dict[str, Any],
) -> dict[str, Any]:
    visible_package = dict(package)
    visible_package["synthesis_visibility"] = {
        "mode": mode,
        "reason": reason,
        "admission_decision": admission.get("decision", "unknown"),
        "downstream_visible": bool(admission.get("downstream_visible", False)),
    }
    return visible_package


def build_synthesis_input_packages(
    department_packages: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return report-segment packages Synthesis may inspect.

    The Supervisor admission gate remains authoritative. Accepted or
    accepted-with-gaps packages are normal synthesis inputs. Rejected packages
    with an existing report segment are exposed as diagnostic inputs only, so
    Synthesis can reason about gaps without treating the content as admitted
    downstream truth.
    """
    if not isinstance(department_packages, dict):
        return {}

    ordered_departments = [
        *[dept for dept in SYNTHESIS_DOMAIN_DEPARTMENTS if dept in department_packages],
        *[
            dept
            for dept in department_packages
            if dept not in SYNTHESIS_DOMAIN_DEPARTMENTS and dept != "SynthesisDepartment"
        ],
    ]

    synthesis_packages: dict[str, Any] = {}
    for dept in ordered_departments:
        package = department_packages.get(dept)
        if not isinstance(package, dict):
            continue
        segment = resolve_report_segment(package)
        if not _has_usable_report_segment(segment):
            continue

        admission = resolve_admission(package)
        if bool(admission.get("downstream_visible", False)):
            synthesis_packages[dept] = _with_synthesis_visibility(
                package=package,
                mode="admitted",
                reason="supervisor_admitted_package",
                admission=admission,
            )
            continue

        synthesis_packages[dept] = _with_synthesis_visibility(
            package=package,
            mode="diagnostic",
            reason="supervisor_rejected_package_with_report_segment",
            admission=admission,
        )

    return synthesis_packages
