# ADR-002: OpenTelemetry And Usage Telemetry On RuntimeSteps

Status: Proposed

Date: 2026-05-20

## Context

ADR-001 introduced `RuntimeStep` and `StepBus` as the shared trace contract for
phase boundaries, department turns, capability calls, state transitions,
observations, outcomes, and usage metadata.

ADR-002 attaches production observability to that step stream. The target is to
make runtime behavior inspectable across local development, staging, and
production without changing the department autonomy model or replacing the
current phase pipeline.

The ADR-001 observation sprint was completed on branch
`codex/fix-run-exit-cleanup` after PR #86 was merged. The sprint used three
production-like local runs with runtime step emission enabled:

| Run ID | Company | Sector | Status | Exit | Steps | Trace bytes |
| --- | --- | --- | --- | --- | ---: | ---: |
| `20260520T160645Z` | Festo SE & Co. KG | industrial goods | `blocked_not_meeting_ready` | clean | 50 | 92,652 |
| `20260520T162219Z` | Carl Zeiss Meditec AG | medical technology | `blocked_not_meeting_ready` | clean | 64 | 117,705 |
| `20260520T163621Z` | Phoenix Contact GmbH & Co. KG | electrical engineering | `blocked_not_meeting_ready` | clean | 51 | 94,361 |

Observed aggregate:

- 3/3 runs exited cleanly after export.
- Step count range: 50-64, average 55.0.
- Trace size range: 92.7-117.7 KB, average 101.6 KB.
- Average bytes per step: about 1.84-1.85 KB.
- No step exceeded 12 KB.
- `department_groupchat` no-op turn steps dominate volume: 24-38 per run.
- `execution.usage` appeared on only one step per run.
- `execution.reasoning_realized` was absent in all runs because the current
  default model profile is non-reasoning.

## Decision

Implement an optional `StepBus` OpenTelemetry consumer that consumes the same
sanitized `RuntimeStep` payloads already emitted by ADR-001. The OTel consumer
must not introduce a second trace schema.

Activation is controlled by `LIQUISTO_OTEL_ENABLED=1`. The consumer must remain
dependency-light at import time and only load OpenTelemetry SDK modules when
export is enabled or a deployment explicitly injects an OTel sink.

Telemetry export is non-blocking after ADR-001 secret validation has passed. If
OTel export fails, the runtime path continues and the failure is logged locally
without emitting raw sensitive payloads.

## Span Mapping

Use one trace per `run_id`.

Create a root span:

- `runtime.run`

Root span attributes:

- `run.id`
- `runtime.mode`
- `runtime.status`
- `storage.profile`
- `step.schema_version`

Create phase spans from RuntimeSteps whose `scope.phase` marks a phase boundary
or whose `intent.planned_action.kind` is `state_transition` with runtime-level
scope:

- `runtime.initialized`
- `runtime.storage_init`
- `runtime.memory_retrieval`
- `runtime.supervisor_brief`
- `runtime.step1_handoff`
- `runtime.first_pass`
- `runtime.synthesis`
- `runtime.finalization`
- `runtime.report_and_export`

Create department spans under the relevant phase span:

- `department.CompanyDepartment`
- `department.MarketDepartment`
- `department.BuyerDepartment`
- `department.ContactDepartment`

Create child spans for capability calls and state transitions that are
operationally meaningful:

- `capability.<normalized_target>` for `planned_action.kind == "capability_call"`
- `state.<normalized_target>` for important `state_transition` steps

Checkpoint writes remain state-transition events and may be represented as span
events instead of full child spans when the backend charges heavily per span.
They must carry `checkpoint_id`, `phase`, `sequence`, and `content_hash`.

AG2 `department_groupchat` no-op turn steps are not exported as individual spans
by default. They are exported as span events on the current department span and
are eligible for compaction.

## Attribute Policy

Allowed low-cardinality span attributes:

- `step.id`
- `step.sequence`
- `step.schema_version`
- `step.mode`
- `step.status`
- `phase`
- `department`
- `task.key`
- `task.attempt`
- `actor.role`
- `action.kind`
- `action.target`
- `decision`
- `stop.reason`
- `error.class`
- `model.provider`
- `model.name`
- `reasoning.effort_planned`
- `reasoning.effort_used`

High-cardinality or sensitive values must not be exported as OTel attributes:

- raw prompts
- raw observations
- raw page content
- full search queries
- full URLs
- company-specific long-form evidence
- secrets or secret-like values

When these values are required for local debugging, keep them in the local
sanitized step trace only. OTel should receive stable IDs, refs, hashes, counts,
or bounded classifications.

## Usage Telemetry

`execution.usage` is the canonical place for consumption metrics.

Usage fields should be populated where available:

- `provider`
- `model`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `thinking_tokens`
- `cached_prompt_tokens`
- `tool_calls`
- `search_calls`
- `page_fetches`
- `latency_ms`
- `retry_count`
- `estimated_cost_usd`

`execution.reasoning_realized` is not the canonical token counter. It records
reasoning-policy realization only:

- `effort_used`
- `thinking_tokens` when the provider exposes it
- `reasoning_summary_available`

This prevents duplicate `prompt_tokens`, `completion_tokens`, and `total_tokens`
between `execution.usage` and `execution.reasoning_realized`.

Observation sprint result: current traces only populate usage once per run,
which is enough for run-level cost accounting but not enough for role-level or
step-level calibration. ADR-002 implementation must therefore add usage capture
around model calls and capability calls in Supervisor, Departments, Synthesis,
ReportWriter, search, fetch, extraction, and PDF/report export paths.

## Metrics

Emit metrics from RuntimeSteps, not from ad-hoc runtime side channels.

Initial metric set:

- `runtime.run.count`
- `runtime.run.duration_ms`
- `runtime.run.status.count`
- `runtime.step.count`
- `runtime.step.bytes`
- `runtime.phase.duration_ms`
- `runtime.department.duration_ms`
- `runtime.department.step.count`
- `runtime.capability.call.count`
- `runtime.capability.error.count`
- `runtime.state_transition.count`
- `runtime.tokens.total`
- `runtime.tokens.prompt`
- `runtime.tokens.completion`
- `runtime.tokens.thinking`
- `runtime.cost.estimated_usd`
- `runtime.retry.count`
- `runtime.error.count`

Metric labels must stay low-cardinality: phase, department, actor role, action
kind, normalized target, model family, provider, status, and error class are
allowed. Raw company names and run IDs are not metric labels.

## Compaction Rules

The observed trace size is small enough to persist full local traces for now.
However, AG2 turn steps dominate the trace count and will grow with longer
runs.

Compaction policy:

- Never compact capability-call steps.
- Never compact state-transition steps.
- Never compact checkpoint writes, approval gates, pause/resume transitions,
  final decisions, errors, or cancelled steps.
- Keep the first and last no-op AG2 turn step per department un-compacted.
- Compact middle no-op AG2 turn steps into a summary record when either:
  - a department emits more than 100 `department_groupchat` no-op steps, or
  - a run trace exceeds 500 KB.
- The compaction summary must include count, first sequence, last sequence,
  actor-role counts, task-key counts, and error count.
- Local development may keep full traces; production OTel export should use the
  compacted event representation by default.

## Storage And Retention

Given the observed average trace size of about 101.6 KB per run, raw local trace
storage is acceptable during the next phase.

Default retention proposal:

- Local artifacts: keep full `step_trace.json` with run artifacts.
- Staging OTel: export full phase spans and compacted AG2 turn events.
- Production OTel: export full phase/capability/state spans and compacted AG2
  turn events.
- Production raw trace retention: decide after volume is known under real
  traffic; do not vendor-lock in this ADR.

ADR-002 defines OTLP-compatible export semantics but does not choose a hosted
backend. Backend selection remains deployment configuration.

## Privacy Boundary

ADR-001 remains the privacy boundary. `StepEmitter` runs secret validation before
publishing to `StepBus`; the OTel consumer only sees publishable step payloads.

The OTel consumer must still defensively avoid exporting high-cardinality raw
payload fields as attributes. Sensitive local trace fields may be represented by
counts, hashes, refs, or bounded enums.

## ADR-003 Dependency

The observation sprint did not include a reasoning-capable model run. Therefore
ADR-002 is proposed for non-reasoning telemetry and usage capture only.

Reasoning-policy calibration remains dependent on ADR-003. ADR-003 must add at
least one controlled validation run with a reasoning-capable provider/profile to
observe `execution.reasoning_realized`, `thinking_tokens`, and planned-vs-used
reasoning deltas.

## Goals

- Define how `RuntimeStep` records map to OpenTelemetry traces, spans, metrics,
  and logs.
- Define a `StepBus` OpenTelemetry consumer that is optional and
  schema-version-aware.
- Capture complete non-reasoning usage telemetry across Supervisor,
  Departments, Synthesis, ReportWriter, and tool/capability calls.
- Track model/provider, role, department, task key, phase, decision outcome,
  reasoning policy, token usage, latency, cost, retries, stop reason, and error
  class where available.
- Preserve the ADR-001 privacy boundary: telemetry must not export secrets, raw
  prompts, unbounded page content, or company-specific long-form evidence.
- Define metric cardinality limits before production export.
- Define local and production export modes, including a no-op mode for tests.
- Keep telemetry failure non-blocking for the runtime happy path after secret
  guard validation has passed.
- Provide enough non-reasoning telemetry for ADR-008 eval scoring and enough
  structure for ADR-003 to add reasoning telemetry later.

## Non-Goals

- Do not redesign `RuntimeStep`.
- Do not implement a second trace schema separate from `RuntimeStep`.
- Do not change pipeline routing, department autonomy, or package admission
  behavior.
- Do not export raw prompts, page content, evidence dumps, secrets, or
  high-cardinality business content to OTel.
- Do not choose a hosted production telemetry backend in this ADR.
- Do not claim reasoning-policy calibration is complete before ADR-003 produces
  reasoning-capable validation traces.

## Implementation Notes

Recommended implementation order:

1. Add an optional `OpenTelemetryStepConsumer` behind configuration.
2. Map phase and state-transition steps to spans/events using the rules above.
3. Add usage capture wrappers around model and capability calls.
4. Add compaction for AG2 no-op turn events before production OTel export.
5. Add architecture tests for attribute allowlists and payload exclusion.
6. Add runtime tests with a fake OTel exporter to verify non-blocking failure.

Promotion from `Proposed` to `Accepted` requires implementation and tests, not
additional observation runs, unless the runtime shape changes materially.
