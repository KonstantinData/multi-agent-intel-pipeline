# Runtime Step 1: Runner Init + Supervisor Brief

This file explains the step shown in `docs/drawio/runtime_step1.drawio` in a precise, code-level way.

The source of truth for this step is `src/pipeline_runner.py::run_pipeline(...)`.

## Goal of Step 1

Starting from minimal input (`company_name`, `web_domain`), Step 1 prepares the live runtime state required for department routing:

1. create a run id and run directory path
2. validate the intake contract
3. instantiate runtime agents
4. initialize long-term memory access and run-scoped context
5. retrieve process-pattern strategies for the normalized domain
6. build the `SupervisorBrief`
7. initialize the question registry and answer matrix
8. emit the first Supervisor runtime message

Step 1 ends immediately before this call:

```python
run_supervisor_loop(
    brief=brief,
    run_context=run_context,
    agents=agents,
    on_message=on_message,
)
```

## Involved Scripts

- `src/pipeline_runner.py` -> `run_pipeline(...)`
- `src/agents/runtime_factory.py` -> `create_runtime_agents(...)`
- `src/agents/supervisor.py` -> `SupervisorAgent.build_intake_brief(...)`
- `src/domain/intake.py` -> `IntakeRequest`, `SupervisorBrief`
- `src/memory/long_term_store.py` -> `FileLongTermMemoryStore`
- `src/memory/backfill.py` -> optional `backfill_long_term_memory_from_runs(...)`
- `src/memory/retrieval.py` -> `retrieve_strategies(...)`
- `src/memory/consolidation.py` -> `RETRIEVABLE_ROLE_ORDER`
- `src/research/normalize.py` -> `normalize_domain(...)`, `homepage_url(...)`
- `src/research/tools.py` -> `build_company_research(...)`
- `src/research/fetch.py` -> `fetch_website_snapshot(...)`
- `src/research/extract.py` -> `infer_company_identity(...)`, `infer_industry(...)`, `summarize_visible_text(...)`
- `src/orchestration/meeting_questions.py` -> `build_question_registry(...)`, `build_initial_answer_matrix(...)`
- `src/orchestration/supervisor_loop.py` -> `emit_message(...)`, next-step `run_supervisor_loop(...)`

## Exact Flow

1. **Input enters the runner**
   - `run_pipeline(company_name, web_domain, on_message=...)` is called.
   - `start_time = perf_counter()` is recorded.
   - `run_id = _timestamp_run_id()` is created.
   - `run_dir = resolve_run_dir(run_id, runs_root=RUNS_DIR)` resolves the artifact directory path.

2. **Intake contract is validated**
   - `IntakeRequest(company_name=company_name, web_domain=web_domain)` is instantiated.
   - `language` defaults through the intake model.
   - If intake validation fails, Step 1 returns immediately with:
     - `status = "failed"`
     - empty `messages`
     - empty `pipeline_data`
     - a minimal `run_context.intake`
     - the validation error string

3. **Runtime agents are created**
   - `agents = create_runtime_agents()` is called.
   - The returned runtime map contains:
     - `supervisor`
     - `departments`
     - `synthesis`
     - `report_writer`
   - This happens before the Supervisor brief is built.

4. **Memory store and RunContext are initialized**
   - `memory_store = FileLongTermMemoryStore(LONG_TERM_MEMORY_PATH)` opens the process-pattern store.
   - Backfill from previous run artifacts is opt-in through `LIQUISTO_BACKFILL_LONG_TERM_MEMORY`.
   - If enabled, `backfill_long_term_memory_from_runs(memory_store=memory_store, runs_dir=RUNS_DIR)` updates the store.
   - `run_context = RunContext(...)` is created with:
     - `run_id`
     - `company_name`
     - `web_domain`
     - intake `language`

5. **Process strategies are retrieved**
   - The domain is normalized for retrieval:
     - `normalize_domain(web_domain)`
   - General strategies are loaded:
     - `retrieve_strategies(memory_store, domain=..., limit=5)`
   - Role-specific strategies are loaded for every role in `RETRIEVABLE_ROLE_ORDER`:
     - `retrieve_strategies(memory_store, domain=..., role=role, limit=3)`
   - These are process patterns only. Company-specific run facts stay in run-scoped memory.

6. **Step-1 runtime containers are prepared**
   - `messages: list[dict[str, Any]] = []`
   - `budget_tracker = PhaseBudgetTracker()`
   - The first budget measurement happens later, after the first department pass.

7. **Supervisor builds the intake brief**
   - `brief, supervisor_message = agents["supervisor"].build_intake_brief(intake)` is called.
   - Inside `SupervisorAgent.build_intake_brief(...)`, the Supervisor calls:
     - `build_company_research(intake.web_domain, intake.company_name)`
   - `build_company_research(...)` performs:
     - `normalize_domain(...)`
     - `homepage_url(...)`
     - `fetch_website_snapshot(...)`
     - `infer_company_identity(...)`
     - `summarize_visible_text(...)`
   - The Supervisor then derives:
     - `industry_hint = infer_industry(title, description, summary)`

8. **SupervisorBrief is assembled**
   - `SupervisorBrief` includes, among others:
     - submitted company name and web domain
     - verified company name and legal name
     - name confidence
     - website reachability
     - homepage URL
     - page title and meta description
     - raw homepage excerpt
     - normalized domain
     - industry hint
     - observations
     - initial owned source
     - fetch error fields

9. **Serializable Supervisor message is produced**
   - `supervisor_message` has this shape:

```python
{
    "section": "supervisor_brief",
    "payload": asdict(brief),
    "status": "ready_for_department_routing",
}
```

10. **RunContext is seeded for routing**
    - `run_context.supervisor_brief = supervisor_message["payload"]`
    - `run_context.question_registry = build_question_registry()`
    - `run_context.answer_matrix = build_initial_answer_matrix()`

11. **First runtime message is emitted**
    - `emit_message(...)` emits the Supervisor message into `messages`.
    - The emitted event is also sent through `on_message` when a UI hook is provided.

12. **Step 1 hands off to Step 2**
    - The next statement is the department routing call:
      - `run_supervisor_loop(brief, run_context, agents, on_message)`
    - This is the Step-1 boundary.

## Output of Step 1

At the boundary before `run_supervisor_loop(...)`, these live objects exist:

- `brief: SupervisorBrief`
- `supervisor_message: dict`
- `agents: dict[str, object]`
- `run_context: RunContext`
- `messages` with the initial Supervisor event
- `budget_tracker`

The `run_context` already contains:

- normalized strategy retrieval results
- role-specific strategy retrieval results
- `supervisor_brief`
- `question_registry`
- `answer_matrix`

## What Step 1 Explicitly Does Not Do

- no department execution
- no department package admission
- no first-pass checkpoint
- no auto-close follow-up
- no synthesis
- no meeting-readiness finalization
- no report assembly
- no final export

These begin after Step 1, starting with `run_supervisor_loop(...)`.
