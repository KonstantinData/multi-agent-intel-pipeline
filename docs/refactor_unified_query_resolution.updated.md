# Refactoring: Unified Query Resolution Pipeline

**Status:** Planned (revised after code review)
**Branch:** `refactor/unified-query-resolution`
**Goal:** Consolidate the currently fragmented query-generation logic into a single, deterministic, testable query-resolution path without changing business intent.
**Description:** This refactoring is based on a code-level review of the current pipeline. Its purpose is to centralize runtime query resolution, preserve existing search behavior during migration, and remove misleading configuration drift. It also corrects earlier assumptions that were too absolute or factually inaccurate: the current YAML `search_patterns_*` are not executed as runtime queries, but they are also not injected into the Lead prompt verbatim; runtime safety is not yet “loud only” because department profile loading still contains silent fallback behavior; and a migration cannot require strict golden parity while simultaneously changing query merge semantics.

---

## Why this refactoring is necessary

The research pipeline currently has multiple, only partially aligned places that influence search-query construction.

1. The `knowledge/sources/*.yaml` files contain `search_patterns_de` and `search_patterns_en` per source record. These patterns are loaded as part of source-profile metadata, but they are **not executed as runtime search queries**. They also do **not** get injected into the Lead prompt verbatim. As of the current code, the Lead prompt only receives selected source metadata such as source name, priority, and evidence type.

2. `src/research/search.py` contains hardcoded query builders (`build_company_queries`, `build_market_queries`, `build_buyer_queries`). These are not the single runtime authority. They are used only where `worker.py` explicitly calls them.

3. `src/agents/worker.py` contains task-specific runtime query logic in `_build_queries()`. This is currently the effective orchestration path for most executed queries.

The result is architectural drift:

- search behavior is not driven from one deterministic contract,
- configuration suggests flexibility that does not fully exist,
- migration and regression testing are harder than necessary,
- changes to search strategy still require Python edits in operational code.

This refactoring solves the problem by introducing **one central query-resolution layer** for runtime queries while keeping **source metadata** and **query strategy** as separate concerns.

---

## Current state (verified)

| #  | Concern                                              | Location                                      | Current behavior                                                                                       |
| -- | ---------------------------------------------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| 1  | Source metadata, including `search_patterns_de/en`   | `knowledge/sources/*.yaml`                    | Loaded as source-profile data; not executed as runtime queries                                         |
| 2  | `build_company_queries()`, `build_buyer_queries()`   | `src/research/search.py`                      | Partially active — called explicitly from `_build_queries()` for specific task keys                    |
| 3  | `build_market_queries()`                             | `src/research/search.py`                      | Registered in `tools.py`; **not called** in the `_build_queries()` runtime path                        |
| 4  | Task-specific query construction                     | `src/agents/worker.py::_build_queries()`      | Effective runtime construction path for the queries executed by research tasks                         |
| 5  | Department profile fallback                          | `src/orchestration/department_knowledge.py`   | Still contains silent fallback behavior via `_DEFAULT_SOURCE_PROFILES`                                 |

### Important factual corrections

- The YAML `search_patterns_*` are currently **dead with respect to executed runtime queries**.
- They are **not** currently injected into the Lead prompt as concrete prose patterns.
- The current system is **not yet free of silent fallback**, because department profile loading can still fall back to `_DEFAULT_SOURCE_PROFILES` when file loading/parsing fails.

---

## Design principle for the target state

The target state should not mix two different responsibilities into one file format.

### Responsibility 1 — Source metadata

This remains in:

```text
knowledge/sources/*.yaml
```

Purpose:

- source registry,
- source priority,
- evidence type,
- source-level guidance for planning,
- optional provenance notes.

### Responsibility 2 — Runtime query strategy

This should live in a dedicated layer, for example:

```text
knowledge/query_strategies/*.yaml
```

Purpose:

- per-task query templates,
- placeholder vocabulary,
- runtime fallback queries,
- task-specific query expansion rules.

This separation keeps the architecture cleaner, easier to validate, and less tightly coupled.

---

## Target state

```text
knowledge/sources/*.yaml                 → source metadata for planning and evidence weighting
knowledge/query_strategies/*.yaml        → runtime query templates per task
src/research/query_resolver.py           → placeholder expansion, validation, deterministic resolution
src/agents/worker.py::_build_queries()   → delegates to resolver
worker._search_queries()                 → cache, limits, dedup, execution sequencing
perform_search()                         → OpenAI web search execution
```

### Target properties

- One authoritative runtime query-resolution path
- Query text becomes declarative and testable
- Python remains responsible for runtime concerns:
  - placeholder expansion,
  - validation,
  - guardrails,
  - dynamic per-buyer expansion,
  - deterministic ordering,
  - compatibility behavior during migration
- Source metadata and query strategy remain decoupled
- Migration preserves existing behavior first; improvements come only after parity is established

---

## Affected files

| File | Change type |
| ---- | ----------- |
| `knowledge/sources/company.yaml` | keep as source metadata only |
| `knowledge/sources/market.yaml` | keep as source metadata only |
| `knowledge/sources/buyer.yaml` | keep as source metadata only |
| `knowledge/sources/contact.yaml` | keep as source metadata only |
| `knowledge/query_strategies/company.yaml` | **new**: task-level runtime query strategies |
| `knowledge/query_strategies/market.yaml` | **new**: task-level runtime query strategies |
| `knowledge/query_strategies/buyer.yaml` | **new**: task-level runtime query strategies |
| `knowledge/query_strategies/contact.yaml` | **new**: task-level runtime query strategies |
| `src/research/query_resolver.py` | **new**: central runtime query resolver |
| `src/agents/worker.py` | refactor: replace query construction with resolver call |
| `src/research/search.py` | cleanup: deprecate legacy query builders after parity |
| `src/orchestration/department_knowledge.py` | harden: remove or gate silent fallback behavior |
| `src/agents/lead.py` | minimal: wording only if needed; no claim that search patterns are injected |
| `preflight.py` | extend: validate query-strategy files and placeholder contracts |
| `tests/` | extend: parity tests, consistency tests, strict failure tests |

---

## Explicitly out of scope

- `perform_search()` in `search.py`
- `_search_queries()` in `worker.py` (cache, limits, sequencing)
- `_QUERY_LIMITS` in `worker.py`
- policy YAMLs (`knowledge/policies/*.yaml`)
- LLM synthesis prompts in `worker.py._llm_synthesis()`
- report, synthesis, and meeting-readiness logic

---

## Task-key-to-department mapping (reference)

From `use_cases.py:STANDARD_TASK_BACKLOG`:

| task_key | Department | target_section |
|----------|-----------|----------------|
| `company_fundamentals` | CompanyDepartment | company_profile |
| `economic_commercial_situation` | CompanyDepartment | company_profile |
| `financial_deep_dive` | CompanyDepartment | company_profile |
| `product_asset_scope` | CompanyDepartment | company_profile |
| `transaction_event_intelligence` | CompanyDepartment | company_profile |
| `market_situation` | MarketDepartment | industry_analysis |
| `peer_companies` | BuyerDepartment | market_network |
| `monetization_redeployment` | BuyerDepartment | market_network |
| `contact_discovery` | ContactDepartment | contact_intelligence |
| `target_company_contacts` | ContactDepartment | contact_intelligence |
| `contact_qualification` | ContactDepartment | contact_intelligence |

---

## Placeholder contract

To avoid mixed placeholder dialects, the query-strategy layer should define **one canonical placeholder vocabulary**.

### Canonical placeholders

| Placeholder | Substitution | Source |
|-------------|-------------|--------|
| `{company}` | `brief.company_name` | SupervisorBrief |
| `{domain}` | `brief.normalized_domain` | SupervisorBrief |
| `{industry}` | `infer_industry()` result | research/extract.py |
| `{keywords}` | `extract_product_keywords()[:3]` joined | research/extract.py |
| `{buyer}` | buyer candidate name | `current_section.buyer_candidates` |

### Placeholder format migration

The existing `knowledge/sources/*.yaml` files use **angle-bracket syntax** for their `search_patterns_de/en` entries (e.g. `<firma>`, `<company>`, `<branche>`). The new query-strategy files will use **curly-brace syntax** (e.g. `{company}`, `{industry}`).

This is not only a vocabulary alias change — it is a format migration. Both concerns must be handled together:

- angle-bracket patterns from source metadata are **not** inputs to the resolver; they are provenance notes only and must not be processed as templates
- any content copied from old YAML files into `knowledge/query_strategies/*.yaml` must be rewritten to curly-brace format as part of Phase 1
- the consistency test (Phase 8) must validate that no angle-bracket patterns exist in strategy files

### Migration compatibility for vocabulary aliases

During migration, the resolver may temporarily normalize legacy German aliases if strategy file content is copied from the old pattern format:

- `{firma}` → `{company}`
- `{branche}` → `{industry}`
- `{produktkategorie}` → `{keywords}`

This normalization is a **temporary migration guard only** — a safety net for content accidentally carried over from legacy YAML entries during Phase 1. It is not a permanent feature of the resolver and must not be treated as a supported input format. Once Phase 1 content has been reviewed and rewritten to canonical form, the alias shim should be removed. The target schema accepts only canonical curly-brace placeholders; the consistency test in Phase 8 enforces this permanently.

---

## `query_overrides` semantics (current Ist-Code)

The current behavior is defined by a single line in `worker.py`:

```python
queries = query_overrides or self._build_queries(brief=brief, task_key=task_key, ...)
```

This means:

| Value passed      | Runtime behavior                                                    |
| ----------------- | ------------------------------------------------------------------- |
| `None`            | standard path → `_build_queries()`                                  |
| `[]` (empty list) | standard path → `_build_queries()` (falsy, treated like `None`)     |
| non-empty list    | override path → list used directly, `_build_queries()` skipped      |

`[]` is currently **not** a signal for “use no queries” — it silently falls through to the standard path. This is the Ist-behavior.

### Open design decision for the refactor

The resolver must decide explicitly whether to preserve this semantics or tighten it:

- **Option A (preserve):** `resolve_queries()` uses the same `or`-idiom; `[]` routes to template resolution. No behavior change.
- **Option B (strict):** `resolve_queries()` checks `query_overrides is not None`; `[]` would return an empty list. This is a behavior change and must be flagged.

This decision must be made before Phase 2 begins, not discovered during parity testing.

---

## Migration rule: preserve behavior first

A crucial constraint for this refactoring:

> The first resolver-based implementation must preserve current runtime behavior as closely as possible.

That means:

- no automatic semantic expansion beyond current behavior,
- no language-order changes that alter which queries survive limits,
- no “better” merging logic in the first migration step unless parity impact is explicitly accepted.

### Consequence

If the migration requires a golden-trace assertion of exact order and content, then the resolver **must not** simultaneously introduce a new default rule such as “merge `queries_de` + `queries_en` with DE first”.

That kind of behavioral improvement belongs in a later phase, after runtime parity has been proven and intentionally relaxed.

---

## Checklist

### Phase 0 — Preparation

- [ ] **0.1** Create branch `refactor/unified-query-resolution` from `refactor-architecture`
- [ ] **0.2** Confirm baseline: `pytest` + `python preflight.py` green
- [ ] **0.3** Record current query output: for each of the 11 task keys, capture current `_build_queries()` output with a fixed test brief and save as a golden fixture
- [ ] **0.4** Record current behavior for `query_overrides` semantics (`None`, `[]`, non-empty list)

### Phase 1 — Introduce dedicated query-strategy files

- [ ] **1.1** Create `knowledge/query_strategies/company.yaml`
- [ ] **1.2** Create `knowledge/query_strategies/market.yaml`
- [ ] **1.3** Create `knowledge/query_strategies/buyer.yaml`
- [ ] **1.4** Create `knowledge/query_strategies/contact.yaml`
- [ ] **1.5** Encode existing runtime behavior from `worker.py` into these files without intentional behavior change
- [ ] **1.6** Rewrite any content copied from legacy `search_patterns_de/en` entries: replace `<angle_bracket>` placeholder syntax with canonical `{curly_brace}` syntax (e.g. `<firma>` → `{company}`, `<branche>` → `{industry}`)
- [ ] **1.7** Keep `knowledge/sources/*.yaml` unchanged as source metadata
- [ ] **1.8** Decide file format explicitly:
  - [ ] either rename to `.json` if JSON parsing remains the intended contract,
  - [ ] or switch to real YAML parsing if `.yaml` is the intended contract

### Phase 2 — Implement `query_resolver.py`

- [ ] **2.1** Create file `src/research/query_resolver.py`
- [ ] **2.2** Implement `resolve_queries()` with a contract tied to task execution:

  ```python
  def resolve_queries(
      task_key: str,
      brief: SupervisorBrief,
      *,
      query_overrides: list[str] | None = None,
      current_section: dict[str, Any] | None = None,
  ) -> list[str]:
  ```

- [ ] **2.3** Core logic:
  - [ ] Preserve current `query_overrides` semantics exactly
  - [ ] Resolve owning department from the task contract or task-to-department mapping
  - [ ] Load query strategy for the resolved department
  - [ ] Read task entry for `task_key`
  - [ ] If missing: raise explicit error
  - [ ] Apply temporary migration alias normalization before strict placeholder validation, only for migration-mode inputs (e.g. `{firma}` → `{company}`, `{branche}` → `{industry}`)
  - [ ] Expand canonical placeholders deterministically
  - [ ] Apply task-specific runtime expansion rules
  - [ ] Return queries in parity-preserving order

- [ ] **2.4** Special logic for `contact_discovery` / `contact_qualification`:
  - [ ] Expand `{buyer}` per candidate from `current_section.buyer_candidates`
  - [ ] Preserve current fallback behavior when no buyer candidates exist

- [ ] **2.5** Unit tests for `resolve_queries()`:
  - [ ] known task key → correct queries
  - [ ] unknown task key → explicit error
  - [ ] `query_overrides` semantics preserved
  - [ ] empty `buyer_candidates` → correct fallback behavior
  - [ ] unknown placeholder → explicit validation error

### Phase 3 — Runtime parity safeguard

- [ ] **3.1** Create test `tests/test_query_migration.py`
- [ ] **3.2** For each of the 11 task keys:
  - [ ] define a fixed `SupervisorBrief` fixture
  - [ ] call legacy `_build_queries()` → expected query list
  - [ ] call `resolve_queries()` → actual query list
  - [ ] assert exact parity for content and order in migration mode
- [ ] **3.3** Migration does not proceed until parity is green

### Phase 4 — Refactor `worker.py`

- [ ] **4.1** Rename current `_build_queries()` to `_build_queries_legacy()`
- [ ] **4.2** Implement new `_build_queries()` as a resolver delegation
- [ ] **4.3** Avoid passing a separate `department` constructor parameter unless required; derive department from task contract to prevent task/department drift
- [ ] **4.4** Add temporary verify mode:
  - [ ] env var `LIQUISTO_QUERY_RESOLVER_VERIFY=1`
  - [ ] run both paths and log divergence
- [ ] **4.5** `pytest` must stay green
- [ ] **4.6** parity test from Phase 3 must stay green

### Phase 5 — Harden profile loading

- [ ] **5.1** Remove or strictly gate silent fallback in `load_department_source_profile()`
- [ ] **5.2** Ensure broken or unparsable files fail loudly in strict mode
- [ ] **5.3** Add tests that verify no silent fallback masks malformed runtime configuration

### Phase 6 — Clean up `search.py`

- [ ] **6.1** Deprecate `build_company_queries()` — currently called for `company_fundamentals`, `product_asset_scope` task keys
- [ ] **6.2** Deprecate `build_buyer_queries()` — currently called for `peer_companies` and as fallback for `monetization_redeployment`
- [ ] **6.3** Deprecate `build_market_queries()` — imported but **not called** in the current runtime path; lowest-risk removal candidate
- [ ] **6.4** Remove direct calls from `worker.py` only after parity-based migration is complete

### Phase 7 — Extend preflight checks

- [ ] **7.1** Validate query-strategy files (`knowledge/query_strategies/*.yaml`) independently of source metadata:
  - [ ] parse succeeds
  - [ ] every task key has an entry
  - [ ] every entry contains at least one query template
  - [ ] placeholder set is valid (curly-brace canonical form only)
  - [ ] no angle-bracket placeholders remain (`<...>` → hard preflight failure)
- [ ] **7.2** Validate source metadata (`knowledge/sources/*.yaml`) independently — source metadata failures must not block query-strategy validation
- [ ] **7.3** `python preflight.py` must fail loudly on any malformed strategy file — zero silent fallback is the hard requirement for this layer (unlike source profiles, which are governed separately by Phase 5)

### Phase 8 — Permanent consistency tests

- [ ] **8.1** Create test `tests/test_query_consistency.py`
- [ ] **8.2** For each research task:
  - [ ] owning strategy entry exists
  - [ ] placeholder set is valid (only canonical `{curly_brace}` placeholders)
  - [ ] no angle-bracket placeholders remain in any strategy file (`<firma>`, `<company>`, etc.)
  - [ ] no empty task strategy exists
- [ ] **8.3** Add strict tests for task-to-department resolution

### Phase 9 — Optional post-parity improvements

> Only after exact migration parity has been achieved and validated.

- [ ] **9.1** Decide whether bilingual query expansion should change from parity mode to an intentionally improved mode
- [ ] **9.2** If yes, introduce such changes explicitly and document them as a behavior change
- [ ] **9.3** Replace parity tests with approved expected-behavior tests where appropriate

### Phase 10 — Remove legacy code

> Prerequisite: successful validation of the new path in real runs.

- [ ] **10.1** Remove `_build_queries_legacy()`
- [ ] **10.2** Remove parallel verify mode
- [ ] **10.3** Remove legacy query builders from `search.py`
- [ ] **10.4** Remove unused imports and migration scaffolding
- [ ] **10.5** `pytest` and `python preflight.py` both green

### Phase 11 — Finalization

- [ ] **11.1** Update README with the final query-resolution architecture
- [ ] **11.2** Document query-strategy schema and placeholder contract
- [ ] **11.3** Commit and open PR with migration notes and risk summary

---

## Risk mitigation (summary)

| Risk | Safeguard | When it triggers |
|------|-----------|-----------------|
| Query migration accidentally changes runtime behavior | parity fixture + verify mode | on `pytest` and during migration runs |
| Malformed strategy file | preflight + strict runtime validation | before run and at runtime |
| New task without strategy entry | consistency test + explicit runtime error | on `pytest` and at runtime |
| Placeholder typo | placeholder validation test + resolver validation | on `pytest` and at runtime |
| Angle-bracket syntax in strategy files | preflight + consistency test | on `pytest` and before run |
| Task-to-department drift | explicit mapping tests | on `pytest` |
| Broken department profile hidden by fallback | strict-mode tests for profile loading (Phase 5) | on `pytest` and at runtime |

### Error model separation

Two configuration layers have deliberately different failure contracts:

**`knowledge/query_strategies/*.yaml` (new layer)**
Zero silent fallback. A missing file, unparsable content, or missing task entry must raise an explicit error immediately. No default is acceptable — these files are the single runtime authority for query construction.

**`knowledge/sources/*.yaml` + `department_knowledge.py` (existing layer)**
Currently still contains silent fallback via `_DEFAULT_SOURCE_PROFILES`. This is a pre-existing problem addressed in Phase 5 (hardening), not automatically fixed by the resolver introduction. Until Phase 5 is complete, source-profile loading remains partially soft.

Introducing `query_resolver.py` does **not** close the source-profile fallback gap. The two layers must be hardened independently.

---

## Effort estimate

| Phase | Estimated effort |
|-------|-----------------|
| Phase 0 — Preparation | 30 min |
| Phase 1 — Strategy files | 1.5 h |
| Phase 2 — Resolver | 45 min |
| Phase 3 — Parity tests | 45 min – 2 h (volatile: depends on undocumented edge-case behavior in `_build_queries()`) |
| Phase 4 — Worker refactor | 45 min |
| Phase 5 — Fallback hardening | 30 min |
| Phase 6 — Legacy cleanup prep | 15 min |
| Phase 7 — Preflight | 20 min |
| Phase 8 — Consistency tests | 20 min |
| Phase 9 — Optional improvements | variable |
| Phase 10 — Legacy removal | 15 min |
| Phase 11 — Finalization | 20 min |
| **Total (through parity migration)** | **~6–8 h** (best case ~5.5 h if no parity divergences surface) |

---

## Final recommendation

Proceed with the refactoring, but do it under these constraints:

1. **Separate source metadata from runtime query strategy.**
2. **Preserve behavior first; improve behavior later.**
3. **Do not claim loud-failure guarantees until fallback paths are actually hardened.**
4. **Use one canonical placeholder contract.**
5. **Keep the resolver tied to the task contract, not to loosely injected department state where avoidable.**

This yields a cleaner and more truthful design than the earlier draft while preserving the same business objective: a deterministic, centrally governed, production-ready query-resolution pipeline.
