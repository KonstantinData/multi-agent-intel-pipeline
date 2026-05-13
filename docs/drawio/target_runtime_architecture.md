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

- secret resolution: process/deployment secret first, OS keyring second;
  plaintext `.env` is not used for API keys;
- Phase-2 production storage boundary: Hetzner runs the Python/AG2 runtime and
  PostgreSQL/pgvector as the system of record; Cloudflare provides DNS, TLS,
  WAF, DDoS protection, rate limiting, Access/Zero Trust, and Tunnel; Workers
  are limited to thin gateway/status/webhook duties, not long-running
  orchestration;
- `preflight.py`: dependency, import-chain, query-strategy, credential
  availability, and Streamlit-port readiness checks before local UI startup;
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
2. initialize the explicit storage boundary, health-check it, and load process
   memory via the `LongTermMemoryStore` contract
3. build the Supervisor intake brief and bounded intake-research result
4. initialize `question_registry` and `answer_matrix`
5. build and validate the versioned `Step1Handoff`, including the first
   runtime event and the `after_supervisor_brief` checkpoint
6. run the domain department round via `run_supervisor_loop()`
   - Company + Market first pass can run in parallel
   - Buyer runs after the first pass
   - Contact runs after Buyer
7. classify first-round resolution state
8. write `after_first_pass` checkpoint
9. run bounded auto-close only when `AUTO_CLOSE_REQUIRED`
10. write `after_closure` checkpoint when closure ran
11. run the Synthesis Department on admitted department packages
12. write `after_synthesis` checkpoint
13. build quality, readiness, playbook, and report-facing pipeline sections
14. evaluate `MeetingReadinessGate`
15. compose `meeting_actions` via `FinalBriefingComposer`
16. sync finalization artifacts
17. run `ReportWriterRuntime`
18. persist budget telemetry and write `after_finalization` checkpoint
19. export JSON/PDF artifacts and consolidate scrubbed process patterns

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

**Observed calibration note**: In practice, the Lead's LLM judgment determines
whether to consume retries or escalate directly to the Judge. For
information-scarce domains or when the Critic's rejection signal is strong,
the Lead may escalate to the Judge on the first attempt without issuing a
retry — even when `attempts < MAX_TASK_RETRIES`. This means the retry path
via CodingSpecialist is available but not guaranteed to activate.
Zero strategy changes (`strategy_changes: []`) with concurrent Judge
escalations is a valid runtime state, not an error.

### Two-layer admission model

Department quality is evaluated at two independent levels:

1. **Internal gate (deterministic)** — Lead or Judge issues a
   `TaskDecisionArtifact` with outcome `accepted`, `accepted_with_gaps`, or
   `closed_unresolved`. This is based on the stored artifact history and the
   department-specific KB policy rules.

2. **Supervisor admission gate (LLM-based)** — After `finalize_package`,
   the Supervisor evaluates the full `DepartmentPackage` and assigns
   `accepted`, `accepted_with_gaps`, or `rejected`.

These two gates are **independent**. A package whose individual tasks were
all Judge-accepted can still receive a Supervisor-level `rejected` if the
package as a whole does not meet the Supervisor's cross-task coherence and
evidence-coverage expectations. This divergence routes the run to
`BLOCKING_FAILURE` via the ResolutionController even when no individual task
failed.

Implication: the two gates must be calibrated together. An overly strict
Supervisor admission gate relative to the internal Judge thresholds will
produce `BLOCKING_FAILURE` on runs where substantive evidence was collected.

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

## Observability and Cost Tracking

### What is tracked

- **Department timings**: wall-clock seconds per department, stored in
  `run_meta.json` and `resolution_state.budget_tracker`.
- **Researcher token usage**: tracked per `worker_report` in
  `ShortTermMemoryStore`. Aggregated in `usage_totals` and surfaced in
  `run_meta.json` under `usage.agents.<role>`.
- **Web search call cost**: counted and priced separately via
  `estimate_web_search_preview_call_cost_usd()`.
- **Phase token budgets**: `PhaseBudgetTracker` tracks first_pass, closure,
  and optional_depth token consumption against configured caps.
- **Phase checkpoints**: `after_supervisor_brief`, `after_first_pass`,
  `after_closure`, `after_synthesis`, `after_finalization` are written to
  `checkpoints/` for crash recovery and failure diagnostics.
- **Run-level structured trace**: `current_phase`, `last_checkpoint`,
  and failure context are persisted in `resolution_state`.

### Known tracking gap

`worker_reports` records only **Researcher** LLM calls (via `run_research`
tool). Lead, Critic, Judge, and CodingSpecialist LLM calls are **not**
captured in per-agent usage tracking. The `estimated_cost_usd` in
`run_meta.json` therefore reflects Researcher token cost plus web search
cost only. Lead/Critic/Judge token usage — which is significant when many
Judge escalations occur — is invisible to the cost model.

Target (2026): all `ConversableAgent` LLM calls must be tracked per role,
contributing to a complete per-run cost breakdown.

## Phase-2 Storage Backbone Target

The production runtime target replaces local-first recovery with a
Hetzner/Postgres/pgvector backbone while keeping the local MVP runnable without
Postgres.

### Hetzner responsibilities

- run the Python/AG2/AutoGen pipeline;
- host PostgreSQL as the system of record for runs, checkpoints, runtime state,
  artifact metadata, memory retrieval metadata, and scrubbed process memory;
- enable `pgvector` for semantic long-term process-memory retrieval;
- keep long-running orchestration on Hetzner, not Cloudflare Workers.

### Cloudflare responsibilities

- DNS, TLS, WAF, DDoS protection, rate limiting, Access/Zero Trust, and Tunnel;
- optional R2 object storage for large report/export artifacts;
- request correlation via edge request IDs;
- no ownership of department orchestration or long-running AG2 execution.

### Storage contracts

`src/storage/contracts.py` defines the production boundary:

- `LongTermMemoryStore`: `retrieve`, `upsert_strategy`, `healthcheck`;
- `RunStateStore`: `create_run`, `write_checkpoint`, `healthcheck`;
- `RuntimeStorageConfig`: non-secret profile/backend selection;
- `RuntimeStores`: selected stores plus required healthcheck and redacted
  snapshot.

`src/storage/runtime_stores.py` currently implements:

- `local_dev`: local file-backed process memory and local file exports;
- `production`: fail-fast placeholders until a migrated Postgres/pgvector store
  is enabled. Production never silently falls back to file memory.

The schema target is `sql/20260512_phase2_storage.sql`. It defines `runs`,
`run_checkpoints`, `run_events`, `run_artifacts`, `run_locks`,
`memory_patterns`, `memory_retrieval_events`, and `memory_backfill_jobs`.
Detailed alignment lives in `docs/runtime/phase2_storage_architecture.md`.

## Contextual Process-Memory Retrieval Target

Process-memory retrieval is context-aware and policy-gated. The code boundary
lives in `src/memory/retrieval.py`.

### Retrieval context

`RetrievalContext` carries `run_id`, `company_name`, `normalized_domain`,
`language`, `industry_hint`, `phase`, `target_scope`, `role`, `department`, and
`question_ids`.

`company_name` and `normalized_domain` are explicitly current-run context only:
they may support scrubbing and diagnostics, but they must not be persisted into
long-term memory and must not add retrieval score. The non-sensitive
`retrieval_query_summary` excludes both fields.

### Step-1 timing

Retrieval is two-stage:

1. `_initialize_run()` loads a minimal generic snapshot before the Supervisor
   brief. This gives the runner process patterns for orchestration/gating even
   when no industry hint exists yet.
2. `_build_supervisor_brief()` refreshes retrieval after `brief.industry_hint`
   and the question registry are available. Role-specific retrieval is final
   before `run_supervisor_loop()` starts.

The final role map is stored in `run_context.retrieved_role_strategies`.
Non-sensitive audit snapshots live under
`run_context.resolution_state["memory_retrieval"]`.

### Role scopes and fallback

Active role scopes are fixed:

- Lead: `lead_delegation`
- Researcher: `researcher_strategy`
- Critic: `critic_heuristics`
- Judge: `judge_principles`
- Coding Specialist: `coding_methods`
- Supervisor: `orchestration`

The local MVP uses deterministic score/filter fallback. Production retrieval
should combine hard filters (`role`, `pattern_scope`, `schema_version`, optional
`industry_hint`), embedding similarity from pgvector, pattern score, freshness,
and policy score.

Fallback and warning codes are machine-readable, including
`memory_retrieval_empty`, `memory_policy_rejected_all`, and
`local_score_fallback_no_embedding`.

### Policy gate

Every retrieved pattern is checked before it enters the Run Brain. The gate
rejects domains, URLs, e-mail addresses, contact/person fields, legal company
names, concrete financial values, role mismatches, scope mismatches, and schema
version mismatches. Rejections are counted and stored as non-sensitive audit
metadata.

## Evidence-Backed Supervisor Brief Target

The Supervisor Brief is a versioned handoff contract, not just a loose homepage
snapshot. The code boundary is `src/domain/briefing.py` plus
`SupervisorAgent.build_intake_brief()`.

### Identity and evidence contract

`SupervisorBrief` carries:

- submitted identity: caller-provided company name and domain;
- validated identity context: canonical domain from intake normalization;
- verified brand name from owned-website evidence;
- `verified_legal_name` only when a legal source is available;
- `EvidenceItem` entries for claims that support briefing fields;
- `MissingEvidence` entries when expected evidence is absent or Phase-2-only;
- `BriefingFetchAudit` for homepage reachability, final URL, redirect chain,
  HTTP status, content type, content length, language, timestamp and error
  fields.

The MVP uses owned website evidence. Register, LinkedIn, Wikidata, and curated
company data sources are Phase-2 evidence providers.

### Intake research contract

Step 1 has a bounded intake-research pipeline. It prepares identity and routing
context; it does not perform Company/Market/Buyer/Contact Department research.

The runtime path is:

1. `pipeline_runner._initialize_run()` validates intake and produces
   `NormalizedDomainResult`.
2. `SupervisorAgent.build_intake_brief()` passes that validated contract to
   `build_company_research()`.
3. `build_company_research()` derives the homepage URL from
   `NormalizedDomainResult.canonical_url`, fetches a guarded
   `WebsiteSnapshot`, resolves homepage-based identity, summarizes bounded
   visible text, infers an industry start signal and returns
   `CompanyResearchResult`.

The contract types live in `src/research/contracts.py`:

- `WebsiteSnapshot`: requested/final URL, reachability, HTTP status,
  content type, title/meta/OpenGraph/headings, language, redirect chain,
  structured fetch error, content hash, content length, extraction quality,
  JS-content signal and About/Impressum links. Raw HTML is not stored.
- `IdentityResolutionResult`: submitted name, homepage-derived brand/company
  name, empty MVP legal name, confidence reason, homepage match flag and
  Phase-2 source gaps.
- `IndustryInferenceResult`: industry hint, confidence, reason, evidence fields
  and alternatives.
- `CompanyResearchResult`: versioned envelope with snapshot, identity,
  industry, summary, evidence, warnings, errors, source registry and substep
  timings.

Fetch safety boundaries:

- DNS and redirect targets are validated against private, loopback, link-local,
  reserved and otherwise non-global IPs.
- The opener caps redirects and pins the initial connection to a validated IP.
- Homepage fetch uses controlled User-Agent, Accept and Accept-Language headers,
  bounded timeout, bounded response size and a content-type allowlist.
- Timeouts, TLS failures, access denied/rate limited/bot-protection signals,
  unsupported content types, weak extraction and JS-heavy pages become
  machine-readable warnings/errors.

`RunContext.resolution_state["intake_research"]` stores only non-sensitive
diagnostics: schema version, timings, warnings/errors, snapshot audit data,
identity diagnostics and industry diagnostics.

### Confidence and readiness

Identity confidence and industry confidence are separate:

- identity: `high`, `medium`, `low`, `unverified`;
- industry: `high`, `low`, `unknown`.

Submitted name, homepage title, brand name, and legal name are kept distinct.
When the homepage clearly names a different company, the brief records
`identity_conflict` and can block department routing. If the final fetched URL
lands on a different host than the canonical intake domain, the brief records
`redirect_domain_mismatch` as a routing gap.

`SupervisorBriefMessage` is versioned and validated. It exposes
`schema_version`, `status`, `briefing_readiness`, confidence values,
`routing_gaps`, and `evidence_summary` at the top level while keeping the
legacy `section="supervisor_brief"` and `payload` fields.

`RunContext.resolution_state["supervisor_brief"]` stores only non-sensitive
diagnostics: evidence count, confidence classes, fetch status, readiness,
routing gaps and duration. Homepage raw text remains bounded in the brief and
is not copied into the diagnosis snapshot.

## Step-1 Handoff Contract Target

Step 1 ends with a versioned `Step1Handoff`, not a loose collection of seeded
fields. The contract is built after the Supervisor Brief, question registry,
answer matrix, first runtime event and `after_supervisor_brief` checkpoint are
available.

The local MVP contract contains:

- `schema_version`, `run_id`, intake snapshot and validated supervisor brief;
- versioned `supervisor_message`;
- 12-question registry and matching initial answer matrix;
- retrieved general and role strategies;
- runtime-agent snapshot, storage snapshot and budget snapshot;
- first runtime event with `event_id`, `run_id`, `sequence`, `timestamp`,
  `schema_version`, `phase` and `content_type`;
- checkpoint metadata with id, phase, path, hash and write status;
- handoff readiness: `ready_for_department_routing`, `ready_with_gaps` or
  `blocked_step1_handoff`;
- validation errors with machine-readable codes.

The gate validates Supervisor Brief message shape, registry/matrix key
consistency, `TASK_TO_QUESTION_IDS`, runtime event shape and checkpoint write
status. Step 2 may only start when the gate returns an allowed readiness.

Production target: the local JSON checkpoint is an export/development artifact.
Authoritative recovery belongs in the transactional Run State Store from the
storage architecture, with checkpoint/event writes coupled to run phase updates.

### What is not yet tracked

- Distributed traces (no OpenTelemetry span/trace IDs)
- Per-turn AG2 GroupChat latency
- Metric emission for external monitoring (Prometheus/Grafana)

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

**Current local implementation**: flat JSON file
(`artifacts/memory/long_term_memory.json`) behind the
`LongTermMemoryStore` contract, used for local development and tests. Pattern
consolidation runs only on `completed` / `meeting_ready` runs —
`discovery_ready` runs do not contribute patterns.

**Production target**: Hetzner PostgreSQL with `pgvector`, table
`memory_patterns`, stable `content_hash`, `schema_version`, `embedding_model`,
role/scope/industry filters, and HNSW vector index. `source_run_id` is retained
only for audit/trace and must not be used as a domain-specific retrieval boost.

**Known limitation**: the DSN-backed `PostgresLongTermMemoryStore` and
transactional `RunStateStore` are not implemented yet. Until then, production
profile fails fast instead of silently using local files.

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

### Follow-up routing

**Current implementation**: keyword-based routing against the lowercased
question text. Questions containing terms like "contact", "market",
"buyer" are routed to the corresponding department; unmatched questions
default to `CompanyDepartment`. Routing happens in `run_bounded_follow_up()`
and `answer_follow_up()` in `src/orchestration/follow_up.py`.

**Known limitation**: keyword matching is brittle. A question like
"Who is the right contact for a restructuring discussion?" routes to
`CompanyDepartment` because no contact keyword matches — despite being
a clear `ContactDepartment` question.

**Target (2026)**: route via embedding similarity of the question against
the `MEETING_QUESTION_REGISTRY` entries, or a lightweight classifier LLM
call. This would make routing robust to phrasing variation and cross-domain
questions.

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
| Monolithic `run_pipeline()` function | Phase-decomposed runner with typed dataclasses per phase |
| Inline `OPENAI_API_KEY` in deploy script | Secret forwarded as SSH session env var; no literal in script |

## Architecture Gap Analysis — 2026 State-of-the-Art Targets

This section documents the delta between the current implementation and
2026 best-practice standards for production multi-agent AI pipelines.
Items are ordered by impact.

### GAP-01 · Complete LLM cost tracking across all roles

**Current**: Only Researcher LLM calls are tracked in `worker_reports`.
Lead, Critic, Judge, and CodingSpecialist token usage is not captured.
Cost figures in `run_meta.json` understate true LLM cost — especially on
runs with many Judge escalations.

**Target**: Instrument all `ConversableAgent` LLM calls. Emit a usage
record per role per call. Aggregate into a complete per-run cost breakdown
by role.

### GAP-02 · Distributed tracing (OpenTelemetry)

**Current**: Phase checkpoints and `logging.info/warning` provide local
observability. No trace/span IDs, no metric emission, no integration with
external monitoring (Prometheus, Grafana).

**Target**: Instrument the pipeline with OpenTelemetry spans at phase,
department, and tool-call level. Emit metrics (department duration,
token cost, resolution bucket frequency) to a time-series backend.
This is a prerequisite for production SLA monitoring on Hetzner.

### GAP-03 · Vector store for Long-Term Process Memory

**Current**: `long_term_memory.json` is a flat JSON file with filter-based
retrieval. Does not scale beyond ~200 patterns and cannot retrieve by
semantic similarity.

**Target**: Replace with an embedding-indexed store (e.g. `pgvector` on
the Hetzner Postgres instance, or `ChromaDB`). Use embedding similarity
for pattern retrieval at run start. This becomes relevant once the system
has processed 50+ distinct runs.

### GAP-04 · LLM/embedding-based follow-up routing

**Current**: Keyword matching on lowercased question text.
Phrasing variation and cross-domain questions route incorrectly.

**Target**: Embed the question and compute cosine similarity against the
`MEETING_QUESTION_REGISTRY` embeddings, or issue a single lightweight
classifier LLM call with the 5 department descriptions as candidates.
Latency cost: < 200 ms. Accuracy improvement: significant.

### GAP-05 · Systematic evaluation framework

**Current**: `tests/golden/` covers structural regressions. No systematic
measurement of research quality, evidence completeness, or synthesis
accuracy across runs.

**Target**: Build a run-level eval pipeline that scores each run against
a rubric (e.g. question coverage rate, evidence-to-gap ratio, Supervisor
admission rate per department). Run evals after every release. Use results
to calibrate Critic thresholds and Supervisor admission prompts.

### GAP-06 · Turn-level AG2 GroupChat streaming

**Current**: `on_message` hook fires at phase boundaries (department
assigned, department reviewed, synthesis reviewed). Within a GroupChat,
the UI receives no updates until the department returns its full package.

**Target**: Stream AG2 GroupChat turns via `on_message` at each
Lead/Researcher/Critic/Judge turn. Requires hooking into AG2's
`process_message` callback or equivalent. Reduces perceived latency
significantly for runs lasting 5–20 minutes.

### GAP-07 · Adaptive department execution

**Current**: All departments always execute all assigned tasks. No
shortcut path for well-documented companies where primary data is
immediately available.

**Target**: After Supervisor brief, evaluate a readiness pre-check
(e.g. public annual report present, company in LTM with high-confidence
prior run). If pre-check passes, reduce task scope for Company Department.
Estimated impact: 30–50% runtime reduction for well-known targets.

### GAP-08 · Gate calibration alignment

**Current**: The internal Judge gate (deterministic, rule-based) and the
Supervisor admission gate (LLM-based) are calibrated independently.
Divergence produces `BLOCKING_FAILURE` on runs where evidence was
collected but did not satisfy the Supervisor's cross-task coherence check.

**Target**: Define explicit calibration tests that run both gates against
synthetic department packages. Ensure that a Judge-accepted package at
`accepted_with_gaps` confidence meets the Supervisor admission threshold
for `accepted_with_gaps`. Gate prompts and KB policy thresholds must be
jointly reviewed when either is changed.
