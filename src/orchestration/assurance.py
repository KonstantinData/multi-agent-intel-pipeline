"""Task-level assurance signals, policies, and shadow gate verdicts.

ADR-004: Progressive Assurance Shadow Mode.

Confidence is derived from observable artifact properties only. The assurance
gate is intentionally dependency-light and deterministic so architecture tests
can validate it without AG2/autogen or model clients.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ASSURANCE_SIGNAL_SCHEMA_VERSION = "2026-05-21.1"
ASSURANCE_SCORING_VERSION = "2026-05-21.2"
ASSURANCE_WEIGHTS_VERSION = "2026-05-21.1"
TASK_ASSURANCE_POLICY_VERSION = "2026-05-21.2"

TaskCriticality = Literal["low", "medium", "high", "critical"]
JudgeCondition = Literal["conflict", "max_retries", "critical_decision", "ambiguity"]
CriticSeverity = Literal["none", "minor", "major", "blocking"]
UnknownSourceDatesPolicy = Literal["neutral", "penalize"]

_VALID_TASK_CRITICALITIES = frozenset({"low", "medium", "high", "critical"})
_VALID_JUDGE_CONDITIONS = frozenset(
    {"conflict", "max_retries", "critical_decision", "ambiguity"}
)
_VALID_CRITIC_SEVERITIES = frozenset({"none", "minor", "major", "blocking"})
_VALID_UNKNOWN_SOURCE_DATE_POLICIES = frozenset({"neutral", "penalize"})

_SIGNAL_FIELDS = (
    "required_fields_score",
    "source_mix_score",
    "source_freshness_score",
    "contradiction_score",
    "evidence_strength_score",
)

# Weights must sum to 1.0. Unknown signals contribute 0.0 until upstream
# artifacts expose reliable structured observations.
_SIGNAL_WEIGHTS: dict[str, float] = {
    "required_fields_score": 0.30,
    "source_mix_score": 0.20,
    "source_freshness_score": 0.15,
    "contradiction_score": 0.20,
    "evidence_strength_score": 0.15,
}

LTM_BONUS_ENABLED = False
LTM_CONFIDENCE_BONUS = 0.05
DEFAULT_LTM_PRECISION_FLOOR = 0.70
_CONFLICT_SCORE_THRESHOLD = 0.40

_CRITICALITY_DELTA: dict[str, float] = {
    "low": -0.05,
    "medium": 0.0,
    "high": 0.10,
}


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, value))


def _validate_optional_score(name: str, value: float | None) -> None:
    if value is None:
        return
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"{name} must be in [0.0, 1.0], got {value!r}")


def _is_present_payload_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def score_required_fields(
    payload: dict[str, Any],
    required_fields: tuple[str, ...],
) -> float | None:
    """Score required payload field presence.

    Returns None when no required fields are configured so callers do not
    accidentally treat an unknown requirement set as perfect evidence.
    """
    normalized_fields = tuple(field for field in required_fields if field.strip())
    if not normalized_fields:
        return None

    present = sum(
        1
        for field_name in normalized_fields
        if field_name in payload and _is_present_payload_value(payload[field_name])
    )
    return round(present / len(normalized_fields), 6)


@dataclass(frozen=True, slots=True)
class TaskAssuranceSignals:
    """Evidence-derived confidence signals for one task attempt.

    All score fields are either None or in [0.0, 1.0]. None means "unknown",
    not "perfect"; unknown signals contribute 0.0 to initial shadow scoring.
    """

    required_fields_score: float | None
    source_mix_score: float | None
    source_freshness_score: float | None
    contradiction_score: float | None
    evidence_strength_score: float | None
    task_criticality: TaskCriticality
    ltm_pattern_match: bool = False
    ltm_pattern_precision: float | None = None
    ltm_pattern_qualified: bool = False
    schema_version: str = ASSURANCE_SIGNAL_SCHEMA_VERSION
    scoring_version: str = ASSURANCE_SCORING_VERSION
    weights_version: str = ASSURANCE_WEIGHTS_VERSION
    policy_version: str = TASK_ASSURANCE_POLICY_VERSION
    unknown_signal_count: int = 0

    def __post_init__(self) -> None:
        if self.task_criticality not in _VALID_TASK_CRITICALITIES:
            raise ValueError(f"task_criticality must be one of {_VALID_TASK_CRITICALITIES}")

        unknown_count = 0
        for field_name in _SIGNAL_FIELDS:
            value = getattr(self, field_name)
            _validate_optional_score(field_name, value)
            if value is None:
                unknown_count += 1
        object.__setattr__(self, "unknown_signal_count", unknown_count)

        _validate_optional_score("ltm_pattern_precision", self.ltm_pattern_precision)
        if not self.ltm_pattern_match and self.ltm_pattern_precision is not None:
            raise ValueError("ltm_pattern_precision must be None when ltm_pattern_match is False")
        if self.ltm_pattern_qualified and not self.ltm_pattern_match:
            raise ValueError("ltm_pattern_qualified requires ltm_pattern_match=True")
        if self.ltm_pattern_qualified and self.ltm_pattern_precision is None:
            raise ValueError("ltm_pattern_qualified requires ltm_pattern_precision")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scoring_version": self.scoring_version,
            "weights_version": self.weights_version,
            "policy_version": self.policy_version,
            "required_fields_score": self.required_fields_score,
            "source_mix_score": self.source_mix_score,
            "source_freshness_score": self.source_freshness_score,
            "contradiction_score": self.contradiction_score,
            "evidence_strength_score": self.evidence_strength_score,
            "task_criticality": self.task_criticality,
            "ltm_pattern_match": self.ltm_pattern_match,
            "ltm_pattern_precision": self.ltm_pattern_precision,
            "ltm_pattern_qualified": self.ltm_pattern_qualified,
            "unknown_signal_count": self.unknown_signal_count,
        }


@dataclass(frozen=True, slots=True)
class TaskAssurancePolicy:
    """Per-task gate configuration.

    ``auto_accept_allowed=False`` unconditionally disables the fast path
    regardless of signal quality.
    """

    task_key: str
    auto_accept_allowed: bool
    critic_required_below: float
    judge_required_on: frozenset[JudgeCondition]
    required_source_types: tuple[str, ...]
    task_criticality: TaskCriticality
    required_payload_fields: tuple[str, ...] = ()
    policy_version: str = TASK_ASSURANCE_POLICY_VERSION
    preferred_source_types: tuple[str, ...] = ()
    minimum_source_count: int = 0
    unknown_source_dates_policy: UnknownSourceDatesPolicy = "neutral"
    ltm_precision_floor: float = DEFAULT_LTM_PRECISION_FLOOR

    def __post_init__(self) -> None:
        if not self.task_key.strip():
            raise ValueError("task_key must not be empty")
        if self.task_criticality not in _VALID_TASK_CRITICALITIES:
            raise ValueError(f"task_criticality must be one of {_VALID_TASK_CRITICALITIES}")
        unknown_judge_conditions = {
            str(item)
            for item in self.judge_required_on
            if item not in _VALID_JUDGE_CONDITIONS
        }
        if unknown_judge_conditions:
            raise ValueError(f"unknown judge condition(s): {sorted(unknown_judge_conditions)}")
        if self.unknown_source_dates_policy not in _VALID_UNKNOWN_SOURCE_DATE_POLICIES:
            raise ValueError(
                "unknown_source_dates_policy must be one of "
                f"{_VALID_UNKNOWN_SOURCE_DATE_POLICIES}"
            )
        _validate_optional_score("critic_required_below", self.critic_required_below)
        _validate_optional_score("ltm_precision_floor", self.ltm_precision_floor)
        if self.minimum_source_count < 0:
            raise ValueError("minimum_source_count must be >= 0")

    def score_missing_source_date(self) -> float:
        if self.unknown_source_dates_policy == "neutral":
            return 0.5
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "task_key": self.task_key,
            "auto_accept_allowed": self.auto_accept_allowed,
            "critic_required_below": self.critic_required_below,
            "judge_required_on": sorted(self.judge_required_on),
            "required_source_types": list(self.required_source_types),
            "required_payload_fields": list(self.required_payload_fields),
            "preferred_source_types": list(self.preferred_source_types),
            "minimum_source_count": self.minimum_source_count,
            "task_criticality": self.task_criticality,
            "unknown_source_dates_policy": self.unknown_source_dates_policy,
            "ltm_precision_floor": self.ltm_precision_floor,
        }


@dataclass(frozen=True, slots=True)
class GateVerdict:
    """Deterministic output of evaluate_gate for one signals/policy pair."""

    schema_version: str
    scoring_version: str
    weights_version: str
    policy_version: str
    confidence_score: float
    effective_threshold: float
    would_auto_accept: bool
    requires_critic: bool
    requires_judge: bool
    judge_conditions_triggered: tuple[str, ...]
    reasons: tuple[str, ...]
    ltm_bonus_applied: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scoring_version": self.scoring_version,
            "weights_version": self.weights_version,
            "policy_version": self.policy_version,
            "confidence_score": self.confidence_score,
            "effective_threshold": self.effective_threshold,
            "would_auto_accept": self.would_auto_accept,
            "requires_critic": self.requires_critic,
            "requires_judge": self.requires_judge,
            "judge_conditions_triggered": list(self.judge_conditions_triggered),
            "reasons": list(self.reasons),
            "ltm_bonus_applied": self.ltm_bonus_applied,
        }


@dataclass(frozen=True, slots=True)
class CriticDeltaRecord:
    """Minimal structured diff between gate verdict and actual Critic outcome."""

    changed_outcome: bool
    rejected_points_count: int
    failed_core_rules: tuple[str, ...]
    critic_severity: CriticSeverity
    would_have_blocked_auto_accept: bool

    def __post_init__(self) -> None:
        if self.rejected_points_count < 0:
            raise ValueError("rejected_points_count must be >= 0")
        if self.critic_severity not in _VALID_CRITIC_SEVERITIES:
            raise ValueError(f"critic_severity must be one of {_VALID_CRITIC_SEVERITIES}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed_outcome": self.changed_outcome,
            "rejected_points_count": self.rejected_points_count,
            "failed_core_rules": list(self.failed_core_rules),
            "critic_severity": self.critic_severity,
            "would_have_blocked_auto_accept": self.would_have_blocked_auto_accept,
        }


@dataclass(frozen=True, slots=True)
class AssuranceShadowRecord:
    """Shadow-mode observation attached to a future TaskReviewArtifact."""

    gate_verdict: GateVerdict
    gate_signals: TaskAssuranceSignals
    escalation_reason: tuple[str, ...] = ()
    actual_critic_delta: CriticDeltaRecord | None = None
    shadow_mode: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "shadow_mode": self.shadow_mode,
            "gate_verdict": self.gate_verdict.to_dict(),
            "gate_signals": self.gate_signals.to_dict(),
            "escalation_reason": list(self.escalation_reason),
            "actual_critic_delta": (
                self.actual_critic_delta.to_dict()
                if self.actual_critic_delta is not None
                else None
            ),
        }


def get_default_assurance_policy(
    task_key: str,
    *,
    task_criticality: TaskCriticality = "medium",
    required_payload_fields: tuple[str, ...] = (),
    required_source_types: tuple[str, ...] = (),
) -> TaskAssurancePolicy:
    """Return the conservative ADR-004 v1 shadow policy for one task.

    The production fast path is explicitly disabled. Gate outputs are therefore
    observational until shadow data proves a safer per-task policy.
    """
    return TaskAssurancePolicy(
        task_key=task_key,
        auto_accept_allowed=False,
        critic_required_below=0.7,
        judge_required_on=frozenset({"conflict", "critical_decision"}),
        required_source_types=required_source_types,
        required_payload_fields=required_payload_fields,
        task_criticality=task_criticality,
    )


def _critic_severity(
    *,
    approved: bool,
    core_passed: int,
    core_total: int,
    rejected_points_count: int,
    missing_points_count: int,
    issues_count: int,
    method_issue: bool,
) -> CriticSeverity:
    if (
        not approved
        and ((core_total > 0 and core_passed < core_total) or method_issue)
    ):
        return "blocking"
    if not approved or rejected_points_count or missing_points_count:
        return "major"
    if issues_count or method_issue:
        return "minor"
    return "none"


def build_assurance_shadow_record(
    *,
    payload: dict[str, Any],
    policy: TaskAssurancePolicy,
    approved: bool,
    core_passed: int,
    core_total: int,
    rejected_points: tuple[str, ...],
    missing_points: tuple[str, ...] = (),
    issues: tuple[str, ...] = (),
    method_issue: bool = False,
    escalation_reason: tuple[str, ...] = (),
) -> AssuranceShadowRecord:
    """Build the ADR-004 shadow record from observable review-path data."""
    signals = TaskAssuranceSignals(
        required_fields_score=score_required_fields(
            payload,
            policy.required_payload_fields,
        ),
        source_mix_score=None,
        source_freshness_score=None,
        contradiction_score=None,
        evidence_strength_score=None,
        task_criticality=policy.task_criticality,
        policy_version=policy.policy_version,
    )
    verdict = evaluate_gate(signals, policy)
    severity = _critic_severity(
        approved=approved,
        core_passed=core_passed,
        core_total=core_total,
        rejected_points_count=len(rejected_points),
        missing_points_count=len(missing_points),
        issues_count=len(issues),
        method_issue=method_issue,
    )
    material_critic_issue = severity in {"major", "blocking"} or not approved
    gate_would_skip_review = not verdict.requires_critic and not verdict.requires_judge
    critic_delta = CriticDeltaRecord(
        changed_outcome=not approved,
        rejected_points_count=len(rejected_points),
        failed_core_rules=rejected_points,
        critic_severity=severity,
        would_have_blocked_auto_accept=(
            gate_would_skip_review and material_critic_issue
        ),
    )
    return AssuranceShadowRecord(
        gate_verdict=verdict,
        gate_signals=signals,
        escalation_reason=escalation_reason,
        actual_critic_delta=critic_delta,
    )


def _score_value(value: float | None) -> float:
    return 0.0 if value is None else value


def _compute_confidence(
    signals: TaskAssuranceSignals,
    policy: TaskAssurancePolicy,
) -> tuple[float, float]:
    base = sum(
        _SIGNAL_WEIGHTS[field_name] * _score_value(getattr(signals, field_name))
        for field_name in _SIGNAL_FIELDS
    )

    ltm_bonus = 0.0
    if (
        LTM_BONUS_ENABLED
        and signals.ltm_pattern_match
        and signals.ltm_pattern_qualified
        and signals.ltm_pattern_precision is not None
        and signals.ltm_pattern_precision >= policy.ltm_precision_floor
    ):
        ltm_bonus = LTM_CONFIDENCE_BONUS

    return round(_clamp_score(base + ltm_bonus), 6), ltm_bonus


def evaluate_gate(
    signals: TaskAssuranceSignals,
    policy: TaskAssurancePolicy,
) -> GateVerdict:
    """Evaluate the assurance gate deterministically.

    Pure function: no side effects, no I/O, no randomness.
    """
    if signals.task_criticality != policy.task_criticality:
        raise ValueError("signals.task_criticality must match policy.task_criticality")

    reasons: list[str] = []
    judge_conditions_triggered: list[str] = []
    confidence, ltm_bonus = _compute_confidence(signals, policy)

    if signals.unknown_signal_count:
        reasons.append(f"{signals.unknown_signal_count} assurance signal(s) unknown")

    if policy.task_criticality == "critical":
        effective_threshold = 1.0
        requires_critic = True
        reasons.append("critic required: task_criticality=critical")
    else:
        delta = _CRITICALITY_DELTA.get(policy.task_criticality, 0.0)
        effective_threshold = round(
            _clamp_score(policy.critic_required_below + delta),
            6,
        )
        requires_critic = confidence < effective_threshold
        if requires_critic:
            reasons.append(
                f"confidence {confidence:.4f} < threshold {effective_threshold:.4f} "
                f"(criticality={policy.task_criticality})"
            )

    requires_judge = False
    if (
        "conflict" in policy.judge_required_on
        and signals.contradiction_score is not None
        and signals.contradiction_score < _CONFLICT_SCORE_THRESHOLD
    ):
        requires_judge = True
        judge_conditions_triggered.append("conflict")
        reasons.append(
            "judge required: conflict detected "
            f"(contradiction_score={signals.contradiction_score:.4f})"
        )
    if "critical_decision" in policy.judge_required_on and policy.task_criticality == "critical":
        requires_judge = True
        judge_conditions_triggered.append("critical_decision")
        reasons.append("judge required: critical_decision + critical task")

    if not policy.auto_accept_allowed:
        reasons.append("auto_accept disabled by policy")

    would_auto_accept = (
        policy.auto_accept_allowed
        and not requires_critic
        and not requires_judge
    )

    return GateVerdict(
        schema_version=signals.schema_version,
        scoring_version=signals.scoring_version,
        weights_version=signals.weights_version,
        policy_version=policy.policy_version,
        confidence_score=confidence,
        effective_threshold=effective_threshold,
        would_auto_accept=would_auto_accept,
        requires_critic=requires_critic,
        requires_judge=requires_judge,
        judge_conditions_triggered=tuple(judge_conditions_triggered),
        reasons=tuple(reasons),
        ltm_bonus_applied=ltm_bonus,
    )
