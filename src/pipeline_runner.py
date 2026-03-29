"""Public runner for the supervisor-centric department architecture."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from src.agents.specs import AGENT_SPECS
from src.agents.runtime_factory import create_runtime_agents
from src.app.use_cases import (
    BLOCKED_RUN_STATUS,
    SELECTION_REQUIRED_RUN_STATUS,
    build_dashboard_state,
    build_resolution_plan,
    determine_final_status,
)
from src.config import summarize_worker_report_costs
from src.domain.intake import IntakeRequest
from src.exporters.json_export import export_run
from src.memory.consolidation import RETRIEVABLE_ROLE_ORDER, consolidate_role_patterns
from src.memory.long_term_store import FileLongTermMemoryStore
from src.memory.policies import should_store_strategy
from src.memory.retrieval import retrieve_strategies
from src.models.meeting_ready import ResolutionPlan
from src.models.registry import assemble_section
from src.models.schemas import empty_pipeline_data, validate_pipeline_data
from src.orchestration.envelope import resolve_admission
from src.orchestration.follow_up import run_bounded_follow_up
from src.orchestration.meeting_readiness import FinalBriefingComposer, MeetingReadinessGate
from src.orchestration.runtime_guardrails import PhaseBudgetTracker, sort_meeting_actions
from src.orchestration.meeting_questions import build_initial_answer_matrix, build_question_registry
from src.orchestration.run_context import RunContext
from src.orchestration.supervisor_loop import emit_message, run_supervisor_loop
from src.orchestration.synthesis import (
    assess_research_readiness,
    build_quality_review,
    build_report_package,
    build_synthesis_context,
)
from src.research.normalize import normalize_domain


ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "artifacts" / "runs"
LONG_TERM_MEMORY_PATH = ROOT / "artifacts" / "memory" / "long_term_memory.json"


def _write_checkpoint(run_dir: Path, phase: str, run_context: "RunContext") -> None:
    """RA-07: Write a phase-aware checkpoint for crash recovery and observability."""
    cp_dir = run_dir / "checkpoints"
    cp_dir.mkdir(parents=True, exist_ok=True)
    payload = {"phase": phase, "status": run_context.status, **run_context.snapshot()}
    (cp_dir / f"{phase}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8",
    )

AGENT_META = {
    name: {"icon": spec.icon, "color": spec.color, "summary": spec.summary}
    for name, spec in AGENT_SPECS.items()
}

PIPELINE_STEPS = [
    ("Supervisor", "Intake + Routing"),
    ("CompanyDepartment", "Company"),
    ("MarketDepartment", "Market"),
    ("BuyerDepartment", "Buyer"),
    ("ContactDepartment", "Contact Intelligence"),
    ("SynthesisDepartment", "Strategic Synthesis"),
    ("ReportWriter", "Report"),
]

MessageHook = Callable[[dict[str, Any]], None] | None


def _timestamp_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _serialize_message_content(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _extract_pipeline_data(messages: list[dict[str, Any]]) -> dict[str, Any]:
    pipeline_data = empty_pipeline_data()
    for message in messages:
        content = _serialize_message_content(message)
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        section = payload.get("section")
        if section in {"company_profile", "industry_analysis", "market_network"} and "payload" in payload:
            pipeline_data[section] = payload["payload"]
        if section == "quality_review" and "payload" in payload:
            pipeline_data["quality_review"] = payload["payload"]
        if section == "synthesis" and "payload" in payload:
            pipeline_data["synthesis"] = payload["payload"]
    return validate_pipeline_data(pipeline_data)


def resume_pipeline(
    *,
    run_id: str,
    user_selections: dict[str, Any],
    on_message: MessageHook = None,
) -> dict[str, Any]:
    """Resume a paused run after user depth selections.

    Loads the persisted run state, applies user decisions to the resolution
    plan and answer matrix, then re-evaluates the finalization gate.
    """
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Run '{run_id}' not found.")

    run_context = RunContext.from_snapshot(
        json.loads((run_dir / "run_context.json").read_text(encoding="utf-8"))
    )
    pipeline_data = json.loads((run_dir / "pipeline_data.json").read_text(encoding="utf-8"))

    if run_context.status != SELECTION_REQUIRED_RUN_STATUS:
        return {
            "run_id": run_id,
            "status": run_context.status,
            "error": f"Run is not paused for user selection (status={run_context.status}).",
        }

    # Apply user depth selections to answer matrix
    selected_questions = list(user_selections.get("selected_questions", []))
    skipped_questions = list(user_selections.get("skipped_questions", []))

    for qid in selected_questions:
        entry = run_context.answer_matrix.get(qid)
        if entry:
            entry["status"] = "partially_answered"
            entry["notes"] = "User selected for optional depth."

    for qid in skipped_questions:
        entry = run_context.answer_matrix.get(qid)
        if entry:
            entry["status"] = "blocked"
            entry["notes"] = "User skipped optional depth."

    # Persist user selections in resolution state
    run_context.resolution_state["user_selections"] = {
        "selected_questions": selected_questions,
        "skipped_questions": skipped_questions,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    dashboard = run_context.resolution_state.get("dashboard_state", {})
    dashboard["pending_user_selection"] = False
    dashboard["resume_entrypoint"] = "supervisor_finalization_entrypoint"
    run_context.resolution_state["dashboard_state"] = dashboard
    run_context.resolution_state["resume_entrypoint"] = "supervisor_finalization_entrypoint"

    # Re-evaluate finalization gate — user resolved the selection requirement,
    # so override the bucket to prevent re-triggering needs_user_selection.
    first_round_resolution = dict(run_context.resolution_state.get("first_round_resolution", {}))
    first_round_resolution["bucket"] = "NOT_MEETING_CRITICAL"  # user decision applied
    run_context.resolution_state["first_round_resolution"] = first_round_resolution
    readiness = pipeline_data.get("research_readiness", {})
    status = determine_final_status(
        readiness_usable=bool(readiness.get("usable")),
        first_round_resolution=first_round_resolution,
        remaining_public_gaps=[],  # user resolved the selection requirement
    )
    run_context.status = status

    # RA-07: Checkpoint after dashboard resume
    _write_checkpoint(run_dir, "after_dashboard_resume", run_context)

    # Re-export
    run_context_snapshot = run_context.snapshot()
    export_run(
        run_dir=run_dir,
        run_id=run_id,
        company_name=run_context.intake.get("company_name", ""),
        web_domain=run_context.intake.get("web_domain", ""),
        status=status,
        messages=[],
        pipeline_data=pipeline_data,
        run_context=run_context_snapshot,
    )

    if on_message:
        on_message({
            "agent": "Supervisor",
            "content": json.dumps({
                "status": "resumed_after_user_selection",
                "final_status": status,
                "selected_questions": selected_questions,
                "skipped_questions": skipped_questions,
            }, ensure_ascii=False),
            "type": "agent_message",
        })

    return {
        "run_id": run_id,
        "status": status,
        "run_context": run_context_snapshot,
        "pipeline_data": pipeline_data,
        "error": None,
    }


def run_pipeline(
    *,
    company_name: str,
    web_domain: str,
    on_message: MessageHook = None,
) -> dict[str, Any]:
    start_time = perf_counter()
    run_id = _timestamp_run_id()
    run_dir = RUNS_DIR / run_id
    intake = IntakeRequest(company_name=company_name, web_domain=web_domain)
    agents = create_runtime_agents()

    memory_store = FileLongTermMemoryStore(LONG_TERM_MEMORY_PATH)
    run_context = RunContext(
        run_id=run_id,
        intake={"company_name": company_name, "web_domain": web_domain, "language": intake.language},
    )
    run_context.retrieved_strategies = retrieve_strategies(
        memory_store,
        domain=normalize_domain(web_domain),
        limit=5,
    )
    run_context.retrieved_role_strategies = {
        role: retrieve_strategies(
            memory_store,
            domain=normalize_domain(web_domain),
            role=role,
            limit=3,
        )
        for role in RETRIEVABLE_ROLE_ORDER
    }

    messages: list[dict[str, Any]] = []
    budget_tracker = PhaseBudgetTracker()
    try:
        brief, supervisor_message = agents["supervisor"].build_intake_brief(intake)
        run_context.supervisor_brief = supervisor_message["payload"]
        run_context.question_registry = build_question_registry()
        run_context.answer_matrix = build_initial_answer_matrix()
        messages.append(
            emit_message(
                on_message,
                agent="Supervisor",
                content=json.dumps(supervisor_message, ensure_ascii=False),
            )
        )

        sections, department_packages, loop_messages, completed_backlog, department_timings, first_round_resolution = run_supervisor_loop(
            brief=brief,
            run_context=run_context,
            agents=agents,
            on_message=on_message,
        )
        messages.extend(loop_messages)
        run_context.short_term_memory.task_statuses.update(
            {item["task_key"]: item["status"] for item in completed_backlog}
        )
        # RA-08: Record first-pass token consumption
        first_pass_snapshot = run_context.short_term_memory.snapshot()
        first_pass_tokens = int(first_pass_snapshot.get("usage_totals", {}).get("total_tokens", 0) or 0)
        budget_tracker.record_phase_tokens("first_pass", first_pass_tokens)
        if not budget_tracker.check_budget("first_pass"):
            budget_tracker.record_stop("first_pass", "token_budget_exceeded")

        run_context.resolution_state = {
            "first_round_resolution": first_round_resolution,
            "auto_close": {
                "triggered": False,
                "max_questions": 4,
                "attempted_questions": 0,
                "stop_reason": "not_required",
                "remaining_public_gaps": [],
            },
        }

        # RA-07: Checkpoint after first pass
        _write_checkpoint(run_dir, "after_first_pass", run_context)

        if first_round_resolution.get("bucket") == "AUTO_CLOSE_REQUIRED":
            auto_close_result = run_bounded_follow_up(
                run_id=run_id,
                run_context=run_context.snapshot(),
                pipeline_data={
                    "company_profile": sections.get("company_profile", {}),
                    "industry_analysis": sections.get("industry_analysis", {}),
                    "market_network": sections.get("market_network", {}),
                    "contact_intelligence": sections.get("contact_intelligence", {}),
                    "synthesis": sections.get("synthesis", {}),
                    "quality_review": {},
                },
                public_gap_questions=first_round_resolution.get("meeting_critical_public_gaps", []),
                max_questions=4,
            )
            run_context.resolution_state["auto_close"] = {
                "triggered": True,
                **auto_close_result,
            }
            # RA-04: Feed closure results back into answer matrix
            for attempt in auto_close_result.get("attempts", []):
                if attempt.get("resolved"):
                    for qid, entry in run_context.answer_matrix.items():
                        if entry.get("status") in {"pending", "blocked"}:
                            # Mark as partially answered by closure
                            entry["status"] = "partially_answered"
                            entry["notes"] = f"Auto-close follow-up resolved: {attempt.get('question', '')[:80]}"
            messages.append(
                emit_message(
                    on_message,
                    agent="Supervisor",
                    content=json.dumps(
                        {
                            "status": "auto_close_follow_up_completed",
                            **auto_close_result,
                        },
                        ensure_ascii=False,
                    ),
                )
            )

        # RA-08: Record closure token consumption
            closure_tokens = int(
                run_context.short_term_memory.snapshot()
                .get("usage_totals", {}).get("total_tokens", 0) or 0
            ) - first_pass_tokens
            budget_tracker.record_phase_tokens("closure", max(closure_tokens, 0))

            # RA-07: Checkpoint after closure
            _write_checkpoint(run_dir, "after_closure", run_context)

        # Quality review still derived from memory snapshot
        quality_review = build_quality_review(run_context.short_term_memory.snapshot())
        messages.append(
            emit_message(
                on_message,
                agent="SynthesisDepartment",
                content=json.dumps({"section": "quality_review", "payload": quality_review}, ensure_ascii=False),
            )
        )

        # Synthesis admission — read from canonical envelope (P0-3).
        synthesis_envelope = department_packages.get("SynthesisDepartment", {})
        synthesis_admission_info = resolve_admission(synthesis_envelope)
        synthesis_admission = synthesis_admission_info.get("decision", "rejected")
        ag2_synthesis = sections.get("synthesis", {})
        evidence_health = quality_review.get("evidence_health", "low")

        if synthesis_admission == "accepted":
            synthesis = {
                **ag2_synthesis,
                "generation_mode": ag2_synthesis.get("generation_mode", "normal"),
                "confidence": evidence_health,
            }
        elif synthesis_admission == "accepted_with_gaps":
            # Gate already decided this is downstream-usable but degraded.
            # Use the AG2 output as-is; generation_mode is an execution fact.
            synthesis = {
                **ag2_synthesis,
                "generation_mode": ag2_synthesis.get("generation_mode", "fallback"),
                "confidence": evidence_health,
            }
        else:
            # rejected or missing — blocked artifact, not a fallback synthesis.
            # A presentation fallback for UI/Report is built separately;
            # the machine-facing record is a typed blocked artifact.
            synthesis = {
                "section_status": "blocked",
                "reason": synthesis_admission,
                "target_company": ag2_synthesis.get("target_company", "n/v"),
                "executive_summary": "Synthesis was not accepted by the Supervisor gate.",
                "generation_mode": "blocked",
                "confidence": "low",
                "key_risks": ["Synthesis did not pass the quality gate."],
                "next_steps": ["Re-run with improved department evidence."],
                "sources": [],
            }

        readiness = assess_research_readiness(
            company_profile=sections.get("company_profile", {}),
            industry_analysis=sections.get("industry_analysis", {}),
            market_network=sections.get("market_network", {}),
            contact_intelligence=sections.get("contact_intelligence", {}),
            quality_review=quality_review,
        )
        pipeline_data = validate_pipeline_data(
            {
                "company_profile": assemble_section("company_profile", sections.get("company_profile", {})),
                "industry_analysis": assemble_section("industry_analysis", sections.get("industry_analysis", {})),
                "market_network": assemble_section("market_network", sections.get("market_network", {})),
                "contact_intelligence": assemble_section("contact_intelligence", sections.get("contact_intelligence", {})),
                "quality_review": quality_review,
                "synthesis": synthesis,
                "research_readiness": readiness,
                "validation_errors": [],
            }
        )

        remaining_public_gaps = run_context.resolution_state.get("auto_close", {}).get("remaining_public_gaps", [])
        resolution_plan = build_resolution_plan(
            run_id=run_id,
            first_round_resolution=first_round_resolution,
            remaining_public_gaps=list(remaining_public_gaps),
        )
        run_context.short_term_memory.resolution_plans.append(ResolutionPlan.model_validate(resolution_plan))
        run_context.resolution_state["resolution_plan"] = resolution_plan

        report_package = build_report_package(
            pipeline_data=pipeline_data,
            department_packages=department_packages,
        )
        run_context.report_package = report_package
        messages.append(
            emit_message(
                on_message,
                agent="ReportWriter",
                content=json.dumps({"section": "report_package", "payload": report_package}, ensure_ascii=False),
            )
        )

        # RA-06: Meeting-readiness gate — enforced before finalization
        readiness_gate = MeetingReadinessGate()
        meeting_assessment = readiness_gate.evaluate(
            answer_matrix=run_context.answer_matrix,
            resolution_state=run_context.resolution_state,
            evidence_health=quality_review.get("evidence_health", "low"),
            readiness_usable=bool(readiness.get("usable")),
        )
        run_context.meeting_readiness_assessment = meeting_assessment

        # RA-06: Final briefing composer — meeting_actions replace next_steps
        composer = FinalBriefingComposer()
        meeting_actions = composer.compose(
            synthesis=synthesis,
            answer_matrix=run_context.answer_matrix,
            quality_review=quality_review,
            resolution_state=run_context.resolution_state,
            company_name=company_name,
        )
        run_context.short_term_memory.meeting_actions = meeting_actions

        # RA-08: Deterministic ordering for meeting actions
        sorted_action_dicts = sort_meeting_actions(
            [a.model_dump(mode="json") for a in meeting_actions]
        )

        # Inject meeting_actions into pipeline_data for PDF/export access
        pipeline_data["meeting_actions"] = sorted_action_dicts

        status = determine_final_status(
            readiness_usable=bool(readiness.get("usable")),
            first_round_resolution=first_round_resolution,
            remaining_public_gaps=list(remaining_public_gaps),
        )
        resume_entrypoint = (
            "supervisor_resume_after_user_selection"
            if status == SELECTION_REQUIRED_RUN_STATUS
            else "supervisor_finalization_entrypoint"
        )
        run_context.resolution_state["dashboard_state"] = build_dashboard_state(
            status=status,
            run_id=run_id,
            resolution_plan=resolution_plan,
            resume_entrypoint=resume_entrypoint,
        )
        run_context.resolution_state["resume_entrypoint"] = resume_entrypoint
        if status == BLOCKED_RUN_STATUS:
            run_context.resolution_state["finalization_blocked"] = {
                "reason": "meeting_critical_public_gaps_open" if remaining_public_gaps else "meeting_not_ready",
                "open_gaps": list(remaining_public_gaps),
            }
        run_context.status = status

        # RA-08: Persist budget tracker and guardrail telemetry
        run_context.resolution_state["budget_tracker"] = budget_tracker.snapshot()

        # RA-07: Checkpoint after finalization gate
        _write_checkpoint(run_dir, "after_finalization", run_context)

        elapsed_seconds = round(perf_counter() - start_time, 3)
        memory_snapshot = run_context.short_term_memory.snapshot()
        usage = summarize_worker_report_costs(memory_snapshot.get("worker_reports", []))
        usage_total = usage.get("total", {})
        usage_totals = memory_snapshot.get("usage_totals", {})
        budget = {
            "total_pipeline_events": len(messages),
            "tool_calls_used": int(
                (usage_totals.get("search_calls", 0) or 0)
                + (usage_totals.get("page_fetches", 0) or 0)
                + (usage_totals.get("llm_calls", 0) or 0)
            ),
            "max_tool_calls": 140,
            "max_department_attempts": 3,
            "resume_entrypoint": resume_entrypoint,
            "llm_calls_used": int(usage_totals.get("llm_calls", 0) or 0),
            "search_calls_used": int(usage_totals.get("search_calls", 0) or 0),
            "page_fetches_used": int(usage_totals.get("page_fetches", 0) or 0),
            "estimated_cost_usd": float(usage_total.get("total_cost", 0.0) or 0.0),
            "elapsed_seconds": elapsed_seconds,
            "department_timings": department_timings,
        }
        run_context_snapshot = run_context.snapshot()

        role_patterns = consolidate_role_patterns(
            run_context=run_context_snapshot,
            pipeline_data=pipeline_data,
            status=status,
            usable=readiness["usable"],
        )
        if role_patterns and should_store_strategy(
            status=status,
            usable=readiness["usable"],
            readiness_score=readiness.get("score", 0),
            task_statuses=dict(run_context.short_term_memory.task_statuses),
        ):
            for pattern in role_patterns:
                memory_store.upsert_strategy(pattern)

        export_run(
            run_dir=run_dir,
            run_id=run_id,
            company_name=company_name,
            web_domain=web_domain,
            status=status,
            messages=messages,
            pipeline_data=pipeline_data,
            run_context=run_context_snapshot,
            usage=usage,
            budget=budget,
        )
        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "messages": messages,
            "pipeline_data": pipeline_data,
            "run_context": run_context_snapshot,
            "usage": usage,
            "budget": budget,
            "status": status,
            "error": None,
        }
    except Exception as exc:
        error_message = str(exc)
        run_context.status = "failed"
        elapsed_seconds = round(perf_counter() - start_time, 3)
        export_run(
            run_dir=run_dir,
            run_id=run_id,
            company_name=company_name,
            web_domain=web_domain,
            status="failed",
            messages=messages,
            pipeline_data=empty_pipeline_data(),
            run_context=run_context.snapshot(),
            budget={"elapsed_seconds": elapsed_seconds},
            error=error_message,
        )
        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "messages": messages,
            "pipeline_data": empty_pipeline_data(),
            "run_context": run_context.snapshot(),
            "usage": {},
            "budget": {"elapsed_seconds": elapsed_seconds},
            "status": "failed",
            "error": error_message,
        }
