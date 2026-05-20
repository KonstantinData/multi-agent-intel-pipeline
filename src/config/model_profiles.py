"""Typed role model profiles and deterministic step reasoning policy rules."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh"]
PolicySource = Literal["role_default", "rule", "explicit_override", "safety_clamp"]
ProviderName = Literal["openai", "anthropic", "bedrock", "local", "other"]

VALID_REASONING_EFFORTS: frozenset[str] = frozenset(
    {"none", "low", "medium", "high", "xhigh"},
)
VALID_POLICY_SOURCES: frozenset[str] = frozenset(
    {"role_default", "rule", "explicit_override", "safety_clamp"},
)
VALID_PROVIDERS: frozenset[str] = frozenset({"openai", "anthropic", "bedrock", "local", "other"})

REASONING_MODEL_PREFIXES: tuple[str, ...] = ("gpt-5", "o3", "o4")
STRUCTURED_MODEL_PREFIXES: tuple[str, ...] = ("gpt-4.1", "gpt-4o", "gpt-5", "o3", "o4")
TEMPERATURE_LOCKED_MODEL_PREFIXES: tuple[str, ...] = ("gpt-5",)


@dataclass(frozen=True, slots=True)
class StepReasoningPolicy:
    """Step-level reasoning budget resolved from role profile plus step rules."""

    effort: ReasoningEffort = "none"
    max_thinking_tokens: int | None = None
    max_output_tokens: int | None = None
    max_cost_usd: float | None = None
    policy_source: PolicySource = "role_default"
    reason: str = "role default"
    downgrade_allowed: bool = True

    def __post_init__(self) -> None:
        if self.effort not in VALID_REASONING_EFFORTS:
            raise ValueError(f"invalid reasoning effort: {self.effort}")
        if self.policy_source not in VALID_POLICY_SOURCES:
            raise ValueError(f"invalid policy source: {self.policy_source}")
        if self.max_thinking_tokens is not None and self.max_thinking_tokens < 0:
            raise ValueError("max_thinking_tokens must be >= 0")
        if self.max_output_tokens is not None and self.max_output_tokens < 0:
            raise ValueError("max_output_tokens must be >= 0")
        if self.max_cost_usd is not None and self.max_cost_usd < 0:
            raise ValueError("max_cost_usd must be >= 0")

    def as_runtime_step_payload(self) -> dict[str, Any]:
        """Return the ADR-003 payload shape for RuntimeStep.intent."""

        return {
            "effort": self.effort,
            "max_thinking_tokens": self.max_thinking_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_cost_usd": self.max_cost_usd,
            "policy_source": self.policy_source,
            "reason": self.reason,
            "downgrade_allowed": self.downgrade_allowed,
        }


@dataclass(frozen=True, slots=True)
class RoleModelProfile:
    """Role-level model capability envelope."""

    provider: ProviderName
    model: str
    structured_model: str | None = None
    supports_reasoning: bool = False
    supports_structured_output: bool = False
    supports_temperature: bool = True
    default_temperature: float | None = 0.1
    timeout_seconds: float = 90.0
    max_retries: int = 1
    default_reasoning_policy: StepReasoningPolicy = field(
        default_factory=StepReasoningPolicy,
    )
    provider_options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.provider not in VALID_PROVIDERS:
            raise ValueError(f"invalid provider: {self.provider}")
        if not str(self.model or "").strip():
            raise ValueError("model is required")
        if self.structured_model is not None and not str(self.structured_model).strip():
            raise ValueError("structured_model must be non-empty when provided")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "structured_model": self.structured_model,
            "supports_reasoning": self.supports_reasoning,
            "supports_structured_output": self.supports_structured_output,
            "supports_temperature": self.supports_temperature,
            "default_temperature": self.default_temperature,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "default_reasoning_policy": self.default_reasoning_policy.as_runtime_step_payload(),
            "provider_options": dict(self.provider_options),
        }


@dataclass(frozen=True, slots=True)
class StepReasoningContext:
    """Dependency-light context for deterministic reasoning policy resolution."""

    role: str
    actor_role: str = ""
    phase: str = ""
    action_kind: str = ""
    action_target: str = ""
    department: str = ""
    task_key: str = ""
    explicit_policy: StepReasoningPolicy | None = None


def model_supports_reasoning(model_name: str) -> bool:
    normalized = str(model_name or "").strip().lower()
    return bool(normalized) and normalized.startswith(REASONING_MODEL_PREFIXES)


def model_supports_structured_output(model_name: str) -> bool:
    normalized = str(model_name or "").strip().lower()
    return bool(normalized) and normalized.startswith(STRUCTURED_MODEL_PREFIXES)


def model_supports_temperature(model_name: str) -> bool:
    normalized = str(model_name or "").strip().lower()
    return not normalized.startswith(TEMPERATURE_LOCKED_MODEL_PREFIXES)


def default_reasoning_policy_for_role(role: str, *, supports_reasoning: bool) -> StepReasoningPolicy:
    if not supports_reasoning:
        return StepReasoningPolicy(
            effort="none",
            reason="role uses a non-reasoning model",
        )
    lowered = role.lower()
    if "judge" in lowered:
        return StepReasoningPolicy(
            effort="high",
            max_thinking_tokens=32_000,
            policy_source="role_default",
            reason="judge role handles borderline adjudication",
            downgrade_allowed=True,
        )
    if "critic" in lowered:
        return StepReasoningPolicy(
            effort="medium",
            max_thinking_tokens=16_000,
            policy_source="role_default",
            reason="critic role reviews evidence quality",
            downgrade_allowed=True,
        )
    if "synthesis" in lowered:
        return StepReasoningPolicy(
            effort="medium",
            max_thinking_tokens=16_000,
            policy_source="role_default",
            reason="synthesis role integrates cross-domain evidence",
            downgrade_allowed=True,
        )
    if "researcher" in lowered:
        return StepReasoningPolicy(
            effort="low",
            max_thinking_tokens=8_000,
            policy_source="role_default",
            reason="research role is tool-heavy and volume-bound",
            downgrade_allowed=True,
        )
    return StepReasoningPolicy(
        effort="low",
        max_thinking_tokens=8_000,
        policy_source="role_default",
        reason="reasoning-capable default role profile",
        downgrade_allowed=True,
    )


def build_role_model_profile(
    *,
    role: str,
    model: str,
    structured_model: str | None,
    provider: ProviderName = "openai",
    timeout_seconds: float = 90.0,
    max_retries: int = 1,
    default_temperature: float | None = 0.1,
    provider_options: dict[str, Any] | None = None,
) -> RoleModelProfile:
    supports_reasoning = model_supports_reasoning(model)
    structured = structured_model or None
    return RoleModelProfile(
        provider=provider,
        model=model,
        structured_model=structured,
        supports_reasoning=supports_reasoning,
        supports_structured_output=(
            model_supports_structured_output(model)
            or bool(structured and model_supports_structured_output(structured))
        ),
        supports_temperature=model_supports_temperature(model),
        default_temperature=default_temperature if model_supports_temperature(model) else None,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        default_reasoning_policy=default_reasoning_policy_for_role(
            role,
            supports_reasoning=supports_reasoning,
        ),
        provider_options=dict(provider_options or {}),
    )


def resolve_step_reasoning_policy(
    context: StepReasoningContext | dict[str, Any],
    *,
    role_profile: RoleModelProfile,
    max_effort: ReasoningEffort | None = None,
    max_thinking_tokens: int | None = None,
    max_cost_usd: float | None = None,
) -> StepReasoningPolicy:
    """Resolve deterministic ADR-003 step reasoning policy."""

    ctx = _coerce_context(context)
    if ctx.explicit_policy is not None:
        policy = replace(
            ctx.explicit_policy,
            policy_source="explicit_override",
            reason=ctx.explicit_policy.reason or "explicit step override",
        )
    else:
        policy = _rule_policy(ctx) or role_profile.default_reasoning_policy

    if not role_profile.supports_reasoning and policy.effort != "none":
        policy = StepReasoningPolicy(
            effort="none",
            max_output_tokens=policy.max_output_tokens,
            max_cost_usd=policy.max_cost_usd,
            policy_source="safety_clamp",
            reason="model does not support extended reasoning",
            downgrade_allowed=True,
        )

    return _apply_safety_clamp(
        policy,
        max_effort=max_effort,
        max_thinking_tokens=max_thinking_tokens,
        max_cost_usd=max_cost_usd,
    )


def _coerce_context(context: StepReasoningContext | dict[str, Any]) -> StepReasoningContext:
    if isinstance(context, StepReasoningContext):
        return context
    return StepReasoningContext(
        role=str(context.get("role", "") or ""),
        actor_role=str(context.get("actor_role", "") or ""),
        phase=str(context.get("phase", "") or ""),
        action_kind=str(context.get("action_kind", "") or ""),
        action_target=str(context.get("action_target", "") or ""),
        department=str(context.get("department", "") or ""),
        task_key=str(context.get("task_key", "") or ""),
        explicit_policy=context.get("explicit_policy"),
    )


def _rule_policy(context: StepReasoningContext) -> StepReasoningPolicy | None:
    action_kind = context.action_kind.strip().lower()
    action_target = context.action_target.strip().lower()
    actor_role = context.actor_role.strip().lower()
    role = context.role.strip().lower()
    phase = context.phase.strip().lower()

    if action_kind == "no_op":
        return StepReasoningPolicy(
            effort="none",
            policy_source="rule",
            reason="narrated trace-only step",
        )
    if action_target == "checkpoint.write":
        return StepReasoningPolicy(
            effort="none",
            policy_source="rule",
            reason="deterministic checkpoint",
        )
    if action_target == "run.export":
        return StepReasoningPolicy(
            effort="none",
            policy_source="rule",
            reason="deterministic export",
        )
    if action_kind == "capability_call" and action_target == "research.run":
        return StepReasoningPolicy(
            effort="low",
            max_thinking_tokens=8_000,
            policy_source="rule",
            reason="tool-heavy research step",
            downgrade_allowed=True,
        )
    if action_target == "meeting_readiness.evaluate":
        return StepReasoningPolicy(
            effort="high",
            max_thinking_tokens=32_000,
            policy_source="rule",
            reason="final readiness gate",
            downgrade_allowed=True,
        )
    if actor_role == "synthesis_judge" or "synthesisjudge" in role:
        return StepReasoningPolicy(
            effort="high",
            max_thinking_tokens=32_000,
            policy_source="rule",
            reason="cross-domain final decision",
            downgrade_allowed=True,
        )
    if actor_role == "judge" or role.endswith("judge"):
        return StepReasoningPolicy(
            effort="high",
            max_thinking_tokens=32_000,
            policy_source="rule",
            reason="borderline adjudication",
            downgrade_allowed=True,
        )
    if actor_role == "critic" or role.endswith("critic"):
        return StepReasoningPolicy(
            effort="medium",
            max_thinking_tokens=16_000,
            policy_source="rule",
            reason="evidence-quality review",
            downgrade_allowed=True,
        )
    if phase == "synthesis" and actor_role in {"runtime_node", "analyst"}:
        return StepReasoningPolicy(
            effort="medium",
            max_thinking_tokens=16_000,
            policy_source="rule",
            reason="cross-domain integration",
            downgrade_allowed=True,
        )
    return None


def _apply_safety_clamp(
    policy: StepReasoningPolicy,
    *,
    max_effort: ReasoningEffort | None,
    max_thinking_tokens: int | None,
    max_cost_usd: float | None,
) -> StepReasoningPolicy:
    effort = policy.effort
    thinking_tokens = policy.max_thinking_tokens
    cost = policy.max_cost_usd
    changed = False

    if max_effort is not None and _effort_rank(effort) > _effort_rank(max_effort):
        effort = max_effort
        changed = True
    if max_thinking_tokens is not None:
        if thinking_tokens is None or thinking_tokens > max_thinking_tokens:
            thinking_tokens = max_thinking_tokens
            changed = True
    if max_cost_usd is not None:
        if cost is None or cost > max_cost_usd:
            cost = max_cost_usd
            changed = True

    if not changed:
        return policy
    return StepReasoningPolicy(
        effort=effort,
        max_thinking_tokens=thinking_tokens,
        max_output_tokens=policy.max_output_tokens,
        max_cost_usd=cost,
        policy_source="safety_clamp",
        reason=f"safety clamp applied to {policy.reason}",
        downgrade_allowed=policy.downgrade_allowed,
    )


def _effort_rank(effort: str) -> int:
    order = {"none": 0, "low": 1, "medium": 2, "high": 3, "xhigh": 4}
    return order.get(effort, 0)
