"""Core supervisor loop."""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter
from typing import Any, Callable

from src.config.settings import SOFT_TOKEN_BUDGET, HARD_TOKEN_CAP
from src.domain.intake import SupervisorBrief
from src.orchestration.task_router import (
    DEPARTMENT_RESEARCHERS,
    build_department_assignments,
    build_initial_assignments,
    build_synthesis_assignments,
    evaluate_run_conditions,
)
from src.orchestration.synthesis import build_synthesis_context, build_quality_review


MessageHook = Callable[[dict[str, Any]], None] | None

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
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
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

    def _run_single_department(dept_name, dept_assignment, current_sec):
        """Execute one department and return its results with timing."""
        t0 = perf_counter()
        runtime = agents["departments"][dept_name]
        result = runtime.run(
            brief=brief,
            assignments=list(dept_assignment.assignments),
            current_section=current_sec,
            memory_store=run_context.short_term_memory,
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
                futures[pool.submit(_run_single_department, dept_name, da, current_section)] = dept_name

            for future in as_completed(futures):
                dept_name = futures[future]
                da = dept_assignment_map[dept_name]
                section_payload, department_messages, package = future.result()
                messages.extend(department_messages)
                department_packages[dept_name] = package
                sections[da.target_section] = section_payload

                acceptance = agents["supervisor"].accept_department_package(department=dept_name, package=package)
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
    else:
        # Fallback: run parallel_jobs sequentially if only one
        for dept_name in parallel_jobs:
            da = dept_assignment_map[dept_name]
            messages.append(
                emit_message(on_message, agent="Supervisor", content=json.dumps({"department": da.department, "status": "department_assigned", "target_section": da.target_section, "tasks": [{"task_key": a.task_key, "label": a.label, "objective": a.objective} for a in da.assignments]}, ensure_ascii=False))
            )
            section_payload, department_messages, package = _run_single_department(dept_name, da, sections.get(da.target_section, {}))
            messages.extend(department_messages)
            department_packages[dept_name] = package
            sections[da.target_section] = section_payload
            acceptance = agents["supervisor"].accept_department_package(department=dept_name, package=package)
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
        department_packages[department_name] = package
        sections[department_assignment.target_section] = section_payload

        acceptance = agents["supervisor"].accept_department_package(
            department=department_name,
            package=package,
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
            department_packages=department_packages,
            supervisor=agents["supervisor"],
            departments=agents["departments"],
            memory_store=run_context.short_term_memory,
            on_message=on_message,
            synthesis_context=synthesis_ctx,
        )
        messages.extend(synthesis_messages)
        department_packages["SynthesisDepartment"] = synthesis_result
        sections["synthesis"] = synthesis_result

        for assignment in synthesis_assignments:
            run_context.update_task_status(task_key=assignment.task_key, status="accepted")
            run_context.short_term_memory.task_statuses[assignment.task_key] = "accepted"
            completed_backlog.append(
                {
                    "task_key": assignment.task_key,
                    "label": assignment.label,
                    "target_section": assignment.target_section,
                    "status": "accepted",
                }
            )

    # Observability: department timing summary
    timing_summary = ", ".join(
        f"{dept}={elapsed:.3f}s" for dept, elapsed in department_timings.items()
    )
    logging.info("Department timings: %s", timing_summary or "none")

    return sections, department_packages, messages, completed_backlog, department_timings
