"""Pipeline runner with callback support for live UI updates."""
from __future__ import annotations

import autogen
import json
import logging
import os
import re
import threading
import traceback
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic, sleep
from typing import Any, Callable
from urllib.parse import urlparse

from autogen.exception_utils import NoEligibleSpeakerError
from pydantic import ValidationError

from src.models.schemas import (
    CompanyProfile,
    IndustryAnalysis,
    MarketNetwork,
    QualityReview,
    SynthesisReport,
)
from src.exporters.json_export import export_run

# --- Logging setup ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")

# Agent display metadata
AGENT_META = {
    "Admin":                {"icon": "👤", "color": "#6c757d"},
    "Concierge":            {"icon": "🛎️", "color": "#0d6efd"},
    "ConciergeCritic":      {"icon": "🧪", "color": "#6f42c1"},
    "RepairPlanner":        {"icon": "🛠️", "color": "#a16207"},
    "CompanyIntelligence":  {"icon": "🏢", "color": "#198754"},
    "CompanyIntelligenceCritic": {"icon": "🧪", "color": "#146c43"},
    "StrategicSignals":     {"icon": "📡", "color": "#6610f2"},
    "StrategicSignalsCritic": {"icon": "🧪", "color": "#7c3aed"},
    "MarketNetwork":        {"icon": "🌐", "color": "#fd7e14"},
    "MarketNetworkCritic":  {"icon": "🧪", "color": "#b45309"},
    "EvidenceQA":           {"icon": "🔍", "color": "#dc3545"},
    "EvidenceQACritic":     {"icon": "🧪", "color": "#991b1b"},
    "Synthesis":            {"icon": "📋", "color": "#20c997"},
    "SynthesisCritic":      {"icon": "🧪", "color": "#0f766e"},
    "chat_manager":         {"icon": "⚙️", "color": "#adb5bd"},
}

PIPELINE_STEPS = [
    ("Concierge", "Intake validieren"),
    ("CompanyIntelligence", "Firmenprofil erstellen"),
    ("StrategicSignals", "Branchenanalyse"),
    ("MarketNetwork", "Käufernetzwerk ermitteln"),
    ("EvidenceQA", "Evidenz prüfen"),
    ("Synthesis", "Briefing erstellen"),
]
WORKFLOW_PRODUCERS = {
    "Concierge",
    "CompanyIntelligence",
    "StrategicSignals",
    "MarketNetwork",
    "EvidenceQA",
    "Synthesis",
}
STAGE_RECOVERY_CONFIG = {
    "Concierge": {
        "stage_key": "concierge",
        "critic_name": "ConciergeCritic",
        "attempts_key": "concierge_attempts",
        "next_target_name": "CompanyIntelligence",
        "critic_agent_key": "concierge_critic",
    },
    "CompanyIntelligence": {
        "stage_key": "company_intelligence",
        "critic_name": "CompanyIntelligenceCritic",
        "attempts_key": "company_intelligence_attempts",
        "next_target_name": "StrategicSignals",
        "critic_agent_key": "company_intelligence_critic",
    },
    "StrategicSignals": {
        "stage_key": "strategic_signals",
        "critic_name": "StrategicSignalsCritic",
        "attempts_key": "strategic_signals_attempts",
        "next_target_name": "MarketNetwork",
        "critic_agent_key": "strategic_signals_critic",
    },
    "MarketNetwork": {
        "stage_key": "market_network",
        "critic_name": "MarketNetworkCritic",
        "attempts_key": "market_network_attempts",
        "next_target_name": "EvidenceQA",
        "critic_agent_key": "market_network_critic",
    },
    "EvidenceQA": {
        "stage_key": "evidence_qa",
        "critic_name": "EvidenceQACritic",
        "attempts_key": "evidence_qa_attempts",
        "next_target_name": "Synthesis",
        "critic_agent_key": "evidence_qa_critic",
    },
    "Synthesis": {
        "stage_key": "synthesis",
        "critic_name": "SynthesisCritic",
        "attempts_key": "synthesis_attempts",
        "next_target_name": "Terminate",
        "critic_agent_key": "synthesis_critic",
    },
}

COMPANY_SOURCE_MAX_AGE_DAYS = 730
INDUSTRY_SOURCE_MAX_AGE_DAYS = 540
BUYER_SOURCE_MAX_AGE_DAYS = 730
STAGE_CONTRACTS = {
    "company_profile": {"min_sources": 1},
    "industry_analysis": {"min_sources": 1},
    "market_network": {"min_sources": 0},
}


def _env_int_with_min(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw is not None else int(default)
    except (TypeError, ValueError):
        value = int(default)
    return max(int(minimum), value)


MAX_STAGE_ATTEMPTS = _env_int_with_min("PIPELINE_MAX_STAGE_ATTEMPTS", 4, 2)
MAX_TOOL_CALLS = _env_int_with_min("PIPELINE_MAX_TOOL_CALLS", 48, 12)
MAX_RUN_SECONDS = _env_int_with_min("PIPELINE_MAX_RUN_SECONDS", 1200, 600)
COMPANY_INTELLIGENCE_MAX_STAGE_TOOL_CALLS = _env_int_with_min("PIPELINE_COMPANY_INTELLIGENCE_MAX_TOOL_CALLS", 4, 3)
STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS = _env_int_with_min("PIPELINE_STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS", 6, 4)
MARKET_NETWORK_MAX_STAGE_TOOL_CALLS = _env_int_with_min("PIPELINE_MARKET_NETWORK_MAX_STAGE_TOOL_CALLS", 6, 4)
MAX_CONSECUTIVE_TOOL_TURNS_PER_AGENT = int(
    _env_int_with_min(
        "PIPELINE_MAX_CONSECUTIVE_TOOL_TURNS",
        max(7, STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS + 1, MARKET_NETWORK_MAX_STAGE_TOOL_CALLS + 1),
        5,
    )
)
COMPANY_INTELLIGENCE_MAX_CONSECUTIVE_TOOL_TURNS = int(
    _env_int_with_min(
        "PIPELINE_COMPANY_INTELLIGENCE_MAX_CONSECUTIVE_TOOL_TURNS",
        COMPANY_INTELLIGENCE_MAX_STAGE_TOOL_CALLS + 1,
        COMPANY_INTELLIGENCE_MAX_STAGE_TOOL_CALLS,
    )
)
STRATEGIC_SIGNALS_MAX_CONSECUTIVE_TOOL_TURNS = int(
    _env_int_with_min(
        "PIPELINE_STRATEGIC_SIGNALS_MAX_CONSECUTIVE_TOOL_TURNS",
        STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS + 1,
        STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS,
    )
)
MARKET_NETWORK_MAX_CONSECUTIVE_TOOL_TURNS = int(
    _env_int_with_min(
        "PIPELINE_MARKET_NETWORK_MAX_CONSECUTIVE_TOOL_TURNS",
        MARKET_NETWORK_MAX_STAGE_TOOL_CALLS + 1,
        MARKET_NETWORK_MAX_STAGE_TOOL_CALLS,
    )
)
MAX_GROUPCHAT_ROUNDS = 1 + (len(PIPELINE_STEPS) * MAX_STAGE_ATTEMPTS * 3) + 2
GROUPCHAT_POLL_INTERVAL_SECONDS = 0.2
GROUPCHAT_STOP_GRACE_SECONDS = float(os.environ.get("PIPELINE_GROUPCHAT_STOP_GRACE_SECONDS", "20"))
GROUPCHAT_AUTO_RESUME_LIMIT = 2
GROUPCHAT_CRITIC_RECOVERY_LIMIT = 2
# AG2 0.11.x documents prepare_group_chat(...) as a 13-item tuple. Keep this
# unpacking isolated here so version drift fails loudly in one place.
PREPARE_GROUP_CHAT_RESULT_LEN = 13
PREPARE_GROUP_CHAT_FIELD_INDEXES = {
    "context_variables": 3,
    "groupchat": 7,
    "manager": 8,
    "processed_messages": 9,
    "last_agent": 10,
}


@dataclass
class PreparedGroupChat:
    context_variables: Any
    groupchat: Any
    manager: Any
    processed_messages: list[dict[str, Any]]
    last_agent: Any


def build_pipeline_task(company_name: str, web_domain: str) -> str:
    """Build the shared end-to-end task prompt for the AutoGen pipeline."""
    return (
        f"Research the company '{company_name}' (domain: {web_domain}) "
        f"for a Liquisto sales meeting preparation.\n\n"
        f"Run the full pipeline:\n"
        f"1. Concierge: Validate intake and build research brief\n"
        f"2. CompanyIntelligence: Build comprehensive company profile\n"
        f"3. StrategicSignals: Analyze industry trends and overcapacity signals\n"
        f"4. MarketNetwork: Identify buyers across 4 tiers "
        f"(Peer Competitors, Downstream Buyers, Service Providers, Cross-Industry)\n"
        f"5. EvidenceQA: Review evidence quality and flag gaps\n"
        f"6. Synthesis: Compile final briefing with pro/contra arguments "
        f"for Kaufen/Kommission/Ablehnen and Liquisto service area relevance\n\n"
        f"Each agent MUST output structured JSON matching the defined schemas. "
        f"Do not output anything else besides the JSON."
    )


def run_pipeline(
    company_name: str,
    web_domain: str,
    on_message: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run the full pipeline. Calls on_message(event) for each agent message."""
    from src.config import get_llm_config
    from src.agents.definitions import (
        ENFORCE_STRATEGIC_SIGNALS_SOURCE_PACK_KEY,
        create_agents,
        create_group_pattern,
    )

    emitted_system_errors: set[str] = set()
    emitted_duplicate_turn_warnings: set[str] = set()

    def _emit(event_type: str, agent: str, content: str):
        event = {
            "type": event_type,
            "agent": agent,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "meta": AGENT_META.get(agent, {"icon": "⚙️", "color": "#adb5bd"}),
        }
        collected_messages.append(event)
        if on_message:
            on_message(event)

    def _emit_error(content: str) -> None:
        if content in emitted_system_errors:
            return
        emitted_system_errors.add(content)
        _emit("error", "System", content)

    collected_messages: list[dict[str, Any]] = []
    chat_history: list[dict[str, Any]] = []
    budget_state = _build_budget_state()

    log.info("=" * 60)
    log.info("PIPELINE START: %s (%s)", company_name, web_domain)
    log.info("=" * 60)
    _emit("debug", "System", f"Pipeline gestartet für: {company_name} ({web_domain})")

    try:
        log.debug("Loading LLM config...")
        llm_config = get_llm_config()
        model = llm_config.config_list[0].model
        log.info("LLM config loaded: model=%s", model)
        _emit("debug", "System", f"LLM Model: {model}")
    except Exception as e:
        log.error("Failed to load LLM config: %s", e)
        _emit_error(f"LLM Config Fehler: {e}")
        raise

    try:
        log.debug("Creating agents...")
        agents = create_agents()
        log.info("Agents created: %s", list(agents.keys()))
        _emit("debug", "System", f"Agenten erstellt: {', '.join(agents.keys())}")
    except Exception as e:
        log.error("Failed to create agents: %s", e)
        _emit_error(f"Agent-Erstellung fehlgeschlagen: {e}")
        raise

    try:
        log.debug("Creating AG2 workflow pattern...")
        pattern = create_group_pattern(agents)
        prepared_chat = _prepare_group_chat(
            pattern,
            max_rounds=budget_state["max_groupchat_rounds"],
            messages=build_pipeline_task(company_name, web_domain),
        )
        prepared_chat.context_variables.set(ENFORCE_STRATEGIC_SIGNALS_SOURCE_PACK_KEY, True)
        log.info("AG2 pattern created: max_round=%s", prepared_chat.groupchat.max_round)
        _emit("debug", "System", f"AG2 Pattern erstellt: max_round={prepared_chat.groupchat.max_round}")
    except Exception as e:
        log.error("Failed to create AG2 workflow pattern: %s", e)
        _emit_error(f"AG2 Pattern Fehler: {e}")
        raise

    task = (
        prepared_chat.processed_messages[-1]["content"]
        if prepared_chat.processed_messages
        else build_pipeline_task(company_name, web_domain)
    )
    log.info("Task built (%d chars)", len(task))
    _emit("debug", "System", "Task erstellt, starte AG2 Handoff-Workflow...")
    _emit(
        "debug",
        "System",
        (
            "Budget aktiv: "
            f"{budget_state['max_groupchat_rounds']} GroupChat-Runden, "
            f"{budget_state['max_stage_attempts']} Versuche je Producer/Critic-Stufe, "
            f"{budget_state['max_tool_calls']} Tool-Calls, "
            f"{budget_state['max_run_seconds']}s Laufzeit."
        ),
    )

    try:
        chat_result_holder: dict[str, Any] = {}
        chat_error_holder: dict[str, BaseException] = {}
        sender, initial_message, clear_history = _resolve_group_chat_entrypoint(prepared_chat, fallback_message=task)
        interruption_reason: str | None = None

        def _run_groupchat() -> None:
            try:
                chat_result_holder["result"] = sender.initiate_chat(
                    prepared_chat.manager,
                    message=initial_message,
                    clear_history=clear_history,
                    summary_method=pattern.summary_method,
                    silent=True,
                )
            except BaseException as exc:
                chat_error_holder["error"] = exc

        worker = threading.Thread(target=_run_groupchat, daemon=True)
        worker.start()
        emitted_count = 0
        while worker.is_alive():
            emitted_count = _emit_groupchat_messages(prepared_chat.groupchat.messages, emitted_count, _emit)
            if _run_budget_exceeded(budget_state):
                interruption_reason = (
                    "Laufzeitbudget überschritten "
                    f"({budget_state['max_run_seconds']}s). Stoppe den Workflow nach dem aktuellen AG2-Zug."
                )
                _request_group_chat_stop(prepared_chat, sender)
                _emit_error(interruption_reason)
                break
            tool_calls_used = _count_tool_calls_from_chat_messages(prepared_chat.groupchat.messages)
            if tool_calls_used >= budget_state["max_tool_calls"]:
                interruption_reason = (
                    "Tool-Budget überschritten "
                    f"({tool_calls_used}/{budget_state['max_tool_calls']}). Stoppe den Workflow nach dem aktuellen AG2-Zug."
                )
                _request_group_chat_stop(prepared_chat, sender)
                _emit_error(interruption_reason)
                break
            stalled = _detect_stalled_tool_agent(prepared_chat.groupchat.messages)
            if stalled:
                stalled_agent, stalled_threshold = stalled
                interruption_reason = (
                    f"Agent-Schleife erkannt: {stalled_agent} hat {stalled_threshold} "
                    "aufeinanderfolgende Tool-Zuege ohne strukturierten Abschluss erzeugt. Stoppe den Workflow."
                )
                _request_group_chat_stop(prepared_chat, sender)
                _emit_error(interruption_reason)
                break
            duplicate_producer = _detect_duplicate_structured_producer_turn(prepared_chat.groupchat.messages)
            if duplicate_producer and duplicate_producer not in emitted_duplicate_turn_warnings:
                emitted_duplicate_turn_warnings.add(duplicate_producer)
                _emit(
                    "debug",
                    "System",
                    (
                        f"Warnung: {duplicate_producer} hat mehrfach strukturierte Outputs vor dem Critic erzeugt. "
                        "Der letzte strukturierte Output bleibt maßgeblich, sofern der Critic danach sauber übernimmt."
                    ),
                )
            sleep(GROUPCHAT_POLL_INTERVAL_SECONDS)

        if interruption_reason:
            worker.join(timeout=GROUPCHAT_STOP_GRACE_SECONDS)
            emitted_count = _emit_groupchat_messages(prepared_chat.groupchat.messages, emitted_count, _emit)
            if worker.is_alive():
                interruption_reason = (
                    f"{interruption_reason} Der aktuelle AG2-Zug lief auch nach {GROUPCHAT_STOP_GRACE_SECONDS:.0f}s "
                    "Grace-Timeout weiter; verwende den bis dahin vorliegenden Teillauf."
                )
                log.warning("Pipeline stop request did not stop the workflow cleanly; exporting partial run.")
                _emit_error(interruption_reason)

        if worker.is_alive():
            log.warning("Worker thread still alive after partial-stop handling; continuing with current snapshot.")
        else:
            worker.join()
        emitted_count = _emit_groupchat_messages(prepared_chat.groupchat.messages, emitted_count, _emit)

        if "error" in chat_error_holder:
            raise chat_error_holder["error"]

        auto_resume_attempts = 0
        while (
            not interruption_reason
            and auto_resume_attempts < GROUPCHAT_AUTO_RESUME_LIMIT
            and _should_auto_resume_groupchat(prepared_chat.groupchat.messages)
        ):
            auto_resume_attempts += 1
            _emit(
                "debug",
                "System",
                (
                    "AG2-Fortsetzung: Workflow endete auf einem strukturierten Producer-Output ohne nachfolgenden Critic-Handoff. "
                    f"Starte Resume-Versuch {auto_resume_attempts}/{GROUPCHAT_AUTO_RESUME_LIMIT}."
                ),
            )
            try:
                resume_sender, resume_message = prepared_chat.manager.resume(
                    messages=prepared_chat.groupchat.messages,
                    silent=True,
                )
            except NoEligibleSpeakerError:
                break
            except Exception as exc:
                log.warning("Resume attempt failed while preparing continuation: %s", exc)
                break

            try:
                resume_sender.initiate_chat(
                    prepared_chat.manager,
                    message=resume_message,
                    clear_history=False,
                    summary_method=pattern.summary_method,
                    silent=True,
                )
            except NoEligibleSpeakerError:
                break
            except BaseException as exc:
                log.warning("Resume attempt failed during continuation: %s", exc)
                break

            emitted_count = _emit_groupchat_messages(prepared_chat.groupchat.messages, emitted_count, _emit)

        critic_recovery_attempts = 0
        while (
            not interruption_reason
            and critic_recovery_attempts < GROUPCHAT_CRITIC_RECOVERY_LIMIT
            and _should_auto_resume_groupchat(prepared_chat.groupchat.messages)
        ):
            injected_critic = _inject_missing_critic_turn(prepared_chat, agents)
            if not injected_critic:
                break
            critic_recovery_attempts += 1
            _emit(
                "debug",
                "System",
                (
                    "AG2-Handoff-Recovery: Der Critic-Turn wurde nach einem haengengebliebenen Producer-Output "
                    f"deterministisch als {injected_critic} nachgezogen ({critic_recovery_attempts}/{GROUPCHAT_CRITIC_RECOVERY_LIMIT})."
                ),
            )
            emitted_count = _emit_groupchat_messages(prepared_chat.groupchat.messages, emitted_count, _emit)
            try:
                resume_sender, resume_message = prepared_chat.manager.resume(
                    messages=prepared_chat.groupchat.messages,
                    silent=True,
                )
            except NoEligibleSpeakerError:
                break
            except Exception as exc:
                log.warning("Critic recovery resume failed while preparing continuation: %s", exc)
                break

            try:
                resume_sender.initiate_chat(
                    prepared_chat.manager,
                    message=resume_message,
                    clear_history=False,
                    summary_method=pattern.summary_method,
                    silent=True,
                )
            except NoEligibleSpeakerError:
                break
            except BaseException as exc:
                log.warning("Critic recovery resume failed during continuation: %s", exc)
                break

            emitted_count = _emit_groupchat_messages(prepared_chat.groupchat.messages, emitted_count, _emit)

        chat_result = chat_result_holder.get("result")
        chat_history = list(getattr(chat_result, "chat_history", None) or prepared_chat.groupchat.messages)
        log.info("AG2 workflow completed with %d chat messages", len(chat_history))
        _emit("debug", "System", f"Chat beendet. {len(chat_history)} Nachrichten.")
    except Exception as e:
        log.error("AG2 workflow FAILED: %s\n%s", e, traceback.format_exc())
        _emit_error(f"Chat-Fehler: {e}")
        raise

    result = {"chat_history": chat_history}
    pipeline_messages = _normalize_chat_history(result)
    pipeline_data = _extract_pipeline_data(pipeline_messages)
    workflow_completed = _workflow_completed(chat_history, pipeline_data)
    readiness = _assess_research_usability(pipeline_data)
    pipeline_data["research_readiness"] = readiness
    run_error = interruption_reason if 'interruption_reason' in locals() else None
    if not workflow_completed and not run_error:
        run_error = _build_incomplete_run_message(chat_history, pipeline_data)
    completed = bool(workflow_completed and not run_error and readiness.get("research_usable") is True)
    if run_error:
        run_status = "incomplete"
    elif readiness.get("research_usable") is True:
        run_status = "completed"
    else:
        run_status = "completed_but_not_usable"
    usage_summary = _collect_usage_summary(agents)
    filled = [k for k, v in pipeline_data.items() if k != "validation_errors" and v]
    log.info("Parsed pipeline data. Filled keys: %s", filled)
    _emit("debug", "System", f"Ergebnisse geparst: {', '.join(filled) or 'keine'}")
    if run_error:
        _emit_error(run_error)
    elif run_status == "completed_but_not_usable":
        _emit(
            "debug",
            "System",
            "Workflow abgeschlossen, aber der Brief ist noch nicht meeting-tauglich: "
            + "; ".join(readiness.get("reasons", [])[:4]),
        )
    if usage_summary["total"].get("total_cost"):
        _emit(
            "debug",
            "System",
            (
                "Usage erfasst: "
                f"${usage_summary['total']['total_cost']:.4f}, "
                f"{usage_summary['total'].get('prompt_tokens', 0)} Prompt-Tokens, "
                f"{usage_summary['total'].get('completion_tokens', 0)} Completion-Tokens."
            ),
        )

    validation_errors = pipeline_data.get("validation_errors", [])
    if validation_errors:
        for error in validation_errors:
            agent = error.get("agent", "unknown")
            section = error.get("section", "unknown")
            details = error.get("details", "Schema validation failed")
            log.warning("Validation failed for %s/%s: %s", agent, section, details)
            _emit_error(f"Schema-Validierung fehlgeschlagen ({agent}/{section}): {details}")

    # --- Step 8: Export ---
    try:
        run_id = uuid.uuid4().hex[:12]
        run_dir = export_run(
            run_id,
            result,
            pipeline_data=pipeline_data,
            run_meta_extra={
                "status": run_status,
                "completed": completed,
                "workflow_completed": bool(workflow_completed and not run_error),
                "research_usable": bool(readiness.get("research_usable") is True),
                "research_usability_reasons": list(readiness.get("reasons", [])),
                "error": run_error,
                "usage": usage_summary,
                "budget": {
                    "max_groupchat_rounds": budget_state["max_groupchat_rounds"],
                    "max_stage_attempts": budget_state["max_stage_attempts"],
                    "max_tool_calls": budget_state["max_tool_calls"],
                    "tool_calls_used": _count_tool_calls_from_chat_messages(chat_history),
                    "groupchat_rounds_used": len(chat_history),
                    "max_run_seconds": budget_state["max_run_seconds"],
                    "elapsed_seconds": round(monotonic() - budget_state["started_at"], 3),
                },
            },
        )
        log.info("Exported to: %s", run_dir)
        _emit("debug", "System", f"Export: {run_dir}")
    except Exception as e:
        log.error("Export failed: %s", e)
        run_id = "export_failed"
        run_dir = ""

    log.info("=" * 60)
    log.info("PIPELINE DONE: run_id=%s, messages=%d", run_id, len(collected_messages))
    log.info("=" * 60)

    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "messages": collected_messages,
        "pipeline_data": pipeline_data,
        "completed": completed,
        "workflow_completed": bool(workflow_completed and not run_error),
        "research_usable": bool(readiness.get("research_usable") is True),
        "research_usability_reasons": list(readiness.get("reasons", [])),
        "status": run_status,
        "error": run_error,
        "usage": usage_summary,
        "budget": {
            "max_groupchat_rounds": budget_state["max_groupchat_rounds"],
            "max_stage_attempts": budget_state["max_stage_attempts"],
            "max_tool_calls": budget_state["max_tool_calls"],
            "tool_calls_used": _count_tool_calls_from_chat_messages(chat_history),
            "groupchat_rounds_used": len(chat_history),
            "max_run_seconds": budget_state["max_run_seconds"],
            "elapsed_seconds": round(monotonic() - budget_state["started_at"], 3),
        },
    }


def _prepare_group_chat(pattern: Any, max_rounds: int, messages: list[dict[str, Any]] | str) -> PreparedGroupChat:
    prepared = pattern.prepare_group_chat(max_rounds=max_rounds, messages=messages)
    return _coerce_prepared_group_chat(prepared)


def _coerce_prepared_group_chat(prepared: Any) -> PreparedGroupChat:
    """Unpack the documented AG2 0.11.x prepare_group_chat tuple shape."""
    if not isinstance(prepared, tuple) or len(prepared) != PREPARE_GROUP_CHAT_RESULT_LEN:
        installed_ag2 = getattr(autogen, "__version__", "unknown")
        actual_shape = len(prepared) if isinstance(prepared, tuple) else type(prepared).__name__
        raise RuntimeError(
            "Unexpected AG2 prepare_group_chat result shape. "
            f"Expected the documented AG2 0.11.x {PREPARE_GROUP_CHAT_RESULT_LEN}-item tuple, "
            f"got {actual_shape} (installed ag2/autogen: {installed_ag2})."
        )

    return PreparedGroupChat(
        context_variables=prepared[PREPARE_GROUP_CHAT_FIELD_INDEXES["context_variables"]],
        groupchat=prepared[PREPARE_GROUP_CHAT_FIELD_INDEXES["groupchat"]],
        manager=prepared[PREPARE_GROUP_CHAT_FIELD_INDEXES["manager"]],
        processed_messages=list(prepared[PREPARE_GROUP_CHAT_FIELD_INDEXES["processed_messages"]]),
        last_agent=prepared[PREPARE_GROUP_CHAT_FIELD_INDEXES["last_agent"]],
    )


def _resolve_group_chat_entrypoint(
    prepared_chat: PreparedGroupChat,
    fallback_message: str,
) -> tuple[Any, dict[str, Any] | str, bool]:
    clear_history = len(prepared_chat.processed_messages) <= 1

    if len(prepared_chat.processed_messages) > 1:
        sender, initial_message = prepared_chat.manager.resume(
            messages=prepared_chat.processed_messages,
            silent=True,
        )
        if sender is None:
            raise ValueError("AG2 pattern did not select an initial agent.")
        return sender, initial_message, clear_history

    if prepared_chat.last_agent is None:
        raise ValueError("AG2 pattern did not prepare an initial speaker.")

    initial_message = prepared_chat.processed_messages[0] if prepared_chat.processed_messages else fallback_message
    return prepared_chat.last_agent, initial_message, clear_history


def _run_budget_exceeded(budget_state: dict[str, Any]) -> bool:
    max_run_seconds = int(budget_state.get("max_run_seconds", 0) or 0)
    if max_run_seconds <= 0:
        return False
    return (monotonic() - budget_state["started_at"]) >= max_run_seconds


def _request_group_chat_stop(prepared_chat: PreparedGroupChat, sender: Any) -> None:
    def _raise_no_speaker(*_args: Any, **_kwargs: Any) -> Any:
        raise NoEligibleSpeakerError("Pipeline stop requested.")

    for participant in getattr(prepared_chat.groupchat, "agents", []):
        if hasattr(participant, "stop_reply_at_receive"):
            participant.stop_reply_at_receive()
    if hasattr(prepared_chat.manager, "stop_reply_at_receive"):
        prepared_chat.manager.stop_reply_at_receive(sender)
        prepared_chat.manager.stop_reply_at_receive()
    if hasattr(sender, "stop_reply_at_receive"):
        sender.stop_reply_at_receive()
    prepared_chat.manager._is_termination_msg = lambda _message: True
    prepared_chat.groupchat.select_speaker = _raise_no_speaker
    if hasattr(prepared_chat.groupchat, "max_round"):
        prepared_chat.groupchat.max_round = min(
            int(prepared_chat.groupchat.max_round),
            max(len(getattr(prepared_chat.groupchat, "messages", [])), 1),
        )

def _build_budget_state() -> dict[str, Any]:
    return {
        "started_at": monotonic(),
        "max_groupchat_rounds": MAX_GROUPCHAT_ROUNDS,
        "max_stage_attempts": MAX_STAGE_ATTEMPTS,
        "max_tool_calls": MAX_TOOL_CALLS,
        "max_run_seconds": MAX_RUN_SECONDS,
    }


def _emit_groupchat_messages(
    messages: list[dict[str, Any]],
    emitted_count: int,
    emit: Callable[[str, str, str], None],
) -> int:
    for msg in messages[emitted_count:]:
        agent = msg.get("name", msg.get("role", "unknown"))
        content = msg.get("content", "") or ""
        emit("agent_message", agent, str(content))
        emitted_count += 1
    return emitted_count


def _count_tool_calls_from_chat_messages(messages: list[dict[str, Any]]) -> int:
    total = 0
    for msg in messages:
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            total += len(tool_calls)
    return total


def _tool_turn_threshold_for_agent(agent_name: str) -> int:
    if agent_name == "CompanyIntelligence":
        return COMPANY_INTELLIGENCE_MAX_CONSECUTIVE_TOOL_TURNS
    if agent_name == "StrategicSignals":
        return STRATEGIC_SIGNALS_MAX_CONSECUTIVE_TOOL_TURNS
    if agent_name == "MarketNetwork":
        return MARKET_NETWORK_MAX_CONSECUTIVE_TOOL_TURNS
    return MAX_CONSECUTIVE_TOOL_TURNS_PER_AGENT


def _detect_stalled_tool_agent(messages: list[dict[str, Any]]) -> tuple[str, int] | None:
    streak_agent: str | None = None
    streak = 0
    for msg in reversed(messages):
        name = msg.get("name", msg.get("role", "unknown"))
        if name == "_Group_Tool_Executor":
            continue
        tool_calls = msg.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            break
        if streak_agent is None:
            streak_agent = str(name)
        if str(name) != streak_agent:
            break
        streak += 1
        threshold = _tool_turn_threshold_for_agent(streak_agent)
        if threshold > 0 and streak >= threshold:
            return streak_agent, threshold
    return None


def _detect_duplicate_structured_producer_turn(messages: list[dict[str, Any]]) -> str | None:
    previous_name: str | None = None
    for msg in messages:
        name = str(msg.get("name", msg.get("role", "unknown")) or "unknown")
        if name in {"_Group_Tool_Executor", "chat_manager"}:
            continue
        if name not in WORKFLOW_PRODUCERS:
            previous_name = None
            continue
        content = str(msg.get("content", "") or "")
        if _try_parse_json(content) is None:
            previous_name = None
            continue
        if previous_name is None:
            previous_name = name
            continue
        if name == previous_name:
            return name
        previous_name = name
    return None


def _workflow_completed(chat_history: list[dict[str, Any]], pipeline_data: dict[str, Any]) -> bool:
    if not chat_history:
        return False
    required_sections = ("company_profile", "industry_analysis", "market_network", "synthesis")
    if not all(bool(pipeline_data.get(section)) for section in required_sections):
        return False

    last_named = _last_workflow_actor_name(chat_history)
    if last_named == "Admin":
        return True
    if last_named != "SynthesisCritic":
        return False

    for msg in reversed(chat_history):
        name = str(msg.get("name", msg.get("role", "unknown")) or "unknown")
        if name != "SynthesisCritic":
            continue
        payload = _try_parse_json(str(msg.get("content", "") or ""))
        return bool(isinstance(payload, dict) and payload.get("approved") is True)
    return False


def _assess_research_usability(pipeline_data: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    profile = pipeline_data.get("company_profile", {})
    industry = pipeline_data.get("industry_analysis", {})
    market = pipeline_data.get("market_network", {})
    quality = pipeline_data.get("quality_review", {})

    missing_company_basics = [
        label
        for label, key in (
            ("Rechtsform", "legal_form"),
            ("Gegruendet", "founded"),
            ("Hauptsitz", "headquarters"),
        )
        if _is_nv(profile.get(key))
    ]
    if missing_company_basics:
        reasons.append(
            "Firmenprofil unvollstaendig: "
            + ", ".join(missing_company_basics)
            + " fehlen."
        )

    economic = profile.get("economic_situation", {}) if isinstance(profile, dict) else {}
    missing_economic = [
        label
        for label, value in (
            ("Umsatztrend", economic.get("revenue_trend")),
            ("Profitabilitaet", economic.get("profitability")),
            ("Finanzdruck", economic.get("financial_pressure")),
            ("Einschaetzung", economic.get("assessment")),
        )
        if _is_nv(value)
    ]
    if len(missing_economic) >= 3:
        reasons.append(
            "Wirtschaftslage nicht verwertbar: "
            + ", ".join(missing_economic)
            + " stehen auf n/v."
        )

    industry_sources = _as_list(industry.get("sources", []))
    if not industry_sources:
        reasons.append("Branchenanalyse ohne belastbare externe Quellen.")
    elif _sources_lack_external_market_evidence(industry_sources, profile):
        reasons.append("Branchenanalyse ohne belastbare externe Quellen.")

    missing_industry = [
        label
        for label, value in (
            ("Marktgroesse", industry.get("market_size")),
            ("Wachstumsrate", industry.get("growth_rate")),
            ("Nachfrageausblick", industry.get("demand_outlook")),
            ("Ueberschussbestand-Indikatoren", industry.get("excess_stock_indicators")),
        )
        if _is_nv(value)
    ]
    if len(missing_industry) >= 3:
        reasons.append(
            "Branchenanalyse nicht verwertbar: "
            + ", ".join(missing_industry)
            + " fehlen."
        )

    buyer_total = _count_market_buyers(market)
    if buyer_total == 0:
        reasons.append("MarketNetwork ohne belastbare Buyer-, Competitor- oder Service-Treffer.")

    evidence_health = str(quality.get("evidence_health", "n/v") or "n/v").strip().lower()
    if evidence_health in {"niedrig", "low", "n/v", "unklar"}:
        reasons.append(f"Evidenzqualitaet ist nur {quality.get('evidence_health', 'n/v')}.")

    return {
        "research_usable": len(reasons) == 0,
        "reasons": reasons,
    }


def _build_incomplete_run_message(chat_history: list[dict[str, Any]], pipeline_data: dict[str, Any]) -> str:
    missing_sections = [
        section
        for section in ("company_profile", "industry_analysis", "market_network", "synthesis")
        if not pipeline_data.get(section)
    ]
    last_named = _last_workflow_actor_name(chat_history)
    if missing_sections:
        return (
            "Workflow unvollständig beendet. Fehlende Kernartefakte: "
            f"{', '.join(missing_sections)}. Letzter Agent: {last_named}."
        )
    return f"Workflow unvollständig beendet. Letzter Agent: {last_named}."


def _last_workflow_actor_name(chat_history: list[dict[str, Any]]) -> str:
    ignored_names = {"_Group_Tool_Executor", "chat_manager"}
    for msg in reversed(chat_history):
        name = str(msg.get("name", msg.get("role", "unknown")) or "unknown")
        if name in ignored_names:
            continue
        return name
    if not chat_history:
        return "unknown"
    return str(chat_history[-1].get("name", chat_history[-1].get("role", "unknown")) or "unknown")


def _should_auto_resume_groupchat(chat_history: list[dict[str, Any]]) -> bool:
    last_name = _last_workflow_actor_name(chat_history)
    if last_name not in {
        "Concierge",
        "CompanyIntelligence",
        "StrategicSignals",
        "MarketNetwork",
        "EvidenceQA",
        "Synthesis",
    }:
        return False

    for msg in reversed(chat_history):
        name = str(msg.get("name", msg.get("role", "unknown")) or "unknown")
        if name in {"_Group_Tool_Executor", "chat_manager"}:
            continue
        content = str(msg.get("content", "") or "")
        return _try_parse_json(content) is not None
    return False


def _inject_missing_critic_turn(
    prepared_chat: PreparedGroupChat,
    agents: dict[str, Any],
) -> str | None:
    last_name = _last_workflow_actor_name(prepared_chat.groupchat.messages)
    config = STAGE_RECOVERY_CONFIG.get(last_name)
    if not config:
        return None

    last_content = ""
    for msg in reversed(prepared_chat.groupchat.messages):
        name = str(msg.get("name", msg.get("role", "unknown")) or "unknown")
        if name != last_name:
            continue
        content = str(msg.get("content", "") or "")
        if _try_parse_json(content) is None:
            continue
        last_content = content
        break
    if not last_content:
        return None

    from src.agents.definitions import _pre_critic_check

    precheck = _pre_critic_check(
        output=last_content,
        context_variables=prepared_chat.context_variables,
        stage_key=config["stage_key"],
        producer_name=last_name,
        critic_name=config["critic_name"],
        next_target_name=config["next_target_name"],
        attempts_key=config["attempts_key"],
    )
    target_name = getattr(getattr(precheck, "target", None), "agent_name", None)
    if target_name != config["critic_name"]:
        return None

    critic = agents.get(config["critic_agent_key"])
    if critic is None or not hasattr(critic, "generate_reply"):
        return None

    critic_reply = critic.generate_reply(messages=prepared_chat.groupchat.messages, sender=prepared_chat.manager)
    if critic_reply is None:
        return None
    if isinstance(critic_reply, dict):
        critic_content = json.dumps(critic_reply)
    else:
        critic_content = str(critic_reply)
    if not critic_content.strip():
        return None

    prepared_chat.groupchat.messages.append(
        {
            "content": critic_content,
            "name": config["critic_name"],
            "role": "user",
        }
    )
    return config["critic_name"]


def _collect_usage_summary(agents: dict[str, Any]) -> dict[str, Any]:
    per_agent: dict[str, Any] = {}
    total_actual = _empty_usage_totals()
    total_total = _empty_usage_totals()

    for agent_name, agent in agents.items():
        actual = _normalize_usage_summary(agent.get_actual_usage() if hasattr(agent, "get_actual_usage") else None)
        total = _normalize_usage_summary(agent.get_total_usage() if hasattr(agent, "get_total_usage") else None)
        if actual["total_cost"] or actual["models"]:
            per_agent[agent_name] = {
                "actual": actual,
                "total": total,
            }
        total_actual = _merge_usage_totals(total_actual, actual)
        total_total = _merge_usage_totals(total_total, total)

    return {
        "actual": total_actual,
        "total": total_total,
        "agents": per_agent,
    }


def _empty_usage_totals() -> dict[str, Any]:
    return {
        "total_cost": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "models": {},
    }


def _normalize_usage_summary(summary: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _empty_usage_totals()
    if not summary:
        return normalized

    normalized["total_cost"] = round(float(summary.get("total_cost", 0.0) or 0.0), 8)
    for model_name, values in summary.items():
        if model_name == "total_cost" or not isinstance(values, dict):
            continue
        prompt_tokens = int(values.get("prompt_tokens", 0) or 0)
        completion_tokens = int(values.get("completion_tokens", 0) or 0)
        total_tokens = int(values.get("total_tokens", prompt_tokens + completion_tokens) or 0)
        cost = round(float(values.get("cost", 0.0) or 0.0), 8)
        normalized["models"][model_name] = {
            "cost": cost,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        normalized["prompt_tokens"] += prompt_tokens
        normalized["completion_tokens"] += completion_tokens
        normalized["total_tokens"] += total_tokens

    return normalized


def _merge_usage_totals(base: dict[str, Any], addition: dict[str, Any]) -> dict[str, Any]:
    merged = {
        "total_cost": round(base["total_cost"] + addition["total_cost"], 8),
        "prompt_tokens": base["prompt_tokens"] + addition["prompt_tokens"],
        "completion_tokens": base["completion_tokens"] + addition["completion_tokens"],
        "total_tokens": base["total_tokens"] + addition["total_tokens"],
        "models": deepcopy(base["models"]),
    }
    for model_name, values in addition["models"].items():
        current = merged["models"].setdefault(
            model_name,
            {"cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )
        current["cost"] = round(current["cost"] + values["cost"], 8)
        current["prompt_tokens"] += values["prompt_tokens"]
        current["completion_tokens"] += values["completion_tokens"]
        current["total_tokens"] += values["total_tokens"]
    return merged


def _extract_pipeline_data(messages: list[dict]) -> dict[str, Any]:
    """Try to extract structured JSON from agent messages."""
    data: dict[str, Any] = {
        "company_profile": {},
        "industry_analysis": {},
        "market_network": {},
        "quality_review": {},
        "research_readiness": {},
        "synthesis": {},
        "validation_errors": [],
    }

    agent_to_key = {
        "CompanyIntelligence": "company_profile",
        "StrategicSignals": "industry_analysis",
        "MarketNetwork": "market_network",
        "EvidenceQA": "quality_review",
        "Synthesis": "synthesis",
    }
    key_to_model = {
        "company_profile": CompanyProfile,
        "industry_analysis": IndustryAnalysis,
        "market_network": MarketNetwork,
        "quality_review": QualityReview,
        "synthesis": SynthesisReport,
    }

    for msg in messages:
        agent = msg.get("agent", "")
        key = agent_to_key.get(agent)
        if not key:
            continue
        content = msg.get("content", "")
        parsed = _try_parse_json(content)
        if parsed is None:
            log.debug("No JSON parsed from %s (content len=%d)", agent, len(content))
            continue

        model = key_to_model[key]
        try:
            validated = model.model_validate(parsed)
        except ValidationError as exc:
            details = _format_validation_error(exc)
            data["validation_errors"].append(
                {
                    "agent": agent,
                    "section": key,
                    "details": details,
                }
            )
            log.warning("Schema validation failed for %s -> %s: %s", agent, key, details)
            continue

        log.debug("Parsed structured JSON from %s -> %s", agent, key)
        data[key] = validated.model_dump(mode="json")

    profile = data.get("company_profile", {})
    synthesis = data.get("synthesis", {})
    market = data.get("market_network", {})
    fallback_target_company = (
        profile.get("company_name")
        or synthesis.get("target_company")
        or "n/v"
    )
    if market and market.get("target_company") in ("", "n/v", None):
        market["target_company"] = fallback_target_company
    if synthesis and market:
        if not synthesis.get("total_peer_competitors"):
            synthesis["total_peer_competitors"] = len(market.get("peer_competitors", {}).get("companies", []))
        if not synthesis.get("total_downstream_buyers"):
            synthesis["total_downstream_buyers"] = len(market.get("downstream_buyers", {}).get("companies", []))
        if not synthesis.get("total_service_providers"):
            synthesis["total_service_providers"] = len(market.get("service_providers", {}).get("companies", []))
        if not synthesis.get("total_cross_industry_buyers"):
            synthesis["total_cross_industry_buyers"] = len(market.get("cross_industry_buyers", {}).get("companies", []))

    has_core_research = all(bool(data.get(section)) for section in ("company_profile", "industry_analysis", "market_network"))
    if data.get("quality_review") or data.get("synthesis") or has_core_research:
        _apply_quality_guardrails(data)
        data["research_readiness"] = _assess_research_usability(data)
    return data


def _apply_quality_guardrails(data: dict[str, Any]) -> None:
    """Add deterministic QA findings for stale sources and weak buyer evidence."""
    quality = data.setdefault("quality_review", {})
    synthesis = data.setdefault("synthesis", {})
    profile = data.get("company_profile", {})
    industry = data.get("industry_analysis", {})
    market = data.get("market_network", {})

    quality.setdefault("validated_agents", [])
    quality.setdefault("evidence_health", "n/v")
    quality.setdefault("open_gaps", [])
    quality.setdefault("recommendations", [])
    quality.setdefault("gap_details", [])
    synthesis.setdefault("key_risks", [])
    synthesis.setdefault("next_steps", [])

    gap_details = _normalize_gap_details(quality.get("gap_details", []))
    gaps = list(quality.get("open_gaps", []))
    recommendations = list(quality.get("recommendations", []))
    key_risks = list(synthesis.get("key_risks", []))
    next_steps = list(synthesis.get("next_steps", []))
    derived_gap_details: list[dict[str, str]] = []
    company_issue_detected = False
    industry_issue_detected = False

    derived_gap_details.extend(_enforce_stage_contracts(profile, industry, market))

    company_sources = _analyze_sources(profile.get("sources", []), COMPANY_SOURCE_MAX_AGE_DAYS)
    if profile:
        if company_sources["total"] == 0:
            company_issue_detected = True
            derived_gap_details.append(
                _make_gap_detail(
                    agent="CompanyIntelligence",
                    field_path="sources",
                    issue_type="missing_sources",
                    severity="significant",
                    summary="Firmenprofil ohne zitierte Quellen.",
                    recommendation="CompanyIntelligence: Primärquellen wie Website, Impressum, Jahresbericht oder Registerauszug ergänzen.",
                )
            )
        elif company_sources["fresh"] == 0:
            company_issue_detected = True
            derived_gap_details.append(
                _make_gap_detail(
                    agent="CompanyIntelligence",
                    field_path="sources",
                    issue_type="stale_sources",
                    severity="significant",
                    summary="Firmenprofil stützt sich auf veraltete Quellen für volatile Fakten.",
                    recommendation="CompanyIntelligence: Umsatz, Profitabilität und aktuelle Ereignisse mit frischen Primärquellen aktualisieren.",
                )
            )
            if profile.get("revenue") not in ("", "n/v", None):
                profile["revenue"] = "n/v"
            economic = profile.get("economic_situation", {})
            if isinstance(economic, dict):
                for key in ("revenue_trend", "profitability", "financial_pressure"):
                    if economic.get(key) not in ("", "n/v", None):
                        economic[key] = "n/v"
        if company_sources["unusable"] > 0:
            company_issue_detected = True
            derived_gap_details.append(
                _make_gap_detail(
                    agent="CompanyIntelligence",
                    field_path="sources",
                    issue_type="unsupported_source_wrapper",
                    severity="significant",
                    summary="Firmenprofil enthält Such- oder Aggregator-Wrapper statt belastbarer Quellseiten.",
                    recommendation="CompanyIntelligence: Auf direkte Publisher- oder Primärquellen umstellen.",
                )
            )

    industry_sources = _analyze_sources(industry.get("sources", []), INDUSTRY_SOURCE_MAX_AGE_DAYS)
    if industry:
        if industry_sources["total"] == 0:
            industry_issue_detected = True
            derived_gap_details.append(
                _make_gap_detail(
                    agent="StrategicSignals",
                    field_path="sources",
                    issue_type="missing_sources",
                    severity="significant",
                    summary="Branchenanalyse ohne belastbare Marktquellen.",
                    recommendation="StrategicSignals: Aktuelle Branchenquellen aus den letzten 12-18 Monaten ergänzen.",
                )
            )
            for key in ("market_size", "growth_rate"):
                if industry.get(key) not in ("", "n/v", None):
                    industry[key] = "n/v"
        elif industry_sources["unusable"] == industry_sources["total"]:
            industry_issue_detected = True
            derived_gap_details.append(
                _make_gap_detail(
                    agent="StrategicSignals",
                    field_path="sources",
                    issue_type="unsupported_source_wrapper",
                    severity="significant",
                    summary="Branchenanalyse stützt sich auf News-Aggregator-Wrapper statt direkte Publisher-Seiten.",
                    recommendation="StrategicSignals: Direkte Publisher- oder Trade-Publication-URLs nutzen und Wrapper-Links vermeiden.",
                )
            )
            for key in ("market_size", "growth_rate", "demand_outlook", "excess_stock_indicators"):
                if industry.get(key) not in ("", "n/v", None):
                    industry[key] = "n/v"
        elif _sources_lack_external_market_evidence(industry.get("sources", []), profile):
            industry_issue_detected = True
            derived_gap_details.append(
                _make_gap_detail(
                    agent="StrategicSignals",
                    field_path="sources",
                    issue_type="missing_external_market_sources",
                    severity="significant",
                    summary="Branchenanalyse stützt sich nur auf Company- oder Enzyklopädiequellen statt auf externe Marktquellen.",
                    recommendation="StrategicSignals: Mindestens eine direkte Trade-Publication-, Analysten- oder Marktreport-Quelle ergänzen.",
                )
            )
            for key in ("market_size", "growth_rate", "demand_outlook", "excess_stock_indicators"):
                if industry.get(key) not in ("", "n/v", None):
                    industry[key] = "n/v"
        elif industry_sources["fresh"] == 0:
            industry_issue_detected = True
            derived_gap_details.append(
                _make_gap_detail(
                    agent="StrategicSignals",
                    field_path="sources",
                    issue_type="stale_sources",
                    severity="significant",
                    summary="Branchenanalyse basiert auf veralteten Marktquellen.",
                    recommendation="StrategicSignals: Marktgröße, Wachstum und Nachfrageausblick mit frischen Branchenquellen aktualisieren.",
                )
            )
            for key in ("market_size", "growth_rate", "demand_outlook"):
                if industry.get(key) not in ("", "n/v", None):
                    industry[key] = "n/v"

    buyer_strength = _enforce_buyer_evidence(market)
    derived_gap_details.extend(buyer_strength["gap_details"])

    if company_issue_detected and company_sources["fresh"] == 0 and company_sources["total"] > 0:
        key_risks.append("Kern-Firmendaten basieren auf veralteten Quellen und sind für volatile Kennzahlen nicht belastbar.")
        next_steps.append("Vor dem Termin frische Primärquellen für Umsatz, Profitabilität und aktuelle Ereignisse prüfen.")
    if industry_issue_detected and industry_sources["fresh"] == 0:
        key_risks.append("Markt- und Nachfragesignale sind nicht aktuell genug für belastbare Schlüsse.")
        next_steps.append("Aktuelle Branchenreports oder Primärdaten zur Nachfrage- und Überkapazitätslage nachrecherchieren.")
    if buyer_strength["severity"] > 0:
        key_risks.append("Das Käufernetzwerk ist evidenzseitig zu schwach oder zu kandidat-lastig für harte Marktbehauptungen.")
        next_steps.append("Buyer-Longlist nur mit qualifizierten oder verifizierten Treffern aus Primärquellen nachschärfen.")
        summary = synthesis.get("buyer_market_summary", "")
        if summary:
            synthesis["buyer_market_summary"] = f"{summary} Evidenzseitig ist das Käufernetzwerk derzeit nur eingeschränkt belastbar."

    combined_gap_details = _dedupe_gap_details(gap_details + derived_gap_details)
    gaps.extend(_gap_details_to_open_gaps(combined_gap_details))
    recommendations.extend(_gap_details_to_recommendations(combined_gap_details))
    quality["gap_details"] = combined_gap_details
    quality["open_gaps"] = _dedupe_strings(gaps)
    quality["recommendations"] = _dedupe_strings(recommendations)
    synthesis["key_risks"] = _dedupe_strings(key_risks)
    synthesis["next_steps"] = _dedupe_strings(next_steps)
    quality["evidence_health"] = _merge_evidence_health(
        quality.get("evidence_health", "n/v"),
        _gap_detail_severity_score(combined_gap_details),
    )


def _enforce_buyer_evidence(market: dict[str, Any]) -> dict[str, Any]:
    severity = 0
    gap_details: list[dict[str, str]] = []
    strong_buyers = 0
    total_buyers = 0

    for tier_name, label in (
        ("peer_competitors", "Peer Competitors"),
        ("downstream_buyers", "Downstream Buyers"),
        ("service_providers", "Service Providers"),
        ("cross_industry_buyers", "Cross-Industry Buyers"),
    ):
        tier = market.get(tier_name, {})
        if not isinstance(tier, dict):
            continue
        tier_sources = tier.get("sources", [])
        tier_source_info = _analyze_sources(tier_sources, BUYER_SOURCE_MAX_AGE_DAYS)
        companies = tier.get("companies", [])
        if not isinstance(companies, list):
            continue

        if companies and tier_source_info["total"] == 0:
            severity += 1
            gap_details.append(
                _make_gap_detail(
                    agent="MarketNetwork",
                    field_path=f"{tier_name}.sources",
                    issue_type="missing_tier_sources",
                    severity="minor",
                    summary=f"{label} enthält Käufer ohne tierweite Quellen.",
                    recommendation=f"MarketNetwork: {label} mit konkreten Quellen oder direkter Buyer-Evidenz belegen.",
                )
            )
        elif companies and tier_source_info["fresh"] == 0:
            severity += 1
            gap_details.append(
                _make_gap_detail(
                    agent="MarketNetwork",
                    field_path=f"{tier_name}.sources",
                    issue_type="stale_tier_sources",
                    severity="minor",
                    summary=f"{label} basiert auf veralteten Quellen.",
                    recommendation=f"MarketNetwork: {label} mit frischer Buyer-Evidenz aktualisieren.",
                )
            )

        for index, buyer in enumerate(companies):
            if not isinstance(buyer, dict):
                continue
            total_buyers += 1
            buyer_source = buyer.get("source")
            buyer_source_info = _analyze_sources([buyer_source] if buyer_source else [], BUYER_SOURCE_MAX_AGE_DAYS)
            has_usable_source = (buyer_source_info["fresh"] > 0) or (tier_source_info["fresh"] > 0)
            if buyer.get("evidence_tier") in {"qualified", "verified"} and not has_usable_source:
                buyer["evidence_tier"] = "candidate"
                gap_details.append(
                    _make_gap_detail(
                        agent="MarketNetwork",
                        field_path=f"{tier_name}.companies[{index}]",
                        issue_type="unsupported_buyer_evidence",
                        severity="significant",
                        summary=f"{label}: {buyer.get('name', 'Buyer')} hatte kein belastbares Quellenfundament für qualifizierte oder verifizierte Evidenz.",
                        recommendation=f"MarketNetwork: {buyer.get('name', 'Buyer')} nur mit konkreter Buyer-Quelle qualifizieren oder verifizieren.",
                    )
                )
            if buyer.get("evidence_tier") in {"qualified", "verified"}:
                strong_buyers += 1

    peer_count = len(market.get("peer_competitors", {}).get("companies", [])) if isinstance(market.get("peer_competitors"), dict) else 0
    downstream_count = len(market.get("downstream_buyers", {}).get("companies", [])) if isinstance(market.get("downstream_buyers"), dict) else 0
    if peer_count == 0:
        severity += 1
        gap_details.append(
            _make_gap_detail(
                agent="MarketNetwork",
                field_path="peer_competitors.companies",
                issue_type="missing_peer_competitors",
                severity="significant",
                summary="Keine belastbaren Peer-Competitors identifiziert.",
                recommendation="MarketNetwork: Wettbewerber mit ähnlichen Produkten und konkreten Überschneidungen ergänzen.",
            )
        )
    if downstream_count == 0:
        severity += 1
        gap_details.append(
            _make_gap_detail(
                agent="MarketNetwork",
                field_path="downstream_buyers.companies",
                issue_type="missing_downstream_buyers",
                severity="significant",
                summary="Keine belastbaren Downstream-Buyer identifiziert.",
                recommendation="MarketNetwork: Abnehmer oder Aftermarket-Käufer mit klarer Produktpassung ergänzen.",
            )
        )
    if total_buyers > 0 and strong_buyers == 0:
        severity += 2
        gap_details.append(
            _make_gap_detail(
                agent="MarketNetwork",
                field_path="*",
                issue_type="candidate_only_buyer_network",
                severity="critical",
                summary="Buyer-Liste ist komplett kandidat-basiert und nicht belastbar.",
                recommendation="MarketNetwork: Mindestens einige Buyer mit qualifizierter oder verifizierter Evidenz absichern.",
            )
        )
    elif total_buyers > 0 and strong_buyers < max(2, total_buyers // 2):
        severity += 1
        gap_details.append(
            _make_gap_detail(
                agent="MarketNetwork",
                field_path="*",
                issue_type="candidate_heavy_buyer_network",
                severity="significant",
                summary="Buyer-Liste ist überwiegend kandidat-lastig.",
                recommendation="MarketNetwork: Die wichtigsten Buyer-Tiers mit stärkerer Evidenz absichern.",
            )
        )

    return {
        "severity": severity,
        "gap_details": gap_details,
    }


def _enforce_stage_contracts(
    profile: dict[str, Any],
    industry: dict[str, Any],
    market: dict[str, Any],
) -> list[dict[str, str]]:
    gap_details: list[dict[str, str]] = []

    if profile:
        key_people = profile.get("key_people", [])
        if isinstance(key_people, list):
            sanitized_people = []
            removed_placeholder = False
            for person in key_people:
                if not isinstance(person, dict):
                    continue
                name = str(person.get("name", "") or "").strip().lower()
                role = str(person.get("role", "") or "").strip().lower()
                if name in {"", "n/v"} and role in {"", "n/v"}:
                    removed_placeholder = True
                    continue
                sanitized_people.append(person)
            if removed_placeholder:
                profile["key_people"] = sanitized_people
                gap_details.append(
                    _make_gap_detail(
                        agent="CompanyIntelligence",
                        field_path="key_people",
                        issue_type="placeholder_key_people",
                        severity="minor",
                        summary="Nicht verifizierbare Platzhalter in key_people wurden entfernt; ohne Evidenz bleibt das Feld leer.",
                        recommendation="CompanyIntelligence: key_people nur mit echten Namen und Rollen befüllen, sonst leere Liste zurückgeben.",
                    )
                )

        gap_details.extend(
            _validate_source_records(
                agent="CompanyIntelligence",
                field_path="sources",
                sources=profile.get("sources", []),
            )
        )

    if industry:
        min_sources = STAGE_CONTRACTS["industry_analysis"]["min_sources"]
        industry_sources = _as_list(industry.get("sources", []))
        if len([source for source in industry_sources if isinstance(source, dict) and str(source.get("url", "") or "").strip()]) < min_sources:
            assessment = str(industry.get("assessment", "") or "")
            if not _assessment_explicitly_states_absence(assessment):
                gap_details.append(
                    _make_gap_detail(
                        agent="StrategicSignals",
                        field_path="assessment",
                        issue_type="missing_no_evidence_statement",
                        severity="significant",
                        summary="Branchenanalyse ohne Quellen muss im assessment explizit sagen, dass keine belastbaren Marktquellen gefunden wurden.",
                        recommendation="StrategicSignals: Bei leeren sources im assessment die fehlende Marktevidenz ausdrücklich benennen.",
                    )
                )
        gap_details.extend(
            _validate_source_records(
                agent="StrategicSignals",
                field_path="sources",
                sources=industry.get("sources", []),
            )
        )

    if market:
        for tier_name, label in (
            ("peer_competitors", "Peer Competitors"),
            ("downstream_buyers", "Downstream Buyers"),
            ("service_providers", "Service Providers"),
            ("cross_industry_buyers", "Cross-Industry Buyers"),
        ):
            tier = market.get(tier_name, {})
            if not isinstance(tier, dict):
                continue
            companies = tier.get("companies", [])
            if isinstance(companies, list) and not companies:
                assessment = str(tier.get("assessment", "") or "")
                if not _assessment_explicitly_states_absence(assessment):
                    gap_details.append(
                        _make_gap_detail(
                            agent="MarketNetwork",
                            field_path=f"{tier_name}.assessment",
                            issue_type="missing_empty_tier_explanation",
                            severity="minor",
                            summary=f"{label} ist leer, aber die Assessment-Begründung benennt die fehlende Evidenz nicht klar.",
                            recommendation=f"MarketNetwork: Bei leerem Tier in {label} explizit 'no credible evidence found' oder gleichwertig formulieren.",
                        )
                    )
            gap_details.extend(
                _validate_source_records(
                    agent="MarketNetwork",
                    field_path=f"{tier_name}.sources",
                    sources=tier.get("sources", []),
                )
            )
            for index, buyer in enumerate(_as_list(companies)):
                if not isinstance(buyer, dict):
                    continue
                buyer_source = buyer.get("source")
                if buyer_source:
                    gap_details.extend(
                        _validate_source_records(
                            agent="MarketNetwork",
                            field_path=f"{tier_name}.companies[{index}].source",
                            sources=[buyer_source],
                        )
                    )
    return gap_details


def _validate_source_records(
    *,
    agent: str,
    field_path: str,
    sources: Any,
) -> list[dict[str, str]]:
    gap_details: list[dict[str, str]] = []
    for index, source in enumerate(_as_list(sources)):
        if not isinstance(source, dict):
            continue
        url = str(source.get("url", "") or "").strip()
        publisher = str(source.get("publisher", "") or "").strip()
        title = str(source.get("title", "") or "").strip()
        accessed = str(source.get("accessed", "") or "").strip()
        missing_parts = [
            label
            for label, value in (
                ("url", url),
                ("publisher", publisher),
                ("title", title),
                ("accessed", accessed),
            )
            if not value
        ]
        if not missing_parts:
            continue
        gap_details.append(
            _make_gap_detail(
                agent=agent,
                field_path=f"{field_path}[{index}]",
                issue_type="incomplete_source_metadata",
                severity="minor",
                summary=f"Quelle in {field_path} ist unvollständig: es fehlen {', '.join(missing_parts)}.",
                recommendation=f"{agent}: Quellenmetadaten vollständig mit publisher, url, title und accessed ausgeben.",
            )
        )
    return gap_details


def _assessment_explicitly_states_absence(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    markers = (
        "no ",
        "not found",
        "no credible",
        "no specific",
        "no verified",
        "keine ",
        "nicht gefunden",
        "nicht verifiziert",
        "ohne ",
        "absence of",
        "insufficient evidence",
        "lack of",
    )
    return any(marker in normalized for marker in markers)


def _is_nv(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {"", "n/v", "na", "n.a.", "none", "null", "unknown", "unklar"}


def _count_market_buyers(market: dict[str, Any]) -> int:
    total = 0
    for tier_name in (
        "peer_competitors",
        "downstream_buyers",
        "service_providers",
        "cross_industry_buyers",
    ):
        tier = market.get(tier_name, {})
        if not isinstance(tier, dict):
            continue
        companies = tier.get("companies", [])
        if isinstance(companies, list):
            total += len(companies)
    return total


def _sources_are_company_only(sources: list[Any], profile: dict[str, Any]) -> bool:
    if not sources:
        return False
    website = str(profile.get("website", "") or "").strip()
    company_host = _host_for_url(website)
    if not company_host:
        return False
    company_host = company_host.removeprefix("www.")
    for source in sources:
        if not isinstance(source, dict):
            return False
        source_host = _host_for_url(str(source.get("url", "") or "").strip()).removeprefix("www.")
        if not source_host:
            return False
        if source_host == company_host or source_host.endswith(f".{company_host}"):
            continue
        return False
    return True


def _sources_lack_external_market_evidence(sources: list[Any], profile: dict[str, Any]) -> bool:
    if not sources:
        return False
    website = str(profile.get("website", "") or "").strip()
    company_host = _host_for_url(website).removeprefix("www.")
    if not company_host:
        return False
    saw_source = False
    for source in sources:
        if not isinstance(source, dict):
            return False
        source_host = _host_for_url(str(source.get("url", "") or "").strip()).removeprefix("www.")
        if not source_host:
            return False
        saw_source = True
        if source_host.endswith("wikipedia.org"):
            continue
        if source_host == company_host or source_host.endswith(f".{company_host}"):
            continue
        return False
    return saw_source


def _host_for_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    candidate = text if "://" in text else f"https://{text}"
    try:
        return urlparse(candidate).netloc.strip().lower()
    except ValueError:
        return ""


def _analyze_sources(sources: Any, max_age_days: int) -> dict[str, int]:
    total = 0
    fresh = 0
    stale = 0
    undated = 0
    unusable = 0

    for source in _as_list(sources):
        if not isinstance(source, dict):
            continue
        total += 1
        url = str(source.get("url", "") or "").strip()
        if _is_google_news_wrapper_source(url):
            unusable += 1
            continue
        parsed = _parse_accessed_date(source.get("accessed", ""))
        if parsed is None:
            undated += 1
            continue
        age_days = (datetime.now(timezone.utc).date() - parsed).days
        if age_days <= max_age_days:
            fresh += 1
        else:
            stale += 1

    return {
        "total": total,
        "fresh": fresh,
        "stale": stale,
        "undated": undated,
        "unusable": unusable,
    }


def _parse_accessed_date(value: Any):
    text = str(value or "").strip()
    if not text:
        return None
    candidates = [
        text.replace("Z", "+00:00"),
        f"{text}-01" if re.fullmatch(r"\d{4}-\d{2}", text) else "",
        f"{text}-01-01" if re.fullmatch(r"\d{4}", text) else "",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    return None


def _is_google_news_wrapper_source(url: str) -> bool:
    normalized = str(url or "").strip()
    if not normalized:
        return False
    parsed = urlparse(normalized)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    return host == "news.google.com" and (
        path.startswith("/rss/articles") or path.startswith("/articles") or path.startswith("/read")
    )


def _merge_evidence_health(current: str, severity: int) -> str:
    normalized = str(current or "n/v").strip().lower()
    ranking = {
        "hoch": 3,
        "high": 3,
        "mittel": 2,
        "medium": 2,
        "niedrig": 1,
        "low": 1,
        "n/v": 0,
        "unklar": 0,
    }
    current_rank = ranking.get(normalized, 0)
    target_rank = current_rank
    if severity >= 5:
        target_rank = min(current_rank or 3, 1)
    elif severity >= 2:
        target_rank = min(current_rank or 3, 2)
    elif severity == 0 and current_rank == 0:
        target_rank = 2
    label_by_rank = {
        3: "hoch",
        2: "mittel",
        1: "niedrig",
        0: "n/v",
    }
    return label_by_rank[target_rank]


def _make_gap_detail(
    *,
    agent: str,
    field_path: str,
    issue_type: str,
    severity: str,
    summary: str,
    recommendation: str = "",
) -> dict[str, str]:
    normalized_severity = str(severity or "significant").strip().lower()
    if normalized_severity not in {"critical", "significant", "minor"}:
        normalized_severity = "significant"
    return {
        "agent": agent,
        "field_path": field_path,
        "issue_type": issue_type,
        "severity": normalized_severity,
        "summary": summary,
        "recommendation": recommendation,
    }


def _normalize_gap_details(details: Any) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for detail in _as_list(details):
        if not isinstance(detail, dict):
            continue
        summary = str(detail.get("summary", "") or "").strip()
        if not summary:
            continue
        normalized.append(
            _make_gap_detail(
                agent=str(detail.get("agent", "EvidenceQA") or "EvidenceQA"),
                field_path=str(detail.get("field_path", "") or ""),
                issue_type=str(detail.get("issue_type", "qa_gap") or "qa_gap"),
                severity=str(detail.get("severity", "significant") or "significant"),
                summary=summary,
                recommendation=str(detail.get("recommendation", "") or ""),
            )
        )
    return normalized


def _dedupe_gap_details(details: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str, str, str]] = set()
    for detail in details:
        key = (
            str(detail.get("agent", "")),
            str(detail.get("field_path", "")),
            str(detail.get("issue_type", "")),
            str(detail.get("severity", "")),
            str(detail.get("summary", "")),
            str(detail.get("recommendation", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(detail)
    return deduped


def _gap_details_to_open_gaps(details: list[dict[str, str]]) -> list[str]:
    gaps: list[str] = []
    for detail in details:
        severity = str(detail.get("severity", "")).lower()
        if severity == "minor":
            continue
        agent = str(detail.get("agent", "")).strip()
        field_path = str(detail.get("field_path", "")).strip()
        summary = str(detail.get("summary", "")).strip()
        if not summary:
            continue
        prefix = agent
        if field_path and field_path != "*":
            prefix = f"{prefix} ({field_path})"
        gaps.append(f"{prefix}: {summary}" if prefix else summary)
    return gaps


def _gap_details_to_recommendations(details: list[dict[str, str]]) -> list[str]:
    recommendations: list[str] = []
    for detail in details:
        severity = str(detail.get("severity", "")).lower()
        if severity == "minor":
            continue
        recommendation = str(detail.get("recommendation", "")).strip()
        if recommendation:
            recommendations.append(recommendation)
    return recommendations


def _gap_detail_severity_score(details: list[dict[str, str]]) -> int:
    critical = 0
    significant = 0
    minor = 0
    for detail in details:
        severity = str(detail.get("severity", "")).lower()
        if severity == "critical":
            critical += 1
        elif severity == "significant":
            significant += 1
        elif severity == "minor":
            minor += 1
    return (critical * 5) + (significant * 2) + min(minor, 2)


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _normalize_chat_history(chat_result: Any) -> list[dict[str, str]]:
    """Convert a chat result into the minimal message format used by extraction."""
    chat_history = []
    if hasattr(chat_result, "chat_history"):
        chat_history = chat_result.chat_history
    elif isinstance(chat_result, dict):
        chat_history = chat_result.get("chat_history", [])

    normalized = []
    for msg in chat_history or []:
        normalized.append(
            {
                "agent": msg.get("name", msg.get("role", "unknown")),
                "content": msg.get("content", "") or "",
            }
        )
    return normalized


def _format_validation_error(exc: ValidationError) -> str:
    """Create a compact validation error summary for logs and UI."""
    errors = []
    for issue in exc.errors(include_url=False):
        location = ".".join(str(part) for part in issue.get("loc", ())) or "root"
        message = issue.get("msg", "invalid value")
        errors.append(f"{location}: {message}")
    if not errors:
        return "root: validation failed"
    return "; ".join(errors[:3])


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    if value in (None, ""):
        return []
    return [value]


def _try_parse_json(text: str) -> dict | None:
    """Try to extract JSON from text that may contain markdown fences."""
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            pass
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except (json.JSONDecodeError, TypeError):
                        pass
                    break
    return None
