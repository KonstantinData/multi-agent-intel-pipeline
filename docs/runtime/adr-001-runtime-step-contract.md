# ADR-001: RuntimeStep Contract And StepBus

Status: Accepted

Date: 2026-05-19

## Context

The current runtime is a stable phase pipeline:

1. Intake and Supervisor brief
2. Department execution
3. Resolution and optional closure
4. Synthesis
5. Meeting-readiness finalization
6. Report writing and export

This shape is correct for the product goal: build a pre-meeting briefing from
`company_name` and `web_domain`. The high-level phase order should remain
stable. The missing layer is not a replacement orchestrator. The missing layer
is a common step contract that makes phase transitions, department turns,
tool/capability calls, state transitions, reasoning budgets, observations, and
outcomes visible in one trace format.

Today those facts are split across messages, checkpoints, department packages,
`DepartmentRunState`, usage counters, logs, and UI callbacks. That makes it hard
to add OpenTelemetry, streaming, evals, step-level reasoning budgets, and later
imperative loops in closure or follow-up without re-negotiating the data model.

## Decision

Introduce a `RuntimeStep` envelope and a small `StepBus`.

The first implementation is narrated-only: existing phase code and department
runtime code emit `RuntimeStep` records after work is planned or completed. No
pipeline behavior changes in ADR-001.

The schema is deliberately compatible with a later imperative mode: a future
actor may emit an `intent` first, the runtime may validate and execute that
intent, and then append `execution` and `outcome`.

## Goals

- Define a versioned `RuntimeStep` type and validator.
- Introduce a `StepBus` with schema-version-aware consumers.
- Emit narrated steps for all existing major phase boundaries.
- Emit secondary narrated steps for AG2 department turns where the message
  history is already available.
- Persist a first step trace snapshot in run artifacts.
- Provide an in-memory eval sink for local inspection and tests.
- Provide a UI/event-log compatible consumer so streaming can attach later.
- Support deterministic idempotency keys for retried step emission.

## Non-Goals

- Do not change Department autonomy.
- Do not replace the top-level phase pipeline.
- Do not introduce new agent planning behavior.
- Do not migrate tools to MCP.
- Do not introduce provider abstraction.
- Do not implement production OpenTelemetry aggregation.
- Do not change Supervisor admission, Critic, Judge, or package finalization
  semantics.

## RuntimeStep Envelope

`RuntimeStep` has five top-level blocks:

```text
RuntimeStep
- identity
- scope
- intent
- execution
- outcome
```

Shared reference fields use `RuntimeRef`:

```text
RuntimeRef
- kind: artifact_id | uri | inline
- value: string
- mime_type: string | null
```

`artifact_id` points to a run artifact or persisted runtime artifact. `uri`
points to a local or remote resource that is safe to reference. `inline` is for
small bounded values only; emitters should prefer artifact references for raw
page content, prompts, large observations, and generated reports.

Other referenced sub-types (`CapabilityCall`, `StateTransition`,
`Observation`, `RuntimeStepError`, `ReasoningPolicy`, `ApprovalPolicy`,
`ExpectedObservation`, and `UsageRecord`) are intentionally named here but not
fully expanded. Their canonical field definitions belong in
`src/orchestration/runtime_step.py` during ADR-001 implementation. The
implementation should keep those sub-types stable enough for consumers while
allowing the observation sprint to validate their exact payload shape.

### identity

```text
identity
- schema_version: string
- run_id: string
- step_id: string
- parent_step_id: string | null
- idempotency_key: string
- sequence: int
- emitted_at: ISO-8601 timestamp
```

`step_id` is the trace identity. `idempotency_key` is the retry identity.
They are intentionally separate.

Default idempotency key input:

```text
run_id + parent_step_id + mode + planned_action + task_key + attempt
```

The implementation must canonicalize the planned action payload before hashing:
stable JSON key order, normalized whitespace for strings, and removal of
non-semantic formatting differences. Large payloads such as prompts or raw page
text should be referenced by `input_refs` or `output_refs` instead of embedded
directly.

### scope

```text
scope
- mode: narrated | imperative
- phase: string
- department: string | null
- task_key: string | null
- attempt: int | null
- actor: string
- actor_role: string
```

`mode=narrated` means existing code reports what happened. `mode=imperative`
is reserved for later runtime-controlled execution of planned steps.

### intent

```text
intent
- goal: string
- input_refs: list[RuntimeRef]
- planned_action: PlannedAction
- reasoning_policy: ReasoningPolicy | null
- approval_policy: ApprovalPolicy | null
- expected_observation: ExpectedObservation | null
- deadline: timestamp | duration | null
```

`expected_observation` is optional in narrated mode, but should be filled where
the phase code already knows what it expects. This later allows calibration
analysis between expected and realized outcomes.

`deadline` is optional. If omitted, the step inherits the parent or phase-level
guardrail.

### planned_action

```text
PlannedAction
- kind: capability_call | state_transition | sub_step_spawn | no_op
- target: string
- payload: dict
```

`planned_action` is structured, not free text. This allows narrated mode to map
existing code into a typed trace and allows imperative mode to validate and
execute future intents without parsing prose.

### execution

```text
execution
- status: pending | running | completed | failed | skipped | cancelled
- capability_calls: list[CapabilityCall]
- state_transitions: list[StateTransition]
- spawned_steps: list[string]
- observations: list[Observation]
- reasoning_realized: ReasoningRealized | null
- usage: UsageRecord | null
- errors: list[RuntimeStepError]
```

Capabilities are actions in the outside world: search, fetch, extraction,
browser/computer use, code execution, database lookup, or other external tool
work.

State transitions are changes to the runtime's own state: task status updates,
review records, judge decisions, package finalization, admission decisions, and
checkpoint writes. They are auditable in the trace, but remain in-process
functions. They are not generally discoverable MCP tools.

`reasoning_realized` records actual usage:

```text
ReasoningRealized
- effort_used: none | low | medium | high | xhigh | unknown
- thinking_tokens: int
- prompt_tokens: int
- completion_tokens: int
- total_tokens: int
```

This is separate from `intent.reasoning_policy`, so eval consumers can compare
reserved effort with actual consumption.

For non-reasoning-capable models, `reasoning_realized` should be `null`. Use
`effort_used="none"` only when a reasoning-capable model was invoked with no
extended reasoning. Use `effort_used="unknown"` when the provider did not return
enough metadata to classify realized effort.

### outcome

```text
outcome
- decision: string
- reflection: string
- stop_reason: string
- output_refs: list[RuntimeRef]
```

`reflection` is a concise machine-readable or human-readable explanation of the
observed outcome. It is not a hidden chain-of-thought field and must not contain
secrets, raw prompts, or unbounded page content. The validator should enforce a
hard maximum length (initial target: 2,000 characters). Overlong reflections
should be truncated with an explicit marker instead of rejected, so trace
emission does not break the runtime path.

## Narrated Mode Lifecycle

ADR-001 uses single-emission narrated steps. A narrated step is emitted once
after the represented work is known and must have one terminal status:

```text
completed | failed | skipped | cancelled
```

ADR-001 does not emit `pending` or `running` updates for narrated steps.
Multi-emission lifecycle updates are reserved for the later streaming work. When
multi-emission is introduced, `step_id` and `idempotency_key` must remain stable
across all status updates for the same logical step.

## StepBus

ADR-001 introduces a minimal in-process bus:

```text
StepEmitter -> StepBus -> StepConsumer[]
```

Initial consumers:

- `persistence`: stores a step trace snapshot in run artifacts.
- `in_memory_eval_sink`: keeps steps available to tests and local inspection.
- `event_log` or `ui_stream_stub`: converts selected steps to the existing
  event-message shape so future streaming can attach without changing emitters.

Consumers must be schema-version-aware. They should switch on
`identity.schema_version` and ignore unknown optional fields.

OpenTelemetry is intentionally not a required ADR-001 consumer. ADR-002 will
attach an OTel consumer after a short observation period on real step traces.

`StepEmitter.emit()` must run the existing prompt secret guard before publishing
to the bus. Use `assert_no_secrets_in_payload()` for structured payloads and
`assert_no_secrets_in_text()` for bounded text fields. At minimum, scan
user/content-bearing fields in `intent.planned_action.payload`,
`execution.observations[]`, `execution.errors[]`, and `outcome.reflection`. If a
secret-like payload is detected, emission should fail closed for the step trace
and record a safe local error without publishing the sensitive value.

## Relationship To Existing Checkpoints

ADR-001 does not replace existing checkpoints such as `after_first_pass`,
`after_closure`, `after_synthesis`, and `after_finalization`.

Checkpoints remain the recovery boundary: they capture enough run state to
resume or inspect the pipeline after a crash. Runtime steps are the event trace:
they explain which intents, observations, tool/capability calls, state
transitions, and outcomes led to those checkpoints.

To avoid drift, checkpoint writes should also emit a `state_transition` step
whose payload references the checkpoint id, phase, sequence, and content hash.
The checkpoint remains authoritative for recovery; the step trace remains
authoritative for observability and evals.

## Emission Coverage

The first implementation should emit narrated steps at these boundaries:

- run initialization
- storage initialization
- memory retrieval
- Supervisor brief creation
- Step-1 handoff creation and validation
- first-pass start and completion
- department assignment
- department package admission
- first-round resolution classification
- bounded auto-close start and completion
- synthesis start and completion
- meeting-readiness evaluation
- final briefing composition
- report writer execution
- export and memory consolidation
- follow-up run loading
- follow-up routing
- follow-up answer generation from stored memory
- follow-up additional-research handoff when required
- dashboard pause point when user selection is required
- dashboard resume with user selections

Secondary steps should be emitted for AG2 department turns after the existing
GroupChat message history is available. These steps are lower-granularity trace
records and should not change speaker selection or department behavior.

## Migration Plan

1. Add `src/orchestration/runtime_step.py` with dataclasses or Pydantic models,
   validators, canonicalization helpers, and idempotency-key generation.
2. Add `src/orchestration/step_bus.py` with `StepBus`, `StepEmitter`, and
   consumer interfaces.
3. Wire a bus into `RunContext` or the runner state without making it a required
   constructor dependency for existing tests.
4. Emit narrated steps from `pipeline_runner.py` phase boundaries.
5. Emit department-turn steps from `DepartmentLeadAgent` after GroupChat
   completion, reusing the existing message history.
6. Persist a compact step trace snapshot with `run_context` or a dedicated
   `step_trace` artifact.
7. Add a feature flag to disable step emission if needed during rollout.
8. Run at least one staging comparison with step emission enabled and disabled;
   pipeline outputs should remain behaviorally identical except for added trace
   artifacts.

Suggested flag:

```text
LIQUISTO_RUNTIME_STEPS_ENABLED=1
```

The default may be enabled in local/test profiles and controlled explicitly in
production until the observation sprint is complete.

## Test Strategy

- Contract tests validate required fields, allowed enum values, and schema
  version handling.
- Idempotency tests simulate repeated emission of the same planned action and
  assert one logical idempotency key.
- Canonicalization tests verify stable hashes for semantically equivalent
  payloads with different key order or whitespace.
- Phase-emission tests run architecture-light paths and assert step coverage for
  major phase boundaries without requiring AG2.
- Department-turn tests use a small synthetic message history and assert
  secondary step generation without invoking model calls.
- Persistence tests assert that step trace snapshots are included in exported
  run artifacts and do not contain secrets.
- Security tests assert that `StepEmitter.emit()` blocks secret-like values via
  `src/security/secret_guard.py` before publishing or persisting a step.

## Observation Sprint

After ADR-001 lands, run several real or staging pipeline runs with step
emission enabled before implementing ADR-002 and ADR-003.

The observation sprint should answer:

- Which phase boundaries produce too many or too few steps?
- Which fields are consistently empty and should be optional or removed?
- Which reasoning policy fields can be filled from current model configuration?
- Which state transitions need tighter names or payload contracts?
- Which step attributes are useful for UI streaming and which are noise?
- What is the trace volume per run: step count, bytes per step, and total bytes?
- Which step types are candidates for compaction, especially AG2 turn steps in
  long GroupChats?
- Should token counts live only in `execution.usage`, leaving
  `reasoning_realized` for reasoning-specific fields, or should
  `reasoning_realized` retain model-token counters for provider-local fidelity?

ADR-002 and ADR-003 should be based on observed traces, not only on the
theoretical schema.

## Capability Versus State-Transition Boundary

MCP is the target protocol for external capabilities. It is not the target
protocol for internal runtime state transitions.

Use MCP for capabilities:

- search
- page fetch
- extraction
- browser/computer use
- code sandbox
- external database or registry lookup

Keep state transitions in process:

- `review_research`
- `judge_decision`
- `finalize_package`
- package admission
- answer-matrix updates
- checkpoint writes

State transitions still appear in `execution.state_transitions[]`, preserving a
complete audit trail without exposing run-context-bound operations as generic
discoverable tools.

## Known Follow-Up ADRs

- ADR-002: OpenTelemetry and complete usage telemetry on steps.
- ADR-003: `RoleModelProfile` and `StepReasoningPolicy`.
- ADR-004: Provider adapter boundary, with OpenAI as the first adapter.
- ADR-005: MCP capability layer.
- ADR-006: Long-term process memory retrieval on Postgres/pgvector.
- ADR-007: Procedural skills as versioned task recipes.
- ADR-008: Step-trace eval framework.

## Consequences

Positive:

- OTel, streaming, evals, and reasoning-budget tuning get a shared data model.
- The existing pipeline can remain stable while gaining traceability.
- Future imperative loops in closure and follow-up have a compatible contract.
- MCP migration can focus on external capabilities instead of internal state
  mutation.

Costs:

- Additional artifacts increase storage volume.
- Existing tests may need lightweight fixtures for the bus.
- The first traces may reveal schema fields that need adjustment before ADR-002.

Risks:

- If emitters embed raw prompts, page text, or secrets, step traces become an
  audit and privacy risk. Emitters should prefer refs over large payloads and
  use existing secret guards.
- If the bus becomes required too early, unrelated architecture tests may start
  depending on runtime-heavy wiring. Keep ADR-001 bus construction lightweight.
