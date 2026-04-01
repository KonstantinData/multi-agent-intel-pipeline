"""Runtime guardrails: phase-aware budgets, ordering, stop reasons, telemetry.

RA-08: Operational hardening layer consumed by pipeline_runner and
supervisor_loop.  All guardrail state is persisted in the run export.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from src.models.meeting_ready import (
    AnswerMatrixUpdate,
    EvidencePacket,
    GapCandidate,
    MeetingAction,
    ResolutionDecision,
)

# ---------------------------------------------------------------------------
# Phase-aware budget configuration
# ---------------------------------------------------------------------------

FIRST_PASS_TOKEN_BUDGET = int(os.getenv("LIQUISTO_FIRST_PASS_TOKEN_BUDGET", "350000"))
CLOSURE_TOKEN_BUDGET = int(os.getenv("LIQUISTO_CLOSURE_TOKEN_BUDGET", "80000"))
OPTIONAL_DEPTH_TOKEN_BUDGET = int(os.getenv("LIQUISTO_OPTIONAL_DEPTH_TOKEN_BUDGET", "50000"))

MAX_CLOSURE_PASSES = 1
MAX_CLOSURE_QUESTIONS = 4


# ---------------------------------------------------------------------------
# Structured-output validation
# ---------------------------------------------------------------------------

_RUNTIME_ARTIFACT_MODELS = {
    "EvidencePacket": EvidencePacket,
    "GapCandidate": GapCandidate,
    "AnswerMatrixUpdate": AnswerMatrixUpdate,
    "ResolutionDecision": ResolutionDecision,
    "MeetingAction": MeetingAction,
}


def validate_structured_artifact(artifact_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """Validate a runtime-consumed artifact against its Pydantic model.

    Returns {"valid": True, "instance": <model>} or {"valid": False, "error": <str>}.
    """
    model_cls = _RUNTIME_ARTIFACT_MODELS.get(artifact_type)
    if model_cls is None:
        return {"valid": True, "instance": data, "note": "no schema registered"}
    try:
        instance = model_cls.model_validate(data)
        return {"valid": True, "instance": instance}
    except Exception as exc:
        return {"valid": False, "error": str(exc)[:300]}


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------

QUESTION_ORDER = (
    "q_company_fundamentals",
    "q_economic_commercial_situation",
    "q_product_asset_scope",
    "q_market_situation",
    "q_peer_companies",
    "q_monetization_redeployment",
    "q_contact_intelligence",
    "q_liquisto_opportunity_assessment",
    "q_negotiation_relevance",
)

MEETING_ACTION_TYPE_ORDER = ("prepare_meeting", "collect_missing_evidence", "ask_user_selection", "hold")


def sort_answer_matrix(matrix: dict[str, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Return answer matrix entries in deterministic question order."""
    order_map = {qid: idx for idx, qid in enumerate(QUESTION_ORDER)}
    return sorted(matrix.items(), key=lambda kv: order_map.get(kv[0], 999))


def sort_meeting_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return meeting actions in deterministic type order."""
    order_map = {t: idx for idx, t in enumerate(MEETING_ACTION_TYPE_ORDER)}
    return sorted(actions, key=lambda a: order_map.get(a.get("action_type", ""), 999))


def sort_evidence_packets(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return evidence packets sorted by task_key then packet_id."""
    return sorted(packets, key=lambda p: (
        p.get("metadata", {}).get("task_key", ""),
        p.get("packet_id", ""),
    ))


# ---------------------------------------------------------------------------
# Phase budget tracker
# ---------------------------------------------------------------------------

@dataclass
class PhaseBudgetTracker:
    """Track token consumption per phase with explicit stop reasons."""

    first_pass_budget: int = FIRST_PASS_TOKEN_BUDGET
    closure_budget: int = CLOSURE_TOKEN_BUDGET
    optional_depth_budget: int = OPTIONAL_DEPTH_TOKEN_BUDGET

    first_pass_used: int = 0
    closure_used: int = 0
    optional_depth_used: int = 0

    stop_reasons: list[dict[str, str]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)

    def record_phase_tokens(self, phase: str, tokens: int) -> None:
        if phase == "first_pass":
            self.first_pass_used += tokens
        elif phase == "closure":
            self.closure_used += tokens
        elif phase == "optional_depth":
            self.optional_depth_used += tokens
        self.timeline.append({"phase": phase, "tokens_added": tokens})

    def check_budget(self, phase: str) -> bool:
        """Return True if the phase still has budget remaining."""
        if phase == "first_pass":
            return self.first_pass_used < self.first_pass_budget
        if phase == "closure":
            return self.closure_used < self.closure_budget
        if phase == "optional_depth":
            return self.optional_depth_used < self.optional_depth_budget
        return True

    def record_stop(self, phase: str, reason: str) -> None:
        self.stop_reasons.append({"phase": phase, "reason": reason})

    def snapshot(self) -> dict[str, Any]:
        return {
            "budgets": {
                "first_pass": {"budget": self.first_pass_budget, "used": self.first_pass_used},
                "closure": {"budget": self.closure_budget, "used": self.closure_used},
                "optional_depth": {"budget": self.optional_depth_budget, "used": self.optional_depth_used},
            },
            "stop_reasons": self.stop_reasons,
            "timeline_events": len(self.timeline),
        }
