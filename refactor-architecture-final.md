# Refactor Architecture — Meeting-Ready Runtime Refactor (Finalized 2026 Edition)

## Purpose

This file is the **authoritative implementation checklist** for refactoring this repository from a
multi-department research pipeline into a **meeting-ready orchestration system**.

The target system must not treat unresolved public research as a normal success condition.
A successful run must end in one of only two states:

1. **meeting_ready**
   - all meeting-critical, publicly researchable questions are answered strongly enough,
   - all user-prioritized optional depth has either been completed or explicitly skipped by the user,
   - remaining unresolved items are only `customer_confirmation_items` or explicitly non-critical.

2. **blocked_not_meeting_ready** / **needs_user_selection**
   - the runtime has correctly refused to finalize because meeting-readiness is not yet achieved.

This file is written for a VS Code coding agent.
It must be executed **section by section**.
After each section, run the matching audit gate from `refactor-architecture-audit.md`.
The agent may continue to the next section **only if the audit result is `TRUE`**.

---

## Quality Anchors (Mandatory)

Use these artifacts as the target-quality reference for the refactor:

1. **Primary quality anchor: `deep-research-report.md`**
   - This is the strongest available example of the desired end-product quality.
   - It demonstrates the expected level of:
     - inventory / working-capital signal detection,
     - contact intelligence,
     - opportunity prioritization,
     - meeting-angle clarity,
     - fact vs inference separation,
     - and concrete meeting actions.

2. **Secondary quality anchor: repo briefing / professional briefing examples**
   - Use existing repo briefing outputs only as structural / formatting references.
   - Do **not** let weaker legacy outputs lower the target quality threshold.

3. **Primary runtime anchor: latest repository ZIP contents**
   - Refactor against the actual current code and wiring.
   - Do not design against a hypothetical clean-room rewrite.

---

## Repo Runtime Anchors (Current Code Paths)

The following files are current runtime anchors and must be treated as authoritative entry points and coordination points for this refactor:

- `src/pipeline_runner.py`
- `src/orchestration/supervisor_loop.py`
- `src/orchestration/task_router.py`
- `src/app/use_cases.py`
- `src/agents/lead.py`
- `src/agents/worker.py`
- `src/agents/critic.py`
- `src/agents/judge.py`
- `src/orchestration/follow_up.py`
- `src/orchestration/department_runtime.py`
- `src/orchestration/run_context.py`
- `src/memory/short_term_store.py`
- `src/models/schemas.py`
- `src/exporters/json_export.py`
- `src/exporters/pdf_report.py`
- `ui/app.py`
- `docs/target_runtime_architecture.md`
- `docs/runtime_architecture.drawio`

If any path has changed in the active repo, the implementation agent must update this file and the audit file in the same section that introduces the path change.

---

## Non-Negotiable Design Principles

1. **Meeting readiness is the top-level success criterion.**
   Department completion is not enough.

2. **Question coverage is the central planning model.**
   The system must know, before department execution, which meeting questions must be answered.

3. **Evidence-first, schema-first, code-governed.**
   Typed runtime contracts are authoritative. Prompt-only coordination is not sufficient where downstream logic depends on structure.

4. **Departments are question-coverage contributors, not final section owners.**
   Their job is to produce evidence and answer updates for mapped question IDs.

5. **Closure is an explicit runtime phase.**
   The system must run bounded additional research to close publicly researchable meeting-critical gaps.

6. **Human-in-the-loop must be explicit and resumable.**
   If additional depth depends on user priorities or customer-internal facts, the run must pause deterministically and resume deterministically.

7. **No fabricated closure.**
   If a fact cannot be resolved from public sources, it must not be hallucinated. It must be classified correctly.

8. **No generic final `open_questions` block in a successful output.**
   Remaining unresolved items may appear only as:
   - `customer_confirmation_items`
   - `optional_depth_not_selected`
   - or a blocking run status

9. **Runtime guardrails are code, not prose.**
   Budgets, stop conditions, status transitions, retries, ordering, and stop reasons must be persisted runtime state.

10. **Every new architecture primitive must be observable, testable, auditable, and exportable.**

---

## Mandatory Runtime Classification Model

Every unresolved or partially resolved issue must be classified into exactly one of these classes:

- `AUTO_CLOSE_REQUIRED`
  - publicly researchable
  - meeting-critical
  - the runtime must attempt bounded additional research automatically

- `USER_DECISION_REQUIRED`
  - additional depth is useful, but relevance depends on user preference / briefing style / business priority
  - runtime must pause for dashboard selection before finalization

- `CUSTOMER_CONFIRMATION_REQUIRED`
  - not publicly answerable with acceptable certainty
  - can only be confirmed in the customer meeting or by customer-provided material

- `NOT_MEETING_CRITICAL`
  - unresolved, but not blocking meeting readiness

- `BLOCKING_FAILURE`
  - the runtime cannot responsibly finalize and cannot continue automatically

These classes must become explicit typed runtime objects and audit-visible state.

---

## Required Structured Output Artifacts

The following artifacts are **schema-enforced** and must be generated or validated through schema-first runtime logic, not prompt-only best effort:

- `EvidencePacket`
- `GapCandidate`
- `AnswerMatrixUpdate`
- `ResolutionDecision`
- `ResolutionPlan`
- `MeetingReadinessAssessment`
- `MeetingAction`
- `FinalBriefing`

Internal code-only containers may be assembled in Python, but any LLM-generated structured object that is consumed by runtime logic must be schema-enforced.

---

## Required Inputs for This Refactor

Use these artifacts as inputs while implementing:

- the latest uploaded repository ZIP
- `deep-research-report.md` as primary quality anchor
- the latest runtime architecture docs already present in the repo
- the current `refactor-architecture.md`
- the current `refactor-architecture-audit.md`

---

## Mandatory Execution Protocol

For every section:

1. Implement the section completely.
2. Keep the repo runnable.
3. Run the matching audit gate from `refactor-architecture-audit.md`.
4. If the result is `FALSE`, fix the same section and rerun the same gate.
5. Do not start the next section before `TRUE`.
6. Use one focused commit per section.

---

## Final End-State Definition

At the end of RA-10, all of the following must be true:

- the runtime plans around **meeting questions**, not only departments
- departments produce **evidence packets**, **gap candidates**, and **answer updates**
- a **resolution controller** runs a bounded closure phase
- a **resolution dashboard** can pause and resume the run deterministically
- finalization is protected by a **meeting-readiness gate**
- final success outputs contain **meeting actions**, not generic research leftovers
- unresolved items are either **customer confirmation** or **optional depth not selected**
- exports, follow-up, tests, UI, and docs match the new architecture

---

# SECTION RA-00 — Baseline, quality rubric, and golden traces

## Goal

Freeze the current runtime behavior, define the quality target using the deep research report, and create golden traces before any structural refactor begins.

## Files to Change

**Existing**
- `src/pipeline_runner.py`
- `src/exporters/json_export.py`
- `ui/app.py`
- `tests/architecture/*`
- `tests/integration/*`
- `tests/smoke/*`
- `docs/target_runtime_architecture.md`

**New**
- `docs/refactor_baseline.md`
- `tests/golden/README.md`
- `tests/golden/runs/<baseline_run_id>/{run_meta.json,run_context.json,pipeline_data.json,chat_history.json}`
- `tests/golden/quality_reference/deep_research_quality_excerpt.md`
- `tests/golden/quality_reference/deep_research_quality_rubric.md`
- `tests/golden/quality_reference/repo_briefing_excerpt.md` (optional secondary reference)

## Required Changes

### Mandatory

- Create at least one committed baseline run snapshot with minimal stable artifacts:
  - `run_meta.json`
  - `run_context.json`
  - `pipeline_data.json`
  - optional trimmed `chat_history.json`

- Create `docs/refactor_baseline.md` documenting:
  - current runtime flow
  - current success semantics
  - where `open_questions` and `next_steps` are produced today
  - current exports and checkpoints
  - current UI behavior
  - current meeting-readiness limitations

- Create a **quality rubric** derived primarily from `deep-research-report.md`, covering at minimum:
  - inventory / working-capital signal quality
  - contact intelligence quality
  - opportunity prioritization quality
  - buyer / redeployment specificity
  - fact / inference separation
  - meeting-action usefulness

- Add at least one baseline contract regression test that fails on uncontrolled top-level export drift.

### Compatibility

- None.

### Cleanup

- None.

## Definition of Done

- Baseline docs exist.
- Golden traces exist.
- Deep-research quality excerpt + rubric exist.
- Baseline drift test exists and is meaningful.

## Audit Gate

Run **Audit Prompt RA-00**.

---

# SECTION RA-01 — Introduce the typed meeting-ready state model

## Goal

Introduce the minimum complete typed runtime model for meeting readiness. The runtime must stop depending on implicit dict shapes.

## Files to Change

**Existing**
- `src/orchestration/run_context.py`
- `src/memory/short_term_store.py`
- `src/models/schemas.py`
- `src/exporters/json_export.py`

**New**
- `src/models/meeting_ready.py`
- `src/orchestration/meeting_ready_contracts.py` (optional)
- `src/orchestration/compat_legacy.py` (if needed)

## Required Changes

### Mandatory

Implement typed contracts for at least the following:

- `MeetingQuestion`
- `QuestionRegistry`
- `AnswerStatus`
- `AnswerCell`
- `AnswerMatrix`
- `EvidenceItem`
- `EvidencePacket`
- `GapSeverity`
- `GapResolutionClass`
- `GapCandidate`
- `UserDepthOption`
- `DashboardState`
- `ResolutionDecision`
- `ResolutionPlan`
- `ResolutionEvent`
- `MeetingReadinessStatus`
- `MeetingReadinessAssessment`
- `CustomerConfirmationItem`
- `MeetingAction`
- `FinalBriefing`

Extend `RunContext` with persisted top-level fields for:

- `question_registry`
- `answer_matrix`
- `evidence_packets`
- `gap_candidates`
- `resolution_plan`
- `dashboard_state`
- `customer_confirmation_items`
- `meeting_actions`
- `meeting_readiness_assessment`
- `phase`

Extend `ShortTermMemoryStore` with snapshots for:

- `question_registry_snapshot`
- `answer_matrix_snapshot`
- `evidence_packets`
- `gap_candidates`
- `resolution_events`
- `user_depth_selections`
- `customer_confirmation_items`
- `meeting_actions`
- `meeting_readiness_history` (recommended)

Add contract versioning for registry and final briefing artifacts.

### Compatibility

If `open_questions` and `next_actions` still exist in active runtime paths:
- implement deterministic converters in `src/orchestration/compat_legacy.py`
- mark them explicitly as temporary compatibility helpers

### Cleanup

- No removal yet.

## Definition of Done

- New contracts exist.
- RunContext and ShortTermMemory snapshots export them.
- Legacy compatibility exists if legacy fields are still live.

## Audit Gate

Run **Audit Prompt RA-01**.

---

# SECTION RA-02 — Build Question Registry and Answer Matrix before department execution

## Goal

The system must know what “meeting-ready” means before departments run.

## Files to Change

**Existing**
- `src/app/use_cases.py`
- `src/orchestration/task_router.py`
- `src/orchestration/supervisor_loop.py`
- `src/pipeline_runner.py`

**New**
- `src/orchestration/question_planner.py`
- `src/orchestration/answer_matrix.py`

## Required Changes

### Mandatory

- Create a single source of truth meeting-question catalog in `src/app/use_cases.py`.
- Extend backlog items with deterministic `question_ids` mapping.
- Add question priority / weight metadata.
- Implement:
  - `build_question_registry(...)`
  - `init_answer_matrix(...)`
- Wire registry and matrix construction into `src/pipeline_runner.py` **before** `run_supervisor_loop()`.
- Persist both into `RunContext` and `ShortTermMemoryStore`.
- Update `src/orchestration/supervisor_loop.py` so department outcomes update answer cells deterministically.

### Compatibility

- Legacy `open_questions` may still be converted into `GapCandidate`s at this stage.

### Cleanup

- None.

## Definition of Done

- Registry + matrix exist before departments run.
- Matrix is updated by actual task outcomes.
- Run snapshots show non-empty answer state.

## Audit Gate

Run **Audit Prompt RA-02**.

---

# SECTION RA-03 — Convert departments from mini-briefings to evidence production

## Goal

Departments must stop behaving like final section-report generators. Their primary job is to contribute evidence and answer coverage for mapped meeting questions.

## Files to Change

**Existing**
- `src/agents/worker.py`
- `src/agents/lead.py`
- `src/agents/critic.py`
- `src/agents/judge.py`
- `src/orchestration/contracts.py`
- `src/models/schemas.py`
- `src/memory/short_term_store.py`

**New**
- `src/orchestration/evidence_pipeline.py` (optional)

## Required Changes

### Mandatory

- Extend department contracts to carry:
  - `evidence_packets`
  - `gap_candidates`
  - `answer_matrix_updates`
  - `source_register`
  - optional `confidence_breakdown`

- Make `ResearchWorker` produce at least one `EvidencePacket` per task.
- Evidence packets must reference:
  - `task_key`
  - `question_ids`
  - `claims`
  - `evidence_items`
  - `counter_signals`
  - `confidence`

- Make `DepartmentLeadAgent` persist:
  - evidence packets
  - typed gap candidates
  - answer updates

- Reframe department ownership in code comments / module docstrings / contracts:
  - departments are **question-coverage contributors**
  - they do not own the final briefing

- `open_questions` and local `next_steps` may still exist temporarily, but they must no longer be treated as final success outputs.

### Compatibility

- Narrative section summaries may continue to exist temporarily.
- They are secondary and must not drive closure logic.

### Cleanup

- Mark legacy `open_questions` / `next_actions` as deprecated in active code paths.

## Definition of Done

- Departments emit evidence-first outputs.
- Evidence packets and gap candidates are visible in runtime state.
- Answer matrix is fed by department outputs.

## Audit Gate

Run **Audit Prompt RA-03**.

---

# SECTION RA-04 — Resolution Controller and bounded closure loop

## Goal

Introduce an explicit closure phase that actively resolves publicly researchable meeting-critical gaps.

## Files to Change

**Existing**
- `src/pipeline_runner.py`
- `src/orchestration/supervisor_loop.py`
- `src/orchestration/follow_up.py`
- `src/orchestration/department_runtime.py`
- `src/memory/short_term_store.py`

**New**
- `src/orchestration/resolution_controller.py`
- `src/orchestration/closure_rules.py`

## Required Changes

### Mandatory

Implement a `ResolutionController` with public API for:
- building a resolution plan
- running bounded closure passes
- assessing meeting readiness (or delegating to RA-06 logic later)

Implement classification rules so every gap candidate maps to one and only one of:
- `AUTO_CLOSE_REQUIRED`
- `USER_DECISION_REQUIRED`
- `CUSTOMER_CONFIRMATION_REQUIRED`
- `NOT_MEETING_CRITICAL`
- `BLOCKING_FAILURE`

For `AUTO_CLOSE_REQUIRED`, the runtime must automatically trigger targeted follow-up research through the existing follow-up/runtime mechanisms.

Closure must be bounded by:
- max closure passes
- max follow-ups per pass
- elapsed time budget
- token / usage budget
- explicit persisted stop reason

Finalization must be blocked if meeting-critical publicly researchable gaps remain unresolved after closure.

### Compatibility

- If follow-up still returns legacy structures, implement deterministic extraction into typed evidence / answer updates.

### Cleanup

- None.

## Definition of Done

- Closure loop is active in the live run path.
- Public meeting-critical gaps trigger targeted closure.
- Finalization is blocked when closure fails to resolve required public questions.

## Audit Gate

Run **Audit Prompt RA-04**.

---

# SECTION RA-05 — Resolution Dashboard and deterministic pause/resume

## Goal

Introduce an explicit, resumable dashboard step for optional depth and customer-confirmation routing.

## Files to Change

**Existing**
- `ui/app.py`
- `ui/i18n.py`
- `src/pipeline_runner.py`
- `src/exporters/json_export.py`
- `src/memory/short_term_store.py`

**New**
- `src/orchestration/dashboard_runtime.py`

## Required Changes

### Mandatory

- Make `run_pipeline(...)` return / persist `needs_user_selection` when the resolution plan requires dashboard input.
- Persist `dashboard_state` and `resolution_plan` before pausing.
- Add `resume_pipeline(...)` that reloads the run, persists user selections, executes optional depth if selected, and continues deterministically.
- Build a real UI dashboard that shows:
  - answered core questions
  - optional depth areas
  - customer-confirmation items
  - selected / skipped options
- Finalization must remain blocked until required dashboard decisions exist.

### Compatibility

- Existing follow-up UX may remain.
- Dashboard must be separate and behaviorally effective.

### Cleanup

- None.

## Definition of Done

- Runs can pause and resume deterministically.
- User decisions change runtime behavior.
- No silent bypass to final success is possible.

## Audit Gate

Run **Audit Prompt RA-05**.

---

# SECTION RA-06 — Meeting-Readiness Gate and Final Briefing Composer

## Goal

Introduce the real success gate and final success artifact. Final success means meeting-ready, not merely “research completed”.

## Files to Change

**Existing**
- `src/pipeline_runner.py`
- `src/orchestration/synthesis.py`
- `src/agents/synthesis_department.py`
- `src/models/schemas.py`
- `ui/app.py`
- `src/exporters/pdf_report.py`

**New**
- `src/orchestration/meeting_readiness.py`
- `src/orchestration/final_briefing_composer.py`

## Required Changes

### Mandatory

Implement `MeetingReadinessGate` so finalization only passes if:
- no unresolved publicly researchable meeting-critical questions remain
- no required dashboard decision is missing
- evidence quality for critical questions reaches the defined minimum threshold

Implement `FinalBriefingComposer` so successful runs produce:
- `management_snapshot`
- `answer_matrix_summary`
- `meeting_actions`
- `customer_confirmation_items` (only when truly necessary)
- `evidence_appendix` (bounded)

Replace final-success reliance on generic `open_questions` / `next_steps` with:
- concrete `meeting_actions`
- correctly classified confirmation items

Success output must not contain a generic unresolved `open_questions` block.

### Compatibility

- Legacy `next_steps` may still exist temporarily for old runs.
- New runs must use `meeting_actions` as the primary action output.

### Cleanup

- Mark legacy synthesis `next_steps` as deprecated.

## Definition of Done

- Meeting-readiness gate blocks or passes finalization correctly.
- New success outputs contain `meeting_actions` and no generic unresolved open-question block.
- UI and PDF render the new success model.

## Audit Gate

Run **Audit Prompt RA-06**.

---

# SECTION RA-07 — Exports, follow-up grounding, and phase-aware checkpointing

## Goal

Make persistence and post-run follow-up operate on the new meeting-ready state model.

## Files to Change

**Existing**
- `src/exporters/json_export.py`
- `src/orchestration/follow_up.py`
- `src/orchestration/run_context.py`
- `src/memory/short_term_store.py`
- `ui/app.py`

## Required Changes

### Mandatory

Export and rehydrate at minimum:
- question registry
- answer matrix
- evidence packets
- gap candidates
- resolution plan / events
- dashboard state / user depth selections
- customer confirmation items
- meeting actions
- meeting-readiness assessment
- phase and stop reasons

Make follow-up use answer matrix and evidence packets as primary grounding.

Introduce phase-aware checkpointing after:
- first pass
- closure pass(es)
- dashboard pause
- dashboard resume
- finalization

### Compatibility

- Old run loaders may map legacy shapes into the new model when possible.
- They must never silently mark missing information as resolved.

### Cleanup

- None.

## Definition of Done

- New runs export the new state model.
- Follow-up uses the new state as truth.
- Checkpoints exist per major phase.

## Audit Gate

Run **Audit Prompt RA-07**.

---

# SECTION RA-08 — Runtime guardrails and structured-output enforcement

## Goal

Operational hardening: schema-enforced outputs, bounded execution, deterministic ordering, persisted stop reasons, better observability.

## Files to Change

**Existing**
- `src/agents/worker.py`
- `src/research/search.py`
- `src/agents/lead.py`
- `src/orchestration/supervisor_loop.py`
- `src/config/settings.py`

**New**
- `src/orchestration/runtime_guardrails.py`
- `src/llm/client.py` (recommended)

## Required Changes

### Mandatory

- Enforce structured outputs for runtime-consumed artifacts:
  - `EvidencePacket`
  - `GapCandidate`
  - `AnswerMatrixUpdate`
  - `ResolutionDecision`
  - `FinalBriefing` when model-generated

- Add phase-aware budgets:
  - `first_pass_budget`
  - `closure_budget`
  - `optional_depth_budget`

- Persist budget consumption and explicit stop reasons.
- Make department loops and closure loops deterministic and bounded.
- Add deterministic sorting rules for:
  - question order
  - evidence order
  - meeting action order
  - exported summary order
- Add seed-enabled reproducibility mode for golden traces where supported.
- Persist resolution timeline events.

### Compatibility

- Existing client logic may remain temporarily, but schema-first runtime artifacts must already be live.

### Cleanup

- None.

## Definition of Done

- Structured outputs are real runtime behavior, not prompt prose.
- Budgets and stop reasons are visible in exports.
- Deterministic ordering exists.
- Guardrail telemetry is observable.

## Audit Gate

Run **Audit Prompt RA-08**.

---

# SECTION RA-09 — Tests, negative paths, and golden-trace regression

## Goal

Add strong behavior tests and regression protection for the new meeting-ready runtime model.

## Files to Change

**Existing**
- `tests/architecture/*`
- `tests/integration/*`
- `tests/smoke/*`

**New**
- `tests/meeting_readiness/test_question_registry.py`
- `tests/meeting_readiness/test_answer_matrix.py`
- `tests/meeting_readiness/test_resolution_controller.py`
- `tests/meeting_readiness/test_dashboard_pause_resume.py`
- `tests/meeting_readiness/test_final_briefing_composer.py`
- `tests/golden/test_golden_traces.py`

## Required Changes

### Mandatory

Add tests for:
- question registry creation
- answer matrix updates
- resolution controller classification and closure behavior
- dashboard pause/resume
- final briefing composition
- meeting-readiness gating

Add negative-path tests for:
- unresolved public meeting-critical gaps block finalization
- missing dashboard decisions block finalization
- schema parse failure in a meeting-critical artifact blocks success

Add golden-trace regression tests that detect contract drift intentionally.

### Compatibility

- Legacy tests may be adapted, not simply deleted.

### Cleanup

- Remove obsolete weaker tests only if stronger replacements exist.

## Definition of Done

- New architecture concepts are covered by behavior tests.
- Negative paths are covered.
- Golden traces are meaningful and enforced.

## Audit Gate

Run **Audit Prompt RA-09**.

---

# SECTION RA-10 — Documentation alignment and legacy cleanup

## Goal

Make code, docs, diagrams, exports, and wording converge on one architecture.

## Files to Change

**Existing**
- `docs/target_runtime_architecture.md`
- `docs/runtime_architecture.drawio`
- `README.md`
- compat modules created earlier

## Required Changes

### Mandatory

- Update docs and diagrams to reflect the actual final runtime flow:
  - question planning
  - first-pass department evidence production
  - closure loop
  - dashboard pause/resume
  - meeting-readiness gate
  - final briefing composer
  - export

- Remove or sharply limit legacy compatibility shims.
- Remove legacy wording that presents unresolved `open_questions` or generic `next_steps` as a normal success output.
- Document any remaining legacy loading support precisely.

### Compatibility

- If old runs remain loadable, compatibility rules must be explicit and read-only focused.

### Cleanup

- Remove obsolete success-path dependencies on `open_questions` / `next_actions` / legacy next-steps semantics.

## Definition of Done

- Docs and diagrams match real code flow.
- Legacy drift is removed or explicitly documented.
- Success-path wording no longer treats open questions as normal output.

## Audit Gate

Run **Audit Prompt RA-10**.

---

## Final Completion Rule

The refactor is complete only when **RA-00 through RA-10** have each been audited `TRUE`.
Nothing less counts as complete.
