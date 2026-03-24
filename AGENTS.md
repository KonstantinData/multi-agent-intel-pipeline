# AGENTS.md (Updated Draft)

## Purpose of this file

This file is a compact orientation guide for developers working in this repository.
It summarizes the **current** runtime model, agent roles, memory boundaries, and
where to find the canonical architecture documentation.

It is intentionally brief. For full details, use:
- `README.md`
- `docs/target_runtime_architecture.md`
- `src/orchestration/contracts.py`

---

## Project overview

Liquisto Department Runtime is a multi-agent intelligence pipeline that builds
pre-meeting briefings from `company_name` and `web_domain`.

The system uses **bounded AG2 GroupChats inside domain departments**, coordinated
by a single **Supervisor control plane**.

Top-level runtime modes:
1. Initial briefing mode
2. Run-based follow-up mode

---

## Current runtime model

### Control Plane — Supervisor

The `Supervisor` is the single control-plane role.

Responsibilities:
- normalize intake
- create the intake brief
- translate the Liquisto standard scope into department assignments
- coordinate department execution order
- accept completed department packages
- route follow-up questions by `run_id`

Non-responsibilities:
- no domain-level fact interpretation
- no domain-level evidence review
- no intra-department retry decisions
- no intra-department judge decisions

The Supervisor **does not participate in internal department retry/review loops**.
Departments operate autonomously inside their assigned contract.

### Research Plane — Domain departments

The research plane is split into four bounded domain departments:
- Company Department
- Market Department
- Buyer Department
- Contact Department

Each department is a real AG2 GroupChat with bounded multi-agent collaboration.
The output is **not** raw chat. The output is a validated `DepartmentPackage`.

### Synthesis Plane

After domain departments complete, the Synthesis Department performs cross-domain
interpretation and produces the final `synthesis` section.

---

## Department autonomy model

The architecture follows a **fixed contract, autonomous execution** model:

- the Supervisor provides the required questions, scope, and report expectations
- the Department Lead operationalizes that contract
- the department group chooses how to execute internally
- the group may retry, critique, escalate, adapt strategy, and use coding support
- the department must continue until required items are:
  - answered with sufficient support, or
  - explicitly unresolved with justified evidence gaps

The department group is therefore **bounded but autonomous**.

---

## Department roles

Each department group consists of five `ConversableAgent` roles:

| Role | Primary responsibility |
| --- | --- |
| Department Lead / Analyst | operationalize the contract, steer the group, enforce completion, hand off the department package |
| Researcher | gather evidence, adapt search strategy, produce task-level findings |
| Critic | review evidence quality, identify gaps and defects, trigger stronger follow-up work |
| Judge | decide borderline cases using decision principles and conflict-resolution rules |
| Coding Specialist | support parsing, extraction, query refinement, debugging, and structured recovery tactics |

Notes:
- The Lead is **not** just an administrator; the Lead owns completion.
- The Judge and Coding Specialist are bounded support roles, not independent control-plane roles.
- There is no `request_supervisor_revision` tool in department execution.

---

## Runtime artifacts

Department execution is artifact-based.

The core runtime contracts live in `src/orchestration/contracts.py`:
- `DepartmentRunState`
- `TaskArtifact`
- `TaskReviewArtifact`
- `TaskDecisionArtifact`

High-level lifecycle:
1. Research work produces a `TaskArtifact`
2. Critique produces a `TaskReviewArtifact`
3. Escalation or acceptance produces a `TaskDecisionArtifact`
4. Package finalization assembles output from stored artifacts and decisions

This means the authoritative department state is the **artifact history**, not an
implicit Python micro-workflow.

---

## Selector model

The department speaker selector is **guardrail-only**.
It is not a hidden workflow engine.

Its job is to keep the AG2 conversation safe and well-routed, for example:
- route tool calls to the executor
- return executor output to the Lead
- prevent non-Lead text-only loops
- route termination correctly

Beyond those guardrails, workflow ownership sits with the **Lead**, which directs
other agents explicitly through messages and the task contract.

---

## Memory model

### Run Brain

The Run Brain is **case-specific** and persisted by `run_id`.
It is stored in short-term run memory and exported with the run artifacts.

It may contain:
- task artifacts
- review artifacts
- decision artifacts
- evidence
- notes
- open questions
- rejected paths
- strategy changes
- judge escalations
- coding-support usage
- department workspaces
- final department packages

This run-specific memory is reloaded for follow-up.

### Long-Term Process Brain

The long-term memory stores **process patterns only**.
It must not store company-specific or customer-specific facts.

Allowed examples:
- search/query patterns
- critique heuristics
- escalation principles
- completion patterns
- parsing/extraction/debugging tactics

Disallowed examples:
- target-company facts
- customer/domain-specific evidence
- run-specific conclusions as reusable truth

The long-term store must only retain scrubbed structural patterns.

---

## Follow-up model

Follow-up starts from a stored `run_id`.

High-level flow:
1. load run artifacts
2. rehydrate the run brain
3. route the question to the appropriate department answer path
4. answer from stored run evidence first
5. trigger additional research only if unresolved gaps remain

Evidence priority for follow-up:
1. primary: run-brain artifacts
2. secondary: `pipeline_data`
3. fallback: department packages

Follow-up is therefore grounded in the stored run state, not only in shallow
heuristics.

---

## Testing model

The repository separates lighter architecture/contract testing from heavier
runtime/integration testing.

Intended layers:
- **architecture / contract tests**: should run without AG2 runtime dependencies where possible
- **runtime / integration tests**: may require AG2/autogen and fuller wiring

When working on tests:
- avoid importing runtime-heavy modules from pure architecture tests unless required
- prefer extracting dependency-light helpers and contracts
- keep architecture tests fast and isolated

---

## Key file map

| File | Purpose |
| --- | --- |
| `src/pipeline_runner.py` | public runtime entrypoint for UI and CLI |
| `src/orchestration/supervisor_loop.py` | supervisor-controlled department routing loop |
| `src/orchestration/department_runtime.py` | bounded department group runtime |
| `src/orchestration/synthesis_runtime.py` | synthesis department runtime |
| `src/orchestration/follow_up.py` | run loading, follow-up routing, persisted follow-up answers |
| `src/orchestration/contracts.py` | typed runtime contracts and department artifact state |
| `src/orchestration/speaker_selector.py` | guardrail-only selector for department group chats |
| `src/agents/lead.py` | department lead lifecycle and package finalization |
| `src/memory/short_term_store.py` | run-scoped memory including department run states |
| `src/memory/consolidation.py` | process-pattern consolidation into long-term memory |
| `docs/target_runtime_architecture.md` | canonical detailed runtime architecture reference |

---

## Canonical documentation

Use these files as the primary source of truth:
- `README.md`
- `docs/target_runtime_architecture.md`
- `src/orchestration/contracts.py`

If this file ever disagrees with those sources or with the executable code,
prefer:
1. executable code
2. `docs/target_runtime_architecture.md`
3. `README.md`
4. this file

---

## Maintenance rule

`AGENTS.md` should stay short.
Do not turn it into a second architecture handbook.

When the runtime model changes, update this file only at the level of:
- control-plane boundaries
- department autonomy
- role definitions
- artifact model
- memory boundaries
- follow-up behavior
- test layering
