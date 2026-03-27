"""Explicit runtime contracts for department execution.

CHG-01 — Replaces stringly-typed shared mutable dicts (``run_state``,
``workflow_step``) with typed structures that:

- store all task attempts, not only the latest result
- make task decision outcomes an explicit vocabulary
- separate working state (DepartmentRunState) from final output (DepartmentPackage)
- enable serialisation for run-brain persistence and follow-up rehydration

These objects are the canonical runtime state for a department group run.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Task decision outcome vocabulary
# ---------------------------------------------------------------------------

# Explicit outcomes — replaces magic strings like "retry", "skip", "accept"
TaskDecisionOutcome = Literal[
    "accepted",              # All core rules passed — task complete
    "accepted_with_gaps",    # Partial core passed — usable but gaps documented
    "rework_required",       # Lead authorised retry — new attempt pending
    "escalated_to_judge",    # Ambiguous quality — Judge will decide
    "closed_unresolved",     # Max retries reached — documented evidence gap
    "blocked_by_dependency", # F4: dependency not satisfied — scheduler state
]

# Terminal states: no further action expected on this task
TERMINAL_OUTCOMES: frozenset[str] = frozenset({
    "accepted",
    "accepted_with_gaps",
    "closed_unresolved",
    "blocked_by_dependency",
})

# F4: Dependency-satisfying outcomes — a dependent task may start only when
# its upstream has one of these.  Distinct from terminal: closed_unresolved
# and blocked_by_dependency are terminal but NOT dependency-satisfying.
DEPENDENCY_SATISFYING_OUTCOMES: frozenset[str] = frozenset({
    "accepted",
    "accepted_with_gaps",
})

# Non-terminal states: task may still receive more work
NON_TERMINAL_OUTCOMES: frozenset[str] = frozenset({
    "rework_required",
    "escalated_to_judge",
})

# Map from TaskDecisionOutcome → TaskStatus (used in DepartmentPackage)
# F7: `rejected` removed as task-level status. Only exists on Admission level.
OUTCOME_TO_TASK_STATUS: dict[str, str] = {
    "accepted": "accepted",
    "accepted_with_gaps": "degraded",
    "rework_required": "pending",
    "escalated_to_judge": "pending",
    "closed_unresolved": "degraded",
    "blocked_by_dependency": "blocked",
}

# ---------------------------------------------------------------------------
# F7: Canonical vocabulary constants
# ---------------------------------------------------------------------------

# All layers import from here. No free-form status strings.
TASK_LIFECYCLE_STATUSES: frozenset[str] = frozenset({
    "pending", "pending_synthesis", "accepted", "degraded", "blocked", "skipped",
})

ADMISSION_DECISIONS: frozenset[str] = frozenset({
    "accepted", "accepted_with_gaps", "rejected",
})


# ---------------------------------------------------------------------------
# Contract violation record (F4)
# ---------------------------------------------------------------------------

@dataclass
class ContractViolation:
    """Structured record of a task-level schema violation."""
    field_path: str
    violation_type: str   # missing_required_field | type_mismatch | unexpected_field | empty_required_value
    severity: str         # low | medium | high
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "field_path": self.field_path,
            "violation_type": self.violation_type,
            "severity": self.severity,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Task-level artifacts
# ---------------------------------------------------------------------------

@dataclass
class TaskArtifact:
    """Output from a single research attempt for one task_key.

    Multiple attempts are stored per task — the latest is accessible via
    ``DepartmentRunState.latest_artifact(task_key)``.
    """
    task_key: str
    attempt: int
    worker: str = ""
    facts: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    queries_used: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    strategy_notes: str = ""
    objective: str = ""
    contract_violations: list[ContractViolation] = field(default_factory=list)
    needs_contract_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_key": self.task_key,
            "attempt": self.attempt,
            "worker": self.worker,
            "facts": self.facts,
            "payload": self.payload,
            "queries_used": self.queries_used,
            "sources": self.sources,
            "open_questions": self.open_questions,
            "strategy_notes": self.strategy_notes,
            "objective": self.objective,
            "contract_violations": [v.to_dict() for v in self.contract_violations],
            "needs_contract_review": self.needs_contract_review,
        }

    @classmethod
    def from_worker_report(cls, report: dict[str, Any], attempt: int) -> "TaskArtifact":
        """Build a TaskArtifact from a ResearchWorker report dict."""
        return cls(
            task_key=str(report.get("task_key", "")),
            attempt=attempt,
            worker=str(report.get("worker", "")),
            facts=list(report.get("facts", [])),
            payload=dict(report.get("payload", {})),
            queries_used=list(report.get("queries_used", [])),
            sources=list(report.get("sources", [])),
            open_questions=list(report.get("open_questions", [])),
            strategy_notes=str(report.get("strategy_notes", "")),
            objective=str(report.get("objective", "")),
        )


@dataclass
class TaskReviewArtifact:
    """Critic review of a specific TaskArtifact attempt."""
    task_key: str
    attempt: int
    approved: bool
    reviewer: str = ""
    core_passed: int = 0
    core_total: int = 0
    supporting_passed: int = 0
    supporting_total: int = 0
    accepted_points: list[str] = field(default_factory=list)
    rejected_points: list[str] = field(default_factory=list)
    missing_points: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    evidence_strength: str = "weak"
    method_issue: bool = False
    feedback_to_worker: list[str] = field(default_factory=list)
    revision_instructions: list[str] = field(default_factory=list)
    coding_brief: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_key": self.task_key,
            "attempt": self.attempt,
            "approved": self.approved,
            "reviewer": self.reviewer,
            "core_passed": self.core_passed,
            "core_total": self.core_total,
            "supporting_passed": self.supporting_passed,
            "supporting_total": self.supporting_total,
            "accepted_points": self.accepted_points,
            "rejected_points": self.rejected_points,
            "missing_points": self.missing_points,
            "issues": self.issues,
            "evidence_strength": self.evidence_strength,
            "method_issue": self.method_issue,
            "feedback_to_worker": self.feedback_to_worker,
            "revision_instructions": self.revision_instructions,
            "coding_brief": self.coding_brief,
        }

    @classmethod
    def from_critic_review(cls, review: dict[str, Any], *, task_key: str, attempt: int, reviewer: str = "") -> "TaskReviewArtifact":
        """Build a TaskReviewArtifact from a CriticAgent review dict."""
        return cls(
            task_key=task_key,
            attempt=attempt,
            approved=bool(review.get("approved", False)),
            reviewer=reviewer,
            core_passed=int(review.get("core_passed", 0)),
            core_total=int(review.get("core_total", 0)),
            supporting_passed=int(review.get("supporting_passed", 0)),
            supporting_total=int(review.get("supporting_total", 0)),
            accepted_points=list(review.get("accepted_points", [])),
            rejected_points=list(review.get("rejected_points", [])),
            missing_points=list(review.get("missing_points", [])),
            issues=list(review.get("issues", [])),
            evidence_strength=str(review.get("evidence_strength", "weak")),
            method_issue=bool(review.get("method_issue", False)),
            feedback_to_worker=list(review.get("feedback_to_worker", [])),
            revision_instructions=list(review.get("revision_instructions", [])),
            coding_brief=review.get("coding_brief"),
        )


@dataclass
class TaskDecisionArtifact:
    """Lead or Judge decision on a task_key after review.

    Stored by ``judge_decision`` tool (decided_by="judge") or created
    implicitly at ``finalize_package`` time for Lead-approved tasks
    (decided_by="lead").
    """
    task_key: str
    attempt: int
    outcome: str           # TaskDecisionOutcome
    task_status: str       # TaskStatus for final package: accepted|degraded|rejected
    decided_by: str = "lead"  # "lead" | "judge"
    confidence: str = "medium"
    open_questions: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_key": self.task_key,
            "attempt": self.attempt,
            "outcome": self.outcome,
            "task_status": self.task_status,
            "decided_by": self.decided_by,
            "confidence": self.confidence,
            "open_questions": self.open_questions,
            "reason": self.reason,
        }

    @property
    def is_terminal(self) -> bool:
        return self.outcome in TERMINAL_OUTCOMES

    @classmethod
    def from_judge_result(cls, result: dict[str, Any], *, task_key: str, attempt: int) -> "TaskDecisionArtifact":
        """Build a TaskDecisionArtifact from a JudgeAgent result dict.

        F7: Judge now returns Contract-Outcome vocabulary directly in
        the ``decision`` field. The ``task_status`` field carries the
        lifecycle status.
        """
        outcome = str(result.get("decision", "accepted_with_gaps"))
        task_status = str(result.get("task_status", "degraded"))
        return cls(
            task_key=task_key,
            attempt=attempt,
            outcome=outcome,
            task_status=task_status,
            decided_by="judge",
            confidence=str(result.get("confidence", "medium")),
            open_questions=list(result.get("open_questions", [])),
            reason=str(result.get("reason", "")),
        )

    @classmethod
    def lead_accepted(cls, *, task_key: str, attempt: int, review: "TaskReviewArtifact | None" = None) -> "TaskDecisionArtifact":
        """Create a Lead-approved decision artifact (no Judge needed)."""
        confidence = "high" if review and review.core_passed == review.core_total else "medium"
        return cls(
            task_key=task_key,
            attempt=attempt,
            outcome="accepted",
            task_status="accepted",
            decided_by="lead",
            confidence=confidence,
            open_questions=[],
            reason="Critic approved. Lead accepted and moving to next task.",
        )


# ---------------------------------------------------------------------------
# Department-level runtime state
# ---------------------------------------------------------------------------

@dataclass
class DepartmentRunState:
    """Canonical per-run state for one department group execution.

    Replaces the loose ``run_state: dict`` that was previously mutated
    across tool closures. Maintains full artifact history so every task
    attempt, review, and decision is traceable.

    Architecture note: This object is the department's working memory.
    At run end it is serialised and stored in the run brain via
    ``ShortTermMemoryStore.record_department_run_state()``.
    """
    department: str = ""
    current_payload: dict[str, Any] = field(default_factory=dict)
    query_overrides: dict[str, list[str]] = field(default_factory=dict)
    revision_requests: dict[str, dict[str, Any]] = field(default_factory=dict)
    attempts: dict[str, int] = field(default_factory=dict)

    # Artifact registries — keyed by task_key, list = all attempts
    task_artifacts: dict[str, list[TaskArtifact]] = field(default_factory=dict)
    review_artifacts: dict[str, list[TaskReviewArtifact]] = field(default_factory=dict)
    decision_artifacts: dict[str, list[TaskDecisionArtifact]] = field(default_factory=dict)

    # Backward-compat flat views (kept so caller code that reads run_state dicts still works)
    task_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_reviews: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Observability trace
    tool_errors: list[dict[str, Any]] = field(default_factory=list)
    strategy_changes: list[dict[str, Any]] = field(default_factory=list)
    coding_support_used: list[dict[str, Any]] = field(default_factory=list)
    judge_escalations: list[dict[str, Any]] = field(default_factory=list)

    # Guardrail state (used by speaker_selector)
    _consecutive_text_turns: dict[str, int] = field(default_factory=dict)

    # ---------------------------------------------------------------------------
    # Artifact registration
    # ---------------------------------------------------------------------------

    def record_task_artifact(self, artifact: TaskArtifact) -> None:
        self.task_artifacts.setdefault(artifact.task_key, []).append(artifact)
        # Keep backward-compat flat view
        self.task_results[artifact.task_key] = artifact.to_dict()
        logger.debug(
            "TaskArtifact recorded: task=%s attempt=%d facts=%d",
            artifact.task_key, artifact.attempt, len(artifact.facts),
        )

    def record_review_artifact(self, artifact: TaskReviewArtifact) -> None:
        self.review_artifacts.setdefault(artifact.task_key, []).append(artifact)
        # Keep backward-compat flat view
        self.last_reviews[artifact.task_key] = artifact.to_dict()
        logger.debug(
            "TaskReviewArtifact recorded: task=%s attempt=%d approved=%s core=%d/%d",
            artifact.task_key, artifact.attempt, artifact.approved,
            artifact.core_passed, artifact.core_total,
        )

    def record_decision_artifact(self, artifact: TaskDecisionArtifact) -> None:
        self.decision_artifacts.setdefault(artifact.task_key, []).append(artifact)
        if artifact.outcome == "rework_required":
            self.strategy_changes.append({
                "task_key": artifact.task_key,
                "attempt": artifact.attempt,
                "reason": artifact.reason,
            })
        if artifact.decided_by == "judge":
            self.judge_escalations.append({
                "task_key": artifact.task_key,
                "attempt": artifact.attempt,
                "outcome": artifact.outcome,
                "confidence": artifact.confidence,
            })
        logger.info(
            "TaskDecisionArtifact recorded: task=%s outcome=%s decided_by=%s",
            artifact.task_key, artifact.outcome, artifact.decided_by,
        )

    # ---------------------------------------------------------------------------
    # Latest-artifact accessors
    # ---------------------------------------------------------------------------

    def latest_artifact(self, task_key: str) -> TaskArtifact | None:
        artifacts = self.task_artifacts.get(task_key, [])
        return artifacts[-1] if artifacts else None

    def latest_review(self, task_key: str) -> TaskReviewArtifact | None:
        reviews = self.review_artifacts.get(task_key, [])
        return reviews[-1] if reviews else None

    def latest_decision(self, task_key: str) -> TaskDecisionArtifact | None:
        decisions = self.decision_artifacts.get(task_key, [])
        return decisions[-1] if decisions else None

    def is_task_terminal(self, task_key: str) -> bool:
        decision = self.latest_decision(task_key)
        return decision is not None and decision.is_terminal

    def is_dependency_satisfied(self, task_key: str) -> bool:
        """F4: A dependency is satisfied when the upstream task has produced output.

        Hierarchy (most authoritative first):
        1. Explicit decision with accepted/accepted_with_gaps outcome
        2. Approved review (decision not yet recorded during GroupChat)
        3. TaskArtifact exists (research completed, review pending)

        Level 3 is necessary because the Lead may call run_research for
        a dependent task before the Critic has reviewed the upstream task.
        The dependency semantics is 'upstream has produced data', not
        'upstream has been quality-checked'.

        NOT satisfied:
        - No artifact at all
        - Decision is closed_unresolved or blocked_by_dependency
        """
        # Level 1: explicit decision
        decision = self.latest_decision(task_key)
        if decision is not None:
            if decision.outcome in DEPENDENCY_SATISFYING_OUTCOMES:
                return True
            # Explicit non-satisfying decision (closed_unresolved, blocked_by_dependency)
            return False
        # Level 2: approved review without decision yet
        review = self.latest_review(task_key)
        if review is not None and review.approved:
            return True
        # Level 3: artifact exists (research completed, review pending)
        artifact = self.latest_artifact(task_key)
        if artifact is not None and artifact.facts:
            return True
        return False

    # ---------------------------------------------------------------------------
    # Observability helpers
    # ---------------------------------------------------------------------------

    def record_coding_support(self, task_key: str, queries: list[str]) -> None:
        self.coding_support_used.append({
            "task_key": task_key,
            "attempt": self.attempts.get(task_key, 0),
            "queries_count": len(queries),
        })
        logger.info("CodingSupport used: task=%s query_count=%d", task_key, len(queries))

    # ---------------------------------------------------------------------------
    # Serialisation
    # ---------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "department": self.department,
            "attempts": dict(self.attempts),
            "task_artifacts": {
                k: [a.to_dict() for a in v]
                for k, v in self.task_artifacts.items()
            },
            "review_artifacts": {
                k: [r.to_dict() for r in v]
                for k, v in self.review_artifacts.items()
            },
            "decision_artifacts": {
                k: [d.to_dict() for d in v]
                for k, v in self.decision_artifacts.items()
            },
            "tool_errors": self.tool_errors,
            "strategy_changes": self.strategy_changes,
            "coding_support_used": self.coding_support_used,
            "judge_escalations": self.judge_escalations,
        }

    def guardrail_state(self) -> dict[str, Any]:
        """Return the minimal state dict used by the speaker selector."""
        return self._consecutive_text_turns
