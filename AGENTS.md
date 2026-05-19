# AGENTS.md

## Purpose of this file

Compact orientation guide for developers and AI coding agents working in this repository.
Summarises the **current** runtime model, agent roles, contract vocabulary, memory
boundaries, and where to find canonical architecture documentation.

Intentionally brief. For full details use:
- `README.md`
- `docs/drawio/target_runtime_architecture.md`
- `src/orchestration/contracts.py`

---

## Project overview

**Liquisto Department Runtime** — a multi-agent intelligence pipeline that builds
pre-meeting briefings from `company_name` and `web_domain`.

The system uses **bounded AG2 GroupChats inside domain departments**, coordinated
by a single **Supervisor control plane**.

Top-level runtime modes:
1. Initial briefing mode
2. Run-based follow-up mode

---

## Current runtime model

### Control plane — Supervisor

The `Supervisor` is the single control-plane role.

Responsibilities:
- normalise intake and create the intake brief (`SupervisorBrief`)
- translate the Liquisto standard scope into department task assignments (`task_router.py`)
- coordinate department execution order (respecting dependency contracts)
- accept completed department packages via the admission gate (`envelope.py`)
- route follow-up questions by `run_id`

Non-responsibilities:
- no domain-level fact interpretation
- no domain-level evidence review
- no intra-department retry or judge decisions

The Supervisor does **not** participate in internal department loops.
Departments operate autonomously inside their assigned contract.

### Research plane — Domain departments

Four bounded domain departments run as real AG2 GroupChats:

| Department | Execution order |
| --- | --- |
| Company | Step 1 (parallel with Market) |
| Market | Step 1 (parallel with Company) |
| Buyer | Step 2 (after Step 1 completes) |
| Contact | Step 3 (depends on Buyer) |

Dependency ordering is enforced by `task_router.py` via `run_condition` fields
and `DEPENDENCY_SATISFYING_OUTCOMES` from `contracts.py`.

Each department outputs a validated `DepartmentPackage` — not raw chat.
Package admission goes through the F2 gate in `envelope.py`.

### Department role model

Each department group consists of five `ConversableAgent` roles:

| Role | Primary responsibility |
| --- | --- |
| Department Lead / Analyst | operationalise the contract, steer the group, enforce completion, hand off the package |
| Researcher (Worker) | gather evidence, adapt search strategy, produce `TaskArtifact` evidence packets |
| Critic | review evidence quality, identify gaps and defects, produce `TaskReviewArtifact` |
| Judge | decide borderline cases using decision principles; produce `TaskDecisionArtifact` |
| Coding Specialist | targeted escalation for parsing, extraction, query refinement, structured recovery |

Notes:
- The Lead owns completion — it is not just an administrator.
- The Judge and Coding Specialist are bounded support roles, not independent control-plane roles.
- There is no `request_supervisor_revision` tool inside department execution.

### Synthesis plane

After domain departments complete, the `SynthesisDepartment` performs cross-domain
interpretation (AG2 GroupChat: SynthesisLead, SynthesisAnalyst, SynthesisCritic,
SynthesisJudge).

The pipeline then passes all artifacts through:
1. **Meeting-Readiness Gate** (`meeting_readiness.py`, RA-06): finalization only
   passes when meeting-critical questions are resolved and evidence quality meets
   the minimum threshold; produces `meeting_actions` as the primary action output.
2. **ReportWriter** (`report_runtime.py`): assembles the final `report_package`
   using `report_knowledge.py` and `knowledge/report/*.yaml`.
3. **DashboardComposer** (`dashboard_composer.py`): derives all visual elements
   for Streamlit UI and PDF export from real run artifacts — no mock data.

### Resolution controller

After the first department round the `resolution_controller.py` classifies the
run into exactly one bucket:

- `AUTO_CLOSE_REQUIRED` — artifacts are sufficient, finalize automatically
- `USER_DECISION_REQUIRED` — gaps require human input before continuation
- `CUSTOMER_CONFIRMATION_REQUIRED` — domain-specific confirmation needed

Classification is based on **typed runtime artifacts** (`gap_candidates`,
`answer_matrix`) as primary sources, with `open_questions` as fallback.

### Runtime guardrails

`runtime_guardrails.py` (RA-08) is the operational hardening layer consumed by
`pipeline_runner.py` and `supervisor_loop.py`:
- phase-aware token/time budgets
- enforced department ordering
- stop-reason tracking
- all guardrail state persisted in the run export

---

## Contract vocabulary

Canonical types live in `src/orchestration/contracts.py`.

### TaskDecisionOutcome (6 states)

| Outcome | Meaning |
| --- | --- |
| `accepted` | all core rules passed, task complete |
| `accepted_with_gaps` | partial core passed, usable but gaps documented |
| `rework_required` | Lead authorised retry, new attempt pending |
| `escalated_to_judge` | ambiguous quality, Judge will decide |
| `closed_unresolved` | max retries reached, evidence gap documented |
| `blocked_by_dependency` | F4 dependency not satisfied |

Terminal outcomes: `accepted`, `accepted_with_gaps`, `closed_unresolved`,
`blocked_by_dependency`.

Dependency-satisfying outcomes (allow dependents to start): `accepted`,
`accepted_with_gaps`.

### Core artifact types

| Type | Produced by |
| --- | --- |
| `TaskArtifact` | Researcher / Worker |
| `TaskReviewArtifact` | Critic |
| `TaskDecisionArtifact` | Judge |
| `DepartmentRunState` | Lead at package finalization |

High-level artifact lifecycle:
1. Research → `TaskArtifact`
2. Critique → `TaskReviewArtifact`
3. Escalation / acceptance → `TaskDecisionArtifact`
4. Package finalization assembles stored artifacts into `DepartmentPackage`

Authoritative department state is the **artifact history**, not an implicit
Python micro-workflow.

---

## Department autonomy model

Architecture follows a **fixed contract, autonomous execution** model:

- Supervisor provides required questions, scope, and report expectations
- Department Lead operationalises that contract
- Department group chooses how to execute internally
- Group may retry, critique, escalate, adapt strategy, and use coding support
- Group may use KB-recommended sources or alternate sources when justified
- Department must continue until required items are answered with sufficient
  support, or explicitly unresolved with justified evidence gaps

The department group is therefore **bounded but autonomous**.

---

## Selector model

`speaker_selector.py` is **guardrail-only** — not a hidden workflow engine.

Guardrail responsibilities:
- route tool calls to the executor
- return executor output to the Lead
- prevent non-Lead text-only loops
- route termination correctly

Workflow ownership sits with the **Lead**.

---

## Knowledge base

Each department has three KB files under `knowledge/`:

| KB category | Path pattern | Authority for |
| --- | --- | --- |
| Sources | `knowledge/sources/<dept>.yaml` | source registry: priorities, evidence type, provenance |
| Query strategies | `knowledge/query_strategies/<dept>.yaml` | runtime query templates (`{placeholder}`) expanded by `query_resolver.py` |
| Policies | `knowledge/policies/<dept>.yaml` | required output fields, evidence minima, acceptance gates |

Report composition uses a separate KB:

| File | Purpose |
| --- | --- |
| `knowledge/report/blueprint_de.yaml` | German report structure blueprint |
| `knowledge/report/blueprint_en.yaml` | English report structure blueprint |
| `knowledge/report/quality_gates.yaml` | report-level quality gate rules |
| `knowledge/report/rules.yaml` | report assembly rules |

KB and policy gates do **not** script turn-by-turn conversation flow.
Departments remain conversation-driven and autonomous inside GroupChat.

---

## Memory model

### Run Brain

Case-specific, persisted by `run_id` in `short_term_store.py`.

May contain: task artifacts, review artifacts, decision artifacts, evidence,
notes, open questions, rejected paths, strategy changes, judge escalations,
coding-support usage, department workspaces, final department packages,
`MeetingReadinessAssessment`, `FinalBriefing`.

Run context is shared across the pipeline via `run_context.py` (`RunContext`).
This run-specific memory is reloaded for follow-up.

### Long-term process memory

Stores **process patterns only** — managed by `consolidation.py`,
`long_term_store.py`, `retrieval.py`.

Admission threshold: minimum readiness score of 70 (see `memory/policies.py`).

Allowed patterns:
- search/query patterns
- critique heuristics
- escalation principles
- completion patterns
- parsing/extraction/debugging tactics

Disallowed:
- target-company facts
- customer/domain-specific evidence
- run-specific conclusions as reusable truth

Historical runs can bootstrap the long-term store via `backfill.py`.

---

## Follow-up model

Follow-up starts from a stored `run_id`.

High-level flow:
1. load run artifacts (`follow_up.py`, `followup_config.py`)
2. rehydrate the run brain
3. route the question to the appropriate department answer path
4. answer from stored run evidence first
5. trigger additional research only if unresolved gaps remain

Evidence priority for follow-up:
1. run-brain artifacts
2. `pipeline_data`
3. department packages

Follow-up section routing is governed by `FOLLOWUP_TARGET_SECTION_BY_DEPARTMENT`
in `followup_config.py`.

---

## Tool policy

`tool_policy.py` defines explicit tool grants per runtime role and task via
`BASE_TOOL_POLICY`. All agent tool access is bounded by this policy — agents
may not self-grant tools outside their assigned grant set.

---

## Testing model

| Layer | Scope |
| --- | --- |
| Architecture / contract tests | must run without AG2 runtime dependencies |
| Runtime / integration tests | may require AG2/autogen and fuller wiring |

Rules:
- avoid importing runtime-heavy modules from pure architecture tests
- prefer dependency-light helpers and contracts for unit coverage
- keep architecture tests fast and isolated

---

## Export and storage

| Layer | Path |
| --- | --- |
| PDF export (DE + EN) | `src/exporters/pdf_report.py` |
| JSON export | `src/exporters/json_export.py` |
| Run artifact persistence | `src/storage/run_artifacts.py` |
| Runtime stores (PostgreSQL) | `src/storage/runtime_stores.py` |

---

## Security

`src/security/secret_guard.py` — runtime prompt secret guard: blocks
secret-like prompt payloads before model calls.

Additional security references:
- `docs/security_policy_enforcement_checklist.md`
- `docs/en/security/` — threat model, agent-to-agent security, permission matrix
- `SECURITY.md`

---

## Git and publishing model

The remote `main` branch is protected.

When committing or publishing work:
- do not push directly to `main`
- use a PR branch, preferably `codex/<short-description>`
- ensure commits are GPG-signed before pushing
- use the repo-local signing key `3EB5B5E8705BDA15`
- on Windows, Git may need `gpg.program` set to
  `C:/Program Files/Git/usr/bin/gpg.exe`
- open a pull request against `main` instead of updating `main` directly

If local `main` is ahead with unsigned commits, create a PR branch from
`origin/main` and cherry-pick the commits with signing enabled.

---

## Key file map

### Entrypoints

| File | Purpose |
| --- | --- |
| `src/pipeline_runner.py` | public runtime entrypoint for UI and CLI |
| `launcher.py` | CLI launcher wrapper |

### Orchestration

| File | Purpose |
| --- | --- |
| `src/orchestration/supervisor_loop.py` | supervisor-controlled department routing loop |
| `src/orchestration/task_router.py` | translates supervisor mandate into department task assignments |
| `src/orchestration/department_runtime.py` | bounded department group runtime (AG2 GroupChat) |
| `src/orchestration/synthesis_runtime.py` | synthesis department runtime |
| `src/orchestration/report_runtime.py` | report writer runtime node |
| `src/orchestration/follow_up.py` | run loading, follow-up routing, persisted follow-up answers |
| `src/orchestration/followup_config.py` | follow-up routing constants and section mapping |
| `src/orchestration/contracts.py` | typed runtime contracts and department artifact state |
| `src/orchestration/contract_validation.py` | dependency-light contract validation helpers |
| `src/orchestration/envelope.py` | canonical F2 admission gate for department package envelopes |
| `src/orchestration/department_knowledge.py` | department source/policy KB loading and acceptance-gate evaluation |
| `src/orchestration/report_knowledge.py` | KB loading for report composition |
| `src/orchestration/speaker_selector.py` | guardrail-only selector for department group chats |
| `src/orchestration/meeting_questions.py` | meeting-question catalog and answer-matrix helpers |
| `src/orchestration/meeting_readiness.py` | meeting-readiness gate and final briefing composer (RA-06) |
| `src/orchestration/resolution_controller.py` | run-level resolution classification after first department round |
| `src/orchestration/runtime_guardrails.py` | operational hardening layer — budgets, ordering, stop reasons (RA-08) |
| `src/orchestration/run_context.py` | run-level context shared across pipeline (`RunContext`) |
| `src/orchestration/runtime_agents.py` | typed `RuntimeAgents` bundle |
| `src/orchestration/dashboard_composer.py` | composes `DashboardBundle` from runtime artifacts for UI and PDF |
| `src/orchestration/tool_policy.py` | explicit tool grants per runtime role |
| `src/orchestration/step1_handoff.py` | Step-1 handoff contract and validation gate |
| `src/orchestration/synthesis.py` | synthesis helpers |

### Agents

| File | Purpose |
| --- | --- |
| `src/agents/supervisor.py` | Supervisor agent implementation |
| `src/agents/lead.py` | Department Lead lifecycle and package finalization |
| `src/agents/worker.py` | evidence-driven Researcher/Worker agent |
| `src/agents/critic.py` | Critic agent |
| `src/agents/judge.py` | Judge agent |
| `src/agents/coding_assistant.py` | Coding Specialist (targeted escalation) |
| `src/agents/synthesis_department.py` | Synthesis Department GroupChat |
| `src/agents/report_writer.py` | ReportWriter agent |
| `src/agents/runtime_factory.py` | runtime agent factory (AG2-dependent) |
| `src/agents/specs.py` | agent metadata specs (pure, no runtime deps) |

### Memory

| File | Purpose |
| --- | --- |
| `src/memory/short_term_store.py` | run-scoped memory including department run states |
| `src/memory/long_term_store.py` | file-backed long-term process pattern store |
| `src/memory/consolidation.py` | process-pattern consolidation into long-term memory |
| `src/memory/retrieval.py` | contextual retrieval helpers for long-term memory |
| `src/memory/backfill.py` | bootstrap long-term memory from historical run artifacts |
| `src/memory/policies.py` | admission policies for long-term memory (min readiness score) |

### Research

| File | Purpose |
| --- | --- |
| `src/research/query_resolver.py` | central query resolver: placeholder expansion, validation, buyer expansion |
| `src/research/search.py` | web search execution |
| `src/research/fetch.py` | page fetch and content retrieval |
| `src/research/extract.py` | structured extraction |
| `src/research/normalize.py` | evidence normalisation |
| `src/research/source_scoring.py` | source quality scoring |
| `src/research/ssrf_guard.py` | SSRF protection for fetch operations |
| `src/research/tools.py` | research tool registrations |

### Security

| File | Purpose |
| --- | --- |
| `src/security/secret_guard.py` | runtime prompt secret guard |

### Export and storage

| File | Purpose |
| --- | --- |
| `src/exporters/pdf_report.py` | PDF report generation (DE + EN) |
| `src/exporters/json_export.py` | JSON export |
| `src/storage/run_artifacts.py` | run artifact persistence |
| `src/storage/runtime_stores.py` | PostgreSQL-backed runtime stores |

### Knowledge base (YAML)

| Path | Purpose |
| --- | --- |
| `knowledge/sources/<dept>.yaml` | source registry per department |
| `knowledge/policies/<dept>.yaml` | required fields, evidence minima, gate rules |
| `knowledge/query_strategies/<dept>.yaml` | runtime query templates per task |
| `knowledge/report/blueprint_*.yaml` | report structure blueprint (DE + EN) |
| `knowledge/report/quality_gates.yaml` | report-level quality gate rules |
| `knowledge/report/rules.yaml` | report assembly rules |

---

## Canonical documentation

Primary sources of truth (in priority order):

1. Executable code
2. `docs/drawio/target_runtime_architecture.md`
3. `README.md`
4. `docs/target_runtime_architecture.md`
5. This file

If this file disagrees with any of the above, prefer the higher-ranked source.

---

## Maintenance rule

`AGENTS.md` must stay short — it is an orientation guide, not a second
architecture handbook.

Update this file only when the following change:
- control-plane boundaries
- department autonomy model
- role definitions
- contract vocabulary (new outcome states or artifact types)
- memory boundaries (what may / must not enter long-term store)
- follow-up routing behaviour
- key file map (new runtime-significant modules or removed files)
- test layering rules
