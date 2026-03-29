# Refactor Architecture Audit — Sequential TRUE/FALSE Gatekeeper (Finalized 2026 Edition)

## Purpose

This file is the **strict audit protocol** for `refactor-architecture.md`.
After each RA section, the auditor must determine whether the repository has implemented the required behavior strongly enough to proceed.
The implementation agent may continue to the next section **only if the audit result is `TRUE`**.

This audit exists to prevent:

- doc-only refactors,
- prompt-only refactors,
- schema-only changes with no runtime effect,
- cosmetic renaming,
- dead-code architecture,
- and partial implementation being treated as complete.

---

## Global Audit Rules

The auditor must evaluate the **actual repository runtime behavior**, not the stated intent.

The auditor must verify, where relevant:

- code symbols and imports
- live runtime wiring
- state transitions
- persistence and snapshots
- export behavior
- UI behavior
- tests
- compatibility handling
- documentation only when the section explicitly requires it

If behavior is claimed but not wired into the active runtime path, the result must be `FALSE`.

If evidence is ambiguous, under-tested, dead, or partial, the result must be `FALSE`.

---

## Non-Negotiable Audit Prohibitions

Do **not** return `TRUE` merely because:
- a file exists,
- a schema exists,
- a prompt changed,
- a doc changed,
- names were renamed,
- a TODO promises later completion,
- or a new structure exists but is not used.

Do **not** infer missing behavior charitably.

Do **not** treat legacy fields as acceptable success-path truth once the section requires the new model to be authoritative.

---

## Required Audit Method

For every section under audit, the auditor must:

1. Read the matching section in `refactor-architecture.md`.
2. Inspect the expected files and symbols.
3. Trace the live runtime path (`run_pipeline`, and where relevant `resume_pipeline`).
4. Inspect persistence and export outputs.
5. Inspect tests for behavior-level coverage.
6. Inspect whether compatibility logic is acceptable for that stage.
7. Return only the required output format.

When useful, the auditor should cite evidence by:
- file path,
- symbol name,
- call path,
- exported field,
- and test path.

---

## Required Audit Output Format

### If the section passes
```text
TRUE
<section_id>
<one short paragraph explaining the strongest evidence paths: file + symbol + wiring + persistence/export + test>
```

### If the section fails
```text
FALSE
<section_id>
1. <first concrete failure>
2. <second concrete failure>
3. <third concrete failure>
```

No other format is allowed.

---

## Master Audit Prompt Template

```text
You are a strict repository refactor auditor.

Audit target:
- repo root: <REPO_ROOT>
- governing implementation file: refactor-architecture.md
- governing audit file: refactor-architecture-audit.md
- section under audit: <SECTION_ID>

Your job is to determine whether section <SECTION_ID> has been implemented completely enough that the implementation agent may continue to the next section.

Audit rules:
1. Inspect code, runtime wiring, persistence paths (run_context.json / pipeline_data.json), exporters, UI behavior, and tests relevant to <SECTION_ID>.
2. Do not accept doc-only, prompt-only, schema-only, or dead-code changes.
3. Do not accept partial implementation.
4. Do not infer missing behavior charitably.
5. Use the section-specific pass/fail rules from refactor-architecture-audit.md.
6. Prefer FALSE when ambiguous, under-tested, or not wired into the live run path.
7. Return the result in the exact required output format and nothing else.

Now audit section <SECTION_ID>.
```

---

## Common Evidence Checklist (apply to every section)

Before `TRUE`, verify all relevant items for that section:

- expected files exist
- expected symbols exist
- symbols are reachable from the live runtime path
- new state is persisted in `RunContext.snapshot()` / `ShortTermMemoryStore.snapshot()` when relevant
- exports expose the required new contracts when relevant
- UI has behavior impact when relevant
- tests verify behavior, not just construction
- legacy drift is controlled, not silently authoritative

If any required dimension is missing, return `FALSE`.

---

# Section-Specific Audit Gates

## Audit Prompt RA-00

### Pass conditions

- `docs/refactor_baseline.md` exists and describes the current live runtime concretely.
- `tests/golden/runs/...` contains a minimal baseline run snapshot.
- `tests/golden/quality_reference/deep_research_quality_excerpt.md` exists.
- `tests/golden/quality_reference/deep_research_quality_rubric.md` exists and is clearly derived from the deep research report quality target.
- At least one meaningful baseline drift / contract regression test exists.

### Fail conditions

- Baseline is generic prose with no concrete runtime paths.
- No deep-research-derived quality anchor exists.
- No meaningful drift guard exists.

### Gate prompt
Use Master Audit Prompt Template with `SECTION_ID = RA-00`.

---

## Audit Prompt RA-01

### Pass conditions

- `src/models/meeting_ready.py` contains the required typed contracts.
- `RunContext` contains the new top-level state and exports it in `snapshot()`.
- `ShortTermMemoryStore` contains and exports the new meeting-ready state.
- If legacy fields remain live, deterministic compatibility conversion exists and is explicitly marked temporary.

### Fail conditions

- Contracts exist but are not persisted.
- Snapshot wiring is missing.
- Legacy fields remain authoritative without compatibility controls.

### Gate prompt
Use Master Audit Prompt Template with `SECTION_ID = RA-01`.

---

## Audit Prompt RA-02

### Pass conditions

- A meeting-question catalog exists as a single source of truth.
- Tasks map deterministically to `question_ids`.
- Question Registry and Answer Matrix are created before department execution.
- They are persisted into run state.
- Supervisor/runtime updates answer state based on real department outcomes.
- At least one real run snapshot shows non-empty answer-state updates.

### Fail conditions

- Registry exists only as constants or docs.
- Matrix is initialized but never updated.
- Task-to-question mapping is missing or non-deterministic.

### Gate prompt
Use Master Audit Prompt Template with `SECTION_ID = RA-02`.

---

## Audit Prompt RA-03

### Pass conditions

- Department output contracts now include evidence packets, gap candidates, and answer updates.
- `src/agents/worker.py` produces structured evidence packets per task.
- `src/agents/lead.py` persists evidence packets and typed gap candidates.
- Departments are clearly implemented as question-coverage contributors rather than final-briefing owners.
- Narrative summaries may still exist, but closure/readiness no longer depends on them as authoritative truth.

### Fail conditions

- Evidence structures exist only on paper.
- Gap candidates are still raw string lists.
- Answer updates are not wired from department outputs.
- Departments still behave as section-briefing owners in runtime-critical logic.

### Gate prompt
Use Master Audit Prompt Template with `SECTION_ID = RA-03`.

---

## Audit Prompt RA-04

### Pass conditions

- `ResolutionController` exists and is wired into the active run flow after first-pass department execution.
- Gap classification maps every unresolved issue into one of the required five classes.
- `AUTO_CLOSE_REQUIRED` gaps trigger bounded targeted follow-up research.
- Closure events update evidence, gaps, and answer state.
- Public meeting-critical unresolved gaps block finalization.
- Stop reasons and closure bounds are persisted.

### Fail conditions

- Controller exists but is dead code.
- Gap classification is incomplete or not exclusive.
- Follow-up research is not actually triggered.
- Finalization can still succeed despite unresolved public meeting-critical gaps.

### Gate prompt
Use Master Audit Prompt Template with `SECTION_ID = RA-04`.

---

## Audit Prompt RA-05

### Pass conditions

- Runs can pause into `needs_user_selection` with persisted dashboard state and resolution plan.
- `resume_pipeline(...)` exists and is used to continue the live runtime.
- UI dashboard changes runtime behavior by persisting and applying user depth decisions.
- Finalization remains blocked without required dashboard decisions.

### Fail conditions

- Dashboard is visual only.
- Resume path is missing or not wired.
- User decisions have no behavior impact.
- The run can finalize without required dashboard input.

### Gate prompt
Use Master Audit Prompt Template with `SECTION_ID = RA-05`.

---

## Audit Prompt RA-06

### Pass conditions

- `MeetingReadinessGate` exists and is enforced in the success path.
- `FinalBriefingComposer` exists and is used in successful finalization.
- Success outputs contain `meeting_actions` as the primary action output.
- Successful outputs do not contain a generic unresolved `open_questions` block.
- Remaining unresolved items are correctly reclassified as `customer_confirmation_items` or `optional_depth_not_selected`.

### Fail conditions

- Legacy `next_steps` or `open_questions` remain the effective success-path action model.
- Readiness is evaluated but not enforced.
- Final briefing is not derived from answer state / evidence / resolution decisions.

### Gate prompt
Use Master Audit Prompt Template with `SECTION_ID = RA-06`.

---

## Audit Prompt RA-07

### Pass conditions

- Exports include the new meeting-ready state.
- Follow-up uses answer matrix and evidence packets as primary grounding.
- Typed updates from follow-up are persisted.
- Phase-aware checkpoints exist across the main runtime phases.

### Fail conditions

- Exports omit critical new state.
- Follow-up still relies primarily on legacy shapes.
- Checkpointing is end-only or incomplete.

### Gate prompt
Use Master Audit Prompt Template with `SECTION_ID = RA-07`.

---

## Audit Prompt RA-08

### Pass conditions

- Structured outputs are enforced for runtime-consumed structured artifacts.
- Budgets are phase-aware and persisted.
- Stop reasons are explicit and exported.
- Deterministic ordering rules exist.
- Seed-enabled reproducibility mode exists where supported.
- Resolution timeline / guardrail telemetry is observable.

### Fail conditions

- Structured outputs are only described in prompts or docs.
- Budgets exist only as constants with no runtime persistence.
- Stop reasons are missing.
- Ordering remains unstable.

### Gate prompt
Use Master Audit Prompt Template with `SECTION_ID = RA-08`.

---

## Audit Prompt RA-09

### Pass conditions

- Behavior tests cover:
  - registry creation
  - answer matrix updates
  - resolution controller behavior
  - dashboard pause/resume
  - final briefing composition
  - meeting-readiness gate
- Negative paths are tested.
- Golden-trace regression tests exist and are meaningful.

### Fail conditions

- Tests are mostly constructor or shallow snapshot tests.
- Negative paths are missing.
- Golden traces are not actually enforced.

### Gate prompt
Use Master Audit Prompt Template with `SECTION_ID = RA-09`.

---

## Audit Prompt RA-10

### Pass conditions

- Docs and diagrams reflect the final live runtime flow.
- Remaining compatibility support is explicit and limited.
- Success-path docs no longer present unresolved open questions as a normal outcome.
- Legacy drift has been removed or clearly isolated.

### Fail conditions

- Docs describe architecture not implemented in code.
- Compat logic remains broad and undocumented.
- Legacy success-path wording survives.

### Gate prompt
Use Master Audit Prompt Template with `SECTION_ID = RA-10`.

---

## Final Completion Rule

The refactor is complete only when **every section from RA-00 through RA-10 has passed with `TRUE`**.
Anything less is still in progress.
