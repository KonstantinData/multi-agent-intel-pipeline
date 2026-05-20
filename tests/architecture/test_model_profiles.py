"""Architecture tests for ADR-003 role profiles and reasoning policy resolution."""

from __future__ import annotations

import pytest

from src.config import resolve_step_reasoning_policy as exported_resolve_step_reasoning_policy
from src.config.model_profiles import (
    RoleModelProfile,
    StepReasoningContext,
    StepReasoningPolicy,
    build_role_model_profile,
    resolve_step_reasoning_policy,
)


def _reasoning_profile(role: str = "CompanyJudge") -> RoleModelProfile:
    return build_role_model_profile(
        role=role,
        model="gpt-5-mini",
        structured_model="gpt-4.1-mini",
        timeout_seconds=30.0,
        max_retries=0,
    )


def test_role_model_profile_detects_reasoning_and_structured_capabilities():
    profile = _reasoning_profile()

    assert profile.provider == "openai"
    assert profile.supports_reasoning is True
    assert profile.supports_structured_output is True
    assert profile.supports_temperature is False
    assert profile.default_temperature is None
    assert profile.default_reasoning_policy.effort == "high"


def test_role_model_profile_for_non_reasoning_model_uses_none_policy():
    profile = build_role_model_profile(
        role="MarketResearcher",
        model="gpt-4.1-mini",
        structured_model="gpt-4.1-mini",
    )

    assert profile.supports_reasoning is False
    assert profile.default_reasoning_policy.effort == "none"
    assert profile.default_reasoning_policy.reason == "role uses a non-reasoning model"


@pytest.mark.parametrize(
    ("context", "expected_effort", "expected_reason"),
    [
        (
            StepReasoningContext(
                role="CompanyResearcher",
                actor_role="researcher",
                action_kind="capability_call",
                action_target="research.run",
            ),
            "low",
            "tool-heavy research step",
        ),
        (
            StepReasoningContext(
                role="CompanyCritic",
                actor_role="critic",
                action_kind="state_transition",
                action_target="review_research",
            ),
            "medium",
            "evidence-quality review",
        ),
        (
            StepReasoningContext(
                role="CompanyJudge",
                actor_role="judge",
                action_kind="state_transition",
                action_target="judge_decision",
            ),
            "high",
            "borderline adjudication",
        ),
        (
            StepReasoningContext(
                role="SynthesisJudge",
                actor_role="synthesis_judge",
                phase="synthesis",
                action_kind="state_transition",
                action_target="finalize_synthesis",
            ),
            "high",
            "cross-domain final decision",
        ),
        (
            StepReasoningContext(
                role="MeetingReadinessGate",
                actor_role="runtime_gate",
                phase="finalization",
                action_kind="state_transition",
                action_target="meeting_readiness.evaluate",
            ),
            "high",
            "final readiness gate",
        ),
        (
            StepReasoningContext(
                role="RuntimeCheckpoint",
                actor_role="runtime",
                action_kind="state_transition",
                action_target="checkpoint.write",
            ),
            "none",
            "deterministic checkpoint",
        ),
        (
            StepReasoningContext(
                role="PipelineRunner",
                actor_role="runtime",
                action_kind="state_transition",
                action_target="run.export",
            ),
            "none",
            "deterministic export",
        ),
        (
            StepReasoningContext(
                role="CompanyResearcher",
                actor_role="researcher",
                action_kind="no_op",
                action_target="ag2.turn",
            ),
            "none",
            "narrated trace-only step",
        ),
    ],
)
def test_step_reasoning_policy_rules(context, expected_effort, expected_reason):
    policy = resolve_step_reasoning_policy(context, role_profile=_reasoning_profile(context.role))

    assert policy.policy_source == "rule"
    assert policy.effort == expected_effort
    assert policy.reason == expected_reason


def test_non_reasoning_profile_clamps_rule_policy_to_none():
    profile = build_role_model_profile(
        role="CompanyJudge",
        model="gpt-4.1",
        structured_model="gpt-4.1-mini",
    )

    policy = resolve_step_reasoning_policy(
        StepReasoningContext(
            role="CompanyJudge",
            actor_role="judge",
            action_kind="state_transition",
            action_target="judge_decision",
        ),
        role_profile=profile,
    )

    assert policy.policy_source == "safety_clamp"
    assert policy.effort == "none"
    assert policy.reason == "model does not support extended reasoning"


def test_explicit_policy_override_is_preserved_then_clamped():
    explicit = StepReasoningPolicy(
        effort="xhigh",
        max_thinking_tokens=64_000,
        max_cost_usd=5.0,
        reason="operator requested deep adjudication",
    )

    policy = resolve_step_reasoning_policy(
        StepReasoningContext(
            role="CompanyJudge",
            actor_role="judge",
            action_kind="state_transition",
            action_target="judge_decision",
            explicit_policy=explicit,
        ),
        role_profile=_reasoning_profile(),
        max_effort="high",
        max_thinking_tokens=32_000,
        max_cost_usd=1.0,
    )

    assert policy.policy_source == "safety_clamp"
    assert policy.effort == "high"
    assert policy.max_thinking_tokens == 32_000
    assert policy.max_cost_usd == 1.0
    assert policy.reason == "safety clamp applied to operator requested deep adjudication"


def test_policy_payload_matches_runtime_step_contract():
    policy = StepReasoningPolicy(
        effort="medium",
        max_thinking_tokens=16_000,
        max_output_tokens=4_000,
        max_cost_usd=0.5,
        policy_source="rule",
        reason="evidence-quality review",
        downgrade_allowed=False,
    )

    assert policy.as_runtime_step_payload() == {
        "effort": "medium",
        "max_thinking_tokens": 16_000,
        "max_output_tokens": 4_000,
        "max_cost_usd": 0.5,
        "policy_source": "rule",
        "reason": "evidence-quality review",
        "downgrade_allowed": False,
    }


def test_profile_rejects_invalid_provider():
    with pytest.raises(ValueError):
        RoleModelProfile(provider="invalid", model="gpt-5-mini")  # type: ignore[arg-type]


def test_policy_resolver_is_exported_from_config_package():
    assert exported_resolve_step_reasoning_policy is resolve_step_reasoning_policy
