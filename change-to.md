# change-to.md

# Runtime Refactor Change Plan

This document defines the implementation plan for moving the current department runtime from a **Python-micro-orchestrated AG2 execution** to a **contract-driven, execution-autonomous department group**.

It is written as a working checklist so the change can be tracked block by block.

---

## Objective

Keep the existing business intent and top-level report structure, but change the implementation so that:

- the **Supervisor** provides the department contract, not the internal work choreography
- the **Department group** works autonomously inside that contract
- the **Lead** owns completion and package handoff
- the **Researcher / Critic / Judge / Coding Specialist** collaborate as a real bounded AG2 group
- the **run memory** stores case-specific working knowledge for later follow-up by `run_id`
- the **long-term memory** stores only reusable process patterns, never customer-/run-specific facts

---

## Target operating model

### Fixed from Supervisor to Department Lead

- mandatory questions / expected information scope
- report section / output schema requirements
- quality expectations
- non-optional completion requirements

### Autonomous inside the Department

- task ordering
- search strategy selection
- strategy changes after weak results
- critique / retry / escalation decisions
- coding support usage
- judge usage for genuine decision conflicts
- completion management until all mandatory questions are either:
  - answered with sufficient support, or
  - explicitly marked as unresolved with a justified evidence gap

### Memory separation

#### Run memory
Case-specific and persistent per `run_id`:
- evidence gathered
- notes
- rejected paths
- open questions
- critique comments
- strategy changes
- task-level decisions
- department conversations / execution trace

#### Long-term process memory
Reusable and non-case-specific only:
- search heuristics
- refinement patterns
- critique heuristics
- judge conflict classes
- judge decision principles
- coding tactics
- delegation / completion patterns
- successful process recipes and anti-patterns

No company-specific facts, no customer-specific evidence, no run-specific outcomes.

---

## Implementation rules

- Do **not** change the business questions asked by the pipeline.
- Do **not** break the final report schema.
- Do **not** remove the ability to replay and inspect a run by `run_id`.
- Do **not** persist run/customer facts into long-term memory.
- Prefer additive refactors and explicit artifacts over hidden side effects.
- Avoid introducing another implicit orchestration layer while removing the current one.

---

## Suggested delivery order

The blocks below are ordered by dependency. The safest sequence is:

1. CHG-00 baseline + safety rails
2. CHG-01 runtime contracts and state objects
3. CHG-02 memory split and persistence model
4. CHG-03 remove Supervisor from internal department loop
5. CHG-04 reduce selector to guardrails only
6. CHG-05 convert task flow to artifact-based execution
7. CHG-06 rework Lead / role prompts for autonomous group behavior
8. CHG-07 package finalization from stored decisions
9. CHG-08 follow-up rehydration from run brain
10. CHG-09 role brains and consolidation rules
11. CHG-10 tests, migration checks, documentation

---

# Change blocks

## CHG-00 — Baseline, safety rails, inventory

### Goal
Create a clean implementation baseline before runtime behavior changes.

### Files likely touched
- `change-to.md`
- `docs/target_runtime_architecture.md`
- `docs/updated_runtime_architecture.drawio` or new runtime docs
- `test_integration.py`
- `test_pipeline.py`
- `test_contracts.py`

### Checklist
- [x] Freeze current expected runtime behavior in notes / docs.
- [x] Record current department flow assumptions from:
  - [x] `src/agents/lead.py`
  - [x] `src/orchestration/speaker_selector.py`
  - [x] `src/orchestration/supervisor_loop.py`
  - [x] `src/orchestration/department_runtime.py`
- [x] Add or update tests that protect the current report schema and export shape.
- [x] Add a test fixture for a representative `run_id` artifact directory.
- [x] Confirm which current outputs must remain backward-compatible.

### Acceptance check
- [x] Existing pipeline still runs before refactor starts.
- [x] Baseline tests pass.
- [x] Team can compare pre-/post-refactor outputs on the same sample run.

### Implementation notes
Baseline confirmed via `test_contracts.py` (38 tests). `DepartmentPackage`, `PipelineData`, `FollowUpAnswer` schemas preserved as backward-compatibility contract throughout the refactor.

---

## CHG-01 — Introduce explicit runtime contracts and state objects

### Goal
Replace stringly-typed hidden orchestration with explicit runtime structures.

### Why
Today, the runtime is largely driven by shared mutable dictionaries and `workflow_step`. That is too implicit for the target model.

### Files likely touched
- `src/models/schemas.py`
- `src/orchestration/department_runtime.py`
- `src/agents/lead.py`
- `src/orchestration/speaker_selector.py`
- optionally new files under `src/orchestration/` or `src/models/`

### Design tasks
- [x] Define explicit department runtime objects:
  - [x] `DepartmentRunState`
  - [x] `TaskArtifact`
  - [x] `TaskReviewArtifact`
  - [x] `TaskDecisionArtifact`
- [x] Define terminal / non-terminal task states.
- [x] Define allowed task decision outcomes:
  - [x] `accepted`
  - [x] `accepted_degraded`
  - [x] `reject`
  - [x] `needs_coding_support`
  - [x] `closed_unresolved`

### Implementation tasks
- [x] Introduce typed objects without yet changing all runtime logic.
- [x] Create adapters so current code can read/write through the new structures.
- [x] Minimize raw dict mutation in `lead.py`.
- [x] Mark `workflow_step` as deprecated — replaced by artifact-driven Lead control.

### Acceptance check
- [x] Department runtime state can be serialized.
- [x] Core runtime decisions can be expressed without relying on magic strings.

### Implementation notes
New file: `src/orchestration/contracts.py`. Defines `TaskDecisionOutcome` Literal, `TERMINAL_OUTCOMES`, `NON_TERMINAL_OUTCOMES`, `OUTCOME_TO_TASK_STATUS`. `DepartmentRunState` has backward-compat flat views (`task_results`, `last_reviews`). All dataclasses serialize via `to_dict()`. 38 contract tests pass.

---

## CHG-02 — Split memory into run brain and long-term process brain

### Goal
Make the memory model match the required separation:
- run-specific working knowledge
- process-only long-term learning

### Files likely touched
- `src/memory/short_term_store.py`
- `src/memory/long_term_store.py`
- `src/memory/consolidation.py`
- `src/memory/models.py`
- `src/memory/policies.py`
- `src/pipeline_runner.py`
- `src/exporters/json_export.py`

### Checklist
- [x] Store department run states per run (`department_run_states` in `ShortTermMemoryStore`).
- [x] `snapshot()` includes `department_run_states` key.
- [x] `record_department_run_state(department, run_state_dict)` method added.
- [x] Consolidation emits only process-safe patterns (scrubbed of company identifiers).
- [x] `domain` field set to `""` in all patterns — never stores company/domain name.

### Acceptance check
- [x] A full run brain can be reloaded without the original live process.
- [x] Long-term memory contains no company-specific facts.
- [x] Consolidation produces process patterns only.

### Implementation notes
`src/memory/short_term_store.py` extended with `department_run_states` dict. `src/memory/consolidation.py` rewritten: `_scrub_company_from_query()` strips domains/quoted names/legal suffixes; `_is_process_safe_query()` validates min length + substantive word; `domain` always `""`. Emits structural, critic, judge, coding, and retry patterns.

---

## CHG-03 — Remove Supervisor from the internal department work loop

### Goal
Keep the Supervisor as control-plane owner, but remove it from intra-department retry decisions.

### Files likely touched
- `src/agents/lead.py`
- `src/agents/supervisor.py`
- `src/orchestration/supervisor_loop.py`
- `src/orchestration/department_runtime.py`

### Checklist
- [x] Remove `request_supervisor_revision(...)` from the department group runtime path.
- [x] Remove direct revision callbacks from Lead tools.
- [x] Supervisor responsibilities limited to: brief building, routing assignments, accepting packages, routing follow-up.
- [x] Retry authorization moved into the department (Lead prompt encodes `MAX_TASK_RETRIES` policy).
- [x] Coding-specialist authorization moved into department logic.
- [x] Judge escalation decision moved into department logic.

### Acceptance check
- [x] Department completes critique → retry → coding support → judge escalation without Supervisor intervention.
- [x] Supervisor sees only contract handoff and final package return.

### Implementation notes
`request_supervisor_revision` removed from `lead.py` tool registration and logic. `supervisor=None` default in `DepartmentRuntime.run()` and `DepartmentLeadAgent.run()`. `supervisor_loop.py` updated to omit supervisor from both parallel and sequential department calls. Warning logged if `supervisor` is passed to Lead (CHG-03 guard).

---

## CHG-04 — Reduce the selector to runtime guardrails, not workflow choreography

### Goal
Allow the AG2 group to work autonomously while keeping loop safety and sane turn routing.

### Files likely touched
- `src/orchestration/speaker_selector.py`
- `src/agents/lead.py`

### Checklist
- [x] Remove hard-coded step sequencing based on `workflow_step`.
- [x] Selector has exactly 4 guardrails: tool_calls→executor, after executor→lead, text-only loop prevention, TERMINATE→lead.
- [x] Lead-driven routing: Lead's message content parsed to route to researcher/critic/judge/coding.
- [x] Default: any non-lead text turn → lead.
- [x] `build_department_selector` takes `guardrail_state: dict` (not `run_state`).

### Acceptance check
- [x] The group is no longer forced through a fixed micro-order.
- [x] The selector prevents chaos, but does not script the work.

### Implementation notes
`src/orchestration/speaker_selector.py` fully rewritten. `_DEPT_STEP_SPEAKER` dict removed. `workflow_step` absent from all code paths (present only in module docstring as historical note). `_MAX_TEXT_TURNS=3` prevents stagnation. Synthesis selector retained unchanged.

---

## CHG-05 — Convert department execution to artifact-based work, not payload mutation

### Goal
Make the group operate on explicit task artifacts and decisions instead of mutating a section payload.

### Checklist
- [x] Research step produces `TaskArtifact` via `from_worker_report()`.
- [x] Artifacts include: task_key, attempt, facts, sources, unresolved_points, strategy_notes.
- [x] Critic produces `TaskReviewArtifact` via `from_critic_review()`.
- [x] Judge produces `TaskDecisionArtifact` via `from_judge_result()`.
- [x] All artifacts stored in `DepartmentRunState` registries.
- [x] Section/package merged only from accepted artifact decisions.

### Acceptance check
- [x] Every accepted package field traceable to a task artifact.
- [x] Rework decisions attached to specific task attempts.

### Implementation notes
`run_research`, `review_research`, `judge_decision` closures in `lead.py` all create typed artifacts via factory methods and call `run_state.record_*_artifact()`. Attempt counter incremented per task.

---

## CHG-06 — Rework role prompts and internal department protocol

### Goal
Align role behavior with the new operating model: fixed contract, autonomous execution.

### Checklist
- [x] Lead prompt rewritten: contract-driven autonomy, explicit retry policy with `MAX_TASK_RETRIES`.
- [x] Researcher prompt: adaptive search, varied framing across attempts.
- [x] Critic prompt: defect-class feedback (missing_core_fact, weak_evidence, placeholder_remaining, list_too_short, method_issue).
- [x] Judge prompt: principle-based decisions (accept/accept_degraded/reject).
- [x] Coding prompt: method tactics (structural operators, diverse source types).
- [x] Prompts reinforce memory boundaries.

### Acceptance check
- [x] Prompts no longer imply a rigid micro-sequence.
- [x] Role instructions aligned with autonomous bounded collaboration.

### Implementation notes
All role system prompts rewritten in `src/agents/lead.py`. Lead prompt embeds `MAX_TASK_RETRIES` value (read from env `LIQUISTO_MAX_TASK_RETRIES`, default 2). No workflow-step language in any prompt.

---

## CHG-07 — Make final package assembly depend on stored task decisions

### Goal
Final department package must emerge from already-made decisions, not hidden re-judging.

### Checklist
- [x] `finalize_package()` consumes stored `TaskDecisionArtifact`s.
- [x] 4-path logic: stored decision → use it; research+approved review → implicit lead_accepted; research+rejected review → inline judge fallback; research only → full inline critic+judge fallback.
- [x] `memory_store.record_department_run_state()` called after assembly.
- [x] `_build_fallback_package` takes `DepartmentRunState` parameter.

### Acceptance check
- [x] Package explainable from already-recorded task decisions.
- [x] Finalization is assembly + completeness validation, not a second secret workflow.

### Implementation notes
`finalize_package` in `lead.py` checks `run_state.latest_decision(task_key)` first. Only falls back to inline critic/judge for tasks with no recorded decision. Run state persisted to `memory_store` after every finalization.

---

## CHG-08 — Rehydrate the full run brain for follow-up by `run_id`

### Goal
When a user asks follow-up questions for a completed run, reload the run-specific department memory and answer from it.

### Checklist
- [x] `load_run_artifact(run_id)` loads both `pipeline_data.json` and `run_context.json`.
- [x] `_get_department_run_state(run_context, department)` navigates `short_term_memory.department_run_states`.
- [x] `_extract_task_evidence(department_run_state)` extracts facts, accepted_points, open_questions from artifact registries.
- [x] All 5 department answer functions use artifact evidence.
- [x] `answer_follow_up()` logs run_id, route, question length.

### Acceptance check
- [x] A run can be reopened by `run_id` and answered with contextual awareness.
- [x] Follow-up answers grounded in the rehydrated run brain.

### Implementation notes
`src/orchestration/follow_up.py` fully rewritten. Evidence sourced from `task_artifacts` (latest facts), `review_artifacts` (accepted_points), `decision_artifacts` (open_questions). Unresolved items drive `requires_additional_research` flag.

---

## CHG-09 — Expand role-brain retrieval and safe consolidation

### Goal
Give the right roles useful process memory without introducing case bias.

### Checklist
- [x] `ROLE_MEMORY_CATEGORIES` maps role names to memory scopes.
- [x] `consolidate_role_patterns()` emits: structural queries (researcher), critic heuristics, judge patterns, coding patterns, retry triggers.
- [x] `_scrub_company_from_query()` strips domains, quoted names, GmbH/AG/etc.
- [x] `_is_process_safe_query()` validates min 12 chars + substantive word.
- [x] `domain` always `""` in emitted patterns.
- [x] Judge patterns from `judge_escalations`; coding patterns from `coding_support_used`; retry triggers from `strategy_changes`.

### Acceptance check
- [x] Roles get useful process memory.
- [x] No role receives customer-specific prior facts as long-term memory.

### Implementation notes
`src/memory/consolidation.py` rewritten with full scrubber pipeline. Structural pattern dedup via `_to_structural_patterns()`. Memory categories drive per-role retrieval boundaries. `domain: ""` enforced on all emitted records.

---

## CHG-10 — Tests, migration, observability, documentation

### Goal
Make the refactor safe, testable, and understandable.

### Checklist
- [x] Tests for department autonomy:
  - [x] no supervisor revision callback during department run
  - [x] selector does not enforce fixed micro-sequence
  - [x] `workflow_step` absent from `build_department_selector` code paths
- [x] Tests for task artifact lifecycle:
  - [x] research artifact creation
  - [x] critic review artifact creation
  - [x] judge decision artifact creation
  - [x] full research → review → decision sequence
  - [x] final package assembly from stored decisions
- [x] Tests for memory separation:
  - [x] run brain persistence in `ShortTermMemoryStore`
  - [x] `record_department_run_state` and `snapshot` integration
- [x] Tests for run rehydration and follow-up:
  - [x] `_extract_task_evidence` from artifact registries
  - [x] `load_run_artifact` with missing run raises `FileNotFoundError`
- [x] Tests for consolidation safety:
  - [x] company name scrubbing
  - [x] empty domain enforcement
  - [x] defect class patterns emitted
  - [x] judge escalation patterns emitted
- [x] Tests for selector guardrails (4 guardrails verified with mocks).
- [x] Update docs so they describe the new runtime truthfully.
- [x] Add department timing observability to `supervisor_loop.py` summary output.

### Acceptance check
- [x] Test suite proves the intended autonomy model (55 architecture tests + 38 contract tests = 93 total passing).
- [x] Docs match the actual implementation.

### Implementation notes
New file: `test_runtime_architecture.py` — 55 tests across 9 test classes. All 93 tests (38 contracts + 55 architecture) pass. Source-inspection tests use comment/docstring-aware parsing to avoid false positives on documentation references. Two tests updated to use regex-based code-only matching after docstring references caused false failures.

---

# Cross-block dependencies

## Hard dependencies
- CHG-01 before CHG-05
- CHG-02 before CHG-08 and CHG-09
- CHG-03 before CHG-04 and CHG-06
- CHG-05 before CHG-07
- CHG-08 before final UI follow-up validation

## Recommended sequencing
- Do not rewrite prompts before the runtime boundaries are changed.
- Do not expand role brains before memory policies are enforced.
- Do not simplify the selector until department-internal decision ownership is defined.

---

# Risks to watch

- Hidden orchestration may reappear in another place if `workflow_step` is removed without replacing it with explicit artifacts and completion rules.
- Long-term memory contamination may happen if consolidation remains too close to raw run outputs.
- Follow-up may appear to work while still ignoring the true run brain.
- Finalization may silently remain a second decision engine if not simplified properly.
- AG2 group autonomy may degrade into chaos if the selector loses too many guardrails too early.

---

# Definition of done

The refactor is complete only when all of the following are true:

- [x] Supervisor provides the contract and accepts the package, but does not drive internal department retries.
- [x] Department group works autonomously inside the contract.
- [x] Selector acts as guardrail logic, not hidden workflow engine.
- [x] Task work is artifact-based and traceable.
- [x] Final package is assembled from explicit task decisions.
- [x] Run brain is stored and can be rehydrated by `run_id` for follow-up.
- [x] Long-term memory stores process patterns only.
- [x] Role-specific brains are available with safe boundaries.
- [x] Report schema and user-facing run inspection remain intact.

---

# Optional implementation note

If the implementation is done incrementally, preserve temporary compatibility layers until:

- task artifacts are stable
- follow-up rehydration works end to end
- old exports are either migrated or explicitly versioned

