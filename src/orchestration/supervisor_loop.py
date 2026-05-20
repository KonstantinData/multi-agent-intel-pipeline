"""Core supervisor loop."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, NamedTuple

from src.config.settings import HARD_TOKEN_CAP, SOFT_TOKEN_BUDGET
from src.domain.intake import SupervisorBrief
from src.memory.short_term_store import ShortTermMemoryStore
from src.models.meeting_ready import AnswerMatrixUpdate, EvidencePacket, GapCandidate
from src.models.schemas import BlockedArtifact
from src.orchestration.meeting_questions import (
    build_initial_answer_matrix,
    build_question_registry,
    matrix_status_for_task_status,
)
from src.orchestration.resolution_controller import ResolutionController
from src.orchestration.step1_handoff import RUNTIME_EVENT_SCHEMA_VERSION
from src.orchestration.task_router import (
    build_department_assignments,
    build_initial_assignments,
    evaluate_run_conditions,
)

MessageHook = Callable[[dict[str, Any]], None] | None


class SupervisorLoopResult(NamedTuple):
    """F10: Typed return value for run_supervisor_loop."""
    sections: dict[str, Any]
    department_packages: dict[str, Any]
    messages: list[dict[str, Any]]
    completed_backlog: list[dict[str, str]]
    department_timings: dict[str, float]
    first_round_resolution: dict[str, Any]


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


def _apply_structured_runtime_artifacts(run_context, package: dict[str, Any]) -> None:
    """Consume structured artifacts as runtime state (not narrative-only fields)."""
    updates = [
        AnswerMatrixUpdate.model_validate(item)
        for item in package.get("answer_matrix_updates", [])
    ]
    for update in updates:
        run_context.short_term_memory.answer_matrix_updates.append(update)
        matrix_entry = run_context.answer_matrix.setdefault(
            update.field_key,
            {
                "status": "pending",
                "answer": "",
                "notes": "",
                "source_tasks": [],
                "target_section": "n/v",
            },
        )
        matrix_entry["status"] = update.status
        matrix_entry["answer"] = update.answer
        matrix_entry["notes"] = update.notes
        source_tasks = matrix_entry.setdefault("source_tasks", [])
        for packet_id in update.evidence_packet_ids:
            if packet_id not in source_tasks:
                source_tasks.append(packet_id)

    gaps = [
        GapCandidate.model_validate(item)
        for item in package.get("gap_candidates", [])
    ]
    run_context.short_term_memory.gap_candidates.extend(gaps)
    packets = [
        EvidencePacket.model_validate(item)
        for item in package.get("evidence_packages", [])
    ]
    run_context.short_term_memory.evidence_packets.extend(packets)


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
    run_id: str = "",
    sequence: int = 0,
    phase: str = "",
    content_type: str = "application/json",
) -> dict[str, Any]:
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    event_sequence = int(sequence or 0)
    event = {
        "event_id": f"{run_id or 'runtime'}:{event_sequence:06d}:{phase or message_type}",
        "run_id": run_id,
        "sequence": event_sequence,
        "timestamp": timestamp,
        "agent": agent,
        "content": content,
        "content_type": content_type,
        "phase": phase,
        "schema_version": RUNTIME_EVENT_SCHEMA_VERSION,
        "type": message_type,
    }
    if on_message:
        on_message(event)
    return event


def run_supervisor_loop(
    *,
    brief: SupervisorBrief,
    run_context,
    agents: dict[str, Any],
    on_message: MessageHook = None,
    step_emitter: Any | None = None,
) -> SupervisorLoopResult:
    if not run_context.question_registry:
        run_context.question_registry = build_question_registry()
    if not run_context.answer_matrix:
        run_context.answer_matrix = build_initial_answer_matrix()

    sections: dict[str, Any] = {}
    department_packages: dict[str, Any] = {}
    messages: list[dict[str, Any]] = []
    assignments = build_initial_assignments(brief)
    department_assignments = build_department_assignments(brief)
    completed_backlog: list[dict[str, str]] = []
    department_timings: dict[str, float] = {}

    def _emit_department_assignment_step(dept_name: str, dept_assignment) -> None:
        if step_emitter is None:
            return
        step_emitter.emit_narrated(
            phase="first_pass",
            actor="Supervisor",
            actor_role="supervisor",
            department=dept_name,
            goal=f"Assign tasks to {dept_name}",
            action_kind="state_transition",
            action_target="department.assign",
            action_payload={
                "department": dept_name,
                "target_section": dept_assignment.target_section,
                "task_keys": [a.task_key for a in dept_assignment.assignments],
            },
            state_transitions=[
                {
                    "kind": "department_assigned",
                    "department": dept_name,
                    "task_count": len(dept_assignment.assignments),
                }
            ],
            decision="assigned",
            reflection=f"{dept_name} assigned {len(dept_assignment.assignments)} task(s).",
            stop_reason="department_assigned",
        )

    def _emit_package_admission_step(dept_name: str, acceptance: dict[str, Any]) -> None:
        if step_emitter is None:
            return
        decision = str(acceptance.get("decision", "rejected"))
        step_emitter.emit_narrated(
            phase="first_pass",
            actor="Supervisor",
            actor_role="supervisor",
            department=dept_name,
            goal=f"Review package admission for {dept_name}",
            action_kind="state_transition",
            action_target="department_package.admit",
            action_payload={
                "department": dept_name,
                "decision": decision,
                "accepted_tasks": acceptance.get("accepted_tasks", 0),
                "total_tasks": acceptance.get("total_tasks", 0),
                "policy_gate_passed": acceptance.get("policy_gate_passed", False),
            },
            state_transitions=[
                {
                    "kind": "department_package_admission",
                    "department": dept_name,
                    "decision": decision,
                }
            ],
            decision=decision,
            reflection=f"{dept_name} package admission decision: {decision}.",
            stop_reason="department_package_reviewed",
        )

    def _update_answer_matrix_from_task(assignment, task_status: str) -> None:
        matrix_status = matrix_status_for_task_status(task_status)
        for question_id in assignment.question_ids:
            entry = run_context.answer_matrix.setdefault(
                question_id,
                {
                    "status": "pending",
                    "answer": "",
                    "notes": "",
                    "source_tasks": [],
                    "target_section": assignment.target_section,
                },
            )
            if assignment.task_key not in entry["source_tasks"]:
                entry["source_tasks"].append(assignment.task_key)
            entry["status"] = matrix_status
            entry["notes"] = (
                f"Last update from task '{assignment.task_key}' "
                f"({task_status}) in department '{assignment.assignee}'."
            )

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

    def _run_single_department(dept_name, dept_assignment, current_sec, current_sections, memory_store):
        """Execute one department and return its results with timing."""
        t0 = perf_counter()
        runtime = agents["departments"][dept_name]
        result = runtime.run(
            brief=brief,
            assignments=list(dept_assignment.assignments),
            current_section=current_sec,
            current_sections=current_sections,
            memory_store=memory_store,
            role_memory=run_context.retrieved_role_strategies,
            on_message=on_message,
            step_emitter=step_emitter,
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
                _emit_department_assignment_step(dept_name, da)
                current_section = sections.get(da.target_section, {})
                ws = run_context.short_term_memory.create_working_set()
                baseline = run_context.short_term_memory.create_working_set()
                working_sets[dept_name] = ws
                baselines[dept_name] = baseline
                futures[pool.submit(_run_single_department, dept_name, da, current_section, dict(sections), ws)] = dept_name

            for future in as_completed(futures):
                dept_name = futures[future]
                da = dept_assignment_map[dept_name]
                section_payload, department_messages, package = future.result()
                messages.extend(department_messages)

                acceptance = agents["supervisor"].accept_department_package(department=dept_name, package=package)
                _apply_structured_runtime_artifacts(run_context, package)
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
                _emit_package_admission_step(dept_name, acceptance)
                status_by_task = {task["task_key"]: task["status"] for task in package.get("completed_tasks", [])}
                for assignment in da.assignments:
                    task_status = status_by_task.get(assignment.task_key, "degraded")
                    run_context.update_task_status(task_key=assignment.task_key, status=task_status)
                    run_context.short_term_memory.task_statuses[assignment.task_key] = task_status
                    _update_answer_matrix_from_task(assignment, task_status)
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
            _emit_department_assignment_step(dept_name, da)
            section_payload, department_messages, package = _run_single_department(
                dept_name,
                da,
                sections.get(da.target_section, {}),
                dict(sections),
                run_context.short_term_memory,
            )
            messages.extend(department_messages)
            acceptance = agents["supervisor"].accept_department_package(department=dept_name, package=package)
            _apply_structured_runtime_artifacts(run_context, package)
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
            _emit_package_admission_step(dept_name, acceptance)
            status_by_task = {task["task_key"]: task["status"] for task in package.get("completed_tasks", [])}
            for assignment in da.assignments:
                task_status = status_by_task.get(assignment.task_key, "degraded")
                run_context.update_task_status(task_key=assignment.task_key, status=task_status)
                run_context.short_term_memory.task_statuses[assignment.task_key] = task_status
                _update_answer_matrix_from_task(assignment, task_status)
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
        _emit_department_assignment_step(department_name, da)

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
            assignment = next((a for a in department_assignment.assignments if a.task_key == sk["task_key"]), None)
            if assignment:
                _update_answer_matrix_from_task(assignment, "skipped")

        if not runnable:
            # All tasks in this department were skipped
            continue

        # Enrich current_section with upstream data when available
        current_section = sections.get(department_assignment.target_section, {})
        if department_name == "ContactDepartment":
            market_payload = sections.get("market_network", {})
            # Extract real company names from typed company lists (peer + downstream)
            buyer_candidates: list[str] = []
            for tier_key in ("downstream_buyers", "service_providers", "cross_industry_buyers"):
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
            current_sections=dict(sections),
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
        _apply_structured_runtime_artifacts(run_context, package)
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
        _emit_package_admission_step(department_name, acceptance)

        status_by_task = {task["task_key"]: task["status"] for task in package.get("completed_tasks", [])}
        for assignment in department_assignment.assignments:
            task_status = status_by_task.get(assignment.task_key, "degraded")
            run_context.update_task_status(task_key=assignment.task_key, status=task_status)
            run_context.short_term_memory.task_statuses[assignment.task_key] = task_status
            _update_answer_matrix_from_task(assignment, task_status)
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

    controller = ResolutionController()
    first_round_resolution = controller.classify(
        sections=sections,
        department_packages=department_packages,
        answer_matrix=run_context.answer_matrix,
        task_statuses=dict(run_context.short_term_memory.task_statuses),
    )
    messages.append(
        emit_message(
            on_message,
            agent="Supervisor",
            content=json.dumps({"status": "first_round_resolution", **first_round_resolution}, ensure_ascii=False),
        )
    )

    # Strategic Synthesis Department is intentionally not run here.  The public
    # pipeline orchestrator runs it after first-round resolution and optional
    # auto-close so synthesis sees the final answer matrix for the domain round.

    # Observability: department timing summary
    timing_summary = ", ".join(
        f"{dept}={elapsed:.3f}s" for dept, elapsed in department_timings.items()
    )
    logging.info("Department timings: %s", timing_summary or "none")

    return SupervisorLoopResult(sections, department_packages, messages, completed_backlog, department_timings, first_round_resolution)
