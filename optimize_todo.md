# Optimization Checklist

Status legend: `[ ]` open · `[~]` in progress · `[x]` done

---

## P0 — Architectural Risks (fix before scaling)

### Synthesis Consolidation
> **Decision B resolved**: AG2 SynthesisDepartment is the single authoritative
> synthesis path. The rule-based path becomes pre-processing input, not a
> parallel author. No merge in `pipeline_runner.py`.

- [ ] Rename `build_synthesis_from_memory()` → `build_synthesis_context()` — output becomes structured input for the AG2 synthesis chat, not a standalone synthesis
- [ ] Extend `SynthesisDepartmentAgent` to receive the context payload and produce a complete `Synthesis`-schema-compliant output
- [ ] Update `finalize_synthesis()` tool contract to require all fields of the `Synthesis` Pydantic model
- [ ] Remove the manual merge in `pipeline_runner.py` (lines 96–103) that patches AG2 output into rule-based output
- [ ] Add fallback path: if AG2 synthesis hits `max_round`, use `build_synthesis_context()` output directly with `generation_mode: "fallback"` — confidence is derived from input package strength, not hardcoded
- [ ] Ensure a single, traceable synthesis path from department packages → final synthesis payload

### Non-Deterministic GroupChat Control
> **Decision C resolved**: Custom Speaker Selector as deterministic workflow
> controller. State-machine per GroupChat type. `auto` only as unreachable
> fallback. No framework change needed — AG2 supports `speaker_selection_method=callable`.

- [ ] Implement Department GroupChat state-machine: `RESEARCH → REVIEW → DECIDE → (RETRY|NEXT|FINALIZE)` — custom callable returns next speaker based on `run_state`
- [ ] Implement Synthesis GroupChat state-machine: `READ → CRITIQUE → DECIDE → (BACK_REQUEST|FINALIZE)`
- [ ] Add workflow-step tracking inside `run_state` so the selector always knows the current phase
- [ ] Replace `speaker_selection_method="auto"` with the custom callable in both `lead.py` and `synthesis_department.py`
- [ ] Define a max-retry cap per task (currently implicit via `attempt < 2` in Supervisor) — make it explicit and configurable

### Task Contract Hardening (`use_cases.py`)
> **Decision A resolved**: `use_cases.py` becomes the canonical task-contract
> source. `LIQUISTO_STANDARD_SCOPE` remains business/prompt policy.
> `STANDARD_TASK_BACKLOG` becomes the orchestration specification.
>
> **Decision D resolved**: Contact tasks are conditional. `contact_discovery`
> runs only when Buyer produces prioritized firms. `contact_qualification`
> runs only when `contact_discovery` finds contacts.

Final task-contract shape:
```python
{
    "task_key": str,
    "label": str,
    "assignee": str,
    "target_section": str,           # reporting/assembly target
    "objective_template": str,
    "depends_on": list[str],         # control-flow deps (task_keys)
    "run_condition": str | None,     # None = mandatory
    "input_artifacts": list[str],    # upstream typed artifacts to consume
    "output_schema_key": str,        # Pydantic model name from schemas.py
    "validation_rules": list[dict],  # structured rules with class: core|supporting
}
```

- [ ] Migrate all 12 tasks in `STANDARD_TASK_BACKLOG` to the new contract shape
- [ ] Add `depends_on` per task (e.g., `contact_discovery` depends on `peer_companies` + `monetization_redeployment`)
- [ ] Add `run_condition` for conditional tasks: `contact_discovery` → `"buyer_department_has_prioritized_firms"`, `contact_qualification` → `"contact_discovery_completed"`
- [ ] Add `input_artifacts` per task to make data-flow explicit (e.g., `contact_discovery` consumes `["MarketNetwork"]`)
- [ ] Add `output_schema_key` per task pointing to a task-specific Pydantic sub-schema (**blocked by P2 sub-schema extraction** — must be done first or in parallel)
- [ ] Add `validation_rules` per task with `class: "core" | "supporting"` per rule
- [ ] Make `industry_hint` an explicit input-contract field per Assignment, not an implicitly inferred value passed loosely through `run_state`
- [ ] Update `task_router.py` to evaluate `depends_on` and `run_condition` before building assignments
- [ ] Remove `TASK_POINT_RULES` from `critic.py` — Critic reads rules from the contract

### Contact Department Tool Policy Gap
- [ ] Add `ContactResearcher`, `ContactCritic`, `ContactJudge`, `ContactCodingSpecialist` to `BASE_TOOL_POLICY` in `tool_policy.py`
- [ ] Add `ContactResearcher` task overrides for `contact_discovery` and `contact_qualification` in `TASK_TOOL_OVERRIDES`
- [ ] Verify that ContactResearcher actually receives `("search", "page_fetch", "llm_structured")` at runtime

---

## P1 — Quality & Correctness (directly affects output quality)

### Canonical Status & Confidence Vocabulary
Before implementing Critic/Judge changes, establish the shared vocabulary:

Task status (mutually exclusive):
- `accepted` — all `core` rules passed, evidence sufficient
- `degraded` — partial `core` evidence, usable with caveats
- `skipped` — `run_condition` not met, task was never executed
- `rejected` — task ran but produced no usable `core` evidence

Note: `conservative` (current codebase) is replaced by `degraded` or
`rejected` depending on whether any core evidence exists.
All references in `lead.py`, `pipeline_runner.py`, `DepartmentTaskResult`,
and UI must be migrated.

`skipped` vs `rejected` distinction:
- `skipped`: task did not run (e.g., Contact tasks when Buyer has no firms) — not a quality failure, just not applicable
- `rejected`: task ran, Judge found zero core evidence — a real quality failure that should be visible in reporting

Confidence scale (applies to packages and synthesis):
- `high` / `medium` / `low`

Generation mode (applies to synthesis only):
- `normal` — produced by AG2 SynthesisDepartment
- `fallback` — produced by `build_synthesis_context()` on AG2 timeout

Confidence and generation mode are orthogonal. A `fallback` synthesis
can still be `medium` confidence if the input packages were strong.

- [ ] Define status (`accepted | degraded | skipped | rejected`), confidence (`high | medium | low`), and generation_mode (`normal | fallback`) as Literal types or enums in `schemas.py`
- [ ] Migrate all `"conservative"` references to `"degraded"` or `"rejected"` across codebase
- [ ] Add `generation_mode` field to `Synthesis` schema
- [ ] Ensure `skipped` tasks produce no output artifact (clean absence, not empty placeholder)
- [ ] Ensure `rejected` tasks produce a minimal artifact with `open_questions` explaining the failure

### Critic → Generic Rule Evaluator
> **Decision E resolved**: Critic stays deterministic. No LLM. Rules come
> from the task contract, not from a parallel `TASK_POINT_RULES` dict.

- [ ] Refactor `CriticAgent.review()` to accept `validation_rules` from the task contract instead of looking up `TASK_POINT_RULES`
- [ ] Implement generic check evaluators: `non_placeholder`, `min_items`, `min_length` (extensible)
- [ ] Each rule carries `class: "core" | "supporting"` — Critic reports pass/fail per class
- [ ] Remove `TASK_POINT_RULES` dict from `critic.py` after migration
- [ ] Contact task rules are now defined in the contract — no separate addition needed

### Judge → Three-Level Deterministic Gate
> **Decision E resolved**: Judge stays deterministic. No LLM until contracts
> are stable. Three outcomes based on rule-class pass rates.

Judge decision → task status mapping:
- **accept** → status `accepted`: all `core` rules passed + at least one `supporting` passed
- **accept_degraded** → status `degraded`: at least one `core` rule passed, but not all → `confidence: "low"`, must generate `open_questions` from failed rules
- **reject** → status `rejected`: no `core` rule passed

`degraded` downstream semantics:
- Output flows into synthesis with `confidence: "low"`
- Failed rules become `open_questions` in the department package
- Downstream tasks may consume the artifact but synthesis must flag the weakness

- [ ] Implement three-outcome `JudgeAgent.decide()` reading `validation_rules` with `class` from the task contract
- [ ] Replace current no-op logic (`accept_conservative_output: True` always) with class-aware heuristic
- [ ] Map judge decisions to canonical task statuses: `accept→accepted`, `accept_degraded→degraded`, `reject→rejected`
- [ ] `skipped` is set by the task router when `run_condition` is not met — the Judge never produces `skipped`
- [ ] Ensure `degraded` packages carry `open_questions` derived from failed rules

### Industry Inference Is Too Narrow
- [ ] `infer_industry()` covers only 4 keyword groups — most companies will return `"n/v"`
- [ ] Option A: expand keyword list to cover 15–20 common industries
- [ ] Option B: replace with a single LLM call during intake (Supervisor already has homepage text)
- [ ] Propagate a reliable `industry_hint` to all downstream query builders — current fallback to `"n/v"` weakens every department's search quality

### Supervisor Routing Is Fragile
- [ ] `route_question()` uses flat keyword matching with no scoring or ranking
- [ ] Option A: add a priority/weight system so overlapping keywords resolve deterministically
- [ ] Option B: replace with a single LLM classification call (low cost, high accuracy)
- [ ] Add a fallback route when no keywords match (currently defaults to CompanyDepartment — is that always correct?)

---

## P2 — Schema Refactor & Domain Model Decisions

> Now that Decision A is resolved (`use_cases.py` is the canonical contract
> source with `output_schema_key` per task), this section has two jobs:
> (1) create task-specific sub-schemas so `output_schema_key` is a real type
> contract, and (2) decide whether existing unused domain models become those
> sub-schemas or get removed.
>
> **Execution dependency**: P0 Task Contract Hardening sets `output_schema_key`
> per task, but the referenced sub-schemas must exist first. Sub-schema
> extraction (below) must run before or in parallel with the P0 contract
> migration — not after it.

### Task-Specific Sub-Schemas
Current schemas are monolithic per section (e.g., `CompanyProfile` serves 3
tasks). `output_schema_key` needs a dedicated model per task.

- [ ] Extract `CompanyFundamentals` sub-schema from `CompanyProfile` (identity, offering, footprint, business model)
- [ ] `EconomicSituation` already exists as sub-model — verify it covers the `economic_commercial_situation` task contract
- [ ] Extract `ProductAssetScope` sub-schema from `CompanyProfile` (product classification, asset inventory)
- [ ] Verify `IndustryAnalysis` covers `market_situation` or extract a focused sub-schema
- [ ] Extract `RepurposingCircularity` and `AnalyticsSignals` sub-schemas from `IndustryAnalysis`
- [ ] Verify `MarketNetwork` covers `peer_companies` and `monetization_redeployment` or split
- [ ] Create `ContactDiscoveryResult` sub-schema from `ContactIntelligenceSection`
- [ ] Create `ContactQualificationResult` sub-schema from `ContactIntelligenceSection`
- [ ] Define assembly convention: how sub-schemas merge into section-level models for `PipelineData`

### Schema Registry
`output_schema_key` is a string in the task contract. To avoid drift between
string names and actual Pydantic classes, a central registry must resolve them.

- [ ] Create `src/models/registry.py` with a `SCHEMA_REGISTRY: dict[str, type[BaseModel]]` mapping `output_schema_key` strings to Pydantic classes
- [ ] All runtime code that needs to validate or instantiate a task output resolves through the registry, not through ad-hoc imports or string matching
- [ ] Add a startup check (in `preflight.py` or test) that verifies every `output_schema_key` in `STANDARD_TASK_BACKLOG` exists in the registry

### Unused Domain Models — Keep, Promote, or Remove?
> Evaluate each against the new sub-schema needs. Some may map directly to
> task-level output types; others are genuinely dead.

- [ ] `src/domain/briefing.py` — `Briefing`: does it map to any task output? If not, remove
- [ ] `src/domain/findings.py` — `Finding`: potential base for `validation_rules` result type?
- [ ] `src/domain/evidence.py` — `EvidenceRecord`: potential source-tracking model for sub-schemas?
- [ ] `src/domain/decisions.py` — `OpportunityAssessment`: overlaps with `Synthesis` — likely remove
- [ ] `src/domain/buyers.py` — `BuyerPath`: candidate for `monetization_redeployment` output type?
- [ ] `src/domain/market.py` — `MarketSignal`: candidate for `market_situation` output type?
- [ ] Final decision per model after sub-schema design is complete

### Unused Agent Stubs — Assign Responsibility or Remove?
- [ ] `src/agents/strategic_analyst.py` — `CrossDomainStrategicAnalystAgent` has only `__init__`, never called at runtime
- [ ] `src/agents/report_writer.py` — `ReportWriterAgent` has only `__init__`, no `run()` method; report is built in `pipeline_runner.py`
- [ ] **Decision required**: give these agents real responsibilities, or remove them and keep the logic where it currently lives

### Backward-Compat Shim
- [ ] `src/tools/research.py` — re-exports with underscore prefixes, not imported anywhere
- [ ] Remove unless an external consumer depends on it

---

## P3 — Robustness & Error Handling

### AG2 GroupChat Error Propagation
- [ ] Wrap tool closures in `lead.py` with try/except so a single tool failure doesn't crash the entire department run
- [ ] Return a structured error JSON from failed tool calls instead of letting exceptions propagate through GroupChatManager
- [ ] Log tool-call failures to `run_state` so they appear in the department package's `open_questions`

### LLM Fallback Consistency
- [ ] `worker.py` has LLM fallback logic, but `synthesis_department.py` has none — if the AG2 synthesis chat fails, the fallback in `pipeline_runner.py` is a generic dict
- [ ] Standardize: every AG2 group should produce a valid typed output even on total failure

### File I/O Safety
- [ ] `long_term_store.py` does read-modify-write without locking — concurrent runs could corrupt the JSON file
- [ ] Option A: add file locking (e.g., `filelock` package)
- [ ] Option B: switch to SQLite for long-term memory

---

## P4 — Test Coverage Gaps

### Critic & Judge (post-refactor)
- [ ] Add unit test for `CriticAgent.review()` with `validation_rules` from contract — verify per-check-type evaluation (`non_placeholder`, `min_items`, `min_length`)
- [ ] Add unit test verifying `core` vs `supporting` classification in Critic output
- [ ] Add unit test for `JudgeAgent.decide()` — verify three-outcome heuristic: `accept`, `accept_degraded`, `reject` based on `core`/`supporting` pass rates
- [ ] Add unit test verifying judge decision → task status mapping (`accepted`, `degraded`, `rejected`)
- [ ] Add unit test verifying `skipped` is set by task router (not Judge) when `run_condition` is unmet

### Routing & Follow-up
- [ ] Add unit test for `SupervisorAgent.route_question()` — verify routing for each department keyword set
- [ ] Add unit test for `follow_up.py::answer_follow_up()` — verify routing and answer assembly per department

### Integration
- [ ] Add integration test for a single department AG2 GroupChat run (monkeypatched LLM, real AG2 flow)
- [ ] Add test for Contact Department end-to-end (currently zero test coverage)
- [ ] Add test for `SynthesisDepartmentAgent.run()` with mocked department packages
- [ ] Add test for fallback package assembly when `max_round` is hit
- [ ] Add test verifying `run_condition` evaluation skips Contact tasks when Buyer has no prioritized firms

---

## P5 — Performance & Cost Optimization

### Reduce Unnecessary LLM Calls
- [ ] `finalize_package()` in `lead.py` calls `self.critic.review()` again for every task — this is a second full review pass that duplicates work already done during the chat
- [ ] Evaluate caching the last review result and reusing it in `finalize_package()` instead of re-running

### Search Efficiency
- [ ] Worker caches search results per instance, but each department creates a new `ResearchWorker` — cache is not shared across departments
- [ ] Evaluate a run-level search cache passed via `run_state` or `memory_store`

### Token Budget Awareness
- [ ] No token budget enforcement exists — a verbose LLM response can blow through costs without any guardrail
- [ ] Add a soft token budget per department (warn) and a hard cap per run (abort)

---

## P6 — Future Architecture Considerations

### Parallel Department Execution
- [ ] Current: strictly sequential (Company → Market → Buyer → Contact)
- [ ] Company and Market have no data dependency — they could run in parallel
- [ ] Contact depends on Buyer output — must remain sequential after Buyer
- [ ] Evaluate `asyncio` or thread-pool execution for independent departments

### Structured Output Mode
- [ ] Worker uses `response_format={"type": "json_object"}` — consider migrating to OpenAI structured outputs with Pydantic schema enforcement for tighter contracts

### Observability
- [ ] No structured logging — all runtime events go through `on_message` callback as flat dicts
- [ ] Add run-level structured logging (e.g., JSON lines) for debugging failed runs without reading full chat histories
- [ ] Add per-department timing metrics to `run_meta.json`

---

## Resolved Design Decisions

All five governance decisions have been resolved. They are documented here
for traceability and referenced inline in the P0/P1/P2 blocks above.

**A. `use_cases.py` is the canonical contract source.** ✅
`LIQUISTO_STANDARD_SCOPE` remains business/prompt policy.
`STANDARD_TASK_BACKLOG` becomes the orchestration specification with
`depends_on`, `run_condition`, `input_artifacts`, `output_schema_key`,
and `validation_rules` (with `class: core|supporting`).

**B. AG2 SynthesisDepartment is the single authoritative synthesis path.** ✅
`build_synthesis_from_memory()` becomes `build_synthesis_context()` —
pre-processing input for the AG2 chat, not a parallel author.
No merge in `pipeline_runner.py`. Fallback on AG2 timeout uses
`generation_mode: "fallback"` with confidence derived from input packages.

**C. Custom Speaker Selector as deterministic workflow controller.** ✅
State-machine per GroupChat type. Department: `RESEARCH → REVIEW →
DECIDE → (RETRY|NEXT|FINALIZE)`. Synthesis: `READ → CRITIQUE → DECIDE →
(BACK_REQUEST|FINALIZE)`. `auto` only as unreachable safety fallback.

**D. Contact tasks are conditional.** ✅
`contact_discovery`: `run_condition: "buyer_department_has_prioritized_firms"`.
`contact_qualification`: `run_condition: "contact_discovery_completed"`.
Modelled via `run_condition` in the task contract.

**E. Critic and Judge stay deterministic. No LLM before stable contracts.** ✅
Critic becomes generic rule evaluator reading `validation_rules` from
the task contract. Judge uses three-level heuristic (accept / accept
degraded / reject) based on `core` vs `supporting` rule-class pass rates.
`skipped` is set by the task router, not the Judge.
`TASK_POINT_RULES` in `critic.py` will be removed after migration.
