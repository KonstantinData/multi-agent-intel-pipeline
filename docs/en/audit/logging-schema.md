# Logging Schema

> Language: `en`
> Path: `audit/logging-schema.md`

## Purpose

This document describes the repository's run artifact and audit logging schema.
The runtime persists structured run artifacts under `artifacts/runs/<run_id>/`.
These files are the primary audit trail for meeting-readiness, evidence
coverage, follow-up grounding, and export behavior.

## Run Directory

Each pipeline run writes to:

```text
artifacts/runs/<run_id>/
```

`run_id` is generated as a UTC timestamp by `src/pipeline_runner.py` unless a
paused run is resumed.

## Required Files

| File | Writer | Purpose |
| --- | --- | --- |
| `run_meta.json` | `src/exporters/json_export.py` | Run-level metadata, status, usage, budget, unresolved items, meeting-readiness summary |
| `chat_history.json` | `src/exporters/json_export.py` | Display-oriented agent message history with `name` and `content` |
| `pipeline_data.json` | `src/exporters/json_export.py` | Final structured briefing sections and report-facing artifacts |
| `run_context.json` | `src/exporters/json_export.py` | Full run context, including run brain, answer matrix, resolution state, report package |
| `memory_snapshot.json` | `src/exporters/json_export.py` | Exported `ShortTermMemoryStore` snapshot |
| `checkpoints/<phase>.json` | `src/pipeline_runner.py` | Phase-aware recovery and observability snapshots |
| `follow_up_history.json` | `src/exporters/json_export.py` | Appended follow-up answers for the run |
| `reports/liquisto_briefing_<run_id>_DE.pdf` | PDF exporter | German report export when generation succeeds |
| `reports/liquisto_briefing_<run_id>_EN.pdf` | PDF exporter | English report export when generation succeeds |

## `run_meta.json`

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

## `run_context.json`

Important top-level fields:

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

## `short_term_memory` Fields

| Field | Description |
| --- | --- |
| `facts` | Collected text facts |
| `sources` | Source dictionaries with URL/title/source type where available |
| `open_questions` | Legacy unresolved question list |
| `gap_candidates` | Structured unresolved gaps |
| `task_outputs` | Task-level payloads |
| `task_statuses` | Canonical task statuses |
| `critic_reviews` | Review details by task |
| `department_packages` | Final package per department |
| `department_conversations` | Department conversation traces where recorded |
| `department_run_states` | Serialized `DepartmentRunState` per department |
| `follow_up_sessions` | Follow-up answer records |
| `answer_matrix_updates` | Structured meeting-question updates |
| `resolution_decisions` | Resolution-controller decisions |
| `resolution_plans` | Planned closure/user-decision actions |
| `meeting_actions` | Final `MeetingAction` list |
| `evidence_packets` | Structured evidence packets |
| `usage_totals` | LLM/search/page-fetch counters |

## Department Artifact Schema

`department_run_states` contains the authoritative department state:

| Artifact | Meaning |
| --- | --- |
| `TaskArtifact` | Research attempt for a task: facts, payload, queries, sources, open questions, contract violations |
| `TaskReviewArtifact` | Critic assessment of a specific attempt |
| `TaskDecisionArtifact` | Lead or judge decision using canonical outcomes |

Canonical task decision outcomes are defined in `src/orchestration/contracts.py`.

## Follow-Up Logging

`follow_up_history.json` is appended under a file lock. A follow-up answer should
record:

- run id;
- user question;
- routed department;
- generated answer;
- evidence list;
- unresolved points;
- `requires_additional_research` flag;
- timestamp when supplied by the caller.

## Minimization Rules

- Do not log API keys, environment variables, cookies, auth headers, or raw HTTP
  request bodies.
- Prefer structured evidence packets and source URLs over full copied page text.
- Store run-specific facts only in the run directory, not in long-term memory.
- Keep `chat_history.json` for audit/debugging but do not treat it as the
  authoritative state. The authoritative state is `run_context.json` and
  department artifacts.
- Use `atomic_write_json()` for JSON export and file locks for follow-up append.
