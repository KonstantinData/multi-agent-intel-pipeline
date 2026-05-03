"""Run-level resolution controller after the first department round.

The controller classifies the run state into exactly one resolution bucket
based on **typed runtime artifacts** (gap_candidates, answer_matrix) as
primary sources, with legacy open_questions as a fallback.

Buckets:
- AUTO_CLOSE_REQUIRED
- USER_DECISION_REQUIRED
- CUSTOMER_CONFIRMATION_REQUIRED
- NOT_MEETING_CRITICAL
- BLOCKING_FAILURE
"""
from __future__ import annotations

from typing import Any, Literal

ResolutionBucket = Literal[
    "AUTO_CLOSE_REQUIRED",
    "USER_DECISION_REQUIRED",
    "CUSTOMER_CONFIRMATION_REQUIRED",
    "NOT_MEETING_CRITICAL",
    "BLOCKING_FAILURE",
]


def _resolve_raw_package(package_envelope: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(package_envelope, dict):
        return {}
    if "raw_package" in package_envelope and isinstance(package_envelope.get("raw_package"), dict):
        return package_envelope["raw_package"]
    return package_envelope


def _extract_typed_gaps(package_envelope: dict[str, Any]) -> list[str]:
    """Extract gap questions from typed gap_candidates (primary) or legacy open_questions (fallback)."""
    raw = _resolve_raw_package(package_envelope)
    typed_gaps = [
        str(g.get("question", "")).strip()
        for g in raw.get("gap_candidates", [])
        if isinstance(g, dict) and str(g.get("question", "")).strip()
    ]
    if typed_gaps:
        return typed_gaps
    return [str(q).strip() for q in raw.get("open_questions", []) if str(q).strip()]


class ResolutionController:
    """Classify first-round run state into exactly one resolution bucket."""

    _PUBLIC_EVIDENCE_DEPARTMENTS = {"CompanyDepartment", "MarketDepartment", "BuyerDepartment"}

    def classify(
        self,
        *,
        sections: dict[str, Any],
        department_packages: dict[str, Any],
        answer_matrix: dict[str, dict[str, Any]],
        task_statuses: dict[str, str],
    ) -> dict[str, Any]:
        rejected_departments = [
            dept
            for dept, envelope in department_packages.items()
            if isinstance(envelope, dict) and envelope.get("admission", {}).get("decision") == "rejected"
        ]
        blocked_tasks = [k for k, status in task_statuses.items() if status == "blocked"]

        unresolved_by_department: dict[str, list[str]] = {}
        for dept, envelope in department_packages.items():
            gaps = _extract_typed_gaps(envelope)
            if gaps:
                unresolved_by_department[dept] = gaps

        meeting_critical_public_gaps = [
            q
            for dept, questions in unresolved_by_department.items()
            if dept in self._PUBLIC_EVIDENCE_DEPARTMENTS
            for q in questions
        ]
        unresolved_contact_gaps = unresolved_by_department.get("ContactDepartment", [])

        unresolved_matrix = [
            question_id
            for question_id, entry in answer_matrix.items()
            if entry.get("status") in {"pending", "blocked"}
        ]

        # Exclusive priority order
        if rejected_departments or blocked_tasks:
            bucket: ResolutionBucket = "BLOCKING_FAILURE"
            rationale = "One or more department outputs were rejected or blocked tasks remain."
        elif meeting_critical_public_gaps:
            bucket = "AUTO_CLOSE_REQUIRED"
            rationale = "Meeting-critical public evidence gaps remain after the first round."
        elif unresolved_contact_gaps and not meeting_critical_public_gaps:
            bucket = "CUSTOMER_CONFIRMATION_REQUIRED"
            rationale = "Only contact-discovery gaps remain and require customer-side confirmation."
        elif unresolved_matrix:
            bucket = "USER_DECISION_REQUIRED"
            rationale = "Some meeting questions remain unanswered and require user prioritization."
        else:
            bucket = "NOT_MEETING_CRITICAL"
            rationale = "No meeting-critical blockers were detected."

        return {
            "bucket": bucket,
            "rationale": rationale,
            "rejected_departments": rejected_departments,
            "blocked_tasks": blocked_tasks,
            "unresolved_by_department": unresolved_by_department,
            "meeting_critical_public_gaps": meeting_critical_public_gaps,
            "unresolved_contact_gaps": unresolved_contact_gaps,
            "unresolved_matrix_questions": unresolved_matrix,
            "first_round_sections": sorted(sections.keys()),
        }
