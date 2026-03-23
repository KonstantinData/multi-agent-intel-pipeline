# Optimization Checklist

Status legend: `[ ]` open · `[~]` in progress · `[x]` done

---

## P0 — Architectural Risks (fix before scaling)

### Synthesis Consolidation
- [ ] Decide: AG2 SynthesisDepartment as primary, `build_synthesis_from_memory()` as deterministic fallback, or remove one
- [ ] Remove the manual merge in `pipeline_runner.py` (lines 96–103) that patches AG2 output into rule-based output
- [ ] Ensure a single, traceable synthesis path from department packages → final synthesis payload

### Non-Deterministic GroupChat Control
- [ ] Evaluate replacing `speaker_selection_method="auto"` with a custom selector that enforces the Lead→Researcher→Critic→(Revision)→Lead workflow
- [ ] Add workflow-step tracking inside `run_state` so the Lead can detect when the chat deviates from the expected sequence
- [ ] Define a max-retry cap per task (currently implicit via `attempt < 2` in Supervisor) — make it explicit and configurable

### Task Contract Hardening (`use_cases.py`)
- [ ] Decide: does `use_cases.py` remain a business-definition file, or become the canonical task-contract source for orchestration?
- [ ] Add `depends_on` field per task to make implicit ordering explicit (e.g., `contact_discovery` depends on `peer_companies` + `monetization_redeployment`)
- [ ] Add `run_condition` for conditional tasks — `contact_discovery` and `contact_qualification` may only be meaningful after Buyer produces prioritized firms
- [ ] Add `output_schema_key` per task pointing to the Pydantic model that validates the task output
- [ ] Add `validation_rules` per task (minimum evidence thresholds, required fields) so Critic rules derive from the contract, not from a parallel hardcoded dict
- [ ] Distinguish mandatory vs conditional tasks in `STANDARD_TASK_BACKLOG`
- [ ] Make `industry_hint` an explicit input-contract field per Assignment, not an implicitly inferred value passed loosely through `run_state`

### Contact Department Tool Policy Gap
- [ ] Add `ContactResearcher`, `ContactCritic`, `ContactJudge`, `ContactCodingSpecialist` to `BASE_TOOL_POLICY` in `tool_policy.py`
- [ ] Add `ContactResearcher` task overrides for `contact_discovery` and `contact_qualification` in `TASK_TOOL_OVERRIDES`
- [ ] Verify that ContactResearcher actually receives `("search", "page_fetch", "llm_structured")` at runtime

---

## P1 — Quality & Correctness (directly affects output quality)

### Critic Blind Spots
- [ ] Add `TASK_POINT_RULES` for `contact_discovery` (e.g., at least one contact with `name != "n/v"`, at least one `firma != "n/v"`)
- [ ] Add `TASK_POINT_RULES` for `contact_qualification` (e.g., at least one contact with `senioritaet != "n/v"`, `suggested_outreach_angle != "n/v"`)
- [ ] Evaluate adding a lightweight LLM-based quality score alongside the rule-based check (hybrid critic)
- [ ] Consider checking payload values beyond `!= "n/v"` — e.g., minimum string length, no placeholder patterns

### Judge Is a No-Op
- [ ] Decide: should the Judge use LLM reasoning, or remain a deterministic "accept conservative" gate?
- [ ] If deterministic: at minimum, differentiate between "partial evidence exists" and "no evidence at all"
- [ ] If LLM-based: define the input contract (critic issues + payload snapshot) and output schema

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

## P2 — Architecture Decisions: Domain Models & Agent Stubs

> **Do not treat this as cleanup.** These are architecture decisions that depend on
> the P0 contract-hardening work. If `use_cases.py` becomes the canonical contract
> source with typed `output_schema_key` per task, some of these "dead" models may
> become the correct canonical runtime artefacts. Decide P0 first, then revisit.

### Unused Domain Models — Keep or Promote?
- [ ] `src/domain/briefing.py` — `Briefing` class not imported anywhere
- [ ] `src/domain/findings.py` — `Finding` class not imported anywhere
- [ ] `src/domain/evidence.py` — `EvidenceRecord` class not imported anywhere
- [ ] `src/domain/decisions.py` — `OpportunityAssessment` class not imported anywhere
- [ ] `src/domain/buyers.py` — `BuyerPath` class not imported anywhere
- [ ] `src/domain/market.py` — `MarketSignal` class not imported anywhere
- [ ] **Decision required**: remove all six, or promote them to typed runtime artefacts referenced by task contracts. Do not delete before the contract model is settled.

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

- [ ] Add unit test for `CriticAgent.review()` — verify approval/rejection logic for each `TASK_POINT_RULES` entry
- [ ] Add unit test for `JudgeAgent.decide()` — currently trivial, but should be tested before adding real logic
- [ ] Add unit test for `SupervisorAgent.route_question()` — verify routing for each department keyword set
- [ ] Add unit test for `follow_up.py::answer_follow_up()` — verify routing and answer assembly per department
- [ ] Add integration test for a single department AG2 GroupChat run (monkeypatched LLM, real AG2 flow)
- [ ] Add test for Contact Department end-to-end (currently zero test coverage)
- [ ] Add test for `SynthesisDepartmentAgent.run()` with mocked department packages
- [ ] Add test for fallback package assembly when `max_round` is hit

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

## Open Design Decisions

These must be resolved before or during P0/P1 execution. They are not tasks
themselves but governance choices that determine how the tasks above are
implemented.

**A. Is `use_cases.py` business policy or canonical contract source?**
Solange das offen ist, repariert man Runtime-Logik downstream, ohne den Typ
des Systems upstream festzuziehen. `STANDARD_TASK_BACKLOG` ist derzeit eher
ein Backlog als eine Orchestrierungsspezifikation.

**B. What is the single authoritative synthesis path?**
The To-do names the right question (Synthesis Consolidation). But this must be
treated as a governance decision, not a technical cleanup. A final synthesis
payload needs exactly one traceable authority path.

**C. How strict should AG2 determinism be?**
Custom speaker selector is a good start. But the real question is: do we want
a true workflow controller, or just a slightly more controlled chat? If
workflow, then `auto` plus run-state hints will not be enough long-term.

**D. Are Contact tasks mandatory or conditional?**
In the current backlog they appear canonical, but functionally they are
downstream of Buyer results. This distinction must be modelled in
`use_cases.py` via `run_condition`.

**E. Should Judge and Critic be deterministic or hybrid?**
Avoid putting LLM intelligence into the Judge before input contracts and
task validation are properly typed. Otherwise uncertainty just shifts to a
later layer.
