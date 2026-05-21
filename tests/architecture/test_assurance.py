"""Architecture tests for ADR-004 progressive assurance contracts.

These tests intentionally avoid AG2/autogen imports.
"""
from __future__ import annotations

import pytest

from src.orchestration.assurance import (
    ASSURANCE_WEIGHTS_VERSION,
    CriticDeltaRecord,
    TaskAssurancePolicy,
    TaskAssuranceSignals,
    build_assurance_shadow_record,
    evaluate_gate,
    get_default_assurance_policy,
    score_required_fields,
)


def _signals(
    *,
    contradiction_score: float | None = 1.0,
    criticality: str = "medium",
    ltm_match: bool = False,
    ltm_precision: float | None = None,
    ltm_qualified: bool = False,
) -> TaskAssuranceSignals:
    return TaskAssuranceSignals(
        required_fields_score=1.0,
        source_mix_score=1.0,
        source_freshness_score=1.0,
        contradiction_score=contradiction_score,
        evidence_strength_score=1.0,
        task_criticality=criticality,  # type: ignore[arg-type]
        ltm_pattern_match=ltm_match,
        ltm_pattern_precision=ltm_precision,
        ltm_pattern_qualified=ltm_qualified,
    )


def _policy(
    *,
    auto_accept_allowed: bool = True,
    threshold: float = 0.7,
    criticality: str = "medium",
    judge_required_on: frozenset[str] = frozenset(),
) -> TaskAssurancePolicy:
    return TaskAssurancePolicy(
        task_key="company_overview",
        auto_accept_allowed=auto_accept_allowed,
        critic_required_below=threshold,
        judge_required_on=judge_required_on,  # type: ignore[arg-type]
        required_source_types=("primary",),
        required_payload_fields=("company_name",),
        task_criticality=criticality,  # type: ignore[arg-type]
    )


def test_requires_judge_blocks_auto_accept_even_with_high_confidence() -> None:
    verdict = evaluate_gate(
        _signals(contradiction_score=0.2),
        _policy(judge_required_on=frozenset({"conflict"})),
    )

    assert verdict.requires_judge is True
    assert verdict.requires_critic is False
    assert verdict.would_auto_accept is False
    assert verdict.judge_conditions_triggered == ("conflict",)


def test_auto_accept_allowed_false_blocks_fast_path_unconditionally() -> None:
    verdict = evaluate_gate(
        _signals(),
        _policy(auto_accept_allowed=False, threshold=0.1),
    )

    assert verdict.requires_critic is False
    assert verdict.requires_judge is False
    assert verdict.would_auto_accept is False
    assert "auto_accept disabled by policy" in verdict.reasons


def test_critical_task_always_requires_critic() -> None:
    verdict = evaluate_gate(
        _signals(criticality="critical"),
        _policy(
            criticality="critical",
            threshold=0.1,
            judge_required_on=frozenset({"critical_decision"}),
        ),
    )

    assert verdict.effective_threshold == 1.0
    assert verdict.requires_critic is True
    assert verdict.requires_judge is True
    assert verdict.would_auto_accept is False


def test_threshold_is_clamped_to_lower_bound() -> None:
    verdict = evaluate_gate(
        TaskAssuranceSignals(
            required_fields_score=0.0,
            source_mix_score=0.0,
            source_freshness_score=0.0,
            contradiction_score=0.0,
            evidence_strength_score=0.0,
            task_criticality="low",
        ),
        _policy(threshold=0.0, criticality="low"),
    )

    assert verdict.effective_threshold == 0.0
    assert verdict.requires_critic is False


def test_threshold_is_clamped_to_upper_bound() -> None:
    verdict = evaluate_gate(
        _signals(criticality="high"),
        _policy(threshold=0.95, criticality="high"),
    )

    assert verdict.effective_threshold == 1.0
    assert verdict.requires_critic is False


def test_ltm_bonus_is_disabled_until_empirical_precision_exists() -> None:
    verdict = evaluate_gate(
        TaskAssuranceSignals(
            required_fields_score=0.5,
            source_mix_score=0.5,
            source_freshness_score=0.5,
            contradiction_score=0.5,
            evidence_strength_score=0.5,
            task_criticality="medium",
            ltm_pattern_match=True,
            ltm_pattern_precision=1.0,
            ltm_pattern_qualified=True,
        ),
        _policy(threshold=0.5),
    )

    assert verdict.confidence_score == 0.5
    assert verdict.ltm_bonus_applied == 0.0


def test_unknown_signals_are_not_treated_as_perfect_scores() -> None:
    verdict = evaluate_gate(
        TaskAssuranceSignals(
            required_fields_score=None,
            source_mix_score=None,
            source_freshness_score=None,
            contradiction_score=None,
            evidence_strength_score=None,
            task_criticality="medium",
        ),
        _policy(threshold=0.1),
    )

    assert verdict.confidence_score == 0.0
    assert verdict.requires_critic is True
    assert "5 assurance signal(s) unknown" in verdict.reasons


def test_policy_unknown_source_date_scoring_is_explicit() -> None:
    neutral = _policy().score_missing_source_date()
    penalize = TaskAssurancePolicy(
        task_key="company_overview",
        auto_accept_allowed=True,
        critic_required_below=0.7,
        judge_required_on=frozenset(),
        required_source_types=("primary",),
        task_criticality="medium",
        unknown_source_dates_policy="penalize",
    ).score_missing_source_date()

    assert neutral == 0.5
    assert penalize == 0.0


def test_required_payload_fields_are_serialized() -> None:
    payload = _policy().to_dict()

    assert payload["required_payload_fields"] == ["company_name"]


def test_score_required_fields_returns_none_without_configured_fields() -> None:
    assert score_required_fields({"company_name": "ACME"}, ()) is None


def test_score_required_fields_counts_only_present_non_empty_values() -> None:
    assert (
        score_required_fields(
            {
                "company_name": "ACME",
                "industry": "  ",
                "products": [],
                "website": "https://example.com",
            },
            ("company_name", "industry", "products", "website"),
        )
        == 0.5
    )


def test_default_policy_disables_fast_path_but_preserves_gate_verdict() -> None:
    policy = get_default_assurance_policy(
        "company_overview",
        required_payload_fields=("company_name",),
    )
    verdict = evaluate_gate(
        TaskAssuranceSignals(
            required_fields_score=1.0,
            source_mix_score=1.0,
            source_freshness_score=1.0,
            contradiction_score=1.0,
            evidence_strength_score=1.0,
            task_criticality="medium",
        ),
        policy,
    )

    assert policy.auto_accept_allowed is False
    assert verdict.requires_critic is False
    assert verdict.would_auto_accept is False


def test_build_shadow_record_uses_required_field_score_and_critic_delta() -> None:
    policy = get_default_assurance_policy(
        "company_overview",
        required_payload_fields=("company_name", "industry"),
    )
    shadow = build_assurance_shadow_record(
        payload={"company_name": "ACME", "industry": ""},
        policy=policy,
        approved=False,
        core_passed=1,
        core_total=2,
        rejected_points=("industry missing",),
        issues=("Core field missing.",),
    )

    assert shadow.gate_signals.required_fields_score == 0.5
    assert shadow.gate_verdict.would_auto_accept is False
    assert shadow.actual_critic_delta is not None
    assert shadow.actual_critic_delta.failed_core_rules == ("industry missing",)
    assert shadow.actual_critic_delta.critic_severity == "blocking"


def test_validation_rejects_invalid_scores_and_thresholds() -> None:
    with pytest.raises(ValueError, match="required_fields_score"):
        TaskAssuranceSignals(
            required_fields_score=1.1,
            source_mix_score=1.0,
            source_freshness_score=1.0,
            contradiction_score=1.0,
            evidence_strength_score=1.0,
            task_criticality="medium",
        )

    with pytest.raises(ValueError, match="critic_required_below"):
        _policy(threshold=1.1)


def test_validation_rejects_unknown_policy_literals() -> None:
    with pytest.raises(ValueError, match="unknown judge condition"):
        TaskAssurancePolicy(
            task_key="company_overview",
            auto_accept_allowed=True,
            critic_required_below=0.7,
            judge_required_on=frozenset({"unmodelled"}),  # type: ignore[arg-type]
            required_source_types=("primary",),
            task_criticality="medium",
        )

    with pytest.raises(ValueError, match="unknown_source_dates_policy"):
        TaskAssurancePolicy(
            task_key="company_overview",
            auto_accept_allowed=True,
            critic_required_below=0.7,
            judge_required_on=frozenset(),
            required_source_types=("primary",),
            task_criticality="medium",
            unknown_source_dates_policy="optimistic",  # type: ignore[arg-type]
        )


def test_critic_delta_rejects_negative_counts() -> None:
    with pytest.raises(ValueError, match="rejected_points_count"):
        CriticDeltaRecord(
            changed_outcome=True,
            rejected_points_count=-1,
            failed_core_rules=(),
            critic_severity="major",
            would_have_blocked_auto_accept=True,
        )


def test_verdict_serialization_is_json_compatible() -> None:
    verdict = evaluate_gate(_signals(), _policy())
    payload = verdict.to_dict()

    assert payload["weights_version"] == ASSURANCE_WEIGHTS_VERSION
    assert isinstance(payload["reasons"], list)
    assert isinstance(payload["judge_conditions_triggered"], list)
