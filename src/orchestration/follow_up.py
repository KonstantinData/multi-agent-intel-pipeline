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
- Secondary evidence: accepted_points from reviews
- Unresolved: open_questions from decisions and open task artifacts

The difference between:
- Answering from known run context: uses stored artifacts (this module)
- Performing new research: uses ``DepartmentRuntime.run_followup()``

The ``requires_additional_research`` flag signals which path is needed.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.exporters.json_export import export_follow_up
from src.models.schemas import FollowUpAnswer
from src.orchestration.envelope import resolve_open_questions, resolve_raw_package
from src.utils import dedup_safe as _dedup_safe

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "artifacts" / "runs"


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
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Run '{run_id}' was not found.")
    pipeline_data = json.loads((run_dir / "pipeline_data.json").read_text(encoding="utf-8"))
    run_context = json.loads((run_dir / "run_context.json").read_text(encoding="utf-8"))
    logger.info(
        "load_run_artifact: run_id=%s departments=%s",
        run_id,
        list(run_context.get("short_term_memory", {}).get("department_run_states", {}).keys()),
    )
    return {
        "run_id": run_id,
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

    # From task artifacts — facts from the latest attempt per task
    for task_key, artifacts in department_run_state.get("task_artifacts", {}).items():
        if artifacts:
            latest = artifacts[-1]
            evidence.extend(latest.get("facts", [])[:3])

    # From review artifacts — accepted points per task
    for task_key, reviews in department_run_state.get("review_artifacts", {}).items():
        if reviews:
            latest = reviews[-1]
            evidence.extend(latest.get("accepted_points", [])[:2])

    # From decision artifacts — open questions from terminal decisions
    for task_key, decisions in department_run_state.get("decision_artifacts", {}).items():
        if decisions:
            latest = decisions[-1]
            unresolved.extend(latest.get("open_questions", [])[:2])

    return _dedup_safe(list(filter(None, evidence))), _dedup_safe(list(filter(None, unresolved)))


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
    run_state = _get_department_run_state(run_context, "CompanyDepartment")

    # RA-07: Primary grounding from answer matrix + evidence packets
    answer_matrix = run_context.get("answer_matrix", {})
    memory = run_context.get("short_term_memory", {})
    evidence_packets = memory.get("evidence_packets", [])

    artifact_evidence, artifact_unresolved = _extract_task_evidence(run_state)

    # Evidence priority: answer_matrix > evidence_packets > task_artifacts > pipeline_data
    matrix_evidence = []
    for qid in ("q_company_fundamentals", "q_economic_commercial_situation", "q_product_asset_scope"):
        entry = answer_matrix.get(qid, {})
        if entry.get("answer") and entry["answer"] != "n/v":
            matrix_evidence.append(entry["answer"][:200])

    packet_evidence = [
        str(p.get("claim", ""))[:200]
        for p in evidence_packets[:4]
        if isinstance(p, dict)
        and p.get("metadata", {}).get("task_key", "").startswith("company")
        and p.get("claim")
    ]

    evidence = [
        *matrix_evidence[:3],
        *packet_evidence[:3],
        *artifact_evidence[:2],
        profile.get("description", ""),
    ]
    unresolved = _dedup_safe(
        [entry.get("notes", "") for entry in answer_matrix.values()
         if entry.get("status") in {"pending", "blocked"} and entry.get("notes")]
        + artifact_unresolved[:2]
    )
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
    run_state = _get_department_run_state(run_context, "MarketDepartment")
    answer_matrix = run_context.get("answer_matrix", {})
    artifact_evidence, artifact_unresolved = _extract_task_evidence(run_state)

    matrix_evidence = []
    for qid in ("q_market_situation", "q_repurposing_circularity", "q_analytics_operational_improvement"):
        entry = answer_matrix.get(qid, {})
        if entry.get("answer") and entry["answer"] != "n/v":
            matrix_evidence.append(entry["answer"][:200])

    evidence = [
        *matrix_evidence[:3],
        *artifact_evidence[:3],
        analysis.get("assessment", ""),
        analysis.get("demand_outlook", ""),
    ]
    unresolved = _dedup_safe(
        [entry.get("notes", "") for qid, entry in answer_matrix.items()
         if qid.startswith("q_market") and entry.get("status") in {"pending", "blocked"} and entry.get("notes")]
        + artifact_unresolved[:2]
    )
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
    run_state = _get_department_run_state(run_context, "BuyerDepartment")
    answer_matrix = run_context.get("answer_matrix", {})
    artifact_evidence, artifact_unresolved = _extract_task_evidence(run_state)

    matrix_evidence = []
    for qid in ("q_peer_companies", "q_monetization_redeployment"):
        entry = answer_matrix.get(qid, {})
        if entry.get("answer") and entry["answer"] != "n/v":
            matrix_evidence.append(entry["answer"][:200])

    peers = network.get("peer_competitors", {}).get("companies", [])
    buyers = network.get("downstream_buyers", {}).get("companies", [])
    evidence = [
        *matrix_evidence[:2],
        *artifact_evidence[:3],
        network.get("peer_competitors", {}).get("assessment", ""),
        network.get("downstream_buyers", {}).get("assessment", ""),
    ]
    unresolved = _dedup_safe(
        [entry.get("notes", "") for qid, entry in answer_matrix.items()
         if qid in ("q_peer_companies", "q_monetization_redeployment")
         and entry.get("status") in {"pending", "blocked"} and entry.get("notes")]
        + artifact_unresolved[:2]
    )
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
    run_state = _get_department_run_state(run_context, "ContactDepartment")
    answer_matrix = run_context.get("answer_matrix", {})
    artifact_evidence, artifact_unresolved = _extract_task_evidence(run_state)

    matrix_entry = answer_matrix.get("q_contact_intelligence", {})
    matrix_evidence = [matrix_entry["answer"][:200]] if matrix_entry.get("answer") and matrix_entry["answer"] != "n/v" else []

    contacts = section.get("prioritized_contacts", section.get("contacts", []))
    evidence = [
        *matrix_evidence,
        *artifact_evidence[:2],
        section.get("narrative_summary", ""),
        *[f"{c.get('name', '')} — {c.get('rolle_titel', '')} at {c.get('firma', '')}" for c in contacts[:3]],
    ]
    unresolved = _dedup_safe(
        ([matrix_entry.get("notes", "")] if matrix_entry.get("status") in {"pending", "blocked"} and matrix_entry.get("notes") else [])
        + artifact_unresolved[:2]
    )
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
        *synthesis.get("next_steps", [])[:2],
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
        *synthesis.get("next_steps", [])[:2],
    ]
    unresolved = quality.get("open_gaps", [])[:3]
    answer = (
        f"Cross-domain follow-up for '{question}': "
        f"{synthesis.get('opportunity_assessment_summary', 'n/v')} "
        f"Recommended next steps: {', '.join(synthesis.get('next_steps', [])[:3]) or 'n/v'}."
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
    logger.info(
        "answer_follow_up: run_id=%s route=%s question_len=%d",
        run_id, route, len(question),
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
        run_id=run_id,
        routed_to=route,
        question=question,
        answer=answer,
        evidence_used=evidence[:5],
        unresolved_points=unresolved,
        requires_additional_research=bool(unresolved),
    ).model_dump(mode="json")
    export_follow_up(RUNS_DIR / run_id, payload)
    return payload


def run_bounded_follow_up(
    *,
    run_id: str,
    run_context: dict[str, Any],
    pipeline_data: dict[str, Any],
    public_gap_questions: list[str],
    max_questions: int = 4,
) -> dict[str, Any]:
    """Run bounded, run-brain-grounded follow-up for public evidence gaps.

    This helper is used inside the live run (before final export) and therefore
    does not write follow-up artifacts to disk.
    """
    candidates = [q.strip() for q in public_gap_questions if str(q).strip()]
    queue = candidates[:max_questions]
    attempts: list[dict[str, Any]] = []

    for question in queue:
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

        attempts.append({
            "route": route,
            "question": question,
            "answer": answer,
            "evidence_used": evidence[:3],
            "unresolved_points": unresolved[:2],
            "resolved": not bool(unresolved),
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
    stop_reason = "all_questions_resolved" if not unresolved_after else "bounded_budget_exhausted"
    return {
        "run_id": run_id,
        "attempted_questions": len(attempts),
        "max_questions": max_questions,
        "closure_pass": 1,
        "max_closure_passes": 1,
        "stop_reason": stop_reason,
        "attempts": attempts,
        "resolved_questions": resolved_questions,
        "remaining_public_gaps": unresolved_after,
    }
