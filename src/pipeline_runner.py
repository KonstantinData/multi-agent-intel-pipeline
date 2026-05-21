"""Public runner for the supervisor-centric department architecture."""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from src.agents.runtime_factory import create_runtime_agents
from src.app.use_cases import (
    BLOCKED_RUN_STATUS,
    DISCOVERY_READY_RUN_STATUS,
    SELECTION_REQUIRED_RUN_STATUS,
    SUCCESS_RUN_STATUS,
    build_dashboard_state,
    build_resolution_plan,
    determine_final_status,
)
from src.config import (
    estimate_cost_usd,
    estimate_web_search_preview_call_cost_usd,
    get_search_model,
    summarize_worker_report_costs,
)
from src.domain.intake import IntakeRequest, IntakeValidationError, SupervisorBrief
from src.exporters.json_export import export_run
from src.memory.consolidation import RETRIEVABLE_ROLE_ORDER, consolidate_role_patterns
from src.memory.policies import should_store_memory_pattern
from src.memory.retrieval import (
    DEFAULT_GENERAL_RETRIEVAL_LIMIT,
    DEFAULT_ROLE_RETRIEVAL_LIMIT,
    RetrievalContext,
    retrieve_strategy_batch,
)
from src.models.meeting_ready import FinalBriefing, MeetingAction, ResolutionPlan
from src.models.registry import assemble_section
from src.models.schemas import empty_pipeline_data, validate_pipeline_data
from src.orchestration.dashboard_composer import compose_dashboard
from src.orchestration.envelope import resolve_admission
from src.orchestration.factory_logging import log_factory_event
from src.orchestration.follow_up import run_bounded_follow_up
from src.orchestration.intake_logging import log_intake_event
from src.orchestration.meeting_questions import (
    build_initial_answer_matrix,
    build_question_registry,
    matrix_status_for_task_status,
)
from src.orchestration.meeting_readiness import FinalBriefingComposer, MeetingReadinessGate
from src.orchestration.otel_step_consumer import build_otel_step_consumer_from_env
from src.orchestration.run_context import RunContext
from src.orchestration.run_paths import RUNS_DIR, resolve_run_dir
from src.orchestration.runtime_agents import (
    RuntimeAgentFactoryError,
    RuntimeAgents,
)
from src.orchestration.runtime_guardrails import PhaseBudgetTracker, sort_meeting_actions
from src.orchestration.step1_handoff import (
    STEP1_BLOCKED,
    STEP1_HANDOFF_SCHEMA_VERSION,
    CheckpointInfo,
    build_step1_handoff,
    handoff_allows_department_routing,
    stable_json_hash,
)
from src.orchestration.step_bus import (
    InMemoryStepSink,
    StepBus,
    StepConsumer,
    StepEmitter,
    StepTraceConsumer,
    runtime_steps_enabled,
)
from src.orchestration.supervisor_logging import log_supervisor_brief_event
from src.orchestration.supervisor_loop import emit_message, run_supervisor_loop
from src.orchestration.synthesis import (
    assess_research_readiness,
    build_contact_briefing_assets,
    build_contact_enrichment_stage,
    build_playbook_assets,
    build_primary_source_stage,
    build_quality_review,
    build_synthesis_context,
    harmonize_synthesis_output,
)
from src.orchestration.synthesis_inputs import build_synthesis_input_packages
from src.orchestration.task_router import build_synthesis_assignments
from src.research.normalize import IntakeErrorCode, NormalizedDomainResult, normalize_domain_result
from src.research.ssrf_guard import SSRFBlockedError, resolve_and_validate_host
from src.storage.contracts import StorageHealthcheckError
from src.storage.run_artifacts import (
    load_latest_run_artifact_json,
    should_use_postgres_run_artifacts,
)
from src.storage.runtime_stores import create_runtime_stores

ROOT = Path(__file__).resolve().parent.parent
LONG_TERM_MEMORY_PATH = ROOT / "artifacts" / "memory" / "long_term_memory.json"


@dataclass(slots=True)
class InitialRunState:
    start_time: float
    run_id: str
    run_dir: Path
    intake: IntakeRequest
    agents: RuntimeAgents
    memory_store: Any
    run_state_store: Any
    run_context: RunContext
    messages: list[dict[str, Any]]
    budget_tracker: PhaseBudgetTracker
    step_emitter: StepEmitter
    step_eval_sink: InMemoryStepSink
    normalized_domain: str
    normalized_domain_result: NormalizedDomainResult


@dataclass(slots=True)
class SupervisorBriefResult:
    brief: SupervisorBrief
    supervisor_message: dict[str, Any]
    step1_handoff: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FirstPassResult:
    sections: dict[str, Any]
    department_packages: dict[str, Any]
    completed_backlog: list[dict[str, Any]]
    department_timings: dict[str, Any]
    first_round_resolution: dict[str, Any]
    first_pass_tokens: int


@dataclass(slots=True)
class AutoCloseResult:
    triggered: bool
    payload: dict[str, Any]


@dataclass(slots=True)
class SynthesisPhaseResult:
    sections: dict[str, Any]
    department_packages: dict[str, Any]
    completed_backlog: list[dict[str, Any]]
    department_timings: dict[str, Any]
    first_round_resolution: dict[str, Any]


@dataclass(slots=True)
class FinalizationResult:
    pipeline_data: dict[str, Any]
    readiness: dict[str, Any]
    status: str
    resume_entrypoint: str
    department_timings: dict[str, Any]
    department_packages: dict[str, Any]


def _next_checkpoint_sequence(run_context: RunContext) -> int:
    current = int(run_context.resolution_state.get("checkpoint_sequence", 0) or 0)
    sequence = current + 1
    run_context.resolution_state["checkpoint_sequence"] = sequence
    return sequence


def _write_checkpoint(
    run_dir: Path,
    phase: str,
    run_context: RunContext,
    *,
    run_id: str = "",
    run_state_store: Any | None = None,
    step_emitter: StepEmitter | None = None,
) -> dict[str, Any]:
    """RA-07: Write a phase-aware checkpoint for crash recovery and observability."""
    run_context.resolution_state["last_checkpoint"] = phase
    payload = {
        "schema_version": STEP1_HANDOFF_SCHEMA_VERSION,
        "phase": phase,
        "status": run_context.status,
        **run_context.snapshot(),
    }
    content_hash = stable_json_hash(payload)
    payload["checkpoint_hash"] = content_hash
    sequence = _next_checkpoint_sequence(run_context)

    if should_use_postgres_run_artifacts():
        path_text = f"postgres://run_checkpoints/{run_id or run_context.run_id}/{phase}/{sequence}"
    else:
        cp_dir = run_dir / "checkpoints"
        cp_dir.mkdir(parents=True, exist_ok=True)
        path = cp_dir / f"{phase}.json"
        tmp_path = cp_dir / f"{phase}.json.tmp"
        tmp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8",
        )
        tmp_path.replace(path)
        path_text = str(path)

    if run_state_store is not None and run_id:
        run_state_store.write_checkpoint(
            run_id=run_id,
            phase=phase,
            sequence=sequence,
            run_context_snapshot=payload,
        )
    checkpoint = CheckpointInfo(
        checkpoint_id=phase,
        phase=phase,
        path=path_text,
        content_hash=content_hash,
        written=True,
    ).as_dict()
    if step_emitter is not None:
        step_emitter.emit_narrated(
            phase=phase,
            actor="RuntimeCheckpoint",
            actor_role="runtime",
            goal=f"Write checkpoint {phase}",
            action_kind="state_transition",
            action_target="checkpoint.write",
            action_payload={
                "checkpoint_id": phase,
                "phase": phase,
                "sequence": sequence,
                "content_hash": content_hash,
            },
            state_transitions=[
                {
                    "kind": "checkpoint_write",
                    "checkpoint_id": phase,
                    "phase": phase,
                    "sequence": sequence,
                    "content_hash": content_hash,
                    "path": path_text,
                }
            ],
            decision="written",
            reflection=f"Checkpoint {phase} written.",
            stop_reason="checkpoint_written",
        )
    return checkpoint

MessageHook = Callable[[dict[str, Any]], None] | None


def _build_step_consumers(
    step_trace: list[dict[str, Any]],
    eval_sink: InMemoryStepSink,
) -> list[StepConsumer]:
    consumers: list[StepConsumer] = [
        StepTraceConsumer(step_trace),
        eval_sink,
    ]
    otel_consumer = build_otel_step_consumer_from_env()
    if otel_consumer is not None:
        consumers.append(otel_consumer)
    return consumers


def _build_run_usage_record(
    *,
    usage_totals: dict[str, Any],
    usage_total: dict[str, Any],
    search_model: str,
) -> dict[str, Any]:
    """Build ADR-002 usage metadata for the final export RuntimeStep."""

    search_calls = int(usage_totals.get("search_calls", 0) or 0)
    page_fetches = int(usage_totals.get("page_fetches", 0) or 0)
    llm_calls = int(usage_totals.get("llm_calls", 0) or 0)
    return {
        "provider": "openai",
        "model": search_model,
        "prompt_tokens": int(usage_totals.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(usage_totals.get("completion_tokens", 0) or 0),
        "total_tokens": int(usage_totals.get("total_tokens", 0) or 0),
        "thinking_tokens": 0,
        "cached_prompt_tokens": 0,
        "tool_calls": search_calls + page_fetches + llm_calls,
        "search_calls": search_calls,
        "page_fetches": page_fetches,
        "llm_calls": llm_calls,
        "retry_count": 0,
        "estimated_cost_usd": float(usage_total.get("total_cost", 0.0) or 0.0),
    }


def _report_writer_usage_record(report_package: dict[str, Any]) -> dict[str, Any] | None:
    validation = report_package.get("composition_validation", {})
    if not isinstance(validation, dict):
        return None
    aggregate = {
        "provider": "openai",
        "model": "",
        "llm_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "thinking_tokens": 0,
        "cached_prompt_tokens": 0,
        "tool_calls": 0,
        "retry_count": 0,
        "estimated_cost_usd": 0.0,
    }
    for language in ("de", "en"):
        checks = validation.get(language, {})
        if not isinstance(checks, dict):
            continue
        usage = checks.get("usage", {})
        if not isinstance(usage, dict) or not usage:
            continue
        model = str(usage.get("model", "") or "")
        if model and not aggregate["model"]:
            aggregate["model"] = model
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        aggregate["llm_calls"] += int(usage.get("llm_calls", 0) or 0)
        aggregate["prompt_tokens"] += prompt_tokens
        aggregate["completion_tokens"] += completion_tokens
        aggregate["total_tokens"] += int(
            usage.get("total_tokens", 0) or (prompt_tokens + completion_tokens)
        )
        if model:
            aggregate["estimated_cost_usd"] = round(
                float(aggregate["estimated_cost_usd"])
                + estimate_cost_usd(
                    model_name=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                ),
                10,
            )
    aggregate["tool_calls"] = int(aggregate["llm_calls"])
    return aggregate if int(aggregate["llm_calls"]) > 0 else None


def _timestamp_run_id() -> str:
    """Create a sortable UTC run id used for persisted artifact directories."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _record_phase(run_context: RunContext, phase: str) -> None:
    """Store the current phase in run artifacts for failure diagnostics."""
    run_context.resolution_state["current_phase"] = phase



def _failed_intake_result(
    *,
    run_id: str,
    run_dir: Path,
    company_name: str,
    web_domain: str,
    start_time: float,
    error: str,
    error_code: str = "",
    error_detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    elapsed_seconds = round(perf_counter() - start_time, 3)
    resolution_state: dict[str, Any] = {
        "current_phase": "intake_validation",
        "intake_validation": {
            "status": "failed",
            "error_code": error_code,
            "rejection_reason": (error_detail or {}).get("rejection_reason", error),
            "original_value": (error_detail or {}).get("original_value", web_domain),
            "field": (error_detail or {}).get("field", "web_domain"),
        },
    }
    result: dict[str, Any] = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "messages": [],
        "pipeline_data": empty_pipeline_data(),
        "run_context": {
            "intake": {"company_name": company_name, "web_domain": web_domain},
            "resolution_state": resolution_state,
        },
        "usage": {},
        "budget": {"elapsed_seconds": elapsed_seconds, "failed_phase": "intake_validation"},
        "status": "failed",
        "error": error,
        "failed_phase": "intake_validation",
    }
    if error_code:
        result["error_code"] = error_code
    if error_detail:
        result["error_detail"] = error_detail
    return result


def _failed_factory_result(
    *,
    run_id: str,
    run_dir: Path,
    company_name: str,
    web_domain: str,
    start_time: float,
    error: str,
    error_code: str,
    errors: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Failure result for `RuntimeAgentFactoryError` — distinct from intake errors."""
    elapsed_seconds = round(perf_counter() - start_time, 3)
    resolution_state: dict[str, Any] = {
        "current_phase": "runtime_agent_factory",
        "runtime_agents": {
            "status": "failed",
            "error_code": error_code,
            "errors": list(errors),
        },
    }
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "messages": [],
        "pipeline_data": empty_pipeline_data(),
        "run_context": {
            "intake": {"company_name": company_name, "web_domain": web_domain},
            "resolution_state": resolution_state,
        },
        "usage": {},
        "budget": {
            "elapsed_seconds": elapsed_seconds,
            "failed_phase": "runtime_agent_factory",
        },
        "status": "failed",
        "error": error,
        "failed_phase": "runtime_agent_factory",
        "error_code": error_code,
        "error_detail": {
            "phase": "runtime_agent_factory",
            "errors": list(errors),
        },
    }


def _failed_storage_result(
    *,
    run_id: str,
    run_dir: Path,
    company_name: str,
    web_domain: str,
    start_time: float,
    error: str,
    error_code: str,
    component: str,
) -> dict[str, Any]:
    """Failure result for Phase-2 storage profile/configuration errors."""
    elapsed_seconds = round(perf_counter() - start_time, 3)
    resolution_state: dict[str, Any] = {
        "current_phase": "storage_init",
        "storage": {
            "status": "failed",
            "component": component,
            "error_code": error_code,
            "message": error,
        },
    }
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "messages": [],
        "pipeline_data": empty_pipeline_data(),
        "run_context": {
            "intake": {"company_name": company_name, "web_domain": web_domain},
            "resolution_state": resolution_state,
        },
        "usage": {},
        "budget": {
            "elapsed_seconds": elapsed_seconds,
            "failed_phase": "storage_init",
        },
        "status": "failed",
        "error": error,
        "failed_phase": "storage_init",
        "error_code": error_code,
        "error_detail": {
            "phase": "storage_init",
            "component": component,
        },
    }


def _initialize_run(
    *,
    start_time: float,
    run_id: str,
    run_dir: Path,
    company_name: str,
    web_domain: str,
) -> InitialRunState:
    phase_durations_ms: dict[str, int] = {}

    # Phase: intake_validation — IntakeRequest + domain normalization +
    # DNS-level SSRF pre-flight. All failure paths raise IntakeValidationError
    # so run_pipeline() can surface a stable error_code without re-normalizing.
    t0 = perf_counter()
    intake = IntakeRequest(company_name=company_name, web_domain=web_domain)
    normalization = normalize_domain_result(intake.web_domain)
    if not normalization.is_valid:
        raise IntakeValidationError(
            field="web_domain",
            code=normalization.rejection_code,
            reason=normalization.rejection_reason,
        )
    # DNS pre-flight: catches "evil.example.com" → 192.168.x.x even though the
    # string-level canonical_domain looks public.
    try:
        resolved_ips = resolve_and_validate_host(normalization.canonical_domain)
    except SSRFBlockedError as exc:
        # Map ssrf_guard codes onto IntakeErrorCode for a consistent contract.
        mapped_code = (
            IntakeErrorCode.DNS_RESOLUTION_FAILED
            if exc.code == "dns_resolution_failed"
            else IntakeErrorCode.BLOCKED_PRIVATE_HOST
        )
        raise IntakeValidationError(
            field="web_domain",
            code=mapped_code,
            reason=exc.reason,
        ) from exc
    normalized_domain = normalization.canonical_domain
    t1 = perf_counter()
    phase_durations_ms["intake_validation"] = int((t1 - t0) * 1000)

    # Phase: agent_factory — Supervisor, departments, synthesis, report writer.
    # Raises RuntimeAgentFactoryError on missing role / missing method /
    # constructor crash; caught in run_pipeline() and mapped to a structured
    # failed_phase="runtime_agent_factory" run result.
    agents = create_runtime_agents()
    t2 = perf_counter()
    phase_durations_ms["agent_factory"] = int((t2 - t1) * 1000)
    log_factory_event(
        run_id=run_id,
        status="ok",
        duration_ms=phase_durations_ms["agent_factory"],
        factory_version=agents.config.factory_version,
        role_count=3 + len(agents.departments),  # supervisor + synthesis + report_writer + N depts
    )

    # Phase: memory_retrieval — explicit storage boundary + general process-pattern retrieval.
    stores = create_runtime_stores(
        runs_root=RUNS_DIR,
        long_term_memory_path=LONG_TERM_MEMORY_PATH,
    )
    stores.healthcheck_required()
    memory_store = stores.long_term_memory
    run_state_store = stores.run_state
    run_context = RunContext(
        run_id=run_id,
        intake={
            "company_name": intake.company_name,
            "web_domain": intake.web_domain,
            "normalized_domain": normalized_domain,
            "canonical_url": normalization.canonical_url,
            "language": intake.language,
            "normalization_steps": list(normalization.normalization_steps),
            "resolved_ips": list(resolved_ips),
            "unicode_risk_flags": list(normalization.unicode_risk_flags),
            "registrable_domain": normalization.registrable_domain,
            "public_suffix": normalization.public_suffix,
        },
    )
    step_eval_sink = InMemoryStepSink()
    step_bus = StepBus(_build_step_consumers(run_context.step_trace, step_eval_sink))
    step_emitter = StepEmitter(
        run_id=run_id,
        bus=step_bus,
        enabled=runtime_steps_enabled(),
    )
    _record_phase(run_context, "initialized")
    run_context.resolution_state["storage"] = stores.snapshot()
    run_state_store.create_run(
        run_id=run_id,
        intake={
            "company_name": intake.company_name,
            "web_domain": intake.web_domain,
            "normalized_domain": normalized_domain,
        },
        phase="initialized",
    )
    initial_retrieval_context = RetrievalContext(
        run_id=run_id,
        company_name=intake.company_name,
        normalized_domain=normalized_domain,
        language=intake.language,
        phase="memory_retrieval",
        target_scope="run_start",
    )
    initial_retrieval = retrieve_strategy_batch(
        memory_store,
        context=initial_retrieval_context,
        limit=DEFAULT_GENERAL_RETRIEVAL_LIMIT,
    )
    run_context.retrieved_strategies = initial_retrieval.patterns
    run_context.retrieved_role_strategies = {}
    run_context.resolution_state["memory_retrieval"] = {
        "initial": initial_retrieval.snapshot,
        "final_source": "initial",
    }
    t3 = perf_counter()
    phase_durations_ms["memory_retrieval"] = int((t3 - t2) * 1000)

    run_context.resolution_state["phase_durations_ms"] = phase_durations_ms
    # Composition snapshot — non-sensitive: roles, runtime types, department
    # names, cache strategy, factory version. No secrets, no prompts.
    run_context.resolution_state["runtime_agents"] = agents.snapshot()
    # Persist a structured intake_validation summary for UI, observability, and audit.
    run_context.resolution_state["intake_validation"] = {
        "status": "ok",
        "error_code": "",
        "rejection_reason": "",
        "canonical_domain": normalization.canonical_domain,
        "canonical_url": normalization.canonical_url,
        "registrable_domain": normalization.registrable_domain,
        "public_suffix": normalization.public_suffix,
        "original_hostname": normalization.original_hostname,
        "normalization_steps": list(normalization.normalization_steps),
        "unicode_risk_flags": list(normalization.unicode_risk_flags),
        "resolved_ips": list(resolved_ips),
        "duration_ms": phase_durations_ms["intake_validation"],
    }
    log_intake_event(
        run_id=run_id,
        status="ok",
        duration_ms=phase_durations_ms["intake_validation"],
        canonical_domain=normalization.canonical_domain,
        registrable_domain=normalization.registrable_domain,
        extra={
            "unicode_risk_flags": list(normalization.unicode_risk_flags),
            "resolved_ips_count": len(resolved_ips),
        },
    )
    step_emitter.emit_narrated(
        phase="initialized",
        actor="PipelineRunner",
        actor_role="runtime",
        goal="Initialize run context and runtime agents",
        action_kind="state_transition",
        action_target="run.initialize",
        action_payload={
            "company_name_present": bool(intake.company_name),
            "normalized_domain": normalized_domain,
            "agent_factory_duration_ms": phase_durations_ms["agent_factory"],
            "intake_duration_ms": phase_durations_ms["intake_validation"],
        },
        state_transitions=[
            {"kind": "run_context_created", "run_id": run_id},
            {"kind": "runtime_agents_created", "department_count": len(agents.departments)},
        ],
        decision="initialized",
        reflection="Run context, runtime agents, and intake validation completed.",
        stop_reason="initialized",
    )
    step_emitter.emit_narrated(
        phase="storage_init",
        actor="PipelineRunner",
        actor_role="runtime",
        goal="Initialize storage boundary",
        action_kind="state_transition",
        action_target="storage.initialize",
        action_payload=stores.snapshot(),
        state_transitions=[
            {"kind": "storage_healthcheck", "status": "ok"},
            {"kind": "run_state_created", "run_id": run_id},
        ],
        decision="storage_ready",
        reflection="Runtime storage boundary initialized and health-checked.",
        stop_reason="storage_ready",
    )
    step_emitter.emit_narrated(
        phase="memory_retrieval",
        actor="PipelineRunner",
        actor_role="runtime",
        goal="Retrieve initial long-term process-memory patterns",
        action_kind="capability_call",
        action_target="memory.retrieve_strategy_batch",
        action_payload={
            "target_scope": "run_start",
            "limit": DEFAULT_GENERAL_RETRIEVAL_LIMIT,
            "result_count": len(initial_retrieval.patterns),
            "status": initial_retrieval.snapshot.get("status", ""),
        },
        capability_calls=[
            {
                "kind": "memory_retrieval",
                "target_scope": "run_start",
                "result_count": len(initial_retrieval.patterns),
                "duration_ms": initial_retrieval.snapshot.get("duration_ms", 0),
            }
        ],
        decision=str(initial_retrieval.snapshot.get("status", "ok")),
        reflection="Initial process-memory retrieval completed.",
        stop_reason=str(initial_retrieval.snapshot.get("warning_code") or "retrieval_complete"),
    )

    return InitialRunState(
        start_time=start_time,
        run_id=run_id,
        run_dir=run_dir,
        intake=intake,
        agents=agents,
        memory_store=memory_store,
        run_state_store=run_state_store,
        run_context=run_context,
        messages=[],
        budget_tracker=PhaseBudgetTracker(),
        step_emitter=step_emitter,
        step_eval_sink=step_eval_sink,
        normalized_domain=normalized_domain,
        normalized_domain_result=normalization,
    )


def _serialize_message_content(message: dict[str, Any]) -> str:
    """Normalize event content so downstream JSON extraction can be best-effort."""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _extract_pipeline_data(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Recover section payloads from emitted messages for legacy callers."""
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


def _normalize_meeting_actions(raw_actions: list[Any] | None) -> list[MeetingAction]:
    """Accept already-validated actions and JSON-like dicts from persisted state."""
    actions: list[MeetingAction] = []
    for item in raw_actions or []:
        if isinstance(item, MeetingAction):
            actions.append(item)
        elif isinstance(item, dict):
            actions.append(MeetingAction.model_validate(item))
    return actions


def _sync_finalization_artifacts(
    *,
    run_context: RunContext,
    pipeline_data: dict[str, Any],
    run_id: str,
    company_name: str,
    status: str,
    meeting_actions: list[MeetingAction] | list[dict[str, Any]] | None = None,
) -> None:
    """Keep final status artifacts aligned across run context, memory, and export data."""
    evidence_health = str(
        (pipeline_data.get("quality_review") or {}).get("evidence_health") or "low"
    )
    blocked_reasons = list(run_context.meeting_readiness_assessment.blocked_reasons or [])
    if status in {BLOCKED_RUN_STATUS, DISCOVERY_READY_RUN_STATUS} and not blocked_reasons:
        readiness_reasons = [
            str(reason).strip()
            for reason in ((pipeline_data.get("research_readiness") or {}).get("reasons") or [])
            if str(reason).strip()
        ]
        blocked_reasons = readiness_reasons[:5]
        if not blocked_reasons:
            finalization_reason = str(
                (run_context.resolution_state.get("finalization_blocked") or {}).get("reason") or ""
            ).strip()
            if finalization_reason == "meeting_critical_public_gaps_open":
                blocked_reasons = ["Meeting-critical public gaps remain open."]
            elif finalization_reason == "meeting_not_ready":
                blocked_reasons = ["Research output is not yet meeting-ready."]
            elif finalization_reason == "internal_customer_data_required":
                blocked_reasons = ["Execution requires internal customer data that is not publicly available."]

    readiness = run_context.meeting_readiness_assessment.model_copy(
        update={
            "run_status": status,
            "meeting_ready": status == SUCCESS_RUN_STATUS,
            "discovery_ready": status == DISCOVERY_READY_RUN_STATUS,
            "blocked_reasons": [] if status == SUCCESS_RUN_STATUS else blocked_reasons,
            "confidence": (
                "high"
                if status == SUCCESS_RUN_STATUS and evidence_health == "high"
                else "medium"
                if status in {SUCCESS_RUN_STATUS, DISCOVERY_READY_RUN_STATUS}
                else "low"
            ),
        }
    )
    run_context.meeting_readiness_assessment = readiness
    run_context.short_term_memory.meeting_readiness_assessment = readiness

    actions = _normalize_meeting_actions(
        meeting_actions
        if meeting_actions is not None
        else (
            run_context.short_term_memory.meeting_actions
            or pipeline_data.get("meeting_actions")
            or []
        )
    )
    if actions:
        run_context.short_term_memory.meeting_actions = actions
        pipeline_data["meeting_actions"] = sort_meeting_actions(
            [action.model_dump(mode="json") for action in actions]
        )

    final_briefing = FinalBriefing(
        run_id=run_id,
        company_name=company_name,
        status=status,
        executive_summary=str((pipeline_data.get("synthesis") or {}).get("executive_summary") or "n/v"),
        evidence_packets=list(run_context.short_term_memory.evidence_packets),
        answer_matrix_updates=list(run_context.short_term_memory.answer_matrix_updates),
        readiness=readiness,
        recommended_actions=actions,
        metadata={
            "run_status": status,
            "research_readiness_score": int(
                (pipeline_data.get("research_readiness") or {}).get("score", 0) or 0
            ),
            "evidence_health": evidence_health,
        },
    )
    run_context.final_briefing = final_briefing
    run_context.short_term_memory.final_briefing = final_briefing
    pipeline_data["meeting_readiness_assessment"] = readiness.model_dump(mode="json")
    pipeline_data["final_briefing"] = final_briefing.model_dump(mode="json")


def _admitted_packages_for_synthesis(department_packages: dict[str, Any]) -> dict[str, Any]:
    """Build the report-segment view consumed by synthesis."""
    return build_synthesis_input_packages(department_packages)


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
    # Resume works from persisted artifacts; no department rerun happens here.
    if should_use_postgres_run_artifacts():
        run_dir = resolve_run_dir(run_id, runs_root=RUNS_DIR)
        run_context_payload = load_latest_run_artifact_json(
            run_id=run_id,
            artifact_type="run_context",
        )
        pipeline_data = load_latest_run_artifact_json(
            run_id=run_id,
            artifact_type="pipeline_data",
        )
    else:
        run_dir = resolve_run_dir(run_id, runs_root=RUNS_DIR, must_exist=True)
        run_context_payload = json.loads((run_dir / "run_context.json").read_text(encoding="utf-8"))
        pipeline_data = json.loads((run_dir / "pipeline_data.json").read_text(encoding="utf-8"))

    run_context = RunContext.from_snapshot(run_context_payload)
    resume_eval_sink = InMemoryStepSink()
    resume_emitter = StepEmitter(
        run_id=run_id,
        bus=StepBus(_build_step_consumers(run_context.step_trace, resume_eval_sink)),
        enabled=runtime_steps_enabled(),
    )

    if run_context.status != SELECTION_REQUIRED_RUN_STATUS:
        # Only selection-paused runs can enter this resume path.
        return {
            "run_id": run_id,
            "status": run_context.status,
            "error": f"Run is not paused for user selection (status={run_context.status}).",
        }

    # Apply user depth selections to the answer matrix used by readiness gates.
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

    # Persist user selections so dashboard/export state explains the resume decision.
    run_context.resolution_state["user_selections"] = {
        "selected_questions": selected_questions,
        "skipped_questions": skipped_questions,
        "timestamp": datetime.now(UTC).isoformat(),
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
    meeting_assessment = MeetingReadinessGate().evaluate(
        answer_matrix=run_context.answer_matrix,
        resolution_state=run_context.resolution_state,
        evidence_health=str((pipeline_data.get("quality_review") or {}).get("evidence_health") or "low"),
        readiness_usable=bool(readiness.get("usable")),
        discovery_ready=bool(readiness.get("discovery_ready")),
        minimum_package=dict(readiness.get("minimum_package", {}) or {}),
        blockers=list(readiness.get("readiness_blockers", []) or []),
    )
    run_context.meeting_readiness_assessment = meeting_assessment
    status = determine_final_status(
        readiness_usable=bool(readiness.get("usable")),
        first_round_resolution=first_round_resolution,
        remaining_public_gaps=[],  # user resolved the selection requirement
        discovery_ready=bool(readiness.get("discovery_ready")),
    )
    if status != SELECTION_REQUIRED_RUN_STATUS and not meeting_assessment.meeting_ready:
        status = meeting_assessment.run_status
    run_context.status = status
    resume_emitter.emit_narrated(
        phase="dashboard_resume",
        actor="PipelineRunner",
        actor_role="runtime",
        goal="Resume run with dashboard user selections",
        action_kind="state_transition",
        action_target="dashboard.resume",
        action_payload={
            "selected_question_count": len(selected_questions),
            "skipped_question_count": len(skipped_questions),
            "final_status": status,
        },
        state_transitions=[
            {
                "kind": "dashboard_resume_recorded",
                "selected_question_count": len(selected_questions),
                "skipped_question_count": len(skipped_questions),
                "status": status,
            }
        ],
        decision=status,
        reflection="Dashboard user selections applied and finalization gate re-evaluated.",
        stop_reason="dashboard_resume_complete",
    )
    _sync_finalization_artifacts(
        run_context=run_context,
        pipeline_data=pipeline_data,
        run_id=run_id,
        company_name=run_context.intake.get("company_name", ""),
        status=status,
    )

    # RA-07: Checkpoint after dashboard resume
    _write_checkpoint(
        run_dir,
        "after_dashboard_resume",
        run_context,
        run_id=run_id,
        step_emitter=resume_emitter,
    )

    # Re-export the updated run artifacts for UI and follow-up loading.
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


def _build_supervisor_brief(state: InitialRunState, *, on_message: MessageHook) -> SupervisorBriefResult:
    _record_phase(state.run_context, "supervisor_brief")
    t0 = perf_counter()
    supervisor_agent = state.agents["supervisor"]
    domain_arg: str | NormalizedDomainResult = (
        state.normalized_domain_result
        if supervisor_agent.__class__.__module__ == "src.agents.supervisor"
        else state.normalized_domain
    )
    brief, supervisor_message = supervisor_agent.build_intake_brief(
        state.intake,
        normalized_domain=domain_arg,
    )
    state.run_context.supervisor_brief = supervisor_message["payload"]
    state.run_context.question_registry = build_question_registry()
    state.run_context.answer_matrix = build_initial_answer_matrix()

    # Contextual refresh: keep the early generic snapshot for audit, then use
    # the industry hint and question registry before department routing starts.
    question_ids = tuple(state.run_context.question_registry.keys())
    brief_retrieval_context = RetrievalContext(
        run_id=state.run_id,
        company_name=state.intake.company_name,
        normalized_domain=state.normalized_domain,
        language=state.intake.language,
        industry_hint=brief.industry_hint,
        phase="supervisor_brief",
        target_scope="brief_context",
        question_ids=question_ids,
    )
    brief_retrieval = retrieve_strategy_batch(
        state.memory_store,
        context=brief_retrieval_context,
        limit=DEFAULT_GENERAL_RETRIEVAL_LIMIT,
    )
    if brief_retrieval.patterns:
        state.run_context.retrieved_strategies = brief_retrieval.patterns
        final_source = "brief_context"
    else:
        final_source = "initial"

    role_batches = {
        role: retrieve_strategy_batch(
            state.memory_store,
            context=brief_retrieval_context.role_context(
                role,
                department=role.removesuffix("Lead")
                .removesuffix("Researcher")
                .removesuffix("Critic")
                .removesuffix("Judge")
                .removesuffix("CodingSpecialist"),
            ),
            limit=DEFAULT_ROLE_RETRIEVAL_LIMIT,
        )
        for role in RETRIEVABLE_ROLE_ORDER
    }
    state.run_context.retrieved_role_strategies = {
        role: batch.patterns for role, batch in role_batches.items()
    }
    memory_retrieval_state = state.run_context.resolution_state.setdefault("memory_retrieval", {})
    memory_retrieval_state["brief_context"] = brief_retrieval.snapshot
    memory_retrieval_state["roles"] = {
        role: batch.snapshot for role, batch in role_batches.items()
    }
    memory_retrieval_state["final_source"] = final_source
    memory_retrieval_state["role_count"] = len(role_batches)
    duration_ms = int((perf_counter() - t0) * 1000)
    state.run_context.resolution_state.setdefault("phase_durations_ms", {})[
        "supervisor_brief"
    ] = duration_ms

    # ── Punkt 5.8: persist non-sensitive supervisor_brief diagnose ──
    fetch_audit = getattr(brief, "fetch_audit", {}) or {}
    fetch_status = "reachable" if brief.website_reachable else (
        fetch_audit.get("error_type") or "unreachable"
    )
    state.run_context.resolution_state["supervisor_brief"] = {
        "schema_version": getattr(brief, "schema_version", ""),
        "briefing_readiness": getattr(brief, "briefing_readiness", "ready"),
        "identity_confidence": brief.name_confidence,
        "identity_confidence_reason": getattr(brief, "name_confidence_reason", ""),
        "industry_confidence": getattr(brief, "industry_confidence", "unknown"),
        "industry_confidence_reason": getattr(brief, "industry_confidence_reason", ""),
        "identity_conflict": getattr(brief, "identity_conflict", False),
        "routing_gaps": list(getattr(brief, "routing_gaps", []) or []),
        "evidence_item_count": len(getattr(brief, "evidence_items", []) or []),
        "missing_evidence_fields": [
            item.get("supports_field", "")
            for item in (getattr(brief, "missing_evidence", []) or [])
        ],
        "fetch_status": fetch_status,
        "fetch_http_status": int(fetch_audit.get("http_status", 0) or 0),
        "fetch_final_url": fetch_audit.get("final_url", ""),
        "fetch_content_language": fetch_audit.get("content_language", ""),
        "duration_ms": duration_ms,
    }
    intake_research = supervisor_message.get("payload", {}).get("intake_research", {})
    if intake_research:
        state.run_context.resolution_state["intake_research"] = {
            "schema_version": intake_research.get("schema_version", ""),
            "warnings": intake_research.get("warnings", []),
            "errors": intake_research.get("errors", []),
            "timings_ms": intake_research.get("timings_ms", {}),
            "snapshot": intake_research.get("snapshot", {}),
            "identity": intake_research.get("identity", {}),
            "industry": intake_research.get("industry", {}),
            "duration_ms": duration_ms,
        }
    routing_gaps_tuple = tuple(getattr(brief, "routing_gaps", []) or [])
    readiness = getattr(brief, "briefing_readiness", "ready")
    log_status = "ok" if readiness == "ready" else (
        "blocked" if str(readiness).startswith("blocked_") else "degraded"
    )
    state.step_emitter.emit_narrated(
        phase="supervisor_brief",
        actor="Supervisor",
        actor_role="supervisor",
        goal="Create Supervisor brief and refresh process memory",
        action_kind="state_transition",
        action_target="supervisor_brief.create",
        action_payload={
            "briefing_readiness": str(readiness),
            "identity_confidence": brief.name_confidence,
            "industry_confidence": getattr(brief, "industry_confidence", "unknown"),
            "routing_gap_count": len(routing_gaps_tuple),
            "role_memory_batches": len(role_batches),
            "duration_ms": duration_ms,
        },
        capability_calls=[
            {
                "kind": "memory_retrieval",
                "target_scope": "brief_context",
                "result_count": len(brief_retrieval.patterns),
                "duration_ms": brief_retrieval.snapshot.get("duration_ms", 0),
            }
        ],
        state_transitions=[
            {"kind": "supervisor_brief_recorded", "readiness": str(readiness)},
            {"kind": "question_registry_initialized", "question_count": len(question_ids)},
            {"kind": "answer_matrix_initialized", "entry_count": len(state.run_context.answer_matrix)},
        ],
        decision=log_status,
        reflection="Supervisor brief created and process-memory retrieval refreshed.",
        stop_reason="supervisor_brief_complete",
    )

    # ── Punkt 5.11: structured supervisor briefing event ──
    log_supervisor_brief_event(
        run_id=state.run_id,
        status=log_status,
        duration_ms=duration_ms,
        briefing_readiness=str(readiness),
        identity_confidence=brief.name_confidence,
        industry_confidence=getattr(brief, "industry_confidence", "unknown"),
        fetch_status=fetch_status,
        evidence_item_count=len(getattr(brief, "evidence_items", []) or []),
        routing_gaps=routing_gaps_tuple,
    )

    first_event = emit_message(
        on_message,
        agent="Supervisor",
        content=json.dumps(supervisor_message, ensure_ascii=False, default=str),
        run_id=state.run_id,
        sequence=len(state.messages) + 1,
        phase="supervisor_brief",
        content_type="application/json",
    )
    state.messages.append(first_event)
    checkpoint_info: dict[str, Any]
    try:
        checkpoint_info = _write_checkpoint(
            state.run_dir,
            "after_supervisor_brief",
            state.run_context,
            run_id=state.run_id,
            run_state_store=state.run_state_store,
            step_emitter=state.step_emitter,
        )
    except Exception as exc:
        checkpoint_info = CheckpointInfo(
            checkpoint_id="after_supervisor_brief",
            phase="after_supervisor_brief",
            written=False,
            error_code="checkpoint_write_failed",
            error_message=str(exc)[:300],
        ).as_dict()
    handoff = build_step1_handoff(
        run_context=state.run_context,
        supervisor_message=supervisor_message,
        first_event=first_event,
        checkpoint=checkpoint_info,
        runtime_agents_snapshot=state.agents.snapshot(),
        budget_snapshot={
            "phase_durations_ms": dict(
                state.run_context.resolution_state.get("phase_durations_ms", {})
            ),
            "budget_tracker": state.budget_tracker.snapshot()
            if hasattr(state.budget_tracker, "snapshot")
            else {},
        },
    )
    state.run_context.resolution_state["step1_handoff"] = handoff.as_dict()
    if handoff_allows_department_routing(handoff):
        try:
            checkpoint_info = _write_checkpoint(
                state.run_dir,
                "after_supervisor_brief",
                state.run_context,
                run_id=state.run_id,
                run_state_store=state.run_state_store,
                step_emitter=state.step_emitter,
            )
            handoff = build_step1_handoff(
                run_context=state.run_context,
                supervisor_message=supervisor_message,
                first_event=first_event,
                checkpoint=checkpoint_info,
                runtime_agents_snapshot=state.agents.snapshot(),
                budget_snapshot={
                    "phase_durations_ms": dict(
                        state.run_context.resolution_state.get("phase_durations_ms", {})
                    ),
                    "budget_tracker": state.budget_tracker.snapshot()
                    if hasattr(state.budget_tracker, "snapshot")
                    else {},
                },
            )
            state.run_context.resolution_state["step1_handoff"] = handoff.as_dict()
        except Exception as exc:
            checkpoint_info = CheckpointInfo(
                checkpoint_id="after_supervisor_brief",
                phase="after_supervisor_brief",
                written=False,
                error_code="checkpoint_write_failed",
                error_message=str(exc)[:300],
            ).as_dict()
            handoff = build_step1_handoff(
                run_context=state.run_context,
                supervisor_message=supervisor_message,
                first_event=first_event,
                checkpoint=checkpoint_info,
                runtime_agents_snapshot=state.agents.snapshot(),
                budget_snapshot={
                    "phase_durations_ms": dict(
                        state.run_context.resolution_state.get("phase_durations_ms", {})
                    ),
                },
            )
            state.run_context.resolution_state["step1_handoff"] = handoff.as_dict()
    if not handoff_allows_department_routing(handoff):
        _record_phase(state.run_context, "step1_handoff")
        state.run_context.status = "blocked"
    state.step_emitter.emit_narrated(
        phase="step1_handoff",
        actor="PipelineRunner",
        actor_role="runtime",
        goal="Validate Step-1 handoff before department routing",
        action_kind="state_transition",
        action_target="step1_handoff.validate",
        action_payload={
            "readiness": state.run_context.resolution_state.get("step1_handoff", {}).get("readiness", ""),
            "validation_error_count": len(
                state.run_context.resolution_state.get("step1_handoff", {}).get("validation_errors", [])
            ),
        },
        state_transitions=[
            {
                "kind": "step1_handoff_recorded",
                "allows_department_routing": handoff_allows_department_routing(handoff),
            }
        ],
        decision="ready" if handoff_allows_department_routing(handoff) else "blocked",
        reflection="Step-1 handoff built and validated.",
        stop_reason="handoff_validated",
    )
    return SupervisorBriefResult(
        brief=brief,
        supervisor_message=supervisor_message,
        step1_handoff=state.run_context.resolution_state.get("step1_handoff", {}),
    )


def _run_first_pass(
    state: InitialRunState,
    *,
    brief: SupervisorBrief,
    on_message: MessageHook,
) -> FirstPassResult:
    _record_phase(state.run_context, "first_pass")
    state.step_emitter.emit_narrated(
        phase="first_pass",
        actor="PipelineRunner",
        actor_role="runtime",
        goal="Start first-pass department execution",
        action_kind="state_transition",
        action_target="phase.start",
        action_payload={"phase": "first_pass"},
        state_transitions=[{"kind": "phase_started", "phase": "first_pass"}],
        decision="started",
        reflection="First-pass department execution started.",
        stop_reason="phase_started",
    )
    sections, department_packages, loop_messages, completed_backlog, department_timings, first_round_resolution = run_supervisor_loop(
        brief=brief,
        run_context=state.run_context,
        agents=state.agents,
        on_message=on_message,
        step_emitter=state.step_emitter,
    )
    state.messages.extend(loop_messages)
    state.run_context.short_term_memory.task_statuses.update(
        {item["task_key"]: item["status"] for item in completed_backlog}
    )

    first_pass_snapshot = state.run_context.short_term_memory.snapshot()
    first_pass_tokens = int(first_pass_snapshot.get("usage_totals", {}).get("total_tokens", 0) or 0)
    state.budget_tracker.record_phase_tokens("first_pass", first_pass_tokens)
    if not state.budget_tracker.check_budget("first_pass"):
        state.budget_tracker.record_stop("first_pass", "token_budget_exceeded")

    state.run_context.resolution_state = {
        **state.run_context.resolution_state,
        "first_round_resolution": first_round_resolution,
        "auto_close": {
            "triggered": False,
            "max_questions": 4,
            "attempted_questions": 0,
            "stop_reason": "not_required",
            "remaining_public_gaps": [],
        },
    }
    _write_checkpoint(
        state.run_dir,
        "after_first_pass",
        state.run_context,
        run_id=state.run_id,
        run_state_store=state.run_state_store,
        step_emitter=state.step_emitter,
    )
    state.step_emitter.emit_narrated(
        phase="first_pass",
        actor="PipelineRunner",
        actor_role="runtime",
        goal="Complete first-pass department execution",
        action_kind="state_transition",
        action_target="phase.complete",
        action_payload={
            "phase": "first_pass",
            "completed_task_count": len(completed_backlog),
            "department_count": len(department_packages),
            "resolution_bucket": first_round_resolution.get("bucket", ""),
        },
        state_transitions=[
            {
                "kind": "first_round_resolution_recorded",
                "bucket": first_round_resolution.get("bucket", ""),
            }
        ],
        usage={"total_tokens": first_pass_tokens},
        decision=str(first_round_resolution.get("bucket", "")),
        reflection="First-pass department execution completed and first-round resolution recorded.",
        stop_reason="first_pass_complete",
    )
    return FirstPassResult(
        sections=sections,
        department_packages=department_packages,
        completed_backlog=completed_backlog,
        department_timings=department_timings,
        first_round_resolution=first_round_resolution,
        first_pass_tokens=first_pass_tokens,
    )


def _run_auto_close_if_required(
    state: InitialRunState,
    *,
    first_pass: FirstPassResult,
    on_message: MessageHook,
) -> AutoCloseResult:
    if first_pass.first_round_resolution.get("bucket") != "AUTO_CLOSE_REQUIRED":
        return AutoCloseResult(triggered=False, payload={})

    _record_phase(state.run_context, "auto_close")
    state.step_emitter.emit_narrated(
        phase="auto_close",
        actor="PipelineRunner",
        actor_role="runtime",
        goal="Start bounded auto-close for public evidence gaps",
        action_kind="state_transition",
        action_target="phase.start",
        action_payload={"phase": "auto_close", "max_questions": 4},
        state_transitions=[{"kind": "phase_started", "phase": "auto_close"}],
        decision="started",
        reflection="Bounded auto-close started for meeting-critical public gaps.",
        stop_reason="phase_started",
    )
    auto_close_result = run_bounded_follow_up(
        run_id=state.run_id,
        run_context=state.run_context.snapshot(),
        pipeline_data={
            "company_profile": first_pass.sections.get("company_profile", {}),
            "industry_analysis": first_pass.sections.get("industry_analysis", {}),
            "market_network": first_pass.sections.get("market_network", {}),
            "contact_intelligence": first_pass.sections.get("contact_intelligence", {}),
            "synthesis": first_pass.sections.get("synthesis", {}),
            "quality_review": {},
        },
        public_gap_questions=(
            first_pass.first_round_resolution.get("meeting_critical_public_gap_candidates")
            or first_pass.first_round_resolution.get("meeting_critical_public_gaps", [])
        ),
        max_questions=4,
    )
    state.run_context.resolution_state["auto_close"] = {
        "triggered": True,
        **auto_close_result,
    }

    mapping_missing = False
    for attempt in auto_close_result.get("attempts", []):
        if attempt.get("resolved"):
            resolved_question_ids = [
                str(qid).strip()
                for qid in attempt.get("resolved_question_ids", [])
                if str(qid).strip()
            ]
            if not resolved_question_ids:
                mapping_missing = True
                continue
            for qid in resolved_question_ids:
                entry = state.run_context.answer_matrix.get(qid)
                if entry and entry.get("status") in {"pending", "blocked", "partially_answered"}:
                    entry["status"] = "partially_answered"
                    entry["notes"] = f"Auto-close follow-up resolved: {attempt.get('question', '')[:80]}"
    if mapping_missing:
        state.run_context.resolution_state["auto_close"]["mapping_missing"] = True

    state.messages.append(
        emit_message(
            on_message,
            agent="Supervisor",
            content=json.dumps(
                {"status": "auto_close_follow_up_completed", **auto_close_result},
                ensure_ascii=False,
            ),
        )
    )

    closure_tokens = int(
        state.run_context.short_term_memory.snapshot()
        .get("usage_totals", {}).get("total_tokens", 0) or 0
    ) - first_pass.first_pass_tokens
    state.budget_tracker.record_phase_tokens("closure", max(closure_tokens, 0))
    _write_checkpoint(
        state.run_dir,
        "after_closure",
        state.run_context,
        run_id=state.run_id,
        run_state_store=state.run_state_store,
        step_emitter=state.step_emitter,
    )
    state.step_emitter.emit_narrated(
        phase="auto_close",
        actor="PipelineRunner",
        actor_role="runtime",
        goal="Complete bounded auto-close",
        action_kind="state_transition",
        action_target="auto_close.complete",
        action_payload={
            "attempted_questions": auto_close_result.get("attempted_questions", 0),
            "stop_reason": auto_close_result.get("stop_reason", ""),
            "unresolved_after_count": len(auto_close_result.get("unresolved_after", [])),
        },
        state_transitions=[
            {
                "kind": "auto_close_recorded",
                "attempted_questions": auto_close_result.get("attempted_questions", 0),
            }
        ],
        usage={"total_tokens": max(closure_tokens, 0)},
        decision=str(auto_close_result.get("stop_reason", "")),
        reflection="Bounded auto-close completed.",
        stop_reason=str(auto_close_result.get("stop_reason", "auto_close_complete")),
    )
    return AutoCloseResult(triggered=True, payload=auto_close_result)


def _run_synthesis_phase(
    state: InitialRunState,
    *,
    brief: SupervisorBrief,
    first_pass: FirstPassResult,
    on_message: MessageHook,
) -> SynthesisPhaseResult:
    _record_phase(state.run_context, "synthesis")
    state.step_emitter.emit_narrated(
        phase="synthesis",
        actor="PipelineRunner",
        actor_role="runtime",
        goal="Start synthesis phase",
        action_kind="state_transition",
        action_target="phase.start",
        action_payload={"phase": "synthesis"},
        state_transitions=[{"kind": "phase_started", "phase": "synthesis"}],
        decision="started",
        reflection="Synthesis phase started.",
        stop_reason="phase_started",
    )
    synthesis_assignments = build_synthesis_assignments(brief)
    for assignment in synthesis_assignments:
        state.run_context.record_task(
            assignee=assignment.assignee,
            objective=assignment.objective,
            section=assignment.target_section,
            task_key=assignment.task_key,
            model_name=assignment.model_name,
            allowed_tools=assignment.allowed_tools,
            status="pending_synthesis",
        )

    if "synthesis" not in state.agents:
        return SynthesisPhaseResult(
            sections=first_pass.sections,
            department_packages=first_pass.department_packages,
            completed_backlog=first_pass.completed_backlog,
            department_timings=first_pass.department_timings,
            first_round_resolution=first_pass.first_round_resolution,
        )

    state.messages.append(
        emit_message(
            on_message,
            agent="Supervisor",
            content=json.dumps(
                {"status": "synthesis_assigned", "department": "SynthesisDepartment"},
                ensure_ascii=False,
            ),
        )
    )
    pre_synthesis_quality_review = build_quality_review(state.run_context.short_term_memory.snapshot())
    pre_synthesis_primary_source_stage = build_primary_source_stage(
        company_profile=first_pass.sections.get("company_profile", {}),
        industry_analysis=first_pass.sections.get("industry_analysis", {}),
        market_network=first_pass.sections.get("market_network", {}),
    )
    pre_synthesis_contact_enrichment_stage = build_contact_enrichment_stage(
        company_profile=first_pass.sections.get("company_profile", {}),
        contact_intelligence=first_pass.sections.get("contact_intelligence", {}),
    )
    first_pass.sections["primary_source_stage"] = pre_synthesis_primary_source_stage
    first_pass.sections["contact_enrichment_stage"] = pre_synthesis_contact_enrichment_stage
    synthesis_ctx = build_synthesis_context(
        company_profile=first_pass.sections.get("company_profile", {}),
        industry_analysis=first_pass.sections.get("industry_analysis", {}),
        market_network=first_pass.sections.get("market_network", {}),
        contact_intelligence=first_pass.sections.get("contact_intelligence", {}),
        quality_review=pre_synthesis_quality_review,
        memory_snapshot=state.run_context.short_term_memory.snapshot(),
        primary_source_stage=pre_synthesis_primary_source_stage,
        contact_enrichment_stage=pre_synthesis_contact_enrichment_stage,
    )
    synthesis_result, synthesis_messages = state.agents["synthesis"].run(
        brief=brief,
        department_packages=_admitted_packages_for_synthesis(first_pass.department_packages),
        memory_store=state.run_context.short_term_memory,
        on_message=on_message,
        synthesis_context=synthesis_ctx,
        step_emitter=state.step_emitter,
    )
    state.messages.extend(synthesis_messages)
    synthesis_back_requests = list(synthesis_result.get("back_requests", []) or [])
    if synthesis_back_requests:
        state.run_context.resolution_state["synthesis_back_requests"] = synthesis_back_requests
        for idx, back_request in enumerate(synthesis_back_requests, start=1):
            subject = str(back_request.get("subject", "") or "").strip()
            department = str(back_request.get("department", "") or "SynthesisDepartment")
            request_type = str(back_request.get("type", "") or "clarify")
            note = f"Synthesis back-request for {department} ({request_type}): {subject or 'n/v'}"
            state.run_context.short_term_memory.open_questions.append(note)
            state.messages.append(
                emit_message(
                    on_message,
                    agent="Supervisor",
                    content=json.dumps(
                        {
                            "status": "synthesis_back_request_recorded",
                            "index": idx,
                            "department": department,
                            "request_type": request_type,
                            "subject": subject,
                        },
                        ensure_ascii=False,
                    ),
                )
            )

    synthesis_acceptance = state.agents["supervisor"].accept_synthesis(
        synthesis_payload=synthesis_result,
    )
    synthesis_decision = synthesis_acceptance.get("decision", "rejected")
    first_pass.department_packages["SynthesisDepartment"] = {
        "admission": {
            "decision": synthesis_decision,
            "reason": synthesis_acceptance.get("reason", ""),
            "downstream_visible": synthesis_decision != "rejected",
        },
        "raw_package": synthesis_result,
        "admitted_payload": synthesis_result if synthesis_decision != "rejected" else None,
    }
    first_pass.sections["synthesis"] = synthesis_result
    state.messages.append(
        emit_message(
            on_message,
            agent="Supervisor",
            content=json.dumps(
                {"department": "SynthesisDepartment", "status": "synthesis_reviewed", **synthesis_acceptance},
                ensure_ascii=False,
            ),
        )
    )
    synthesis_task_status = {
        "accepted": "accepted",
        "accepted_with_gaps": "degraded",
        "rejected": "degraded",
    }.get(synthesis_decision, "degraded")
    for assignment in synthesis_assignments:
        state.run_context.update_task_status(task_key=assignment.task_key, status=synthesis_task_status)
        state.run_context.short_term_memory.task_statuses[assignment.task_key] = synthesis_task_status
        matrix_status = matrix_status_for_task_status(synthesis_task_status)
        for question_id in assignment.question_ids:
            entry = state.run_context.answer_matrix.setdefault(
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
                f"({synthesis_task_status}) in department '{assignment.assignee}'."
            )
        first_pass.completed_backlog.append({
            "task_key": assignment.task_key,
            "label": assignment.label,
            "target_section": assignment.target_section,
            "status": synthesis_task_status,
        })
    _write_checkpoint(
        state.run_dir,
        "after_synthesis",
        state.run_context,
        run_id=state.run_id,
        run_state_store=state.run_state_store,
        step_emitter=state.step_emitter,
    )
    state.step_emitter.emit_narrated(
        phase="synthesis",
        actor="PipelineRunner",
        actor_role="runtime",
        goal="Complete synthesis phase",
        action_kind="state_transition",
        action_target="synthesis.complete",
        action_payload={
            "admission_decision": synthesis_decision,
            "back_request_count": len(synthesis_back_requests),
            "synthesis_task_status": synthesis_task_status,
        },
        state_transitions=[
            {"kind": "synthesis_admission_recorded", "decision": synthesis_decision},
            {"kind": "synthesis_task_status_recorded", "status": synthesis_task_status},
        ],
        decision=synthesis_decision,
        reflection="Synthesis phase completed and admission decision recorded.",
        stop_reason="synthesis_complete",
    )
    return SynthesisPhaseResult(
        sections=first_pass.sections,
        department_packages=first_pass.department_packages,
        completed_backlog=first_pass.completed_backlog,
        department_timings=first_pass.department_timings,
        first_round_resolution=first_pass.first_round_resolution,
    )


def _finalize_readiness(
    state: InitialRunState,
    *,
    synthesis_phase: SynthesisPhaseResult,
    company_name: str,
    on_message: MessageHook,
) -> FinalizationResult:
    _record_phase(state.run_context, "finalization")
    sections = synthesis_phase.sections
    department_packages = synthesis_phase.department_packages
    first_round_resolution = synthesis_phase.first_round_resolution

    quality_review = build_quality_review(state.run_context.short_term_memory.snapshot())
    state.messages.append(
        emit_message(
            on_message,
            agent="SynthesisDepartment",
            content=json.dumps({"section": "quality_review", "payload": quality_review}, ensure_ascii=False),
        )
    )

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
        synthesis = {
            **ag2_synthesis,
            "generation_mode": ag2_synthesis.get("generation_mode", "fallback"),
            "confidence": evidence_health,
        }
    else:
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

    contact_intelligence = dict(sections.get("contact_intelligence", {}) or {})
    contact_intelligence.update(
        build_contact_briefing_assets(
            company_profile=sections.get("company_profile", {}),
            contact_intelligence=contact_intelligence,
        )
    )
    sections["contact_intelligence"] = contact_intelligence
    primary_source_stage = dict(
        sections.get("primary_source_stage", {}) or build_primary_source_stage(
            company_profile=sections.get("company_profile", {}),
            industry_analysis=sections.get("industry_analysis", {}),
            market_network=sections.get("market_network", {}),
        )
    )
    contact_enrichment_stage = dict(
        sections.get("contact_enrichment_stage", {}) or build_contact_enrichment_stage(
            company_profile=sections.get("company_profile", {}),
            contact_intelligence=contact_intelligence,
        )
    )

    synthesis = harmonize_synthesis_output(
        synthesis=synthesis,
        company_profile=sections.get("company_profile", {}),
        industry_analysis=sections.get("industry_analysis", {}),
        market_network=sections.get("market_network", {}),
        contact_intelligence=contact_intelligence,
        quality_review=quality_review,
    )
    synthesis.update(
        build_playbook_assets(
            company_profile=sections.get("company_profile", {}),
            market_network=sections.get("market_network", {}),
            contact_intelligence=contact_intelligence,
            synthesis=synthesis,
        )
    )

    readiness = assess_research_readiness(
        company_profile=sections.get("company_profile", {}),
        industry_analysis=sections.get("industry_analysis", {}),
        market_network=sections.get("market_network", {}),
        contact_intelligence=contact_intelligence,
        quality_review=quality_review,
        synthesis=synthesis,
        primary_source_stage=primary_source_stage,
        contact_enrichment_stage=contact_enrichment_stage,
        department_packages=department_packages,
    )
    pipeline_data = validate_pipeline_data(
        {
            "company_profile": assemble_section("company_profile", sections.get("company_profile", {})),
            "industry_analysis": assemble_section("industry_analysis", sections.get("industry_analysis", {})),
            "market_network": assemble_section("market_network", sections.get("market_network", {})),
            "contact_intelligence": assemble_section("contact_intelligence", contact_intelligence),
            "quality_review": quality_review,
            "synthesis": synthesis,
            "research_readiness": readiness,
            "primary_source_stage": readiness.get("primary_source_stage", primary_source_stage),
            "contact_enrichment_stage": readiness.get("contact_enrichment_stage", contact_enrichment_stage),
            "data_request_sheet": readiness.get("data_request_sheet", {}),
            "outreach_playbook": readiness.get("outreach_playbook", {}),
            "validation_errors": [],
        }
    )
    state.run_context.resolution_state["readiness_contract"] = {
        "minimum_package": dict(readiness.get("minimum_package", {}) or {}),
        "readiness_blockers": list(readiness.get("readiness_blockers", []) or []),
        "department_gate_overview": dict(readiness.get("department_gate_overview", {}) or {}),
        "discovery_ready": bool(readiness.get("discovery_ready")),
    }

    remaining_public_gaps = state.run_context.resolution_state.get("auto_close", {}).get("remaining_public_gaps", [])
    resolution_plan = build_resolution_plan(
        run_id=state.run_id,
        first_round_resolution=first_round_resolution,
        remaining_public_gaps=list(remaining_public_gaps),
    )
    if resolution_plan.get("unresolved") is None or not isinstance(resolution_plan.get("unresolved"), dict):
        resolution_plan["unresolved"] = {}
    if bool(readiness.get("discovery_ready")):
        data_request_fields = [
            str(item.get("label", "")).strip()
            for item in (readiness.get("data_request_sheet", {}).get("request_fields", []) or [])
            if isinstance(item, dict) and str(item.get("label", "")).strip()
        ]
        if data_request_fields:
            resolution_plan["unresolved"]["internal_customer_data_request"] = data_request_fields
        resolution_plan["decision"] = {
            "decision": "accept_gap",
            "rationale": "Public research is complete for discovery scope; execution requires internal customer data.",
            "selected_gap_ids": [
                str(item.get("blocker_id", "")).strip()
                for item in (readiness.get("readiness_blockers", []) or [])
                if isinstance(item, dict) and str(item.get("blocker_id", "")).strip()
            ],
        }
        resolution_plan["steps"] = [
            "Provide Data Request Sheet fields under NDA.",
            "Confirm target-company stakeholder owner and intro path.",
            "Resume execution readiness validation once customer data is available.",
        ]

    state.run_context.short_term_memory.resolution_plans.append(ResolutionPlan.model_validate(resolution_plan))
    state.run_context.resolution_state["resolution_plan"] = resolution_plan

    readiness_gate = MeetingReadinessGate()
    meeting_assessment = readiness_gate.evaluate(
        answer_matrix=state.run_context.answer_matrix,
        resolution_state=state.run_context.resolution_state,
        evidence_health=quality_review.get("evidence_health", "low"),
        readiness_usable=bool(readiness.get("usable")),
        discovery_ready=bool(readiness.get("discovery_ready")),
        minimum_package=dict(readiness.get("minimum_package", {}) or {}),
        blockers=list(readiness.get("readiness_blockers", []) or []),
    )
    state.run_context.meeting_readiness_assessment = meeting_assessment
    state.step_emitter.emit_narrated(
        phase="finalization",
        actor="MeetingReadinessGate",
        actor_role="runtime_gate",
        goal="Evaluate meeting-readiness gate",
        action_kind="state_transition",
        action_target="meeting_readiness.evaluate",
        action_payload={
            "evidence_health": quality_review.get("evidence_health", "low"),
            "readiness_usable": bool(readiness.get("usable")),
            "discovery_ready": bool(readiness.get("discovery_ready")),
            "blocker_count": len(readiness.get("readiness_blockers", []) or []),
        },
        state_transitions=[
            {
                "kind": "meeting_readiness_assessment_recorded",
                "meeting_ready": meeting_assessment.meeting_ready,
                "run_status": meeting_assessment.run_status,
            }
        ],
        decision=meeting_assessment.run_status,
        reflection="Meeting-readiness gate evaluated.",
        stop_reason="meeting_readiness_evaluated",
    )

    composer = FinalBriefingComposer()
    meeting_actions = composer.compose(
        synthesis=synthesis,
        answer_matrix=state.run_context.answer_matrix,
        quality_review=quality_review,
        resolution_state=state.run_context.resolution_state,
        company_name=company_name,
    )
    state.run_context.short_term_memory.meeting_actions = meeting_actions
    pipeline_data["meeting_actions"] = sort_meeting_actions(
        [action.model_dump(mode="json") for action in meeting_actions]
    )
    state.step_emitter.emit_narrated(
        phase="finalization",
        actor="FinalBriefingComposer",
        actor_role="runtime_node",
        goal="Compose final briefing meeting actions",
        action_kind="state_transition",
        action_target="final_briefing.compose",
        action_payload={"meeting_action_count": len(meeting_actions)},
        state_transitions=[
            {"kind": "meeting_actions_recorded", "meeting_action_count": len(meeting_actions)}
        ],
        decision="composed",
        reflection="Final briefing meeting actions composed.",
        stop_reason="final_briefing_composed",
    )

    status = determine_final_status(
        readiness_usable=bool(readiness.get("usable")),
        first_round_resolution=first_round_resolution,
        remaining_public_gaps=list(remaining_public_gaps),
        discovery_ready=bool(readiness.get("discovery_ready")),
    )
    if status != SELECTION_REQUIRED_RUN_STATUS and not meeting_assessment.meeting_ready:
        status = meeting_assessment.run_status
    resume_entrypoint = (
        "supervisor_resume_after_user_selection"
        if status == SELECTION_REQUIRED_RUN_STATUS
        else "supervisor_finalization_entrypoint"
    )
    state.run_context.resolution_state["dashboard_state"] = build_dashboard_state(
        status=status,
        run_id=state.run_id,
        resolution_plan=resolution_plan,
        resume_entrypoint=resume_entrypoint,
    )
    state.run_context.resolution_state["resume_entrypoint"] = resume_entrypoint
    if status == BLOCKED_RUN_STATUS:
        state.run_context.resolution_state["finalization_blocked"] = {
            "reason": "meeting_critical_public_gaps_open" if remaining_public_gaps else "meeting_not_ready",
            "open_gaps": list(remaining_public_gaps),
        }
    elif status == DISCOVERY_READY_RUN_STATUS:
        state.run_context.resolution_state["finalization_blocked"] = {
            "reason": "internal_customer_data_required",
            "open_gaps": [
                str(item.get("reason", "")).strip()
                for item in (readiness.get("readiness_blockers", []) or [])
                if isinstance(item, dict) and str(item.get("reason", "")).strip()
            ],
        }
    if status == SELECTION_REQUIRED_RUN_STATUS:
        state.step_emitter.emit_narrated(
            phase="finalization",
            actor="PipelineRunner",
            actor_role="runtime",
            goal="Pause run for dashboard user selection",
            action_kind="state_transition",
            action_target="dashboard.pause",
            action_payload={
                "status": status,
                "resume_entrypoint": resume_entrypoint,
            },
            state_transitions=[
                {"kind": "dashboard_pause_recorded", "resume_entrypoint": resume_entrypoint}
            ],
            decision="needs_user_selection",
            reflection="Run paused for dashboard user selection.",
            stop_reason="user_selection_required",
        )
    state.run_context.status = status
    _sync_finalization_artifacts(
        run_context=state.run_context,
        pipeline_data=pipeline_data,
        run_id=state.run_id,
        company_name=company_name,
        status=status,
        meeting_actions=meeting_actions,
    )
    return FinalizationResult(
        pipeline_data=pipeline_data,
        readiness=readiness,
        status=status,
        resume_entrypoint=resume_entrypoint,
        department_timings=synthesis_phase.department_timings,
        department_packages=department_packages,
    )


def _assemble_report_and_export(
    state: InitialRunState,
    *,
    finalization: FinalizationResult,
    company_name: str,
    web_domain: str,
    on_message: MessageHook,
) -> dict[str, Any]:
    _record_phase(state.run_context, "report_and_export")
    report_package, report_messages = state.agents["report_writer"].run(
        pipeline_data=finalization.pipeline_data,
        department_packages=finalization.department_packages,
        on_message=on_message,
    )
    state.run_context.report_package = report_package
    finalization.pipeline_data["report_package"] = report_package
    state.messages.extend(report_messages)
    state.step_emitter.emit_narrated(
        phase="report_and_export",
        actor="ReportWriter",
        actor_role="runtime_node",
        goal="Assemble report package",
        action_kind="state_transition",
        action_target="report_writer.run",
        action_payload={
            "report_message_count": len(report_messages),
            "report_package_present": bool(report_package),
        },
        state_transitions=[
            {"kind": "report_package_recorded", "report_package_present": bool(report_package)}
        ],
        usage=_report_writer_usage_record(report_package),
        decision="completed",
        reflection="Report writer assembled the report package.",
        stop_reason="report_writer_complete",
    )
    state.run_context.resolution_state["budget_tracker"] = state.budget_tracker.snapshot()
    _write_checkpoint(
        state.run_dir,
        "after_finalization",
        state.run_context,
        run_id=state.run_id,
        run_state_store=state.run_state_store,
        step_emitter=state.step_emitter,
    )

    elapsed_seconds = round(perf_counter() - state.start_time, 3)
    memory_snapshot = state.run_context.short_term_memory.snapshot()
    usage = summarize_worker_report_costs(memory_snapshot.get("worker_reports", []))
    usage_total = usage.get("total", {})
    usage_totals = memory_snapshot.get("usage_totals", {})
    search_calls_used = int(usage_totals.get("search_calls", 0) or 0)
    web_search_preview_call_cost = estimate_web_search_preview_call_cost_usd(
        search_calls=search_calls_used,
        model_name=get_search_model(),
    )
    if web_search_preview_call_cost > 0:
        usage_total["web_search_preview_call_cost"] = web_search_preview_call_cost
        usage_total["total_cost"] = round(
            float(usage_total.get("total_cost", 0.0) or 0.0) + web_search_preview_call_cost,
            10,
        )
        usage_actual = usage.get("actual", {})
        usage_actual["web_search_preview_call_cost"] = web_search_preview_call_cost
        usage_actual["total_cost"] = usage_total["total_cost"]
        usage["actual"] = usage_actual
        usage["total"] = usage_total
    budget = {
        "total_pipeline_events": len(state.messages),
        "tool_calls_used": int(
            (usage_totals.get("search_calls", 0) or 0)
            + (usage_totals.get("page_fetches", 0) or 0)
            + (usage_totals.get("llm_calls", 0) or 0)
        ),
        "max_tool_calls": 140,
        "max_department_attempts": 3,
        "resume_entrypoint": finalization.resume_entrypoint,
        "llm_calls_used": int(usage_totals.get("llm_calls", 0) or 0),
        "search_calls_used": search_calls_used,
        "page_fetches_used": int(usage_totals.get("page_fetches", 0) or 0),
        "estimated_cost_usd": float(usage_total.get("total_cost", 0.0) or 0.0),
        "elapsed_seconds": elapsed_seconds,
        "department_timings": finalization.department_timings,
    }
    run_context_snapshot = state.run_context.snapshot()

    dashboard_bundle = compose_dashboard(
        run_id=state.run_id,
        status=finalization.status,
        pipeline_data=finalization.pipeline_data,
        run_context=run_context_snapshot,
        budget=budget,
    )
    finalization.pipeline_data["dashboard_bundle"] = dashboard_bundle.model_dump(mode="json")

    role_patterns = consolidate_role_patterns(
        run_context=run_context_snapshot,
        pipeline_data=finalization.pipeline_data,
        status=finalization.status,
        usable=finalization.readiness["usable"],
    )
    stored_role_pattern_count = 0
    if role_patterns:
        for pattern in role_patterns:
            if should_store_memory_pattern(
                pattern=pattern,
                status=finalization.status,
                usable=finalization.readiness["usable"],
                readiness_score=finalization.readiness.get("score", 0),
                task_statuses=dict(state.run_context.short_term_memory.task_statuses),
            ):
                if state.memory_store.upsert_strategy(pattern):
                    stored_role_pattern_count += 1
    state.step_emitter.emit_narrated(
        phase="report_and_export",
        actor="PipelineRunner",
        actor_role="runtime",
        goal="Export run artifacts and consolidate process-memory patterns",
        action_kind="state_transition",
        action_target="run.export",
        action_payload={
            "status": finalization.status,
            "role_pattern_count": len(role_patterns),
            "stored_role_pattern_count": stored_role_pattern_count,
            "stored_role_patterns": stored_role_pattern_count > 0,
        },
        state_transitions=[
            {"kind": "run_artifacts_ready_for_export", "status": finalization.status},
            {"kind": "process_patterns_consolidated", "pattern_count": len(role_patterns)},
        ],
        usage=_build_run_usage_record(
            usage_totals=usage_totals,
            usage_total=usage_total,
            search_model=get_search_model(),
        ),
        decision="ready_to_export",
        reflection="Run artifacts prepared for export and process-memory consolidation completed.",
        stop_reason="export_ready",
    )
    run_context_snapshot = state.run_context.snapshot()

    export_run(
        run_dir=state.run_dir,
        run_id=state.run_id,
        company_name=company_name,
        web_domain=web_domain,
        status=finalization.status,
        messages=state.messages,
        pipeline_data=finalization.pipeline_data,
        run_context=run_context_snapshot,
        usage=usage,
        budget=budget,
    )
    return {
        "run_id": state.run_id,
        "run_dir": str(state.run_dir),
        "messages": state.messages,
        "pipeline_data": finalization.pipeline_data,
        "run_context": run_context_snapshot,
        "usage": usage,
        "budget": budget,
        "status": finalization.status,
        "error": None,
    }


def _pipeline_error_result(
    *,
    run_id: str,
    run_dir: Path,
    company_name: str,
    web_domain: str,
    start_time: float,
    error_message: str,
    run_context: RunContext,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    run_context.status = "failed"
    failed_phase = str(run_context.resolution_state.get("current_phase") or "unknown")
    last_checkpoint = str(run_context.resolution_state.get("last_checkpoint") or "")
    run_context.resolution_state["failure"] = {
        "phase": failed_phase,
        "last_checkpoint": last_checkpoint,
        "error": error_message,
    }
    elapsed_seconds = round(perf_counter() - start_time, 3)
    budget = {
        "elapsed_seconds": elapsed_seconds,
        "failed_phase": failed_phase,
        "last_checkpoint": last_checkpoint,
    }
    export_run(
        run_dir=run_dir,
        run_id=run_id,
        company_name=company_name,
        web_domain=web_domain,
        status="failed",
        messages=messages,
        pipeline_data=empty_pipeline_data(),
        run_context=run_context.snapshot(),
        budget=budget,
        error=error_message,
    )
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "messages": messages,
        "pipeline_data": empty_pipeline_data(),
        "run_context": run_context.snapshot(),
        "usage": {},
        "budget": budget,
        "status": "failed",
        "error": error_message,
        "failed_phase": failed_phase,
        "last_checkpoint": last_checkpoint,
    }


def run_pipeline(
    *,
    company_name: str,
    web_domain: str,
    on_message: MessageHook = None,
) -> dict[str, Any]:
    """Run the full initial briefing pipeline and persist all runtime artifacts."""
    start_time = perf_counter()
    run_id = _timestamp_run_id()
    run_dir = resolve_run_dir(run_id, runs_root=RUNS_DIR)

    try:
        state = _initialize_run(
            start_time=start_time,
            run_id=run_id,
            run_dir=run_dir,
            company_name=company_name,
            web_domain=web_domain,
        )
    except IntakeValidationError as exc:
        # Structured per-field intake failures (company_name or web_domain
        # required / too long / placeholder) raised by IntakeRequest.
        original_value = company_name if exc.field == "company_name" else web_domain
        log_intake_event(
            run_id=run_id,
            status="failed",
            error_code=exc.code,
            rejection_reason=exc.reason,
        )
        return _failed_intake_result(
            run_id=run_id,
            run_dir=run_dir,
            company_name=company_name,
            web_domain=web_domain,
            start_time=start_time,
            error=exc.reason,
            error_code=exc.code,
            error_detail={
                "field": exc.field,
                "original_value": original_value,
                "rejection_code": exc.code,
                "rejection_reason": exc.reason,
            },
        )
    except RuntimeAgentFactoryError as exc:
        # Composition error — distinct phase, distinct failure code.
        log_factory_event(
            run_id=run_id,
            status="failed",
            error_code=exc.code,
            errors=exc.errors,
        )
        return _failed_factory_result(
            run_id=run_id,
            run_dir=run_dir,
            company_name=company_name,
            web_domain=web_domain,
            start_time=start_time,
            error=exc.reason,
            error_code=exc.code,
            errors=exc.errors,
        )
    except StorageHealthcheckError as exc:
        return _failed_storage_result(
            run_id=run_id,
            run_dir=run_dir,
            company_name=company_name,
            web_domain=web_domain,
            start_time=start_time,
            error=str(exc),
            error_code=exc.error_code,
            component=exc.component,
        )
    except ValueError as exc:
        # Defensive fallback: unexpected ValueError that did not come through
        # the IntakeValidationError contract. Should not happen in practice;
        # if it does, surface it without a fabricated error_code.
        log_intake_event(
            run_id=run_id,
            status="failed",
            error_code="",
            rejection_reason=str(exc),
        )
        return _failed_intake_result(
            run_id=run_id,
            run_dir=run_dir,
            company_name=company_name,
            web_domain=web_domain,
            start_time=start_time,
            error=str(exc),
        )
    except Exception as exc:
        init_context = RunContext(
            run_id=run_id,
            intake={"company_name": company_name, "web_domain": web_domain},
        )
        _record_phase(init_context, "initialize")
        return _pipeline_error_result(
            run_id=run_id,
            run_dir=run_dir,
            company_name=company_name,
            web_domain=web_domain,
            start_time=start_time,
            error_message=str(exc),
            run_context=init_context,
            messages=[],
        )

    try:
        supervisor = _build_supervisor_brief(state, on_message=on_message)
        handoff_snapshot = state.run_context.resolution_state.get("step1_handoff", {})
        if not handoff_allows_department_routing(handoff_snapshot):
            return _pipeline_error_result(
                run_id=run_id,
                run_dir=run_dir,
                messages=state.messages,
                run_context=state.run_context,
                start_time=start_time,
                error="Step-1 handoff validation failed.",
                failed_phase="step1_handoff",
                error_code="step1_handoff_invalid",
                error_detail={
                    "validation_errors": handoff_snapshot.get("validation_errors", []),
                    "readiness": handoff_snapshot.get("readiness", STEP1_BLOCKED),
                },
            )
        first_pass = _run_first_pass(state, brief=supervisor.brief, on_message=on_message)
        _run_auto_close_if_required(state, first_pass=first_pass, on_message=on_message)
        synthesis_phase = _run_synthesis_phase(
            state,
            brief=supervisor.brief,
            first_pass=first_pass,
            on_message=on_message,
        )
        finalization = _finalize_readiness(
            state,
            synthesis_phase=synthesis_phase,
            company_name=company_name,
            on_message=on_message,
        )
        # Report assembly is delegated to _assemble_report_and_export via state.agents["report_writer"].
        return _assemble_report_and_export(
            state,
            finalization=finalization,
            company_name=company_name,
            web_domain=web_domain,
            on_message=on_message,
        )
    except Exception as exc:
        return _pipeline_error_result(
            run_id=run_id,
            run_dir=run_dir,
            company_name=company_name,
            web_domain=web_domain,
            start_time=start_time,
            error_message=str(exc),
            run_context=state.run_context,
            messages=state.messages,
        )

