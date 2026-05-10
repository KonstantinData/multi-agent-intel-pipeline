# Audit Log Minimization Policy

> Language: `en`
> Path: `privacy/audit-log-minimization-policy.md`

## Purpose

This policy defines what the runtime may persist for auditability and what it
must avoid storing. It applies to run artifacts, checkpoints, follow-up history,
debug logs, CI artifacts, and long-term process memory.

## Policy

The runtime must preserve enough information to explain a briefing, reproduce
the meeting-readiness state, and answer follow-up questions from stored
evidence. It must not preserve unnecessary secrets, raw pages, private customer
data, or reusable company-specific facts.

## Allowed Audit Data

| Data | Where stored | Reason |
| --- | --- | --- |
| Intake `company_name` and `web_domain` | `run_meta.json`, `run_context.json` | Run identification and follow-up |
| Normalized supervisor brief | `run_context.json` | Reproducibility of department assignments |
| Department packages | `run_context.json`, `memory_snapshot.json` | Evidence traceability |
| Task, review, and decision artifacts | `department_run_states` | Explain retry, acceptance, gaps, and judge outcomes |
| Evidence packet claims and source URLs | `memory_snapshot.json`, `pipeline_data.json` | Briefing support |
| Answer matrix and readiness state | `run_context.json`, `pipeline_data.json` | Meeting-readiness audit |
| Token/search/page-fetch usage counters | `usage_totals`, `run_meta.json` | Cost and operational monitoring |
| Follow-up questions and answers | `follow_up_history.json` | Historical Q&A trace |

## Disallowed Audit Data

The runtime must not intentionally store:

- API keys or `.env` contents;
- auth headers, cookies, sessions, or tokens;
- full raw HTML/PDF dumps when snippets, extracted text, source URLs, and
  evidence claims are sufficient;
- customer-private documents unless a separate retention basis exists;
- special-category personal data;
- personal contact data beyond business-contact context needed for the run;
- company-specific facts in long-term process memory;
- hidden chain-of-thought or private model reasoning.

## Run Brain vs Long-Term Memory

| Store | May contain case facts? | Retention intent |
| --- | --- | --- |
| Run brain under `artifacts/runs/<run_id>/` | yes | Case-specific audit, export, and follow-up |
| Long-term process memory | no | Scrubbed process patterns only |

`src/memory/consolidation.py` enforces the long-term boundary by replacing
domains, URLs, emails, quoted names, and company legal suffixes with structural
placeholders.

## Checkpoints

Checkpoints may duplicate parts of `run_context.json` for crash recovery. They
must follow the same minimization rules as final run exports.

Required checkpoint phases include:

- `after_first_pass`
- `after_closure`
- `after_synthesis`
- `after_dashboard_resume`
- `after_finalization`

## Operational Logging

Application logs should record:

- run id;
- department name;
- phase;
- status;
- elapsed time;
- stop reason;
- error class and short message.

Application logs should not record:

- full prompts;
- full model responses;
- raw fetched page content;
- secrets or environment values;
- full contact records when a count or stable id is sufficient.

## Review Checklist

Before adding a new field to run export or logs, verify:

- it is needed for audit, follow-up, quality review, or export;
- it is not a secret;
- it is not better represented as a source URL, evidence packet, or summarized
  claim;
- it does not bypass the run-brain/long-term memory boundary;
- tests or schema validation cover the new structure where practical.
