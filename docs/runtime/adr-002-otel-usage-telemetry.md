# ADR-002: OpenTelemetry And Usage Telemetry On RuntimeSteps

Status: Draft

Date: 2026-05-20

## Context

ADR-001 introduces `RuntimeStep` and `StepBus` as the shared trace contract for
phase boundaries, department turns, capability calls, state transitions,
observations, outcomes, and usage metadata.

ADR-002 will attach production observability to that step stream. The target is
to make runtime behavior inspectable across local development, staging, and
production without changing the department autonomy model or replacing the
current phase pipeline.

This ADR is intentionally a skeleton until ADR-001 has produced real step
traces from several staging or production-like runs.

The data basis for ADR-002 is the ADR-001 observation sprint output, especially:

- actual step count per run;
- bytes per step and total trace volume per run;
- phase and department boundaries that are too coarse or too noisy;
- observed capability-call and state-transition payload shapes;
- fields that are consistently empty or too large;
- which AG2 turn steps require compaction;
- usage metadata available from the current model/provider calls;
- at least one validation run using a reasoning-capable model, so
  `execution.reasoning_realized` and reasoning-token metadata can be observed
  before ADR-003 is calibrated;
- security or privacy issues found in emitted step payloads.

Until that data exists, ADR-002 must not specify final span names, span
hierarchies, metric names, attribute cardinality, backend retention policy, or
alert thresholds. Those choices depend on observed step granularity.

## Goals

- Define how `RuntimeStep` records map to OpenTelemetry traces, spans, metrics,
  and logs.
- Define a `StepBus` OpenTelemetry consumer that is optional and
  schema-version-aware.
- Capture complete usage telemetry across Supervisor, Departments, Synthesis,
  ReportWriter, and tool/capability calls.
- Track model/provider, role, department, task key, phase, decision outcome,
  reasoning policy, realized reasoning metadata, token usage, latency, cost,
  retries, stop reason, and error class where available.
- Preserve the ADR-001 privacy boundary: telemetry must not export secrets,
  raw prompts, unbounded page content, or company-specific long-form evidence.
- Define metric cardinality limits before production export.
- Define local and production export modes, including a no-op mode for tests.
- Keep telemetry failure non-blocking for the runtime happy path after secret
  guard validation has passed.
- Provide enough telemetry for ADR-003 reasoning-policy calibration and ADR-008
  eval scoring.

## Non-Goals

- Do not redesign `RuntimeStep`.
- Do not implement a second trace schema separate from `RuntimeStep`.
- Do not define final OTel span names before the observation sprint completes.
- Do not choose a production backend before observed trace volume is known.
- Do not make telemetry export required for local architecture tests.
- Do not change pipeline routing, department autonomy, or package admission
  behavior.

## ADR-003 Dependency

The current default model family is non-reasoning for this runtime. If the
observation sprint only uses those defaults, `execution.reasoning_realized` will
be `null` and ADR-002 can only be promoted for non-reasoning usage telemetry.

To make ADR-002 useful for ADR-003 reasoning-policy calibration, the observation
sprint should include at least one controlled validation run with a
reasoning-capable model or provider profile. That run is for telemetry-shape
validation, not for changing production defaults.

If that validation run is not available, ADR-002 promotion must explicitly
scope reasoning telemetry as a follow-up dependent on ADR-003 implementation.

## Deferred Until Observation Sprint

The following decisions remain explicitly deferred:

- span hierarchy and parent-child mapping;
- span and metric names;
- high-cardinality attribute policy;
- trace compaction rules;
- sampling strategy;
- backend choice and retention windows;
- dashboard and alert thresholds;
- exact token-count split between `execution.usage` and
  `execution.reasoning_realized`.
- exact promotion criteria, including the minimum number of observation runs,
  phase and department coverage, and the owner of the sprint summary.
- how the ADR-001 privacy guarantee is documented for the OTel consumer:
  `StepEmitter` runs secret-guard validation before the bus publishes, so OTel
  should only receive publishable step payloads.

ADR-002 can move from `Draft` to `Proposed` only after the observation sprint
summarizes those inputs.
