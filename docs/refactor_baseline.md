# Refactor Baseline — Current Runtime Behavior (2026-03-29)

> Historical baseline snapshot (pre-refactor checkpoint).
> This file documents the behavior at 2026-03-29 and is not the live
> architecture source of truth for 2026-04-01+.

## Purpose

This document freezes the **current live runtime behavior** before the
meeting-readiness refactor begins. It serves as the regression anchor for
RA-00 and all subsequent sections.

---

## Current Runtime Flow

Entry point: `src/pipeline_runner.py → run_pipeline()`

### 1. Intake + Context Setup

- `IntakeRequest` created from `company_name` + `web_domain`.
- `create_runtime_agents()` instantiates all AG2 agents.
- `FileLongTermMemoryStore` loaded from `artifacts/memory/long_term_memory.json`.
- `RunContext` created with `run_id`, `intake`, empty `short_term_memory`.
- `retrieved_strategies` (up to 5 general patterns) and
  `retrieved_role_strategies` (up to 3 per active role) loaded from long-term
  memory via `retrieve_strategies()`.
- `question_registry` and `answer_matrix` built from
  `meeting_questions.build_question_registry()` /
  `build_initial_answer_matrix()` — all questions start as `pending`.

### 2. Supervisor Brief

- `agents["supervisor"].build_intake_brief(intake)` produces a
  `SupervisorBrief` with verified company name, domain, homepage excerpt.
- Brief stored in `run_context.supervisor_brief`.

### 3. Department Execution (`run_supervisor_loop`)

- `build_initial_assignments(brief)` creates task assignments from
  `STANDARD_TASK_BACKLOG` in `src/app/use_cases.py`.
- `build_department_assignments(brief)` groups assignments by department.

**Phase 1 — Parallel:** Company + Market departments run via
`ThreadPoolExecutor`. Each gets an isolated `ShortTermMemoryStore`
working-set; deltas merged back in canonical order after completion.

**Phase 2 — Sequential:** Buyer → Contact. Contact receives
`buyer_candidates` extracted from the Market/Buyer output. Run conditions
evaluated per task (`evaluate_run_conditions`); tasks may be skipped.

**Per department:**
- Department runtime (`agents["departments"][name].run(...)`) executes the
  AG2 GroupChat (Lead → Researcher → Critic → optional Judge/Coding).
- Returns `(section_payload, messages, package)`.
- Supervisor acceptance gate (`accept_department_package`) decides
  `accepted` / `accepted_with_gaps` / `rejected`.
- `_apply_acceptance_gate` writes to `sections` and `department_packages`.
- `_apply_structured_runtime_artifacts` extracts `AnswerMatrixUpdate`,
  `GapCandidate`, `EvidencePacket` from the package into runtime state.
- Answer matrix updated per task via `_update_answer_matrix_from_task`.
- Token budget enforcement after each sequential department (soft + hard cap).

### 4. First-Round Resolution

- `ResolutionController.classify(...)` assigns one of five buckets:
  `AUTO_CLOSE_REQUIRED`, `USER_DECISION_REQUIRED`,
  `CUSTOMER_CONFIRMATION_REQUIRED`, `NOT_MEETING_CRITICAL`,
  `BLOCKING_FAILURE`.
- Result emitted as a Supervisor message.

### 5. Bounded Auto-Close (if AUTO_CLOSE_REQUIRED)

- `run_bounded_follow_up(...)` attempts targeted follow-up for up to
  `max_questions` public gaps.
- Returns `remaining_public_gaps` (gaps not resolved after auto-close).

### 6. Synthesis Department

- `build_quality_review(memory_snapshot)` produces evidence health, open
  gaps, recommendations.
- `build_synthesis_context(...)` assembles cross-domain input.
- AG2 SynthesisDepartment GroupChat runs (SynthesisLead, SynthesisAnalyst,
  SynthesisCritic, SynthesisJudge).
- Supervisor acceptance gate for synthesis (`accept_synthesis`).
- Synthesis envelope stored in `department_packages["SynthesisDepartment"]`.

### 7. Finalization

- `assess_research_readiness(...)` scores the run (0–100).
- `determine_final_status(...)` maps to `meeting_ready`,
  `needs_user_selection`, or `blocked_not_meeting_ready`.
- `build_resolution_plan(...)` creates a persisted resolution plan.
- `build_dashboard_state(...)` creates dashboard state with
  `resume_entrypoint`.
- (historical) `build_report_package(...)` assembled report metadata directly in
  the pipeline path. Current runtime uses `agents["report_writer"].run(...)`.
- `validate_pipeline_data(...)` produces the final `pipeline_data`.
- Long-term memory consolidation via `consolidate_role_patterns`.
- `export_run(...)` writes all artifacts to `artifacts/runs/<run_id>/`.

---

## Where `open_questions` and `next_steps` Are Produced Today

### open_questions
- `ShortTermMemoryStore` collects `open_questions` from worker reports
  (`record_worker_report`).
- `build_quality_review` reads `memory_snapshot["open_questions"]` and
  merges with `open_points` into `open_gaps`.
- `build_report_package` exposes `open_gaps` from quality review.
- `ResolutionController` reads `open_questions` from department
  `raw_package` to classify public gaps.

### next_steps
- `build_synthesis_context` reads `memory_snapshot["next_actions"]` and
  exposes them as `next_steps` in the synthesis context.
- Synthesis AG2 output may contain `next_steps`.
- PDF report (`pdf_report.py`) renders `synthesis["next_steps"]`.
- UI (`app.py`) renders `synthesis["next_steps"]`.

### Current limitation
Both `open_questions` and `next_steps` appear in **successful** run outputs.
There is no gate that prevents a run from being marked `meeting_ready` while
publicly researchable meeting-critical questions remain in `open_questions`.

---

## Current Exports and Checkpoints

Artifacts written to `artifacts/runs/<run_id>/`:

| File | Content |
|------|---------|
| `run_meta.json` | Run metadata, status, timing, cost, unresolved classes |
| `chat_history.json` | Full message trace |
| `pipeline_data.json` | Validated structured research output |
| `run_context.json` | Supervisor brief, task statuses, department packages, department run states, answer matrix, question registry, resolution state |
| `memory_snapshot.json` | Short-term memory snapshot |
| `follow_up_history.json` | Follow-up Q&A (when applicable) |

Checkpointing is **end-only** — no intermediate checkpoints exist during
the run. If the process crashes mid-run, no partial state is recoverable.

---

## Current UI Behavior

- **New run:** User enters company name + web domain → `run_pipeline()`.
- **Progress:** Live message stream via `on_message` callback.
- **Results:** Briefing tab (recommendation, meeting prep, contacts),
  detailed research per section, synthesis with `next_steps`.
- **Follow-up:** User enters `run_id` + question → routed to correct
  department via `follow_up.py`.
- **PDF download:** German + English briefings via `pdf_report.py`.
- **No dashboard:** No UI for user depth selections or pause/resume.
- **No resume:** Once a run completes or fails, it cannot be resumed.

---

## Current Meeting-Readiness Limitations

1. **No meeting-readiness gate enforced.** `determine_final_status` exists
   but does not block export when public gaps remain if `readiness_usable`
   is True.
2. **`open_questions` in success output.** Successful runs may contain
   unresolved publicly researchable questions in the final output.
3. **`next_steps` as generic leftovers.** The `next_steps` field contains
   a mix of actionable meeting prep and unresolved research items.
4. **No pause/resume.** `needs_user_selection` status is persisted but
   `resume_pipeline()` does not exist.
5. **No structured evidence production.** Departments produce narrative
   section reports; evidence packets are extracted post-hoc via legacy
   conversion, not produced natively by workers.
6. **End-only checkpointing.** No intermediate state is recoverable.

---

## Baseline Run Artifacts

- Baseline run ID: `baseline_run_20260329`
- Location: `tests/golden/runs/baseline_run_20260329/`
- Files: `run_meta.json`, `run_context.json`, `pipeline_data.json`,
  `memory_snapshot.json`

## Quality References

- `tests/golden/quality_reference/answer_matrix_reference.json`
- `tests/golden/quality_reference/resolution_buckets_reference.json`
- `tests/golden/quality_reference/deep_research_quality_excerpt.md`
- `tests/golden/quality_reference/deep_research_quality_rubric.md`
