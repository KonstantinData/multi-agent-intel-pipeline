"""Run-based follow-up loading, routing, and answering.

CHG-08 — Run brain rehydration.

When a follow-up question arrives for a completed run, the full run brain
is loaded from the stored ``run_context.json``.  This includes:

- ``department_packages`` — the final package per department
- ``department_run_states`` — the full artifact history per department:
    task_artifacts, review_artifacts, decision_artifacts,
    strategy_changes, judge_escalations, coding_support_used
- ``department_workspaces`` — per-department evidence summaries

The answer is grounded in the rehydrated run brain:
- Primary evidence: task_artifacts and decision_artifacts from the run
- Secondary evidence: finalized pipeline_data
- Fallback evidence: department packages
- Unresolved: open_questions from decisions and package gates

The difference between:
- Answering from known run context: uses stored artifacts (this module)
- Performing new research: uses ``DepartmentRuntime.run_followup()``

The ``requires_additional_research`` flag signals which path is needed.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.exporters.json_export import export_follow_up
from src.models.schemas import FollowUpAnswer
from src.orchestration.envelope import resolve_raw_package
from src.orchestration.otel_step_consumer import build_otel_step_consumer_from_env
from src.orchestration.run_paths import RUNS_DIR, resolve_run_dir, validate_run_id
from src.orchestration.step_bus import (
    InMemoryStepSink,
    StepBus,
    StepConsumer,
    StepEmitter,
    StepTraceConsumer,
    runtime_steps_enabled,
)
from src.storage.run_artifacts import (
    load_latest_run_artifact_json,
    should_use_postgres_run_artifacts,
)
from src.utils import dedup_safe as _dedup_safe

logger = logging.getLogger(__name__)


def _followup_step_emitter(run_id: str, run_context: dict[str, Any]) -> StepEmitter:
    trace = run_context.setdefault("step_trace", [])
    if not isinstance(trace, list):
        trace = []
        run_context["step_trace"] = trace
    consumers: list[StepConsumer] = [
        StepTraceConsumer(trace),
        InMemoryStepSink(),
    ]
    otel_consumer = build_otel_step_consumer_from_env()
    if otel_consumer is not None:
        consumers.append(otel_consumer)
    return StepEmitter(
        run_id=run_id,
        bus=StepBus(consumers),
        enabled=runtime_steps_enabled(),
    )

# ---------------------------------------------------------------------------
# Run brain loading (CHG-08)
# ---------------------------------------------------------------------------

def load_run_artifact(run_id: str) -> dict[str, Any]:
    """Load the full run brain for a completed run.

    Returns a dict with:
    - run_id
    - run_dir (Path)
    - pipeline_data  (final PipelineData)
    - run_context    (full run brain including department_run_states)
    """
    if should_use_postgres_run_artifacts():
        pipeline_data = load_latest_run_artifact_json(
            run_id=run_id,
            artifact_type="pipeline_data",
        )
        run_context = load_latest_run_artifact_json(
            run_id=run_id,
            artifact_type="run_context",
        )
        run_dir = resolve_run_dir(run_id, runs_root=RUNS_DIR)
    else:
        run_dir = resolve_run_dir(run_id, runs_root=RUNS_DIR, must_exist=True)
        pipeline_data = json.loads((run_dir / "pipeline_data.json").read_text(encoding="utf-8"))
        run_context = json.loads((run_dir / "run_context.json").read_text(encoding="utf-8"))
    logger.info(
        "load_run_artifact: run_id=%s departments=%s",
        run_id,
        list(run_context.get("short_term_memory", {}).get("department_run_states", {}).keys()),
    )
    _followup_step_emitter(str(run_id).strip(), run_context).emit_narrated(
        phase="follow_up",
        actor="FollowUpRuntime",
        actor_role="runtime",
        goal="Load persisted run artifacts for follow-up",
        action_kind="capability_call",
        action_target="run_artifact.load",
        action_payload={
            "pipeline_data_present": bool(pipeline_data),
            "run_context_present": bool(run_context),
            "department_run_state_count": len(
                run_context.get("short_term_memory", {}).get("department_run_states", {})
            ),
        },
        capability_calls=[
            {"kind": "load_run_artifact", "artifact_type": "pipeline_data"},
            {"kind": "load_run_artifact", "artifact_type": "run_context"},
        ],
        decision="loaded",
        reflection="Persisted run artifacts loaded for follow-up.",
        stop_reason="follow_up_artifacts_loaded",
    )
    return {
        "run_id": str(run_id).strip(),
        "run_dir": run_dir,
        "pipeline_data": pipeline_data,
        "run_context": run_context,
    }


# ---------------------------------------------------------------------------
# Run brain evidence extraction helpers (CHG-08)
# ---------------------------------------------------------------------------

def _extract_task_evidence(
    department_run_state: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Extract accepted facts and open questions from a DepartmentRunState dict.

    Returns (evidence_list, unresolved_list).
    """
    evidence: list[str] = []
    unresolved: list[str] = []

    decisions_by_task = department_run_state.get("decision_artifacts", {})
    reviews_by_task = department_run_state.get("review_artifacts", {})

    # From decision artifacts — terminal unresolved decisions take precedence.
    blocked_tasks: set[str] = set()
    for task_key, decisions in decisions_by_task.items():
        if decisions:
            latest = decisions[-1]
            if latest.get("outcome") in {"closed_unresolved", "blocked_by_dependency"}:
                blocked_tasks.add(task_key)
                unresolved.extend(latest.get("open_questions", [])[:3])

    # From task artifacts — facts from the latest accepted/non-blocked attempt.
    for task_key, artifacts in department_run_state.get("task_artifacts", {}).items():
        if not artifacts or task_key in blocked_tasks:
            continue
        latest_decision = (decisions_by_task.get(task_key) or [])[-1:] or []
        latest_review = (reviews_by_task.get(task_key) or [])[-1:] or []
        if latest_decision:
            if latest_decision[0].get("outcome") not in {"accepted", "accepted_with_gaps"}:
                continue
        elif latest_review and latest_review[0].get("approved") is not True:
            continue
        latest = artifacts[-1]
        evidence.extend(latest.get("facts", [])[:3])

    # From review artifacts — accepted points per task
    for task_key, reviews in reviews_by_task.items():
        if reviews and task_key not in blocked_tasks:
            latest = reviews[-1]
            if latest.get("approved") is True:
                evidence.extend(latest.get("accepted_points", [])[:2])

    return _dedup_safe(list(filter(None, evidence))), _dedup_safe(list(filter(None, unresolved)))


class FollowUpEvidenceResolver:
    """Resolve follow-up grounding in documented priority order."""

    def resolve(
        self,
        *,
        department: str,
        pipeline_candidates: list[str],
        pipeline_data: dict[str, Any],
        run_context: dict[str, Any],
    ) -> tuple[list[str], list[str]]:
        run_state = _get_department_run_state(run_context, department)
        artifact_evidence, artifact_unresolved = _extract_task_evidence(run_state)
        package = (
            run_context.get("short_term_memory", {})
            .get("department_packages", {})
            .get(department, {})
        )
        raw_package = resolve_raw_package(package)
        package_evidence = [
            *[str(item) for item in raw_package.get("accepted_points", []) if str(item).strip()],
            str(raw_package.get("summary", "") or "").strip(),
            str((raw_package.get("report_segment", {}) or {}).get("narrative_summary", "") or "").strip(),
        ]
        package_open = raw_package.get("open_questions", [])
        evidence = [
            *artifact_evidence,
            *[str(item) for item in pipeline_candidates if str(item).strip()],
            *[item for item in package_evidence if item and item != "n/v"],
        ]
        unresolved = [
            *artifact_unresolved,
            *[str(item) for item in package_open if str(item).strip()],
        ]
        return _dedup_safe(evidence), _dedup_safe(unresolved)


def _get_department_run_state(run_context: dict[str, Any], department: str) -> dict[str, Any]:
    """Safely retrieve a department's run state from the run brain."""
    return (
        run_context
        .get("short_term_memory", {})
        .get("department_run_states", {})
        .get(department, {})
    )


# ---------------------------------------------------------------------------
# Department-specific answer functions (CHG-08: grounded in run brain)
# ---------------------------------------------------------------------------

def _company_answer(
    question: str, pipeline_data: dict[str, Any], run_context: dict[str, Any]
) -> tuple[str, list[str], list[str]]:
    profile = pipeline_data.get("company_profile", {})

    resolved_evidence, artifact_unresolved = FollowUpEvidenceResolver().resolve(
        department="CompanyDepartment",
        pipeline_candidates=[profile.get("description", "")],
        pipeline_data=pipeline_data,
        run_context=run_context,
    )

    evidence = resolved_evidence
    unresolved = _dedup_safe(artifact_unresolved)
    answer = (
        f"Company follow-up for '{question}': "
        f"{profile.get('company_name', 'The target company')} is described as {profile.get('description', 'n/v')}. "
        f"Economic context: {profile.get('economic_situation', {}).get('assessment', 'n/v')}."
    )
    return answer, [item for item in evidence if item], unresolved


def _market_answer(
    question: str, pipeline_data: dict[str, Any], run_context: dict[str, Any]
) -> tuple[str, list[str], list[str]]:
    analysis = pipeline_data.get("industry_analysis", {})
    resolved_evidence, artifact_unresolved = FollowUpEvidenceResolver().resolve(
        department="MarketDepartment",
        pipeline_candidates=[analysis.get("assessment", ""), analysis.get("demand_outlook", "")],
        pipeline_data=pipeline_data,
        run_context=run_context,
    )

    evidence = resolved_evidence
    unresolved = _dedup_safe(artifact_unresolved)
    answer = (
        f"Market follow-up for '{question}': "
        f"Industry assessment: {analysis.get('assessment', 'n/v')}. "
        f"Demand outlook: {analysis.get('demand_outlook', 'n/v')}."
    )
    return answer, [item for item in evidence if item], unresolved


def _buyer_answer(
    question: str, pipeline_data: dict[str, Any], run_context: dict[str, Any]
) -> tuple[str, list[str], list[str]]:
    network = pipeline_data.get("market_network", {})
    resolved_evidence, artifact_unresolved = FollowUpEvidenceResolver().resolve(
        department="BuyerDepartment",
        pipeline_candidates=[
            network.get("peer_competitors", {}).get("assessment", ""),
            network.get("downstream_buyers", {}).get("assessment", ""),
        ],
        pipeline_data=pipeline_data,
        run_context=run_context,
    )

    peers = network.get("peer_competitors", {}).get("companies", [])
    buyers = network.get("downstream_buyers", {}).get("companies", [])
    evidence = resolved_evidence
    unresolved = _dedup_safe(artifact_unresolved)
    answer = (
        f"Buyer follow-up for '{question}': "
        f"Peer assessment: {network.get('peer_competitors', {}).get('assessment', 'n/v')}. "
        f"Buyer assessment: {network.get('downstream_buyers', {}).get('assessment', 'n/v')}. "
        f"Visible peer or buyer count: {len(peers)} peers and {len(buyers)} downstream buyers."
    )
    return answer, [item for item in evidence if item], unresolved


def _contact_answer(
    question: str, pipeline_data: dict[str, Any], run_context: dict[str, Any]
) -> tuple[str, list[str], list[str]]:
    section = pipeline_data.get("contact_intelligence", {})
    resolved_evidence, artifact_unresolved = FollowUpEvidenceResolver().resolve(
        department="ContactDepartment",
        pipeline_candidates=[section.get("narrative_summary", "")],
        pipeline_data=pipeline_data,
        run_context=run_context,
    )

    contacts = section.get("prioritized_contacts", section.get("contacts", []))
    evidence = [
        *resolved_evidence,
        *[f"{c.get('name', '')} — {c.get('rolle_titel', '')} at {c.get('firma', '')}" for c in contacts[:3]],
    ]
    unresolved = _dedup_safe(artifact_unresolved)
    answer = (
        f"Contact intelligence follow-up for '{question}': "
        f"{section.get('narrative_summary', 'n/v')} "
        f"Prioritized contacts found: {len(contacts)}. "
        f"Coverage quality: {section.get('coverage_quality', 'n/v')}."
    )
    return answer, [item for item in evidence if item], unresolved


def _synthesis_answer(
    question: str, pipeline_data: dict[str, Any], run_context: dict[str, Any]
) -> tuple[str, list[str], list[str]]:
    synthesis = pipeline_data.get("synthesis", {})
    package = (
        run_context.get("short_term_memory", {})
        .get("department_packages", {})
        .get("SynthesisDepartment", {})
    )
    # RF2-1: read from raw_package via resolver, not from envelope root
    raw = resolve_raw_package(package)
    evidence = [
        synthesis.get("executive_summary", ""),
        synthesis.get("opportunity_assessment_summary", ""),
        raw.get("opportunity_assessment", ""),
        *(synthesis.get("research_backlog", synthesis.get("next_steps", []))[:2]),
    ]
    unresolved = synthesis.get("key_risks", [])[:3]
    answer = (
        f"Synthesis follow-up for '{question}': "
        f"{raw.get('executive_summary', synthesis.get('executive_summary', 'n/v'))} "
        f"Opportunity: {raw.get('opportunity_assessment', synthesis.get('opportunity_assessment_summary', 'n/v'))}."
    )
    return answer, [item for item in evidence if item], unresolved


def _cross_domain_answer(
    question: str, pipeline_data: dict[str, Any], run_context: dict[str, Any]
) -> tuple[str, list[str], list[str]]:
    synthesis = pipeline_data.get("synthesis", {})
    quality = pipeline_data.get("quality_review", {})
    evidence = [
        synthesis.get("executive_summary", ""),
        synthesis.get("opportunity_assessment_summary", ""),
        *(synthesis.get("research_backlog", synthesis.get("next_steps", []))[:2]),
    ]
    unresolved = quality.get("open_gaps", [])[:3]
    answer = (
        f"Cross-domain follow-up for '{question}': "
        f"{synthesis.get('opportunity_assessment_summary', 'n/v')} "
        f"Recommended next steps: {', '.join(synthesis.get('research_backlog', synthesis.get('next_steps', []))[:3]) or 'n/v'}."
    )
    return answer, [item for item in evidence if item], unresolved


# ---------------------------------------------------------------------------
# Main answer entrypoint
# ---------------------------------------------------------------------------

def answer_follow_up(
    *,
    run_id: str,
    route: str,
    question: str,
    pipeline_data: dict[str, Any],
    run_context: dict[str, Any],
) -> dict[str, Any]:
    """Answer a follow-up question grounded in the rehydrated run brain.

    CHG-08: each department answer function now reads from ``department_run_states``
    (the full artifact history) in addition to the final package and pipeline_data.
    """
    safe_run_id = validate_run_id(run_id)
    step_emitter = _followup_step_emitter(safe_run_id, run_context)
    logger.info(
        "answer_follow_up: run_id=%s route=%s question_len=%d",
        safe_run_id, route, len(question),
    )
    step_emitter.emit_narrated(
        phase="follow_up",
        actor="Supervisor",
        actor_role="supervisor",
        goal="Route follow-up question",
        action_kind="state_transition",
        action_target="follow_up.route",
        action_payload={"route": route, "question_length": len(question)},
        state_transitions=[{"kind": "follow_up_route_recorded", "route": route}],
        decision=route,
        reflection="Follow-up question routed to a department answer path.",
        stop_reason="follow_up_routed",
    )

    if route == "MarketDepartment":
        answer, evidence, unresolved = _market_answer(question, pipeline_data, run_context)
    elif route == "BuyerDepartment":
        answer, evidence, unresolved = _buyer_answer(question, pipeline_data, run_context)
    elif route == "ContactDepartment":
        answer, evidence, unresolved = _contact_answer(question, pipeline_data, run_context)
    elif route == "SynthesisDepartment":
        answer, evidence, unresolved = _synthesis_answer(question, pipeline_data, run_context)
    else:
        route = "CompanyDepartment"
        answer, evidence, unresolved = _company_answer(question, pipeline_data, run_context)

    payload = FollowUpAnswer(
        run_id=safe_run_id,
        routed_to=route,
        question=question,
        answer=answer,
        evidence_used=evidence[:5],
        unresolved_points=unresolved,
        requires_additional_research=bool(unresolved),
    ).model_dump(mode="json")
    step_emitter.emit_narrated(
        phase="follow_up",
        actor=route,
        actor_role="department_answer_path",
        goal="Generate follow-up answer from stored run memory",
        action_kind="state_transition",
        action_target="follow_up.answer",
        action_payload={
            "route": route,
            "evidence_count": len(evidence),
            "unresolved_count": len(unresolved),
            "requires_additional_research": bool(unresolved),
        },
        state_transitions=[
            {
                "kind": "follow_up_answer_recorded",
                "route": route,
                "requires_additional_research": bool(unresolved),
            }
        ],
        decision="additional_research_required" if unresolved else "answered_from_memory",
        reflection="Follow-up answer generated from stored run context.",
        stop_reason="follow_up_answered",
    )
    if unresolved:
        step_emitter.emit_narrated(
            phase="follow_up",
            actor="FollowUpRuntime",
            actor_role="runtime",
            goal="Record additional-research handoff requirement",
            action_kind="state_transition",
            action_target="follow_up.additional_research_handoff",
            action_payload={"route": route, "unresolved_count": len(unresolved)},
            state_transitions=[
                {
                    "kind": "follow_up_additional_research_required",
                    "route": route,
                    "unresolved_count": len(unresolved),
                }
            ],
            decision="handoff_required",
            reflection="Follow-up requires additional research beyond stored run memory.",
            stop_reason="additional_research_required",
        )
    export_follow_up(safe_run_id, payload, runs_root=RUNS_DIR)
    return payload


def run_bounded_follow_up(
    *,
    run_id: str,
    run_context: dict[str, Any],
    pipeline_data: dict[str, Any],
    public_gap_questions: list[Any],
    max_questions: int = 4,
) -> dict[str, Any]:
    """Run bounded, run-brain-grounded follow-up for public evidence gaps.

    This helper is used inside the live run (before final export) and therefore
    does not write follow-up artifacts to disk.
    """
    candidates: list[dict[str, Any]] = []
    for item in public_gap_questions:
        if isinstance(item, dict):
            question = str(item.get("question", "")).strip()
            if question:
                candidates.append({
                    "question": question,
                    "gap_id": str(item.get("gap_id", "")).strip(),
                    "question_ids": [str(qid) for qid in item.get("question_ids", []) if str(qid).strip()],
                })
        else:
            question = str(item).strip()
            if question:
                candidates.append({"question": question, "gap_id": "", "question_ids": []})
    queue = candidates[:max_questions]
    attempts: list[dict[str, Any]] = []

    for candidate in queue:
        question = candidate["question"]
        lowered = question.lower()
        if any(token in lowered for token in ("contact", "buyer firm", "decision maker", "reach")):
            route = "ContactDepartment"
            answer, evidence, unresolved = _contact_answer(question, pipeline_data, run_context)
        elif any(token in lowered for token in ("market", "demand", "supply", "industry")):
            route = "MarketDepartment"
            answer, evidence, unresolved = _market_answer(question, pipeline_data, run_context)
        elif any(token in lowered for token in ("buyer", "competitor", "redeployment", "monetization")):
            route = "BuyerDepartment"
            answer, evidence, unresolved = _buyer_answer(question, pipeline_data, run_context)
        else:
            route = "CompanyDepartment"
            answer, evidence, unresolved = _company_answer(question, pipeline_data, run_context)

        resolved = bool(evidence) and not bool(unresolved)
        attempts.append({
            "route": route,
            "question": question,
            "gap_id": candidate.get("gap_id", ""),
            "question_ids": list(candidate.get("question_ids", [])),
            "answer": answer,
            "evidence_used": evidence[:3],
            "unresolved_points": unresolved[:2],
            "resolved": resolved,
            "resolved_gap_ids": [candidate.get("gap_id", "")] if resolved and candidate.get("gap_id") else [],
            "resolved_question_ids": list(candidate.get("question_ids", [])) if resolved else [],
        })

    unresolved_after = [
        item["question"]
        for item in attempts
        if not item.get("resolved", False)
    ]
    resolved_questions = [
        item["question"]
        for item in attempts
        if item.get("resolved", False)
    ]
    resolved_gap_ids = _dedup_safe([
        gap_id
        for item in attempts
        for gap_id in item.get("resolved_gap_ids", [])
        if gap_id
    ])
    resolved_question_ids = _dedup_safe([
        question_id
        for item in attempts
        for question_id in item.get("resolved_question_ids", [])
        if question_id
    ])
    stop_reason = "all_questions_resolved" if not unresolved_after else "bounded_budget_exhausted"
    return {
        "run_id": run_id,
        "attempted_questions": len(attempts),
        "max_questions": max_questions,
        "closure_pass": 1,  # nosec B105 - iteration counter, not a password
        "max_closure_passes": 1,
        "stop_reason": stop_reason,
        "attempts": attempts,
        "resolved_questions": resolved_questions,
        "resolved_gap_ids": resolved_gap_ids,
        "resolved_question_ids": resolved_question_ids,
        "remaining_public_gaps": unresolved_after,
    }
