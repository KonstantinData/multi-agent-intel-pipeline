# ADR-004: Progressive Assurance Shadow Mode

Status: Draft

Date: 2026-05-21

## Context

The current runtime provisions Critic/Judge roles in every department and runs
Critic review as the default assurance path for task artifacts. Judge remains
available as the bounded escalation path inside the department loop. This has
two direct costs:

- Financial: Critic and Judge steps can use medium/high reasoning budgets
  once ADR-003 reasoning policies are activated.
- Latency: additional GroupChat turns add wall-clock time even when Researcher
  output is complete and unambiguous.

Before any agent path is disabled, the runtime needs empirical data:

- How many task attempts would a signal-based gate auto-accept?
- How often would the Critic have found a real problem anyway?
- Which signals predict safe auto-acceptance and which produce false
  confidence?

ADR-004 introduces a shadow mode: the assurance gate is computed for every
task review, but the Critic continues to run. The gate verdict is stored next
to the actual Critic result so both can be compared offline before activating
any fast path.

## Decision

Introduce four typed structures:

- `TaskAssuranceSignals`: evidence-derived confidence signals for a task
  attempt.
- `TaskAssurancePolicy`: per-`task_key` gate configuration.
- `GateVerdict`: deterministic output of gate evaluation.
- `AssuranceShadowRecord`: persisted observation record that attaches signals,
  verdict, and Critic delta to every `TaskReviewArtifact`.

No agents are disabled in this ADR. The gate decides hypothetically. Critic
execution remains the authority for current runtime behavior.

## Non-Goals

ADR-004 does not:

- disable Critic, Judge, or CodingSpecialist execution;
- introduce the production fast path;
- consolidate Researcher implementation across departments;
- change AG2 GroupChat topology;
- change model/provider selection;
- use MCP for internal state transitions.

Researcher logic consolidation is related, but it is out of scope for this ADR.

## Confidence Is Not LLM-Asserted

`TaskAssuranceSignals` are computed from observable artifact properties only.
An LLM may not produce or modify any signal field.

Canonical fields:

```text
TaskAssuranceSignals
- schema_version: string
- scoring_version: string
- weights_version: string
- policy_version: string
- required_fields_score: float | null
- source_mix_score: float | null
- source_freshness_score: float | null
- contradiction_score: float | null
- evidence_strength_score: float | null
- task_criticality: low | medium | high | critical
- ltm_pattern_match: bool
- ltm_pattern_precision: float | null
- ltm_pattern_qualified: bool
- unknown_signal_count: int
```

Signal semantics:

- `required_fields_score`: fraction of required fields populated in the
  `TaskArtifact` payload.
- `source_mix_score`: score for primary/secondary source distribution against
  task policy.
- `source_freshness_score`: score for recency of cited sources. If dates are
  missing, use the policy-defined unknown-source-date behavior.
- `contradiction_score`: inverted score where `1.0` means no known unresolved
  contradiction and `0.0` means severe unresolved conflict. If contradictions
  are not structurally observable, this signal is `null`, not `1.0`.
- `evidence_strength_score`: depth and corroboration of evidence facts.
- `task_criticality`: policy-derived criticality, not model-derived.

## Versioning

The signal schema, scoring algorithm, weight vector, and per-task policy are
versioned independently:

```text
ASSURANCE_SIGNAL_SCHEMA_VERSION = "2026-05-21.1"
ASSURANCE_SCORING_VERSION = "2026-05-21.2"
ASSURANCE_WEIGHTS_VERSION = "2026-05-21.1"
TASK_ASSURANCE_POLICY_VERSION = "2026-05-21.2"
```

Every `GateVerdict` and `AssuranceShadowRecord` must persist these versions.
Without this, shadow-mode observations cannot be compared across runs after
weight or policy changes.

## TaskAssurancePolicy

`TaskAssurancePolicy` is the task-level gate configuration.

Canonical fields:

```text
TaskAssurancePolicy
- policy_version: string
- task_key: string
- auto_accept_allowed: bool
- critic_required_below: float
- judge_required_on: list[judge_condition]
- required_source_types: list[string]
- required_payload_fields: list[string]
- preferred_source_types: list[string]
- minimum_source_count: int
- task_criticality: low | medium | high | critical
- unknown_source_dates_policy: neutral | penalize
- ltm_precision_floor: float
```

The first implementation should default to conservative policies. A task can
only be marked `auto_accept_allowed=true` after shadow-mode data shows that the
gate aligns with Critic outcomes.

Policy invariants:

- `auto_accept_allowed=false` unconditionally disables the fast path regardless
  of signal quality.
- `critic_required_below` must be validated as `0.0 <= value <= 1.0`.
- `required_payload_fields=[]` means field coverage is unknown and
  `required_fields_score=null`, not `1.0`.
- `unknown_source_dates_policy="neutral"` means missing source dates contribute
  `0.5` to `source_freshness_score`.
- `unknown_source_dates_policy="penalize"` means missing source dates contribute
  `0.0` to `source_freshness_score`.
- `judge_required_on` should be represented as an immutable set of known judge
  conditions in code.

## LTM Pattern Match Rule

An LTM match is never a blind confidence booster.

In initial shadow mode:

```text
ltm_bonus_if_qualified = 0.0
```

LTM matches are recorded for analysis, but they do not raise confidence unless
an explicit empirical precision source exists.

Future activation may allow an LTM bonus only when all conditions hold:

- `ltm_pattern_precision >= policy.ltm_precision_floor`;
- matched `task_key` equals the current `task_key`;
- matched department or role scope is compatible;
- matched `pattern_type` is relevant to the current gate signal;
- matched `source_strategy` is structurally compatible with current required
  source expectations.

Below the precision floor, an LTM hit is context only. It must not lower the
Critic threshold or bypass review.

## Gate Evaluation

The gate computes a deterministic confidence score:

```text
confidence = weighted_sum(known_signals) + ltm_bonus_if_qualified
confidence = clamp(confidence, 0.0, 1.0)

effective_threshold = policy.critic_required_below
                    + criticality_delta(policy.task_criticality)
effective_threshold = clamp(effective_threshold, 0.0, 1.0)

requires_critic = confidence < effective_threshold

if policy.task_criticality == "critical":
    requires_critic = true

requires_judge = any(judge_condition_triggered)

would_auto_accept = policy.auto_accept_allowed
                 and not requires_critic
                 and not requires_judge
```

Criticality deltas:

| Criticality | Delta | Effect |
| --- | ---: | --- |
| low | -0.05 | slightly relaxed threshold |
| medium | 0.00 | no change |
| high | +0.10 | stricter threshold |
| critical | n/a | Critic always required |

Judge conditions evaluable from signals in shadow mode:

- `conflict`: triggered when `contradiction_score < 0.40`.
- `critical_decision`: triggered when `task_criticality == "critical"`.

Runtime-only judge conditions:

- `max_retries`
- `ambiguity`

Runtime-only conditions cannot be fully evaluated from signals alone. They are
recorded in `escalation_reason` when they occur.

Implementation rules:

- `evaluate_gate(signals, policy)` must be a pure function: no side effects, no
  I/O, no randomness.
- `score_required_fields(payload, required_fields)` must also be pure. Empty
  required fields return `null`; present non-empty values contribute to the
  fraction.
- The same `(signals, policy)` pair must always produce the same `GateVerdict`.
- All confidence and threshold values must be clamped to `[0.0, 1.0]`.
- `critical` tasks require an explicit `requires_critic=true` branch so
  `confidence=1.0` cannot accidentally bypass review.

## GateVerdict

Canonical fields:

```text
GateVerdict
- schema_version: string
- scoring_version: string
- weights_version: string
- policy_version: string
- confidence_score: float
- effective_threshold: float
- would_auto_accept: bool
- requires_critic: bool
- requires_judge: bool
- judge_conditions_triggered: list[string]
- reasons: list[string]
- ltm_bonus_applied: float
```

## AssuranceShadowRecord

Every `TaskReviewArtifact` should include an `AssuranceShadowRecord` once
ADR-004 is implemented.

Canonical fields:

```text
AssuranceShadowRecord
- shadow_mode: true
- gate_verdict: GateVerdict
- gate_signals: TaskAssuranceSignals
- escalation_reason: list[string]
- actual_critic_delta: CriticDeltaRecord | null
```

The record is observational. It does not change runtime behavior in ADR-004.
`actual_critic_delta` should be emitted as soon as the minimal delta extraction
is wired. A temporary `null` is allowed only during the first wiring step and
must not be treated as evidence that the Critic changed nothing.

## CriticDeltaRecord

`actual_critic_delta` is the minimum viable comparison between the hypothetical
gate decision and the actual Critic result.

Canonical fields:

```text
CriticDeltaRecord
- changed_outcome: bool
- rejected_points_count: int
- failed_core_rules: list[string]
- critic_severity: none | minor | major | blocking
- would_have_blocked_auto_accept: bool
```

This avoids waiting for a perfect structural diff implementation. It is enough
to answer the first activation question: would the gate have auto-accepted a
task that the Critic materially challenged?

In the first runtime wiring, `failed_core_rules` is conservatively populated
from `TaskReviewArtifact.rejected_points`. This is a known approximation until
Critic output separates core and supporting rejected points.

Serialization:

- Runtime dataclasses should be `frozen=True` and `slots=True` where practical.
- Every typed record should expose a deterministic `to_dict()` representation.
- Tuple, frozenset, and enum values must serialize to JSON-compatible lists or
  strings.
- `rejected_points_count` must be validated as non-negative.

## StepReasoningPolicy Coupling

ADR-004 does not enforce reasoning-budget changes. It prepares the mapping for
a later fast-path ADR:

| Path | Reasoning effort |
| --- | --- |
| `would_auto_accept` | none / low deterministic export |
| `requires_critic` | medium |
| `requires_judge` | high |

## Consequences

Positive:

- Gate logic is deterministic and testable without AG2.
- The audit and trace chain is preserved because every task still produces a
  `TaskReviewArtifact`.
- Shadow data enables evidence-based fast-path activation.
- Per-task source expectations become explicit and machine-checkable.
- Reasoning budget reductions can be evaluated before they are enforced.

Negative / risks:

- Shadow records add serialization overhead per task.
- Weight and policy versions must be managed carefully to avoid misleading
  comparisons.
- LTM precision requires empirical calibration before it may influence
  confidence.
- Some signals may be `null` until upstream artifacts expose structured
  observations such as source dates or contradictions.

## Implementation Sketch

Initial implementation files:

- `src/orchestration/assurance.py`
  - `TaskAssuranceSignals`
  - `TaskAssurancePolicy`
  - `GateVerdict`
  - `AssuranceShadowRecord`
  - `CriticDeltaRecord`
  - `score_required_fields`
  - `get_default_assurance_policy`
  - `evaluate_gate`
- `tests/architecture/test_assurance.py`
  - pure unit tests; no AG2 dependency

Integration points:

- `src/orchestration/contracts.py`
  - extend `TaskReviewArtifact` with optional `assurance_shadow`
- `src/agents/lead.py`
  - attach `AssuranceShadowRecord` in the main `review_research` tool after
    Critic review and before `TaskReviewArtifact` persistence
- `src/memory/retrieval.py`
  - provide LTM match metadata for observation only

## Open Wiring Gaps

- Follow-up `review_research` does not emit `AssuranceShadowRecord` in the
  first runtime wiring PR. This is deferred until the initial-briefing shadow
  path has produced at least one clean end-to-end observation run.
- Core/supporting rejected-point separation is not yet available in
  `TaskReviewArtifact`; `failed_core_rules` uses `rejected_points` as a
  conservative v1 approximation.

## Acceptance Criteria For Moving To Proposed

- Typed structures are implemented in a dependency-light module.
- Unit tests cover threshold clamping, criticality behavior, null signals, LTM
  no-bonus behavior, and `CriticDeltaRecord`.
- At least one end-to-end run emits shadow records without changing Critic or
  Judge execution behavior.
- A short observation plan defines how many runs are needed before any fast
  path can be considered.

## Related

- ADR-001: RuntimeStep contract
- ADR-002: OpenTelemetry and usage telemetry
- ADR-003: RoleModelProfile and StepReasoningPolicy
- ADR-005: Provider adapter boundary
