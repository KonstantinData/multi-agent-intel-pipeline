# Target Runtime Architecture

This document describes the runtime architecture as implemented.
It is kept in sync with the codebase after the CHG-00–CHG-10 refactor.

## Runtime Modes

The system supports two runtime modes:

1. Initial briefing mode
2. Run-based follow-up mode

Both modes are coordinated by the `Supervisor`.

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
- repurposing and circularity paths
- analytics and operational improvement signals

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

When the Lead spoke, the selector parses the message content to route to the
addressed agent (researcher / critic / judge / coding specialist). If no
address is found, it defaults to researcher.

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
(default: 2).

### Supervisor boundary (CHG-03)

The Supervisor does **not** pass itself into `DepartmentLeadAgent.run()`.
`supervisor=None` in `DepartmentRuntime.run()` and `DepartmentLeadAgent.run()`.

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
4. Each answer function extracts evidence from the run brain:
   - primary: `task_artifacts` (facts from latest attempt per task)
   - secondary: `review_artifacts` (accepted points)
   - unresolved: `decision_artifacts` (open questions)
5. `requires_additional_research=True` when unresolved points exist
6. The follow-up result is exported as a follow-up artifact

Follow-up answering is grounded in the rehydrated run brain. If additional
research is needed, `DepartmentRuntime.run_followup()` initiates a new
mini-session with the stored context.

## Required Output Artifacts

Each run must produce:
- `pipeline_data.json`
- `run_context.json` (includes run brain: `department_run_states`, `department_packages`)
- `memory_snapshot.json`
- follow-up artifacts when follow-up answers are generated
- PDF export in German and English on demand

## Replaced Architecture Elements

| Old | New |
| --- | --- |
| `request_supervisor_revision` tool | Removed — Lead decides autonomously (CHG-03) |
| `supervisor.decide_revision()` call | Removed — department is autonomous (CHG-03) |
| State-machine speaker selector (`workflow_step`) | Guardrail-only selector, Lead drives workflow (CHG-04) |
| Mutable dict payload as working artifact | Explicit `TaskArtifact` / `TaskReviewArtifact` / `TaskDecisionArtifact` (CHG-01/CHG-05) |
| Hidden re-judging in `finalize_package` | Assembly from stored decisions only (CHG-07) |
| Shallow follow-up heuristics | Run brain rehydration from `department_run_states` (CHG-08) |
| Unguarded company facts in long-term memory | Scrubbed structural patterns only (CHG-09) |
