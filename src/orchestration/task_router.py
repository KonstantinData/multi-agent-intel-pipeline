"""Translate the supervisor mandate into department assignments.

The Assignment dataclass carries the full task contract from use_cases.py
into the runtime layer.  ``evaluate_run_conditions()`` generically decides
which tasks are runnable vs skipped based on ``run_condition`` and the
current pipeline state — no department-specific logic required.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.app.use_cases import build_standard_backlog
from src.config import get_role_model_selection
from src.domain.intake import SupervisorBrief
from src.orchestration.tool_policy import resolve_allowed_tools


DEPARTMENT_RESEARCHERS = {
    "CompanyDepartment": "CompanyResearcher",
    "MarketDepartment": "MarketResearcher",
    "BuyerDepartment": "BuyerResearcher",
    "ContactDepartment": "ContactResearcher",
}


@dataclass(frozen=True, slots=True)
class Assignment:
    task_key: str
    assignee: str
    target_section: str
    label: str
    objective: str
    model_name: str
    allowed_tools: tuple[str, ...]
    # Contract fields from use_cases.py — carried through to runtime
    depends_on: tuple[str, ...] = ()
    run_condition: str | None = None
    output_schema_key: str = ""
    industry_hint: str = "n/v"


@dataclass(frozen=True, slots=True)
class DepartmentAssignment:
    department: str
    target_section: str
    assignments: tuple[Assignment, ...]


def _assignment_role_name(assignee: str) -> str:
    return DEPARTMENT_RESEARCHERS.get(assignee, assignee)


def build_initial_assignments(brief: SupervisorBrief) -> list[Assignment]:
    """Build assignments carrying the full task contract from use_cases.py."""
    industry = brief.industry_hint if brief.industry_hint != "n/v" else brief.company_name
    assignments: list[Assignment] = []
    for item in build_standard_backlog():
        assignee = str(item["assignee"])
        role_name = _assignment_role_name(assignee)
        allowed_tools = resolve_allowed_tools(role_name, str(item["task_key"]))
        chat_model, structured_model = get_role_model_selection(role_name)
        assignments.append(
            Assignment(
                task_key=str(item["task_key"]),
                assignee=assignee,
                target_section=str(item["target_section"]),
                label=str(item["label"]),
                objective=str(item["objective_template"]).format(
                    company_name=brief.company_name,
                    industry_hint=industry,
                ),
                model_name=structured_model if "llm_structured" in allowed_tools else chat_model,
                allowed_tools=allowed_tools,
                depends_on=tuple(item.get("depends_on") or []),
                run_condition=item.get("run_condition"),
                output_schema_key=str(item.get("output_schema_key", "")),
                industry_hint=brief.industry_hint,
            )
        )
    return assignments


# ---------------------------------------------------------------------------
# Generic run_condition evaluation
# ---------------------------------------------------------------------------

# Maps run_condition strings to callables that receive the pipeline state
# and return True when the condition is met.
_CONDITION_EVALUATORS: dict[str, Any] = {
    "buyer_department_has_prioritized_firms": lambda state: _is_admitted_with_points(
        state.get("department_packages", {}), "BuyerDepartment",
    ),
    "contact_discovery_completed": lambda state: (
        state.get("task_statuses", {}).get("contact_discovery") in ("accepted", "degraded")
    ),
}


def _is_admitted_with_points(packages: dict[str, Any], dept: str) -> bool:
    """Check if a department package is admitted and has accepted_points."""
    pkg = packages.get(dept, {})
    # Envelope format (F2): check admission + raw_package
    if "admission" in pkg:
        if not pkg["admission"].get("downstream_visible", False):
            return False
        raw = pkg.get("raw_package", {})
        return bool(raw.get("accepted_points"))
    # Legacy format (pre-F2): direct package dict
    return bool(pkg.get("accepted_points"))


def evaluate_run_conditions(
    assignments: list[Assignment],
    *,
    pipeline_state: dict[str, Any],
) -> tuple[list[Assignment], list[dict[str, str]]]:
    """Split assignments into runnable and skipped based on run_condition.

    Parameters
    ----------
    assignments:
        All assignments for a single department.
    pipeline_state:
        Dict with at least ``department_packages`` and ``task_statuses``
        reflecting the current pipeline progress.

    Returns
    -------
    (runnable, skipped)
        *runnable* — assignments whose run_condition is met (or None).
        *skipped* — dicts with ``task_key``, ``label``, ``target_section``,
        ``status: "skipped"`` for tasks whose condition is not met.
    """
    runnable: list[Assignment] = []
    skipped: list[dict[str, str]] = []
    for a in assignments:
        if a.run_condition is None:
            runnable.append(a)
            continue
        evaluator = _CONDITION_EVALUATORS.get(a.run_condition)
        if evaluator is None:
            # Unknown condition — run the task (fail-open)
            runnable.append(a)
            continue
        if evaluator(pipeline_state):
            runnable.append(a)
        else:
            skipped.append({
                "task_key": a.task_key,
                "label": a.label,
                "target_section": a.target_section,
                "status": "skipped",
            })
    return runnable, skipped


def build_department_assignments(brief: SupervisorBrief) -> list[DepartmentAssignment]:
    grouped: dict[tuple[str, str], list[Assignment]] = {}
    for assignment in build_initial_assignments(brief):
        if assignment.assignee not in DEPARTMENT_RESEARCHERS:
            continue
        key = (assignment.assignee, assignment.target_section)
        grouped.setdefault(key, []).append(assignment)
    return [
        DepartmentAssignment(
            department=department,
            target_section=target_section,
            assignments=tuple(grouped[(department, target_section)]),
        )
        for department, target_section in grouped
    ]


def build_synthesis_assignments(brief: SupervisorBrief) -> list[Assignment]:
    return [
        assignment
        for assignment in build_initial_assignments(brief)
        if assignment.assignee == "SynthesisDepartment"
    ]
