"""Contracts for compliance checks, learning patterns, and proposal workflow."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class ComplianceViolation:
    rule_id: str
    category: str
    severity: str
    message: str
    line: int | None = None
    blocking: bool = True
    fix_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "line": self.line,
            "blocking": self.blocking,
            "fix_hint": self.fix_hint,
        }


@dataclass(slots=True)
class ComplianceArtifact:
    artifact_id: str
    run_id: str
    file_path: str
    file_type: str
    purpose: str
    risk_level: str
    policy_version: str
    status: Literal["pass", "fail"]
    blocking_failure: bool
    evaluated_rule_ids: list[str] = field(default_factory=list)
    violations: list[ComplianceViolation] = field(default_factory=list)
    attempt_count: int = 1
    fix_success: bool | None = None
    time_to_fix_sec: float | None = None
    validator_output: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "run_id": self.run_id,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "purpose": self.purpose,
            "risk_level": self.risk_level,
            "policy_version": self.policy_version,
            "status": self.status,
            "blocking_failure": self.blocking_failure,
            "evaluated_rule_ids": list(self.evaluated_rule_ids),
            "violations": [item.to_dict() for item in self.violations],
            "attempt_count": self.attempt_count,
            "fix_success": self.fix_success,
            "time_to_fix_sec": self.time_to_fix_sec,
            "validator_output": self.validator_output,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ComplianceArtifact:
        violations = [
            ComplianceViolation(
                rule_id=str(item.get("rule_id", "")),
                category=str(item.get("category", "")),
                severity=str(item.get("severity", "")),
                message=str(item.get("message", "")),
                line=int(item["line"]) if item.get("line") is not None else None,
                blocking=bool(item.get("blocking", True)),
                fix_hint=str(item.get("fix_hint", "")),
            )
            for item in payload.get("violations", [])
            if isinstance(item, dict)
        ]
        return cls(
            artifact_id=str(payload.get("artifact_id", "")),
            run_id=str(payload.get("run_id", "")),
            file_path=str(payload.get("file_path", "")),
            file_type=str(payload.get("file_type", "")),
            purpose=str(payload.get("purpose", "")),
            risk_level=str(payload.get("risk_level", "")),
            policy_version=str(payload.get("policy_version", "")),
            status="fail" if payload.get("status") == "fail" else "pass",
            blocking_failure=bool(payload.get("blocking_failure", False)),
            evaluated_rule_ids=[str(item) for item in payload.get("evaluated_rule_ids", [])],
            violations=violations,
            attempt_count=int(payload.get("attempt_count", 1) or 1),
            fix_success=payload.get("fix_success"),
            time_to_fix_sec=float(payload["time_to_fix_sec"]) if payload.get("time_to_fix_sec") is not None else None,
            validator_output=str(payload.get("validator_output", "")),
            metadata=dict(payload.get("metadata", {})),
            created_at=str(payload.get("created_at", _utc_now_iso())),
        )


@dataclass(slots=True)
class CompliancePattern:
    rule_id: str
    category: str
    file_type: str
    purpose: str
    risk_level: str
    total_checks: int
    fail_count: int
    failure_rate: float
    repeat_fail_count: int
    avg_attempts_to_fix: float
    fix_success_rate: float
    false_positive_rate: float
    mean_time_to_fix_sec: float

    @property
    def key(self) -> str:
        return f"{self.rule_id}|{self.file_type}|{self.purpose}|{self.risk_level}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "category": self.category,
            "file_type": self.file_type,
            "purpose": self.purpose,
            "risk_level": self.risk_level,
            "total_checks": self.total_checks,
            "fail_count": self.fail_count,
            "failure_rate": self.failure_rate,
            "repeat_fail_count": self.repeat_fail_count,
            "avg_attempts_to_fix": self.avg_attempts_to_fix,
            "fix_success_rate": self.fix_success_rate,
            "false_positive_rate": self.false_positive_rate,
            "mean_time_to_fix_sec": self.mean_time_to_fix_sec,
            "pattern_key": self.key,
        }


@dataclass(slots=True)
class ComplianceRuleProposal:
    proposal_id: str
    created_at: str
    source_pattern_key: str
    target_kind: Literal["instruction", "skill", "template", "policy"]
    target_identifier: str
    reason: str
    evidence_summary: str
    suggested_change: str
    expected_effect: str
    min_repetitions_required: int = 4
    status: Literal["proposed", "accepted", "rejected", "revised"] = "proposed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "created_at": self.created_at,
            "source_pattern_key": self.source_pattern_key,
            "target_kind": self.target_kind,
            "target_identifier": self.target_identifier,
            "reason": self.reason,
            "evidence_summary": self.evidence_summary,
            "suggested_change": self.suggested_change,
            "expected_effect": self.expected_effect,
            "min_repetitions_required": self.min_repetitions_required,
            "status": self.status,
        }


@dataclass(slots=True)
class ProposalValidationResult:
    proposal_id: str
    verdict: Literal["accepted", "rejected", "needs_voting"]
    confidence: Literal["low", "medium", "high"]
    notes: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    validated_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "notes": list(self.notes),
            "metrics": dict(self.metrics),
            "validated_at": self.validated_at,
        }


@dataclass(slots=True)
class VotingDecision:
    proposal_id: str
    outcome: Literal["accepted", "rejected", "revised"]
    votes_for: int
    votes_against: int
    abstentions: int = 0
    rationale: str = ""
    decided_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "outcome": self.outcome,
            "votes_for": self.votes_for,
            "votes_against": self.votes_against,
            "abstentions": self.abstentions,
            "rationale": self.rationale,
            "decided_at": self.decided_at,
        }
