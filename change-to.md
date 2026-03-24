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
- [ ] Freeze current expected runtime behavior in notes / docs.
- [ ] Record current department flow assumptions from:
  - [ ] `src/agents/lead.py`
  - [ ] `src/orchestration/speaker_selector.py`
  - [ ] `src/orchestration/supervisor_loop.py`
  - [ ] `src/orchestration/department_runtime.py`
- [ ] Add or update tests that protect the current report schema and export shape.
- [ ] Add a test fixture for a representative `run_id` artifact directory.
- [ ] Confirm which current outputs must remain backward-compatible.

### Acceptance check
- [ ] Existing pipeline still runs before refactor starts.
- [ ] Baseline tests pass.
- [ ] Team can compare pre-/post-refactor outputs on the same sample run.

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
- [ ] Define explicit department runtime objects, for example:
  - [ ] `DepartmentRunState`
  - [ ] `DepartmentWorkspace`
  - [ ] `TaskArtifact`
  - [ ] `TaskReviewArtifact`
  - [ ] `TaskDecisionArtifact`
  - [ ] `DepartmentPackageDraft`
- [ ] Define terminal / non-terminal task states.
- [ ] Define allowed task decision outcomes, e.g.:
  - [ ] `accepted`
  - [ ] `accepted_with_gaps`
  - [ ] `rework_required`
  - [ ] `escalated_to_judge`
  - [ ] `closed_unresolved_with_reason`
- [ ] Define completion criteria for a department run.
- [ ] Define what data belongs in runtime state vs. working memory vs. final package.

### Implementation tasks
- [ ] Introduce typed objects without yet changing all runtime logic.
- [ ] Create adapters so current code can read/write through the new structures.
- [ ] Minimize raw dict mutation in `lead.py`.
- [ ] Mark `workflow_step` as deprecated in code comments / TODOs once replacement path exists.

### Acceptance check
- [ ] Department runtime state can be serialized.
- [ ] Core runtime decisions can be expressed without relying on magic strings.
- [ ] No final behavior change required yet.

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

### Design tasks
- [ ] Define the **run brain** schema.
- [ ] Define the **long-term process brain** schema.
- [ ] Define a policy for what may flow from run brain to long-term brain.
- [ ] Define explicit deny rules for customer-/run-specific content.

### Run brain checklist
- [ ] Store department workspace contents per run.
- [ ] Store task artifacts per run.
- [ ] Store review comments per run.
- [ ] Store judge decisions per run.
- [ ] Store coding-support suggestions used in the run.
- [ ] Store strategy changes / retries / rejected paths.
- [ ] Store department chat trace or a normalized execution trace.
- [ ] Ensure all of the above can be reloaded by `run_id`.

### Long-term process brain checklist
- [ ] Store only reusable strategies / heuristics / rules.
- [ ] Researcher brain:
  - [ ] query framing patterns
  - [ ] source discovery patterns
  - [ ] evidence triangulation patterns
  - [ ] failed-search anti-patterns
- [ ] Critic brain:
  - [ ] evidence sufficiency heuristics
  - [ ] common defect classes
  - [ ] critique patterns that led to successful rework
- [ ] Lead brain:
  - [ ] delegation patterns
  - [ ] completion heuristics
  - [ ] escalation patterns
- [ ] Judge brain:
  - [ ] decision principles
  - [ ] conflict classes
  - [ ] tradeoff rules
- [ ] Coding Specialist brain:
  - [ ] parsing tactics
  - [ ] extraction tactics
  - [ ] scraping / debugging patterns
  - [ ] structural workaround patterns
  - [ ] query refinement tactics

### Implementation tasks
- [ ] Refactor `ShortTermMemoryStore` into an explicit run-memory carrier.
- [ ] Update `snapshot()` shape to include the new run-brain sections.
- [ ] Refactor `consolidate_role_patterns()` so it emits only process-safe patterns.
- [ ] Remove or sanitize any current consolidation content that stores company/run facts.
- [ ] Update export logic so run brain is written with the run artifacts.

### Acceptance check
- [ ] A full run brain can be reloaded without the original live process.
- [ ] Long-term memory contains no company-specific facts.
- [ ] Consolidation produces process patterns only.

---

## CHG-03 — Remove Supervisor from the internal department work loop

### Goal
Keep the Supervisor as control-plane owner, but remove it from intra-department retry decisions.

### Files likely touched
- `src/agents/lead.py`
- `src/agents/supervisor.py`
- `src/orchestration/supervisor_loop.py`
- `src/orchestration/department_runtime.py`

### Current problem
The Department Lead currently calls `supervisor.decide_revision(...)` inside the department loop. That breaks department autonomy.

### Checklist
- [ ] Remove `request_supervisor_revision(...)` from the department group runtime path.
- [ ] Remove direct revision callbacks from Lead tools.
- [ ] Keep Supervisor responsibilities limited to:
  - [ ] building the brief
  - [ ] routing assignments to departments
  - [ ] accepting / rejecting completed department packages
  - [ ] routing follow-up questions at top level
- [ ] Move retry authorization into the department itself.
- [ ] Move coding-specialist authorization into department logic.
- [ ] Move judge escalation decision into department logic.

### Acceptance check
- [ ] A department can complete critique → retry → coding support → judge escalation without Supervisor intervention.
- [ ] Supervisor only sees contract handoff and final package return.

---

## CHG-04 — Reduce the selector to runtime guardrails, not workflow choreography

### Goal
Allow the AG2 group to work autonomously while keeping loop safety and sane turn routing.

### Files likely touched
- `src/orchestration/speaker_selector.py`
- `src/agents/lead.py`

### Current problem
The selector currently behaves like a hidden workflow engine.

### Checklist
- [ ] Remove hard-coded step sequencing based on `workflow_step`.
- [ ] Keep only guardrail responsibilities in the selector, such as:
  - [ ] valid first speaker
  - [ ] route after tool execution
  - [ ] prevent dead text-only loops
  - [ ] prevent invalid handoffs
  - [ ] recognize package finalization / termination
- [ ] Verify whether AG2 can use more native group behavior with lighter custom rules.
- [ ] Ensure the Lead can still intervene to keep progress moving.
- [ ] Add explicit max-round and stagnation safeguards.

### Acceptance check
- [ ] The group is no longer forced through a fixed micro-order.
- [ ] The selector prevents chaos, but does not script the work.

---

## CHG-05 — Convert department execution to artifact-based work, not payload mutation

### Goal
Make the group operate on explicit task artifacts and decisions instead of mutating a section payload as the main source of truth.

### Files likely touched
- `src/agents/worker.py`
- `src/agents/critic.py`
- `src/agents/judge.py`
- `src/agents/lead.py`
- `src/models/schemas.py`
- `src/memory/short_term_store.py`

### Current problem
The Worker writes into a running section payload too early, and review happens against that evolving merged state.

### Checklist
- [ ] Change the research step to produce a `TaskArtifact` first.
- [ ] Ensure each artifact includes:
  - [ ] task key
  - [ ] attempt number
  - [ ] evidence / sources
  - [ ] structured findings
  - [ ] unresolved points
  - [ ] strategy notes
- [ ] Change Critic to review a specific `TaskArtifact`, not the whole merged section.
- [ ] Change Judge to decide on a specific review conflict / task decision.
- [ ] Store all task attempts, not only the latest result.
- [ ] Merge task output into the section/package only after a task reaches an acceptable decision state.
- [ ] Preserve provenance so it is clear which task / attempt produced which accepted material.

### Acceptance check
- [ ] Every accepted package field can be traced back to at least one task artifact.
- [ ] Rework decisions are attached to specific task attempts.
- [ ] The section payload is no longer the primary working artifact.

---

## CHG-06 — Rework role prompts and internal department protocol

### Goal
Align the role behavior with the new operating model: fixed contract, autonomous execution.

### Files likely touched
- `src/agents/lead.py`
- possibly prompt assets in `prompts/`

### Checklist
- [ ] Rewrite `DepartmentLeadAgent._lead_system_prompt()` so it no longer scripts a fixed order.
- [ ] Explicitly instruct the Lead to:
  - [ ] ensure all mandatory questions are covered
  - [ ] choose/adapt internal work strategy
  - [ ] use Critic feedback actively
  - [ ] involve Coding Specialist when search paths stall
  - [ ] involve Judge only for genuine decision ambiguity
  - [ ] finalize only when all mandatory items are resolved or justified as unresolved
- [ ] Rewrite researcher prompt to encourage adaptive search, not one-shot execution.
- [ ] Rewrite critic prompt to provide defect-class feedback, not only pass/fail.
- [ ] Rewrite judge prompt around principle-based conflict decisions.
- [ ] Rewrite coding prompt around method support and retrieval adaptation.
- [ ] Ensure prompts reinforce memory boundaries:
  - [ ] run-specific facts stay in run brain
  - [ ] process lessons only may flow to long-term memory

### Acceptance check
- [ ] Prompts no longer imply a rigid micro-sequence.
- [ ] Role instructions are aligned with autonomous bounded collaboration.

---

## CHG-07 — Make final package assembly depend on stored task decisions

### Goal
The final department package must emerge from the department’s already-made decisions, not from hidden re-judging during finalization.

### Files likely touched
- `src/agents/lead.py`
- `src/models/schemas.py`
- `src/memory/short_term_store.py`

### Current problem
`finalize_package()` currently recalculates too much and can become a second hidden decision path.

### Checklist
- [ ] Refactor `finalize_package()` so it consumes stored task decisions.
- [ ] Ensure package assembly uses:
  - [ ] accepted task artifacts
  - [ ] accepted-with-gap artifacts
  - [ ] explicit unresolved records where needed
- [ ] Remove hidden re-review / re-judge behavior from finalization where possible.
- [ ] Keep package confidence / completeness logic explicit.
- [ ] Define and store package acceptance reasons.
- [ ] Keep fallback packaging only as an explicit degraded outcome, not a silent normal path.

### Acceptance check
- [ ] The package can be explained from already-recorded task decisions.
- [ ] Finalization is assembly + completeness validation, not a second secret workflow.

---

## CHG-08 — Rehydrate the full run brain for follow-up by `run_id`

### Goal
When a user reopens a run and asks follow-up questions, the system must reload the run-specific department memory and answer from it.

### Files likely touched
- `src/orchestration/follow_up.py`
- `src/orchestration/department_runtime.py`
- `src/agents/lead.py`
- `src/exporters/json_export.py`
- `src/pipeline_runner.py`
- possibly UI entry points

### Current problem
Follow-up handling is currently too heuristic and too shallow relative to the stored run context.

### Checklist
- [ ] Define a formal rehydration path from `run_id` to run brain.
- [ ] Load the stored department run brain when a follow-up starts.
- [ ] Pass the rehydrated context into the follow-up department runtime.
- [ ] Ensure the department can inspect:
  - [ ] previous evidence
  - [ ] previous decisions
  - [ ] rejected paths
  - [ ] previous open questions
  - [ ] previous critique comments
- [ ] Preserve the difference between:
  - [ ] answering from already-known run context
  - [ ] performing new follow-up research on top of the existing run
- [ ] Update exported follow-up artifacts accordingly.

### Acceptance check
- [ ] A run can be reopened by `run_id` and the group can continue with contextual awareness.
- [ ] Follow-up answers are grounded in the rehydrated run brain.

---

## CHG-09 — Expand role-brain retrieval and safe consolidation

### Goal
Give the right roles useful process memory without introducing case bias.

### Files likely touched
- `src/pipeline_runner.py`
- `src/memory/retrieval.py`
- `src/memory/consolidation.py`
- `src/memory/long_term_store.py`
- `src/agents/lead.py`
- `src/agents/worker.py`
- `src/agents/critic.py`
- `src/agents/judge.py`
- `src/agents/coding_assistant.py`

### Checklist
- [ ] Make role-specific memory retrieval explicit for:
  - [ ] Lead
  - [ ] Researcher
  - [ ] Critic
  - [ ] Judge
  - [ ] Coding Specialist
- [ ] Define per-role allowed memory categories.
- [ ] Ensure Judge memory contains only principle-level guidance.
- [ ] Ensure Coding memory contains only method-level support.
- [ ] Prevent memory retrieval from injecting prior case conclusions.
- [ ] Add sanitization / filtering before long-term write-back.
- [ ] Add traceability: store which memory patterns were retrieved for a run.

### Acceptance check
- [ ] Roles get useful process memory.
- [ ] No role receives customer-specific prior facts as long-term memory.

---

## CHG-10 — Tests, migration, observability, documentation

### Goal
Make the refactor safe, testable, and understandable.

### Files likely touched
- `test_pipeline.py`
- `test_integration.py`
- `test_contracts.py`
- new focused tests under `tests/` if introduced
- `README.md`
- `docs/target_runtime_architecture.md`
- runtime diagrams/docs

### Checklist
- [ ] Add tests for department autonomy:
  - [ ] no supervisor revision callback during department run
  - [ ] selector does not enforce fixed micro-sequence
- [ ] Add tests for task artifact lifecycle:
  - [ ] research artifact creation
  - [ ] critic review artifact creation
  - [ ] judge decision artifact creation
  - [ ] final package assembly from accepted artifacts
- [ ] Add tests for memory separation:
  - [ ] run brain contains case specifics
  - [ ] long-term brain does not contain case specifics
- [ ] Add tests for run rehydration and follow-up.
- [ ] Add regression tests for report schema stability.
- [ ] Add observability/logging for:
  - [ ] task attempts
  - [ ] critique loops
  - [ ] judge escalations
  - [ ] coding-support usage
  - [ ] fallback package events
- [ ] Update docs so they describe the new runtime truthfully.

### Acceptance check
- [ ] Test suite proves the intended autonomy model.
- [ ] Docs match the actual implementation.

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

- [ ] Supervisor provides the contract and accepts the package, but does not drive internal department retries.
- [ ] Department group works autonomously inside the contract.
- [ ] Selector acts as guardrail logic, not hidden workflow engine.
- [ ] Task work is artifact-based and traceable.
- [ ] Final package is assembled from explicit task decisions.
- [ ] Run brain is stored and can be rehydrated by `run_id` for follow-up.
- [ ] Long-term memory stores process patterns only.
- [ ] Role-specific brains are available with safe boundaries.
- [ ] Report schema and user-facing run inspection remain intact.

---

# Optional implementation note

If the implementation is done incrementally, preserve temporary compatibility layers until:

- task artifacts are stable
- follow-up rehydration works end to end
- old exports are either migrated or explicitly versioned

