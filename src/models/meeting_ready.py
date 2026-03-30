"""Typed models for meeting-readiness state and final briefing artifacts."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


RunStatus = Literal[
    "running",
    "completed",
    "completed_partial",
    "completed_but_not_usable",
    "failed",
    "meeting_ready",
    "blocked_not_meeting_ready",
    "needs_user_selection",
]


class EvidencePacket(BaseModel):
    packet_id: str = "n/v"
    claim: str = "n/v"
    confidence: Literal["high", "medium", "low"] = "low"
    claim_type: Literal["fact", "inference", "hypothesis", "gap"] = "fact"
    source_quality: Literal["high", "medium", "low"] = "low"
    source_urls: list[str] = Field(default_factory=list)
    source_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GapCandidate(BaseModel):
    gap_id: str = "n/v"
    question: str = "n/v"
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    owner: str = "unspecified"
    resolution_hint: str = "n/v"
    evidence_packet_ids: list[str] = Field(default_factory=list)
    legacy_origin: str = "structured"


class AnswerMatrixUpdate(BaseModel):
    field_key: str = "n/v"
    answer: str = "n/v"
    status: Literal["answered", "partially_answered", "blocked", "pending"] = "pending"
    evidence_packet_ids: list[str] = Field(default_factory=list)
    notes: str = ""


class ResolutionDecision(BaseModel):
    decision: Literal["resolve_now", "defer", "request_user_selection", "accept_gap"] = "defer"
    rationale: str = "n/v"
    selected_gap_ids: list[str] = Field(default_factory=list)


class ResolutionPlan(BaseModel):
    plan_id: str = "n/v"
    decision: ResolutionDecision = Field(default_factory=ResolutionDecision)
    steps: list[str] = Field(default_factory=list)
    owner: str = "Supervisor"


class MeetingReadinessAssessment(BaseModel):
    run_status: RunStatus = "running"
    meeting_ready: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    unresolved_gaps: list[GapCandidate] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "low"


class MeetingAction(BaseModel):
    action_type: Literal["prepare_meeting", "collect_missing_evidence", "ask_user_selection", "hold"] = "hold"
    title: str = "n/v"
    description: str = "n/v"
    owner: str = "Supervisor"


class FinalBriefing(BaseModel):
    run_id: str = "n/v"
    company_name: str = "n/v"
    status: RunStatus = "running"
    executive_summary: str = "n/v"
    evidence_packets: list[EvidencePacket] = Field(default_factory=list)
    answer_matrix_updates: list[AnswerMatrixUpdate] = Field(default_factory=list)
    readiness: MeetingReadinessAssessment = Field(default_factory=MeetingReadinessAssessment)
    recommended_actions: list[MeetingAction] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
