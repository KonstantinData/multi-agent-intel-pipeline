# Logging Schema

> Language: `en`
> Path: `audit/logging-schema.md`

## Purpose

This document describes the runtime audit schema for run artifacts,
checkpoints, and follow-up history.

Production profile persists artifacts in PostgreSQL tables (`run_artifacts`,
`run_checkpoints`). File-based exports are non-production only.

## Storage Backends

- Production: PostgreSQL (`run_artifacts`, `run_checkpoints`)
- Non-production: optional JSON export for explicit local tests/migration only

`run_id` is generated as a UTC timestamp by `src/pipeline_runner.py` unless a
paused run is resumed.

## Required Artifact Types

| Artifact type | Writer | Purpose |
| --- | --- | --- |
| `run_meta` | `src/exporters/json_export.py` | Run-level metadata, status, usage, budget, unresolved items, meeting-readiness summary |
| `chat_history` | `src/exporters/json_export.py` | Display-oriented agent message history with `name` and `content` |
| `pipeline_data` | `src/exporters/json_export.py` | Final structured briefing sections and report-facing artifacts |
| `run_context` | `src/exporters/json_export.py` | Full run context, including run brain, answer matrix, resolution state, report package |
| `memory_snapshot` | `src/exporters/json_export.py` | Exported `ShortTermMemoryStore` snapshot |
| `follow_up_history` | `src/exporters/json_export.py` | Appended follow-up answers for the run |

## Required Checkpoint Records

Checkpoints are written by `src/pipeline_runner.py` to `run_checkpoints`.
Expected phases include:

- `after_first_pass`
- `after_closure`
- `after_synthesis`
- `after_finalization`

## `run_meta` Fields

| Field | Type | Description |
| --- | --- | --- |
| `run_id` | string | Stable run identifier |
| `timestamp` | ISO timestamp | Export time in UTC |
| `company_name` | string | Intake company name |
| `web_domain` | string | Intake web domain |
| `status` | string | Run status, for example `meeting_ready`, `blocked_not_meeting_ready`, `needs_user_selection` |
| `usage` | object | Token/search/page-fetch and cost counters where available |
| `budget` | object | Phase-budget tracker snapshot |
| `error` | string or null | Fatal error if export follows failure path |
| `unresolved` | object | Status-dependent unresolved items |
| `meeting_readiness` | object | Serialized `MeetingReadinessAssessment` |

## `run_context` Core Fields

| Field | Description |
| --- | --- |
| `run_id` | Run identifier |
| `intake` | Original normalized intake data |
| `supervisor_brief` | Supervisor-generated run brief |
| `active_tasks` | Assigned task records including assignee, task key, model, and allowed tools |
| `report_package` | Report-writer output |
| `question_registry` | Meeting question registry |
| `answer_matrix` | Current coverage state per meeting question |
| `meeting_readiness_assessment` | Final gate assessment |
| `final_briefing` | Final briefing model |
| `short_term_memory` | Run brain snapshot |
| `status` | Current run status |
| `resolution_state` | Resolution bucket, dashboard state, closure state, budget/stop reasons |

## Department Artifact Schema

`department_run_states` contains the authoritative department state:

| Artifact | Meaning |
| --- | --- |
| `TaskArtifact` | Research attempt for a task: facts, payload, queries, sources, open questions, contract violations |
| `TaskReviewArtifact` | Critic assessment of a specific attempt |
| `TaskDecisionArtifact` | Lead or judge decision using canonical outcomes |

Canonical task decision outcomes are defined in `src/orchestration/contracts.py`.

## Minimization Rules

- Do not log API keys, environment variables, cookies, auth headers, or raw HTTP
  request bodies.
- Prefer structured evidence packets and source URLs over full copied page text.
- Store run-specific facts only in run artifacts, not in long-term memory.
- Keep `chat_history` for audit/debugging but do not treat it as authoritative
  state. Authoritative state is `run_context` plus department artifacts.
