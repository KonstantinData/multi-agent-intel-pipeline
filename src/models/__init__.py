"""Structured schema models for pipeline outputs."""

from src.models.meeting_ready import (
    AnswerMatrixUpdate,
    EvidencePacket,
    FinalBriefing,
    GapCandidate,
    MeetingAction,
    MeetingReadinessAssessment,
    MinimumPackageStatus,
    ReadinessBlocker,
    ResolutionDecision,
    ResolutionPlan,
    RunStatus,
)

__all__ = [
    "AnswerMatrixUpdate",
    "EvidencePacket",
    "FinalBriefing",
    "GapCandidate",
    "MinimumPackageStatus",
    "MeetingAction",
    "MeetingReadinessAssessment",
    "PipelineData",
    "ReadinessBlocker",
    "ResolutionDecision",
    "ResolutionPlan",
    "RunStatus",
    "validate_pipeline_data",
]


def __getattr__(name: str) -> object:
    if name in {"PipelineData", "validate_pipeline_data"}:
        from src.models.schemas import PipelineData, validate_pipeline_data

        return {"PipelineData": PipelineData, "validate_pipeline_data": validate_pipeline_data}[name]
    raise AttributeError(name)
