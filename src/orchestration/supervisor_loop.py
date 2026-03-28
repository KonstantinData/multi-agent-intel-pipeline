"""Core supervisor loop."""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter
from typing import Any, Callable, NamedTuple

from src.config.settings import SOFT_TOKEN_BUDGET, HARD_TOKEN_CAP
from src.domain.intake import SupervisorBrief
from src.memory.short_term_store import ShortTermMemoryStore
from src.orchestration.task_router import (
    DEPARTMENT_RESEARCHERS,
    build_department_assignments,
    build_initial_assignments,
    build_synthesis_assignments,
    evaluate_run_conditions,
)
from src.orchestration.synthesis import build_synthesis_context, build_quality_review
from src.models.schemas import BlockedArtifact


MessageHook = Callable[[dict[str, Any]], None] | None


class SupervisorLoopResult(NamedTuple):
    """F10: Typed return value for run_supervisor_loop."""
    sections: dict[str, Any]
    department_packages: dict[str, Any]
    messages: list[dict[str, Any]]
    completed_backlog: list[dict[str, str]]
    department_timings: dict[str, float]


def _blocked_section_artifact(reason: str, open_questions: list[str] | None = None) -> dict[str, Any]:
    """Return a typed blocked-section artifact for rejected departments."""
    return BlockedArtifact(
        reason=reason,
        open_questions=list(open_questions or []),
    ).model_dump(mode="json")


def _apply_acceptance_gate(
    acceptance: dict[str, Any],
    *,
    dept_name: str,
    target_section: str,
    section_payload: dict[str, Any],
    package: dict[str, Any],
    sections: dict[str, Any],
    department_packages: dict[str, Any],
) -> None:
    """Authoritative downstream admission gate.

    Decides what flows into ``sections`` and ``department_packages`` based
    on the Supervisor's admission decision.  Raw package is always kept
    for diagnostics; only admitted payloads are downstream-visible.
    """
    decision = acceptance.get("decision", "rejected")
    reason = acceptance.get("reason", "")
    open_questions = package.get("open_questions", [])

    envelope: dict[str, Any] = {
        "admission": {
            "decision": decision,
            "reason": reason,
            "downstream_visible": decision != "rejected",
        },
        "raw_package": package,
    }

    if decision == "accepted":
        sections[target_section] = section_payload
        envelope["admitted_payload"] = section_payload
    elif decision == "accepted_with_gaps":
        sections[target_section] = {**section_payload, "_admission": "accepted_with_gaps"}
        envelope["admitted_payload"] = section_payload
    else:
        # rejected — blocked artifact, raw preserved for diagnostics
        sections[target_section] = _blocked_section_artifact(reason, open_questions)
        envelope["admitted_payload"] = None

    department_packages[dept_name] = envelope
    logging.info(
        "Acceptance gate: %s → %s (reason: %s)",
        dept_name, decision, reason,
    )


def _admitted_packages_for_synthesis(
    department_packages: dict[str, Any],
) -> dict[str, Any]:
    """Filter department_packages to only downstream-visible envelopes."""
    return {
        dept: pkg
        for dept, pkg in department_packages.items()
        if isinstance(pkg, dict)
        and pkg.get("admission", {}).get("downstream_visible", False)
    }


# Departments that run sequentially after each other (order matters)
_DEPARTMENT_RUN_ORDER = [
    "CompanyDepartment",
    "MarketDepartment",
    "BuyerDepartment",
    "ContactDepartment",  # depends on BuyerDepartment output
]


def emit_message(
    on_message: MessageHook,
    *,
    agent: str,
    content: str,
    message_type: str = "agent_message",
) -> dict[str, Any]:
    event = {"agent": agent, "content": content, "type": message_type}
    if on_message:
        on_message(event)
    return event


def run_supervisor_loop(
    *,
    brief: SupervisorBrief,
    run_context,
    agents: dict[str, Any],
    on_message: MessageHook = None,
) -> SupervisorLoopResult:
    sections: dict[str, Any] = {}
    department_packages: dict[str, Any] = {}
    messages: list[dict[str, Any]] = []
    assignments = build_initial_assignments(brief)
    department_assignments = build_department_assignments(brief)
    completed_backlog: list[dict[str, str]] = []
    department_timings: dict[str, float] = {}

    # Index department assignments by department name for ordered access
    dept_assignment_map = {da.department: da for da in department_assignments}

    messages.append(
        emit_message(
            on_message,
            agent="Supervisor",
            content=agents["supervisor"].opening_message(),
        )
    )

    for assignment in assignments:
        # Skip synthesis tasks here — they are registered later in the
        # dedicated synthesis block to avoid duplicate task entries.
        if assignment.assignee == "SynthesisDepartment":
            continue
        run_context.record_task(
            assignee=assignment.assignee,
            objective=assignment.objective,
            section=assignment.target_section,
            task_key=assignment.task_key,
            model_name=assignment.model_name,
            allowed_tools=assignment.allowed_tools,
        )

    # Run departments — Company and Market can run in parallel
    _PARALLEL_BATCH = {"CompanyDepartment", "MarketDepartment"}
    _SEQUENTIAL_AFTER = ["BuyerDepartment", "ContactDepartment"]

    def _run_single_department(dept_name, dept_assignment, current_sec, memory_store):
        """Execute one department and return its results with timing."""
        t0 = perf_counter()
        runtime = agents["departments"][dept_name]
        result = runtime.run(
            brief=brief,
            assignments=list(dept_assignment.assignments),
            current_section=current_sec,
            memory_store=memory_store,
            role_memory=run_context.retrieved_role_strategies,
            on_message=on_message,
        )
        elapsed = round(perf_counter() - t0, 3)
        department_timings[dept_name] = elapsed
        logging.info("Department %s completed in %.3fs", dept_name, elapsed)
        return result

    # Phase 1: parallel batch (Company + Market)
    parallel_jobs = [
        name for name in _DEPARTMENT_RUN_ORDER
        if name in _PARALLEL_BATCH and name in dept_assignment_map and name in agents.get("departments", {})
    ]
    if len(parallel_jobs) > 1:
        # F5: Each parallel department gets an isolated working-set store
        # seeded with a read-only snapshot of the current main store.
        # After completion, only the delta (new writes) is merged back.
        working_sets: dict[str, ShortTermMemoryStore] = {}
        baselines: dict[str, ShortTermMemoryStore] = {}
        with ThreadPoolExecutor(max_workers=len(parallel_jobs)) as pool:
            futures = {}
            for dept_name in parallel_jobs:
                da = dept_assignment_map[dept_name]
                messages.append(
                    emit_message(
                        on_message,
                        agent="Supervisor",
                        content=json.dumps(
                            {
                                "department": da.department,
                                "status": "department_assigned",
                                "target_section": da.target_section,
                                "tasks": [{"task_key": a.task_key, "label": a.label, "objective": a.objective} for a in da.assignments],
                            },
                            ensure_ascii=False,
                        ),
                    )
                )
                current_section = sections.get(da.target_section, {})
                ws = run_context.short_term_memory.create_working_set()
                baseline = run_context.short_term_memory.create_working_set()
                working_sets[dept_name] = ws
                baselines[dept_name] = baseline
                futures[pool.submit(_run_single_department, dept_name, da, current_section, ws)] = dept_name

            for future in as_completed(futures):
                dept_name = futures[future]
                da = dept_assignment_map[dept_name]
                section_payload, department_messages, package = future.result()
                messages.extend(department_messages)

                acceptance = agents["supervisor"].accept_department_package(department=dept_name, package=package)
                _apply_acceptance_gate(
                    acceptance,
                    dept_name=dept_name,
                    target_section=da.target_section,
                    section_payload=section_payload,
                    package=package,
                    sections=sections,
                    department_packages=department_packages,
                )
                messages.append(
                    emit_message(
                        on_message,
                        agent="Supervisor",
                        content=json.dumps({"department": dept_name, "status": "department_package_reviewed", **acceptance}, ensure_ascii=False),
                    )
                )
                status_by_task = {task["task_key"]: task["status"] for task in package.get("completed_tasks", [])}
                for assignment in da.assignments:
                    task_status = status_by_task.get(assignment.task_key, "degraded")
                    run_context.update_task_status(task_key=assignment.task_key, status=task_status)
                    run_context.short_term_memory.task_statuses[assignment.task_key] = task_status
                    completed_backlog.append({"task_key": assignment.task_key, "label": assignment.label, "target_section": assignment.target_section, "status": task_status})

        # F5: Merge deltas in canonical department order (not as_completed order)
        for dept_name in parallel_jobs:
            ws = working_sets.get(dept_name)
            baseline = baselines.get(dept_name)
            if ws and baseline:
                delta = ws.delta_from(baseline)
                run_context.short_term_memory.merge_from(delta)
    else:
        # Fallback: run parallel_jobs sequentially if only one
        for dept_name in parallel_jobs:
            da = dept_assignment_map[dept_name]
            messages.append(
                emit_message(on_message, agent="Supervisor", content=json.dumps({"department": da.department, "status": "department_assigned", "target_section": da.target_section, "tasks": [{"task_key": a.task_key, "label": a.label, "objective": a.objective} for a in da.assignments]}, ensure_ascii=False))
            )
            section_payload, department_messages, package = _run_single_department(dept_name, da, sections.get(da.target_section, {}), run_context.short_term_memory)
            messages.extend(department_messages)
            acceptance = agents["supervisor"].accept_department_package(department=dept_name, package=package)
            _apply_acceptance_gate(
                acceptance,
                dept_name=dept_name,
                target_section=da.target_section,
                section_payload=section_payload,
                package=package,
                sections=sections,
                department_packages=department_packages,
            )
            messages.append(emit_message(on_message, agent="Supervisor", content=json.dumps({"department": dept_name, "status": "department_package_reviewed", **acceptance}, ensure_ascii=False)))
            status_by_task = {task["task_key"]: task["status"] for task in package.get("completed_tasks", [])}
            for assignment in da.assignments:
                task_status = status_by_task.get(assignment.task_key, "degraded")
                run_context.update_task_status(task_key=assignment.task_key, status=task_status)
                run_context.short_term_memory.task_statuses[assignment.task_key] = task_status
                completed_backlog.append({"task_key": assignment.task_key, "label": assignment.label, "target_section": assignment.target_section, "status": task_status})

    # Phase 2: sequential departments (Buyer → Contact)
    for department_name in _SEQUENTIAL_AFTER:
        department_assignment = dept_assignment_map.get(department_name)
        if department_assignment is None:
            continue
        if department_name not in agents.get("departments", {}):
            continue

        messages.append(
            emit_message(
                on_message,
                agent="Supervisor",
                content=json.dumps(
                    {
                        "department": department_assignment.department,
                        "status": "department_assigned",
                        "target_section": department_assignment.target_section,
                        "tasks": [
                            {
                                "task_key": a.task_key,
                                "label": a.label,
                                "objective": a.objective,
                            }
                            for a in department_assignment.assignments
                        ],
                    },
                    ensure_ascii=False,
                ),
            )
        )

        # Generic run_condition evaluation from the task contract
        pipeline_state = {
            "department_packages": department_packages,
            "task_statuses": dict(run_context.short_term_memory.task_statuses),
        }
        runnable, skipped_tasks = evaluate_run_conditions(
            list(department_assignment.assignments),
            pipeline_state=pipeline_state,
        )

        # Record skipped tasks
        for sk in skipped_tasks:
            run_context.update_task_status(task_key=sk["task_key"], status="skipped")
            run_context.short_term_memory.task_statuses[sk["task_key"]] = "skipped"
            completed_backlog.append(sk)

        if not runnable:
            # All tasks in this department were skipped
            continue

        # Enrich current_section with upstream data when available
        current_section = sections.get(department_assignment.target_section, {})
        if department_name == "ContactDepartment":
            market_payload = sections.get("market_network", {})
            # Extract real company names from typed company lists (peer + downstream)
            buyer_candidates: list[str] = []
            for tier_key in ("peer_competitors", "downstream_buyers"):
                for company in market_payload.get(tier_key, {}).get("companies", []):
                    name = ""
                    if isinstance(company, dict):
                        name = str(company.get("name") or "").strip()
                    elif isinstance(company, str):
                        name = company.strip()
                    if name and name not in {"n/v", "n/a"} and name not in buyer_candidates:
                        buyer_candidates.append(name)
            if buyer_candidates:
                current_section = {**current_section, "buyer_candidates": buyer_candidates}

        department_runtime = agents["departments"][department_name]
        t0 = perf_counter()
        section_payload, department_messages, package = department_runtime.run(
            brief=brief,
            assignments=runnable,
            current_section=current_section,
            memory_store=run_context.short_term_memory,
            role_memory=run_context.retrieved_role_strategies,
            on_message=on_message,
        )
        elapsed = round(perf_counter() - t0, 3)
        department_timings[department_name] = elapsed
        logging.info("Department %s completed in %.3fs", department_name, elapsed)
        messages.extend(department_messages)

        acceptance = agents["supervisor"].accept_department_package(
            department=department_name,
            package=package,
        )
        _apply_acceptance_gate(
            acceptance,
            dept_name=department_name,
            target_section=department_assignment.target_section,
            section_payload=section_payload,
            package=package,
            sections=sections,
            department_packages=department_packages,
        )
        messages.append(
            emit_message(
                on_message,
                agent="Supervisor",
                content=json.dumps(
                    {
                        "department": department_name,
                        "status": "department_package_reviewed",
                        **acceptance,
                    },
                    ensure_ascii=False,
                ),
            )
        )

        status_by_task = {task["task_key"]: task["status"] for task in package.get("completed_tasks", [])}
        for assignment in department_assignment.assignments:
            task_status = status_by_task.get(assignment.task_key, "degraded")
            run_context.update_task_status(task_key=assignment.task_key, status=task_status)
            run_context.short_term_memory.task_statuses[assignment.task_key] = task_status
            completed_backlog.append(
                {
                    "task_key": assignment.task_key,
                    "label": assignment.label,
                    "target_section": assignment.target_section,
                    "status": task_status,
                }
            )

        # Token budget enforcement
        snapshot = run_context.short_term_memory.snapshot()
        totals = snapshot.get("usage_totals", {})
        total_tokens = int(totals.get("total_tokens", 0) or 0)
        if total_tokens >= HARD_TOKEN_CAP:
            logging.warning(
                "HARD token cap reached (%d >= %d) after %s — aborting remaining departments.",
                total_tokens, HARD_TOKEN_CAP, department_name,
            )
            break
        if total_tokens >= SOFT_TOKEN_BUDGET:
            logging.warning(
                "Soft token budget exceeded (%d >= %d) after %s — continuing but budget is tight.",
                total_tokens, SOFT_TOKEN_BUDGET, department_name,
            )

    # Strategic Synthesis Department — AG2 GroupChat
    synthesis_assignments = build_synthesis_assignments(brief)
    for assignment in synthesis_assignments:
        run_context.record_task(
            assignee=assignment.assignee,
            objective=assignment.objective,
            section=assignment.target_section,
            task_key=assignment.task_key,
            model_name=assignment.model_name,
            allowed_tools=assignment.allowed_tools,
            status="pending_synthesis",
        )

    if "synthesis" in agents:
        messages.append(
            emit_message(
                on_message,
                agent="Supervisor",
                content=json.dumps(
                    {"status": "synthesis_assigned", "department": "SynthesisDepartment"},
                    ensure_ascii=False,
                ),
            )
        )
        # Build synthesis context as structured input for the AG2 GroupChat
        quality_review = build_quality_review(run_context.short_term_memory.snapshot())
        synthesis_ctx = build_synthesis_context(
            company_profile=sections.get("company_profile", {}),
            industry_analysis=sections.get("industry_analysis", {}),
            market_network=sections.get("market_network", {}),
            contact_intelligence=sections.get("contact_intelligence", {}),
            quality_review=quality_review,
            memory_snapshot=run_context.short_term_memory.snapshot(),
        )
        synthesis_result, synthesis_messages = agents["synthesis"].run(
            brief=brief,
            department_packages=_admitted_packages_for_synthesis(department_packages),
            supervisor=agents["supervisor"],
            departments=agents["departments"],
            memory_store=run_context.short_term_memory,
            on_message=on_message,
            synthesis_context=synthesis_ctx,
        )
        messages.extend(synthesis_messages)

        # F3: Synthesis acceptance gate — no more auto-accept.
        # Gate reads generation_mode as an execution fact, does not set it.
        synthesis_acceptance = agents["supervisor"].accept_synthesis(
            synthesis_payload=synthesis_result,
        )
        synthesis_decision = synthesis_acceptance.get("decision", "rejected")

        # RF2-1: Synthesis envelope uses canonical keys (raw_package / admitted_payload)
        # identical to department envelopes — one shape for all.
        synthesis_envelope: dict[str, Any] = {
            "admission": {
                "decision": synthesis_decision,
                "reason": synthesis_acceptance.get("reason", ""),
                "downstream_visible": synthesis_decision != "rejected",
            },
            "raw_package": synthesis_result,
        }
        if synthesis_decision != "rejected":
            synthesis_envelope["admitted_payload"] = synthesis_result
        else:
            synthesis_envelope["admitted_payload"] = None

        department_packages["SynthesisDepartment"] = synthesis_envelope
        sections["synthesis"] = synthesis_result

        messages.append(
            emit_message(
                on_message,
                agent="Supervisor",
                content=json.dumps(
                    {"department": "SynthesisDepartment", "status": "synthesis_reviewed", **synthesis_acceptance},
                    ensure_ascii=False,
                ),
            )
        )

        _SYNTHESIS_DECISION_TO_STATUS = {
            "accepted": "accepted",
            "accepted_with_gaps": "degraded",
            "rejected": "degraded",
        }
        synthesis_task_status = _SYNTHESIS_DECISION_TO_STATUS.get(synthesis_decision, "degraded")

        for assignment in synthesis_assignments:
            run_context.update_task_status(task_key=assignment.task_key, status=synthesis_task_status)
            run_context.short_term_memory.task_statuses[assignment.task_key] = synthesis_task_status
            completed_backlog.append(
                {
                    "task_key": assignment.task_key,
                    "label": assignment.label,
                    "target_section": assignment.target_section,
                    "status": synthesis_task_status,
                }
            )

    # Observability: department timing summary
    timing_summary = ", ".join(
        f"{dept}={elapsed:.3f}s" for dept, elapsed in department_timings.items()
    )
    logging.info("Department timings: %s", timing_summary or "none")

    return SupervisorLoopResult(sections, department_packages, messages, completed_backlog, department_timings)
