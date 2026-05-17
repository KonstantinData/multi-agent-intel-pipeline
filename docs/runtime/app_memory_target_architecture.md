# App Memory Target Architecture

Schema version: `2026-05-17.1`

## Purpose

This document defines the target structure for Liquisto app-level memory and
runtime-improvement memory.

It separates three concerns that must not be mixed:

- Runtime artifacts: concrete output and evidence from a specific runtime run.
- Operations brain: app/system knowledge used to operate, maintain, scale, and
  improve the repository and deployment.
- Runtime improvement brain: scrubbed, reviewed learning extracted from runtime
  artifacts to improve future runtime outputs.

The current `liquisto-app-memory-worker` D1 schema is a validated smoke-test
foundation, not the final memory architecture.

## Core Boundary

Hetzner stores runtime artifacts only.

Cloudflare app memory stores app-level and improvement-level memory only after
scrubbing, validation, and review.

Local processing may read runtime artifacts temporarily, but must not persist
raw runtime artifacts into Cloudflare app memory.

```text
Hetzner Runtime Artifact Store
  concrete run artifacts, evidence, reports, checkpoints, follow-up history

Local Processing Layer
  temporary read, scrubbing, extraction, evaluation, embedding preparation

Cloudflare App Memory
  D1: metadata, lifecycle, audit, relationships
  R2: scrubbed objects and reviewed pattern bodies
  Vectorize: rebuildable semantic index over accepted patterns
```

## Terminology

### Runtime Artifact Store

The Runtime Artifact Store contains concrete artifacts produced by runtime
workflow execution.

Examples:

- intake payloads
- department run states
- task artifacts
- evidence packets
- reviews and decisions
- department packages
- synthesis outputs
- report packages
- follow-up history
- checkpoints
- exported JSON/PDF artifacts

This store may contain customer-specific or target-company-specific facts and
therefore remains outside Cloudflare app memory.

### Operations Brain

The Operations Brain contains knowledge that helps operate, maintain, scale, and
evolve the app and repository.

Examples:

- deployment observations
- migration history
- healthcheck observations
- worker smoke-test results
- CI and review gate outcomes
- incident notes
- maintenance notes
- schema change proposals
- schema change applications
- repository and architecture working knowledge

This area is app/system specific, not customer-run specific.

### Runtime Improvement Brain

The Runtime Improvement Brain contains scrubbed and reviewed learning extracted
from runtime artifacts.

Examples:

- query strategy candidates
- accepted query patterns
- critic heuristics
- judge decision principles
- evidence-quality patterns
- department completion patterns
- failure-mode patterns
- report-quality patterns
- test-gap patterns

This area may learn from runtime artifacts, but must not store raw runtime
artifacts or customer-specific facts.

## Non-Negotiable Rules

- Do not store raw runtime artifacts in Cloudflare D1, R2, or Vectorize.
- Do not store target company names, domains, URLs, people, email addresses, or
  concrete run conclusions as reusable memory.
- Do not use Vectorize as a source of truth.
- Do not use D1 `payload_json` as an unbounded dumping ground.
- Do not let raw events become retrieval context for future runtime runs.
- Do not let app memory override canonical code, tests, contracts, YAML policy
  files, or canonical architecture documentation.

## Storage Roles

### D1

D1 is the authoritative metadata and lifecycle store for app memory.

Use D1 for:

- IDs
- statuses
- schema versions
- object keys
- content hashes
- review decisions
- audit events
- relationships between candidates, reviews, accepted patterns, R2 objects, and
  Vectorize IDs
- retrieval telemetry

Do not use D1 for large bodies of reviewed pattern text when R2 is more
appropriate.

### R2

R2 stores larger scrubbed objects.

Use R2 for:

- scrubbed candidate JSON
- accepted pattern Markdown or JSON
- review reports
- snapshot exports
- batch-processing manifests
- offline evaluation reports

R2 object bodies must be scrubbed before upload.

### Vectorize

Vectorize is a semantic retrieval projection.

Use Vectorize for:

- embeddings of accepted patterns
- metadata-filtered semantic search over accepted patterns

Do not treat Vectorize as durable truth. Every vector must be rebuildable from
D1 metadata plus R2 object content.

### Local Processing

The local machine may perform heavier processing that should not run inside a
Worker.

Use local processing for:

- temporary access to Hetzner runtime artifacts
- scrubbing
- PII/company/domain detection
- candidate extraction
- deduplication
- evaluation
- embedding preparation
- backfills
- replay and migration dry-runs

Local processing may emit only scrubbed candidates, reviews, accepted patterns,
or operational events to Cloudflare app memory.

## Target Data Flow

### Operations Flow

```text
Operator / CI / Worker
  -> POST operation event
  -> D1 memory_events / ops_events
  -> optional R2 report object
  -> query by environment, component, status, timestamp
```

Operations events are not used as runtime retrieval context unless explicitly
promoted into a reviewed operational pattern.

### Runtime Improvement Flow

```text
Hetzner runtime artifacts
  -> local temporary processing
  -> scrubber
  -> candidate extractor
  -> learning_candidate in D1
  -> scrubbed candidate body in R2
  -> review / policy gate
  -> accepted_pattern in D1
  -> accepted pattern body in R2
  -> vector upsert in Vectorize
  -> future runtime retrieval reads accepted patterns only
```

Raw runtime artifacts do not cross into Cloudflare app memory.

## Target D1 Schema

The existing `memory_events` table should remain as append-only audit history.
It should not become the only memory model.

### `memory_events`

Purpose: append-only audit log.

Suggested fields:

- `event_id`
- `event_type`
- `area`
- `source`
- `correlation_id`
- `schema_version`
- `payload_json`
- `created_at`

Current compatibility fields may remain during migration:

- `run_id`
- `department`
- `kind`
- `source`
- `payload_json`
- `created_at`

### `memory_objects`

Purpose: registry for R2 objects.

Suggested fields:

- `object_id`
- `object_key`
- `object_type`
- `content_hash`
- `content_type`
- `schema_version`
- `created_at`
- `created_by`

### `learning_candidates`

Purpose: scrubbed proposed learning from runtime artifacts or maintenance work.

Suggested fields:

- `candidate_id`
- `candidate_type`
- `role`
- `scope`
- `status`
- `scrub_status`
- `policy_version`
- `source_reference_hash`
- `object_id`
- `content_hash`
- `schema_version`
- `created_at`
- `updated_at`

Allowed statuses:

- `proposed`
- `needs_review`
- `rejected`
- `accepted`
- `deprecated`

### `pattern_reviews`

Purpose: record review, scrub, and policy decisions.

Suggested fields:

- `review_id`
- `candidate_id`
- `decision`
- `reviewer`
- `policy_version`
- `notes_json`
- `created_at`

Allowed decisions:

- `accepted`
- `rejected`
- `needs_revision`
- `unsafe_payload`
- `duplicate`
- `out_of_scope`

### `accepted_patterns`

Purpose: canonical reusable patterns that may be retrieved for future runtime
improvement.

Suggested fields:

- `pattern_id`
- `candidate_id`
- `pattern_type`
- `role`
- `scope`
- `status`
- `version`
- `object_id`
- `vector_id`
- `content_hash`
- `policy_version`
- `schema_version`
- `created_at`
- `updated_at`

Only `accepted_patterns.status = 'active'` may enter runtime retrieval context.

### `retrieval_events`

Purpose: audit retrieval of accepted patterns.

Suggested fields:

- `retrieval_id`
- `correlation_id`
- `role`
- `scope`
- `query_hash`
- `policy_version`
- `result_count`
- `metadata_json`
- `created_at`

Do not store raw prompt text or customer-specific facts in retrieval events.

### `ops_events`

Purpose: structured operational history for app/system maintenance.

Suggested fields:

- `ops_event_id`
- `component`
- `environment`
- `event_type`
- `status`
- `schema_version`
- `metadata_json`
- `created_at`

## R2 Object Layout

Target object layout:

```text
app-memory/
  learning/
    candidates/<candidate_id>.json
    patterns/<pattern_id>.md
    reviews/<review_id>.json
  snapshots/
    accepted-patterns/<timestamp>.json
    retrieval-index/<timestamp>.json
  ops/
    reports/<date>/<ops_event_id>.json
    migrations/<migration_id>.json
  manifests/
    backfills/<batch_id>.json
```

Every object should include or be associated with:

- `schema_version`
- `content_hash`
- `policy_version`
- `created_at`
- `created_by`
- `scrub_status`

## Vectorize Index Design

Vectorize should index accepted patterns only.

Vector metadata should be small and filterable:

- `pattern_id`
- `role`
- `scope`
- `pattern_type`
- `status`
- `schema_version`
- `policy_version`
- `content_hash`

Vector IDs should be stable:

```text
pattern:<pattern_id>:v<version>
```

Rebuild rule:

```text
D1 accepted_patterns + R2 pattern bodies -> embeddings -> Vectorize upsert
```

If D1 and Vectorize disagree, D1 wins.

## API Target Surface

The current API supports:

- `GET /healthz`
- `POST /v1/memory/events`
- `GET /v1/memory/events?run_id=<id>&limit=<n>`

Target API surface:

- `POST /v1/events`
- `GET /v1/events?area=&component=&correlation_id=&limit=`
- `POST /v1/learning/candidates`
- `GET /v1/learning/candidates/:candidate_id`
- `POST /v1/learning/candidates/:candidate_id/reviews`
- `POST /v1/patterns/:candidate_id/accept`
- `GET /v1/patterns?role=&scope=&pattern_type=&limit=`
- `POST /v1/retrieval/query`
- `GET /v1/ops/events?component=&environment=&status=&limit=`

Retrieval endpoints must return accepted patterns only.

## Event Type Taxonomy

### Operations

- `worker_smoke_test`
- `d1_migration_applied`
- `r2_object_written`
- `vectorize_rebuild_started`
- `vectorize_rebuild_completed`
- `deployment_attempted`
- `deployment_succeeded`
- `deployment_failed`
- `healthcheck_observed`
- `ci_gate_result`
- `schema_change_proposed`
- `schema_change_applied`
- `incident_note`
- `maintenance_note`

### Learning

- `learning_candidate_created`
- `learning_candidate_rejected`
- `learning_pattern_accepted`
- `query_strategy_candidate`
- `critic_heuristic_candidate`
- `judge_principle_candidate`
- `failure_mode_pattern`
- `test_gap_pattern`
- `report_quality_pattern`
- `department_completion_pattern`

### Governance

- `scrub_check_passed`
- `scrub_check_failed`
- `policy_rejection`
- `unsafe_payload_rejected`
- `pattern_deprecated`
- `manual_review_required`
- `manual_review_accepted`
- `manual_review_rejected`

## Retrieval Policy

Runtime retrieval may use only:

- active accepted patterns
- matching role/scope/pattern type
- current schema version or explicitly compatible schema version
- current policy version or explicitly compatible policy version

Runtime retrieval must not use:

- raw `memory_events`
- rejected candidates
- proposed candidates
- deprecated patterns
- operations events
- unreviewed R2 objects
- Vectorize results without D1 confirmation

## Security And Privacy

Required gates before writing learning candidates:

- PII scan
- company/domain/person/entity scan
- URL scan
- customer-specific conclusion scan
- prompt/secret scan
- schema validation
- policy-version assignment

Required gates before accepting patterns:

- scrub status is `passed`
- no forbidden content present
- candidate has review decision `accepted`
- R2 object content hash matches D1 metadata
- pattern type is allowed
- role/scope is allowed

Secrets:

- production secrets must be Cloudflare secrets
- local tests should use temporary process or CLI-injected dummy tokens
- no local secret files should be committed

## Local Processing Contract

Local jobs may:

- read runtime artifacts temporarily
- produce scrubbed candidates
- produce review reports
- produce accepted pattern bodies
- produce embedding batches
- write scrubbed outputs to Cloudflare

Local jobs must:

- avoid persistent raw artifact copies unless explicitly approved
- log only hashes or sanitized references
- keep dry-run mode for migrations and backfills
- validate output before upload
- make every emitted object reproducible from a manifest

## Migration Strategy

### Phase 0: Current Validated Foundation

The current worker and local D1 smoke test prove:

```text
Client -> Worker auth -> D1 insert -> D1 select -> JSON payload roundtrip
```

Keep this as the minimal health path.

### Phase 1: Contracts

Define:

- event type allowlist
- payload schemas
- forbidden content rules
- role/scope taxonomy
- policy versions
- object key conventions

### Phase 2: Additive D1 Migration

Add:

- `memory_objects`
- `learning_candidates`
- `pattern_reviews`
- `accepted_patterns`
- `retrieval_events`
- `ops_events`

Keep `memory_events` for compatibility and audit history.

### Phase 3: R2 Binding

Add an R2 bucket binding for scrubbed memory objects.

Do not upload raw runtime artifacts.

### Phase 4: Vectorize Binding

Add a Vectorize binding for accepted pattern retrieval.

Build vectors only from accepted patterns.

### Phase 5: Local Processor

Build local tooling for:

- candidate extraction
- scrubbing
- review report generation
- embedding batch preparation
- Vectorize rebuilds

### Phase 6: Runtime Integration

Runtime may retrieve accepted patterns to improve future outputs.

Runtime must continue to answer concrete follow-up questions from runtime
artifacts, not from app memory.

## Open Decisions

- Final role/scope taxonomy for accepted patterns.
- Whether operations events live only in `memory_events` or also in `ops_events`.
- Whether `memory_snapshots` remains generic or becomes typed snapshots.
- Embedding model and vector dimensions.
- Review ownership: human-only, agent-assisted, or hybrid.
- Retention policy for candidate provenance hashes.
- Whether rejected candidates are retained forever or time-limited.

## Best Practice Position

The target architecture uses each storage layer for its strongest role:

- D1 for authoritative relational metadata and lifecycle.
- R2 for larger scrubbed objects and reproducible manifests.
- Vectorize for semantic retrieval projections.
- Local processing for heavy extraction, scrubbing, evaluation, and backfills.
- Hetzner for concrete runtime artifacts only.

This avoids using a single flexible JSON table as the entire memory system and
reduces the risk of storing unsafe or unreviewed runtime-derived content as
future runtime context.
