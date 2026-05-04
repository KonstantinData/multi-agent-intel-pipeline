# Target Runtime Architecture

This document describes the runtime architecture as implemented.
It is kept in sync with the codebase after the CHG-00–CHG-10 refactor.

## Runtime Modes

The system supports two runtime modes:

1. Initial briefing mode
2. Run-based follow-up mode

Both modes are coordinated by the `Supervisor`.

## Operational Security And Governance Layer

Security and governance are cross-cutting runtime boundaries, not department
chat participants. The runtime diagram therefore represents them as an
outer operational layer around entry, configuration, CI, and artifact handling.

The layer covers:

- secret resolution: process/deployment secret first, OS keyring second,
  plaintext `.env` only when `LIQUISTO_ALLOW_DOTENV_SECRETS=1`;
- `preflight.py`: dependency, import-chain, query-strategy, API-key-source, and
  Streamlit-port readiness checks before local UI startup;
- CI and review gates: CODEOWNERS, secret scan, workflow hardening,
  architecture/runtime contract tests, and release attestation;
- pre-commit hooks: Ruff (with --fix) and Bandit run locally on every
  git commit -- same scope as CI (src/, scripts/, tests/);
- runtime guardrails: safe `run_id` path resolution, artifact locking/atomic
  JSON writes, audit minimization, and strict profile loading when enabled.

This layer constrains how the runtime is started, reviewed, and persisted. It
does not route department work and does not participate in AG2 GroupChat turns.

## Current Runtime Phase Order

`src/pipeline_runner.py::run_pipeline()` is the public phase orchestrator.
The current initial-run order is:

1. create `run_id`, run directory, runtime agents, and run context
2. load process memory and role strategies
3. build the Supervisor intake brief
4. initialize `question_registry` and `answer_matrix`
5. run the domain department round via `run_supervisor_loop()`
   - Company + Market first pass can run in parallel
   - Buyer runs after the first pass
   - Contact runs after Buyer
6. classify first-round resolution state
7. write `after_first_pass` checkpoint
8. run bounded auto-close only when `AUTO_CLOSE_REQUIRED`
9. write `after_closure` checkpoint when closure ran
10. run the Synthesis Department on admitted department packages
11. write `after_synthesis` checkpoint
12. build quality, readiness, playbook, and report-facing pipeline sections
13. evaluate `MeetingReadinessGate`
14. compose `meeting_actions` via `FinalBriefingComposer`
15. sync finalization artifacts
16. run `ReportWriterRuntime`
17. persist budget telemetry and write `after_finalization` checkpoint
18. export JSON/PDF artifacts and consolidate scrubbed process patterns

## Top-Level Roles

### Supervisor

The `Supervisor` is the single control-plane role.

Responsibilities:
- accept `company_name` and `web_domain` from the UI
- normalize the company domain and visible legal identity
- create the intake brief for the run
- translate the Liquisto standard scope into department assignments
- route assignments to the correct domain department
- track run status and formal completeness
- accept completed department packages
- route follow-up questions by `run_id`

Non-responsibilities:
- no domain-level fact interpretation
- no domain-level evidence review
- no intra-department retry decisions
- no final commercial judgment

### Domain Departments

The research plane is split into four domain departments:
- `Company Department`
- `Market Department`
- `Buyer Department`
- `Contact Department`

Each department is implemented as an AG2 GroupChat with bounded
multi-agent collaboration. Departments work **autonomously** inside
their contract — the Supervisor never intervenes in internal retry,
critique, or escalation decisions.

Each department contains:
- `Department Lead / Analyst`
- `Researcher`
- `Critic`
- optional `Judge`
- optional `Coding Specialist`

Department-specific knowledge base inputs:

- `knowledge/sources/<department>.yaml` (source registry metadata: priorities, evidence type, provenance notes)
- `knowledge/policies/<department>.yaml` (required fields, evidence minima, gate rules)
- `knowledge/query_strategies/<department>.yaml` (runtime query templates; single authority for task query construction)

These KB files guide investigation quality and final package acceptance.
They do not enforce turn order or scripted dialogue.

### Query Resolution

Runtime query construction is centralized in
`src/research/query_resolver.py`.

The resolver:
- maps each standard research task key to its department strategy file
- loads `knowledge/query_strategies/<department>.yaml`
- expands canonical placeholders (`{company}`, `{domain}`, `{industry}`,
  `{keywords}`, `{buyer}`)
- validates strategy files and query overrides
- expands per-buyer contact queries
- fails loudly on missing files, malformed content, missing task entries, and
  invalid placeholders

`src/agents/worker.py::_build_queries()` delegates to the resolver.
Runtime query overrides are not free-form queries. Coding support emits
`strategy:<task_key>:<variant_key>` tokens, and the resolver expands those
tokens only from `query_variants` entries in the owning
`knowledge/query_strategies/<department>.yaml` file.
`_build_queries_legacy()` remains only for parity verification and migration
monitoring via `LIQUISTO_QUERY_RESOLVER_VERIFY=1`.

Source files under `knowledge/sources/*.yaml` are not runtime query-template
files. They contain source metadata only.

Department groups are responsible for:
- domain research
- domain-level interpretation
- bounded internal review loops
- assembling a structured department package as output

The output is not raw chat. The output is a validated `DepartmentPackage`.

### Strategic Synthesis Department

This AG2 GroupChat receives the approved domain packages from all departments
and builds the cross-domain interpretation.

Responsibilities:
- compare findings across departments
- surface tensions or contradictions
- assess the most plausible Liquisto opportunity
- derive negotiation relevance and next-step logic
- produce the final `synthesis` section

The Synthesis Department does not receive a `SupervisorAgent` instance.
If internal analysis identifies a domain gap, it records a structured
BackRequest in its synthesis result. The outer runtime persists those
BackRequests after the GroupChat completes and exposes them to the Supervisor
as post-synthesis artifacts.

### Report Writer Runtime

After synthesis, meeting-readiness evaluation, meeting-action composition, and
finalization-artifact sync, the runtime executes a dedicated
`report_writer` node (`src/orchestration/report_runtime.py`), backed by
`ReportWriterAgent` (`src/agents/report_writer.py`).

Responsibilities:
- build `run_context.report_package` from finalized `pipeline_data`
- expose a stable report-oriented structure for UI/export
- emit explicit `ReportWriter` runtime telemetry messages

## Department Model

Each department operates as a bounded collaborative group.

### Company Department

Questions owned:
- who the target company is
- what it sells or makes
- which goods, materials, spare parts, or inventory positions are visible
- which items are made by the company, distributed/resold, or held in stock
- which public signals suggest economic or commercial pressure

### Market Department

Questions owned:
- market situation, demand, and supply pressure
- overcapacity or contraction signals
- excess-inventory monetization and redeployment paths
- inventory-relevant market pressure and timing signals

### Buyer Department

Questions owned:
- peer companies
- plausible buyers
- resale, redeployment, reuse, or secondary-market paths
- likely downstream, service, broker, distributor, or cross-industry routes

### Contact Department

Questions owned:
- decision-maker contacts at prioritized buyer firms
- procurement leads, COO/VP operations, asset management contacts
- seniority and function classification per contact
- outreach angles per contact based on Liquisto's business model

The Contact Department runs after the Buyer Department. It reads
`buyer_candidates` from the approved `market_network` package and builds
contact queries per firm. If no buyer candidates are available, the department
falls back to industry-scoped contact discovery.

Output section: `contact_intelligence`.

## AG2 Department Groups

Each department is implemented as a real AG2 GroupChat, not as a single
generic worker or a Python orchestration loop.

### Group structure

Each department group consists of five `ConversableAgent` instances:

| Role                      | LLM          | Registered tool          |
| ------------------------- | ------------ | ------------------------ |
| Department Lead / Analyst | gpt-4.1      | `finalize_package`       |
| Researcher                | gpt-4.1-mini | `run_research`           |
| Critic                    | gpt-4.1      | `review_research`        |
| Judge                     | gpt-4.1      | `judge_decision`         |
| Coding Specialist         | gpt-4.1-mini | `suggest_refined_queries`|

Note: `request_supervisor_revision` is **not** a registered tool. The Lead
decides retry, coding support, and judge escalation autonomously from the
task contract and the stored artifact history (CHG-03).

### Conversation mechanics

- The Lead initiates the chat via `initiate_chat` with the investigation plan
- `GroupChatManager` with a custom `speaker_selection_method` (guardrail-only
  selector) routes turns based on tool-call state and loop prevention — it does
  not enforce a fixed micro-sequence
- The Lead explicitly addresses the next agent in every message
- Tools are Python closures registered per agent via `register_function`
- The chat terminates when the Lead calls `finalize_package`, which returns
  `TERMINATE` in the message content

### Speaker selector — guardrails only (CHG-04)

The selector (`build_department_selector` in `speaker_selector.py`) applies
exactly four guardrails in order:

1. `tool_calls` present in last message → executor
2. Last speaker was executor → lead
3. Text-only loop (≥ 3 consecutive text turns) for a non-lead agent → lead
4. `"TERMINATE"` in last message content → lead

Beyond the guardrails, the selector provides Lead-driven routing: when the
Lead spoke, it parses the message content to route to the addressed agent
(researcher / critic / judge / coding specialist). If no address is found,
it defaults to researcher. Non-lead text turns always return to the Lead.

The selector does **not** maintain workflow state. The Lead owns the workflow
through explicit agent addressing and the task contract.

### Intra-group escalation path

```text
Lead → Researcher: run_research(task_key)          [attempt recorded as TaskArtifact]
Lead → Critic: review_research(task_key)           [review recorded as TaskReviewArtifact]
  if review approved:
    Lead records implicit lead_accepted decision
  if review rejected and attempts < MAX_TASK_RETRIES:
    Lead → [optional] CodingSpecialist: suggest_refined_queries(task_key)
    Lead → Researcher: run_research(task_key)      [new TaskArtifact, incremented attempt]
  if review rejected and attempts >= MAX_TASK_RETRIES:
    Lead → Judge: judge_decision(task_key)         [decision recorded as TaskDecisionArtifact]
Lead calls: finalize_package(summary) → TERMINATE
```

`MAX_TASK_RETRIES` is configurable via env var `LIQUISTO_MAX_TASK_RETRIES`
(default: 3).

### Supervisor boundary (CHG-03)

The Supervisor does **not** pass itself into department runs.
The `DepartmentRuntime.run()` and `DepartmentLeadAgent.run()` interfaces
have no `supervisor` parameter.

The department group completes the full critique → retry → coding support →
judge escalation path without any Supervisor intervention. The Supervisor
only sees the final `DepartmentPackage` returned after `finalize_package`.

### Package finalization from stored decisions (CHG-07)

`finalize_package` assembles the department package from stored artifacts,
in this priority order per task:

1. Stored `TaskDecisionArtifact` → use its outcome (no re-judging)
2. Research + approved review → implicit `lead_accepted` decision
3. Research + rejected review → inline judge fallback
4. Research only → full inline critic + judge fallback

The finalized `DepartmentRunState` is persisted to
`ShortTermMemoryStore.department_run_states` after every finalization.

## Memory Model

### Run Brain — per `run_id` (CHG-02)

Case-specific working knowledge, stored in `ShortTermMemoryStore` and
persisted to `run_context.json`:

- `department_run_states`: full artifact history per department
  - `task_artifacts`: all research attempts per task (facts, sources, strategy)
  - `review_artifacts`: all critic reviews per task (accepted/rejected points)
  - `decision_artifacts`: all judge/lead decisions per task (outcome, rationale)
  - `strategy_changes`: retry and query-override events
  - `judge_escalations`: escalation events with conflict context
  - `coding_support_used`: coding specialist interventions
- `department_packages`: final package per department
- `department_workspaces`: per-department evidence summaries
- task statuses, usage totals, department timings

The run brain can be reloaded by `run_id` via `load_run_artifact()` in
`src/orchestration/follow_up.py`.

### Long-Term Process Brain (CHG-02/CHG-09)

Reusable process patterns only — no company-specific facts, no run-specific
evidence.

Stored via `consolidate_role_patterns()` in `src/memory/consolidation.py`:

- **Researcher**: structural query patterns (scrubbed of company identifiers)
- **Critic**: critique heuristics and defect-class frequencies
- **Judge**: decision principles from escalation history
- **Coding Specialist**: method tactics from coding support events
- **Lead**: retry trigger patterns from strategy changes

All patterns are scrubbed before write: company domains, quoted names, and
legal suffixes (`GmbH`, `AG`, etc.) are replaced with `{domain}` / `{company}`.
The `domain` field is always set to `""` — the store never holds a customer
domain name.

## Follow-Up Mode (CHG-08)

Follow-up mode starts from a stored `run_id`.

Flow:
1. User enters `run_id` and a question in the UI
2. `load_run_artifact(run_id)` loads `pipeline_data.json` + `run_context.json`
3. The question is routed to the correct department answer function
4. Each answer function extracts evidence by priority:
   - primary: run-brain `task_artifacts` accepted by a current review/decision
   - unresolved: `decision_artifacts.open_questions` for blocked or closed-unresolved tasks
   - secondary: finalized `pipeline_data`
   - fallback: department packages via the canonical envelope resolver
5. `requires_additional_research=True` when unresolved points exist
6. The follow-up result is exported as a follow-up artifact

Follow-up answering is grounded in the rehydrated run brain. If additional
research is needed, `DepartmentRuntime.run_followup()` initiates a new
mini-session with the stored context.

## Required Output Artifacts

Each run must produce:
- `pipeline_data.json`
- `run_context.json` (includes run brain: `department_run_states`, `department_packages`,
  `answer_matrix`, `question_registry`, `meeting_readiness_assessment`, `resolution_state`)
- `memory_snapshot.json` (includes `evidence_packets`, `gap_candidates`,
  `answer_matrix_updates`, `meeting_actions`, `resolution_plans`)
- `checkpoints/<phase>.json` per major phase (after_first_pass, after_closure,
  after_synthesis, after_dashboard_resume, after_finalization)
- follow-up artifacts when follow-up answers are generated
- PDF export in German and English on demand

## Meeting-Readiness Architecture (RA-01–RA-10)

The runtime plans around **meeting questions**, not only departments.

### Question Planning (RA-02)

- `MEETING_QUESTION_REGISTRY` (11 questions) in `src/orchestration/meeting_questions.py`
- `TASK_TO_QUESTION_IDS` maps each task to its covered question IDs
- `question_registry` and `answer_matrix` built before department execution
- Answer matrix updated by each task outcome via `_update_answer_matrix_from_task`

### Evidence Production (RA-03)

Departments are **question-coverage contributors**, not final-briefing owners.
Primary outputs:
- `EvidencePacket` per collected fact (worker)
- `GapCandidate` per unresolved gap (lead)
- `AnswerMatrixUpdate` per question coverage change (lead)

Narrative summaries exist for human readability but do not drive closure logic.

### Resolution Controller (RA-04)

After the first department round, `ResolutionController.classify()` assigns
exactly one bucket:
- `AUTO_CLOSE_REQUIRED` → bounded closure via `run_bounded_follow_up()`
- `USER_DECISION_REQUIRED` → dashboard pause
- `CUSTOMER_CONFIRMATION_REQUIRED` → accept gap, continue
- `NOT_MEETING_CRITICAL` → proceed to finalization
- `BLOCKING_FAILURE` → block finalization

Closure results feed back into the answer matrix.

### Dashboard Pause/Resume (RA-05)

- `run_pipeline()` returns `needs_user_selection` when dashboard input required
- `resume_pipeline()` loads paused run, applies user selections, re-evaluates gate
- UI shows resolution dashboard with answered questions, optional depth checkboxes,
  customer confirmation items, and resume button

### Meeting-Readiness Gate (RA-06)

`MeetingReadinessGate.evaluate()` blocks finalization when:
- publicly researchable meeting-critical questions remain unresolved
- required dashboard decisions are missing
- evidence quality is below threshold
- non-contact questions are still pending/blocked
- department policy-gate blockers remain unresolved
- minimum execution package is not met (verified decision-maker + hard financial/inventory signals)

Status behavior:
- `meeting_ready`: all hard gates passed
- `discovery_ready_not_execution_ready`: public research sufficient, but hard blockers are internal-customer data/contact gaps
- `blocked_not_meeting_ready`: public hard blockers still open

`FinalBriefingComposer.compose()` produces `MeetingAction` list as the primary
action output, replacing generic `next_steps`.

### Runtime Guardrails (RA-08)

- `PhaseBudgetTracker`: first_pass / closure / optional_depth token budgets
- `validate_structured_artifact()`: Pydantic enforcement for runtime artifacts
- Deterministic ordering: `QUESTION_ORDER`, `MEETING_ACTION_TYPE_ORDER`
- Stop reasons and budget consumption persisted in `resolution_state`

### Success-Path Semantics

A successful run (`meeting_ready`) contains:
- `meeting_actions` as the primary action output
- `customer_confirmation_items` for items requiring customer-side validation
- `optional_depth_not_selected` for user-skipped depth areas

A successful run does **not** contain:
- generic `open_questions` block (removed from synthesis on success export)
- unresolved publicly researchable meeting-critical questions

Legacy `next_steps` in synthesis context exist as a fallback for backward
compatibility but are not the authoritative action model.

## Replaced Architecture Elements

| Old | New |
| --- | --- |
| `request_supervisor_revision` tool | Removed — Lead decides autonomously (CHG-03) |
| `supervisor.decide_revision()` call | Removed — department is autonomous (CHG-03) |
| State-machine speaker selector (`workflow_step`) | Guardrail-only selector, Lead drives workflow (CHG-04) |
| Mutable dict payload as working artifact | Explicit `TaskArtifact` / `TaskReviewArtifact` / `TaskDecisionArtifact` (CHG-01/CHG-05) |
| Hidden re-judging in `finalize_package` | Assembly from stored decisions only (CHG-07) |
| Global one-size-fits-all completion semantics | Department-specific KB policy gates at acceptance time |
| Shallow follow-up heuristics | Run brain rehydration from `department_run_states` (CHG-08) |
| Unguarded company facts in long-term memory | Scrubbed structural patterns only (CHG-09) |
