# ADR-003: RoleModelProfile And StepReasoningPolicy

Status: Proposed

Date: 2026-05-20

## Context

The runtime currently resolves models with role-level defaults in
`src/config/settings.py`:

- `ROLE_MODEL_DEFAULTS`
- `ROLE_STRUCTURED_MODEL_DEFAULTS`
- role-specific environment overrides such as `OPENAI_MODEL_COMPANY_RESEARCHER`

This is sufficient for non-reasoning `gpt-4.1`-family operation, but it is not
enough for reasoning-capable models because reasoning is not only a role choice.
The runtime needs two independent decisions:

1. Which provider/model profile is assigned to a role.
2. How much reasoning budget is allowed for a specific step.

ADR-001 already added `intent.reasoning_policy` and
`execution.reasoning_realized` to `RuntimeStep`. ADR-002 added the telemetry
path for `reasoning.effort_planned`, `reasoning.effort_used`, token metrics,
and usage metrics. The ADR-001 observation sprint did not include a
reasoning-capable model run, so ADR-003 needed a controlled validation path for
`thinking_tokens` and planned-vs-realized reasoning deltas.

ADR-003 defines the configuration and policy layer needed to run one controlled
reasoning-capable validation run and later tune reasoning budgets from traces.

## Decision

Introduce a two-stage model and reasoning configuration model:

1. `RoleModelProfile`
2. `StepReasoningPolicy`

`RoleModelProfile` chooses the provider/model capability envelope for a role.
`StepReasoningPolicy` chooses the reasoning budget for a specific step within
that role.

The runtime must resolve the effective policy in this order:

```text
role defaults
-> role environment override
-> step policy rule
-> explicit step override
-> safety/cost clamp
```

The resolved reasoning policy should be written to
`RuntimeStep.intent.reasoning_policy`. Realized provider metadata should be
written to `RuntimeStep.execution.reasoning_realized` when available.

## RoleModelProfile

`RoleModelProfile` is the stable role-level configuration object.

Canonical fields:

```text
RoleModelProfile
- provider: openai | anthropic | bedrock | local | other
- model: string
- structured_model: string | null
- supports_reasoning: bool
- supports_structured_output: bool
- supports_temperature: bool
- default_temperature: float | null
- timeout_seconds: float
- max_retries: int
- default_reasoning_policy: StepReasoningPolicy
- provider_options: dict
```

Initial defaults:

| Role group | Profile intent |
| --- | --- |
| Supervisor | non-reasoning or low reasoning by default; medium only for ambiguous routing |
| Department Lead | low/medium; owns completion but should not spend high effort on every turn |
| Researcher | low/medium; volume-bound, tool-heavy, not the main reasoning bottleneck |
| Critic | medium/high; evidence-quality review benefits from deeper analysis |
| Judge | high; borderline decisions and conflict resolution are high-leverage |
| Synthesis Lead/Analyst | medium/high; cross-domain integration is high-leverage |
| Synthesis Judge | high; final edge-case adjudication is high-leverage |
| Coding Specialist | low/medium; deterministic code/debug work should stay bounded |
| ReportWriter | low/medium; composition should use structure and gates more than long reasoning |

The first implementation should keep OpenAI as the only concrete adapter and
represent other providers as future-compatible profile fields, not active
runtime dependencies.

## StepReasoningPolicy

`StepReasoningPolicy` is the step-level reasoning budget.

Canonical fields:

```text
StepReasoningPolicy
- effort: none | low | medium | high | xhigh
- max_thinking_tokens: int | null
- max_output_tokens: int | null
- max_cost_usd: float | null
- policy_source: role_default | rule | explicit_override | safety_clamp
- reason: string
- downgrade_allowed: bool
```

`effort=none` means no extended reasoning should be requested. It is valid for
non-reasoning models and for reasoning-capable models where the step should not
spend thinking budget.

`max_thinking_tokens=null` means the provider default applies. A non-null value
is a runtime cap and should be surfaced in traces.

The policy reason must be concise and non-sensitive. It should explain the
budget class, not reveal prompt content or hidden reasoning.

## Step Policy Rules

The first implementation should support deterministic rules before adding any
model-driven budget selector.

Suggested initial rules:

| Match | Effort | Reason |
| --- | --- | --- |
| `action.kind=capability_call` and `action.target=research.run` | low/medium | Tool-heavy research step |
| `actor.role=critic` | medium | Evidence-quality review |
| `actor.role=judge` | high | Borderline adjudication |
| `actor.role=synthesis_judge` | high | Cross-domain final decision |
| `phase=synthesis` and `actor.role in {runtime_node, analyst}` | medium/high | Cross-domain integration |
| `action.target=meeting_readiness.evaluate` | high | Final readiness gate |
| `action.target=run.export` | none | Deterministic export |
| `action.target=checkpoint.write` | none | Deterministic checkpoint |
| `action.kind=no_op` | none | Narrated trace-only step |

Policy rules must be deterministic and testable. Do not let a model decide its
own budget in the initial ADR-003 implementation.

## Telemetry Contract

Planned reasoning:

```text
RuntimeStep.intent.reasoning_policy
- effort
- max_thinking_tokens
- max_output_tokens
- max_cost_usd
- policy_source
- reason
- downgrade_allowed
```

Realized reasoning:

```text
RuntimeStep.execution.reasoning_realized
- effort_used
- thinking_tokens
- reasoning_summary_available
```

Token counts remain canonical in `RuntimeStep.execution.usage`, per ADR-002.
`reasoning_realized` must not duplicate `prompt_tokens`, `completion_tokens`,
or `total_tokens`.

## Controlled Validation Run

ADR-003 cannot move from `Draft` to `Proposed` until one controlled
reasoning-capable validation run is completed.

Validation run requirements:

- Use exactly one production-like initial briefing run.
- Use a manufacturer in industrial goods, medical technology, or electrical
  engineering.
- Keep the high-level pipeline unchanged.
- Enable RuntimeSteps and ADR-002 telemetry.
- Configure only a narrow set of high-leverage roles to a reasoning-capable
  profile: Judge, SynthesisJudge, and MeetingReadinessGate-equivalent steps.
- Keep Researchers on the existing non-reasoning or low-budget profile.
- Persist the full `step_trace.json`.
- Record model/provider, planned effort, realized effort, `thinking_tokens`
  where available, total tokens, cost, latency, and final status.

Suggested input class:

```text
company_name: manufacturer with public website and enough source coverage
web_domain: canonical public domain
```

The run should answer:

- Did `intent.reasoning_policy` appear on the expected steps?
- Did the provider return usable `execution.reasoning_realized` metadata?
- Are `thinking_tokens` available and non-zero for high-effort steps?
- Are Judge/SynthesisJudge decisions materially better or only more expensive?
- Did latency or cost exceed acceptable bounds?
- Which steps should be downgraded before production rollout?

### Validation Run 1 — 2026-05-20

Run metadata:

- `run_id`: `20260520T210613Z`
- Company: Phoenix Contact GmbH & Co. KG
- Domain: `phoenixcontact.com`
- Industry class: electrical engineering / industrial automation
- Storage profile: `local_dev`
- RuntimeSteps: enabled
- OTel flag: enabled, but local OTel SDK was not installed; the OTel consumer
  failed open and was disabled for this run
- Narrow reasoning-capable overrides: Judge roles, `SynthesisJudge`, and
  `MeetingReadinessGate` profile set to `gpt-5-mini`; Researchers remained on
  the existing non-reasoning profile

Run outcome:

- Final status: `blocked_not_meeting_ready`
- `step_trace.json` persisted with 48 steps
- `intent.reasoning_policy` was present on all 48 steps
- Planned reasoning effort distribution: 47 `none`, 1 `high`
- The single high-effort planned step was
  `finalization / MeetingReadinessGate / meeting_readiness.evaluate`
- Usage-bearing steps: 9
- `execution.reasoning_realized` steps: 0
- `thinking_tokens` total: 0

Answers to the validation questions:

- `intent.reasoning_policy` appears reliably on RuntimeSteps.
- The current trace does not capture usable realized reasoning metadata from
  AG2 GroupChat model calls.
- `thinking_tokens` were not available in the persisted trace.
- `SynthesisJudge` did run with the reasoning-capable override and produced a
  conservative accept-with-gaps decision, but that model call was visible only
  in the console transcript, not as a usage-bearing RuntimeStep.
- `MeetingReadinessGate` received a high planned policy, but it is currently a
  deterministic runtime gate and has no provider usage to realize.
- Runtime cost in the exported run was estimated at approximately USD 1.44, but
  AG2 emitted zero-price warnings for dated model aliases, so cost telemetry is
  not yet reliable enough for budget tuning.

Conclusion:

Validation Run 1 completed the production-like workflow, but it does **not**
satisfy the ADR-003 promotion gate. The planned-policy path works; the realized
reasoning telemetry path is still incomplete for reasoning-capable AG2 turns.
ADR-003 remains `Draft`.

Required follow-up before promotion:

- Emit usage-bearing RuntimeSteps for AG2 adjudication/model-call turns,
  especially Judge and `SynthesisJudge`. Completed for the observed
  `SynthesisJudge` path by PR #95 and the SynthesisRuntime forwarding fix in
  PR #96.
- Capture provider usage for those turns and map reasoning/thinking tokens into
  `execution.usage.thinking_tokens` plus
  `execution.reasoning_realized.thinking_tokens`.
- Add OTel SDK dependencies or document the local validation path as
  step-trace-only when OTel is intentionally unavailable.
- Resolve or suppress AG2 pricing warnings for dated model aliases so cost
  telemetry can be trusted.
- Re-run one controlled validation run after these fixes and promote ADR-003
  only if at least one high-effort reasoning-capable step has realized
  reasoning metadata.

### Validation Run 2 — 2026-05-20

Run metadata:

- `run_id`: `20260520T222636Z`
- Company: Phoenix Contact GmbH & Co. KG
- Domain: `phoenixcontact.com`
- Industry class: electrical engineering / industrial automation
- Storage profile: `local_dev`
- RuntimeSteps: enabled
- OTel flag: enabled, but local OTel SDK availability was not required for this
  step-trace validation
- Narrow reasoning-capable overrides: Judge roles, `SynthesisJudge`, and
  `MeetingReadinessGate` profile set to `gpt-5-mini`; Researchers remained on
  the existing non-reasoning profile
- Code state: `main` after PR #95 and PR #96

Run outcome:

- Final status: `blocked_not_meeting_ready`
- `step_trace.json` persisted with 53 steps
- Usage-bearing steps: 10
- AG2 usage-bearing steps: 1
- The AG2 usage-bearing step was
  `synthesis / SynthesisJudge / ag2.synthesis_judge_usage`
- `SynthesisJudge` usage payload:
  - provider: `openai`
  - model: `gpt-5-mini`
  - `llm_calls`: 1
  - `prompt_tokens`: 1439
  - `completion_tokens`: 1787
  - `total_tokens`: 3226
- High-effort planned steps: 2
  - `ag2.synthesis_judge_usage`
  - `meeting_readiness.evaluate`
- `execution.reasoning_realized` steps: 0
- `thinking_tokens` total: 0

Answers to the validation questions:

- `intent.reasoning_policy` now reaches a reasoning-capable AG2 adjudication
  step.
- AG2 usage emission now records the observed `SynthesisJudge` model call in
  the persisted `step_trace.json`.
- The previous `SynthesisRuntime.run(step_emitter=...)` integration failure is
  resolved by PR #96.
- The provider/AG2 path still does not expose `thinking_tokens` in the usage
  summary, so `execution.reasoning_realized` cannot be populated.
- `MeetingReadinessGate` remains deterministic and correctly has no realized
  provider usage.
- AG2 still emits zero-price warnings for dated model aliases, so cost telemetry
  is still not reliable enough for budget tuning.

Conclusion:

Validation Run 2 confirms that the planned-policy path and AG2 usage-step
emission path now work for `SynthesisJudge`. It still does **not** satisfy the
ADR-003 promotion gate because no high-effort reasoning-capable step has
realized reasoning metadata. ADR-003 remains `Draft`.

Remaining follow-up before promotion:

- Identify or implement a provider/API path that exposes reasoning token
  counts for reasoning-capable model calls.
- Extend the AG2 adapter or bypass path so those counts are mapped into
  `execution.usage.thinking_tokens` and
  `execution.reasoning_realized.thinking_tokens`.
- Decide whether the validation criterion should require true provider
  reasoning-token telemetry or accept usage-only telemetry for AG2 models that
  do not expose it.
- Resolve or suppress AG2 pricing warnings for dated model aliases so cost
  telemetry can be trusted.
- Re-run one controlled validation run after the reasoning-token telemetry path
  exists and promote ADR-003 only if at least one high-effort step has realized
  reasoning metadata.

### Validation Run 3 — 2026-05-21

Run metadata:

- `run_id`: `20260521T081418Z`
- Company: ZIEHL-ABEGG SE
- Domain: `ziehl-abegg.com`
- Industry class: mechanical engineering / ventilation, drive, and control
  technology
- Storage profile: `local_dev`
- RuntimeSteps: enabled
- OTel flag: disabled for local step-trace-only validation
- Narrow reasoning-capable overrides: Judge roles, `SynthesisJudge`, and
  `MeetingReadinessGate` profile set to `gpt-5-mini`; Researchers remained on
  the existing non-reasoning profile
- Code state: branch `codex/ag2-reasoning-token-telemetry`
- Implementation under validation:
  - AG2 OpenAI usage enrichment preserves provider `reasoning_tokens` /
    `thinking_tokens`
  - AG2 usage summaries retain reasoning-token deltas
  - AG2 role configs pass `reasoning_effort` inside the `config_list` entry

Discarded validation attempts before this run:

- `20260521T081244Z` / Phoenix Contact failed before AG2 execution because the
  homepage fetch was denied.
- `20260521T081312Z` / ZIEHL-ABEGG reached first-pass setup but exposed an AG2
  config placement bug: `reasoning_effort` was invalid as a top-level
  `llm_config` field and must live in the OpenAI `config_list` entry.

Run outcome:

- Final status: `blocked_not_meeting_ready`
- `step_trace.json` persisted with 83 steps
- Usage-bearing steps: 11
- AG2 usage-bearing steps: 1
- The AG2 usage-bearing step was
  `synthesis / SynthesisJudge / ag2.synthesis_judge_usage`
- `SynthesisJudge` usage payload:
  - provider: `openai`
  - model: `gpt-5-mini`
  - `llm_calls`: 1
  - `prompt_tokens`: 1450
  - `completion_tokens`: 4962
  - `total_tokens`: 6412
  - `thinking_tokens`: 3840
  - estimated cost: USD 0.0102865
- `execution.reasoning_realized` steps: 1
- Realized reasoning payload:
  - `effort_used`: `high`
  - `thinking_tokens`: 3840
  - `reasoning_summary_available`: `false`
- `thinking_tokens` total: 3840

Answers to the validation questions:

- `intent.reasoning_policy` reaches a reasoning-capable AG2 adjudication step.
- AG2 now emits a usage-bearing RuntimeStep for the observed `SynthesisJudge`
  model call.
- Provider reasoning-token telemetry is preserved through AG2 and mapped into
  `execution.usage.thinking_tokens`.
- The StepEmitter now derives `execution.reasoning_realized` for the same
  high-effort step.
- `MeetingReadinessGate` remains deterministic and correctly has no realized
  provider usage.

Conclusion:

Validation Run 3 satisfies the ADR-003 promotion gate: at least one high-effort
reasoning-capable step has realized reasoning metadata in the persisted
RuntimeStep trace. ADR-003 can move from `Draft` to `Proposed`.

Remaining follow-up after promotion:

- Keep monitoring whether AG2 preserves reasoning-token metadata natively in a
  future version so the local compatibility patch can be removed.
- Decide whether Judge and SynthesisJudge should keep identical high-effort
  profiles or receive separate caps after more traces exist.
- Resolve or suppress AG2 pricing warnings for dated model aliases so cost
  telemetry can be trusted for budget tuning.

## Goals

- Replace flat role model defaults with a typed `RoleModelProfile` concept.
- Add deterministic `StepReasoningPolicy` resolution.
- Preserve existing environment override compatibility during migration.
- Populate planned reasoning policy on RuntimeSteps.
- Capture realized reasoning metadata when the provider exposes it.
- Run one controlled reasoning-capable validation run before implementation is
  promoted beyond draft/prototype.
- Make reasoning-budget tuning possible from ADR-002 traces.

## Non-Goals

- Do not replace the phase pipeline.
- Do not change department autonomy or speaker selection.
- Do not migrate providers beyond OpenAI in the first implementation.
- Do not introduce dynamic model-driven budget selection in the first
  implementation.
- Do not require all roles to use reasoning-capable models.
- Do not tune final production budgets from theory alone.
- Do not store hidden chain-of-thought in traces.

## Migration Plan

1. Add dependency-light profile dataclasses or typed dicts in
   `src/config/model_profiles.py`.
2. Keep `get_role_model_selection(role)` as a backwards-compatible facade.
3. Add `get_role_model_profile(role)` for new runtime code.
4. Add deterministic `resolve_step_reasoning_policy(step_context)` with rule
   coverage tests.
5. Update RuntimeStep emitters to attach planned reasoning policy where a
   model call or adjudication step is represented.
6. Add provider metadata extraction for realized reasoning where available.
7. Run the controlled validation run and summarize it in this ADR.
8. Promote ADR-003 from `Draft` to `Proposed` only after the validation run
   confirms the telemetry path works.

## Test Strategy

- Architecture tests for role-profile defaults and environment override
  compatibility.
- Policy tests for deterministic effort selection by role, phase, action kind,
  and target.
- Safety-clamp tests for max cost and max thinking tokens.
- RuntimeStep tests asserting planned policy is emitted without raw prompts.
- Provider-adapter tests using fake responses with and without
  `thinking_tokens`.
- Validation-run snapshot test or fixture asserting at least one high-effort
  step has realized reasoning metadata when the provider returns it.

## Open Questions

- Should Judge and SynthesisJudge use the same profile or separate caps?
- Should `max_thinking_tokens` be global, per role, or per step rule?
- Should `MeetingReadinessGate` be promoted to an explicit model-backed actor,
  or should it remain deterministic with high reasoning only in adjacent
  synthesis/judge steps?
- What cost ceiling per run is acceptable for high-effort reasoning?
- Should the local AG2 usage compatibility patch be upstreamed, kept as a
  version-gated shim, or removed once AG2 preserves reasoning-token metadata
  natively?

## Consequences

Positive:

- Model choice and reasoning budget become separable and auditable.
- High-effort reasoning can be reserved for the few steps where it matters.
- ADR-002 telemetry can support real budget tuning instead of guesswork.
- Existing non-reasoning runtime behavior can remain the default.

Costs:

- Additional configuration surface and tests.
- Provider metadata extraction must handle missing or inconsistent fields.
- Validation runs may be more expensive and slower.

Risks:

- Over-budgeting Judge/SynthesisJudge may increase cost without improving
  output quality.
- Under-instrumented provider responses may make realized effort hard to
  compare across models.
- If policy rules become too broad, the runtime may accidentally spend
  reasoning budget on deterministic or low-value steps.
