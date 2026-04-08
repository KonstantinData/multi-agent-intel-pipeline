# Refactoring: Unified Query Resolution Pipeline

**Status:** Planned
**Branch:** `refactor/unified-query-resolution`
**Goal:** Consolidate three decoupled query sources (YAML search_patterns, search.py hardcoded, worker.py hardcoded) into a single, YAML-driven query resolution path.

---

## Why this refactoring is necessary

The research pipeline has a structural problem: there are **three independent locations** that produce search queries — and they know nothing about each other.

1. The `knowledge/sources/*.yaml` files contain `search_patterns_de` and `search_patterns_en` per source record. At runtime these patterns are loaded and injected into the Lead agent's system prompt as prose guidance. **No code ever executes them as actual search queries.** They are dead configuration.

2. `src/research/search.py` contains three hardcoded query builders (`build_company_queries`, `build_market_queries`, `build_buyer_queries`). The worker calls them partially, but they have no awareness of the YAML files.

3. `src/agents/worker.py` contains ~130 lines of task-specific, hardcoded query templates in `_build_queries()`. **This is the only path that actually produces search queries.** It neither reads the YAMLs nor uses the builders from `search.py` consistently.

The result: changing a search strategy requires touching Python code. The YAML files suggest configurability that does not exist. New sources or patterns added to the YAMLs have **zero effect** on actual search behavior. The three sources partially contradict each other.

This refactoring solves the problem by introducing **a single query resolution path**: the YAML files become the single source of truth, a new module (`query_resolver.py`) substitutes placeholders and delivers ready-to-use queries, and the worker delegates entirely to this path. After completion: new search strategy = YAML change, no code deploy.

---

## Current state (problem)

| # | Source | Location | Actually executed? |
|---|--------|----------|--------------------|
| 1 | `search_patterns_de/en` | `knowledge/sources/*.yaml` | **No** — only lands as prose in the Lead prompt (`lead.py:363-370`) |
| 2 | `build_company_queries()` etc. | `src/research/search.py:76-117` | Partially — only when `worker.py._build_queries()` calls them |
| 3 | Task-specific queries | `src/agents/worker.py._build_queries()` (~130 lines) | **Yes** — this is the real path |

The YAML `search_patterns_de/en` are dead configuration. The actual queries are scattered across hardcoded Python.

## Target state

```
knowledge/sources/*.yaml  →  resolve_queries()  →  worker._search_queries()  →  perform_search()
     (task_queries)           (placeholder sub)       (cache, limits, dedup)      (OpenAI web_search)
```

- YAMLs = single source of truth for search strategies
- Python no longer builds queries — only substitutes placeholders
- New sources/patterns = YAML change only, no code deploy

---

## Affected files

| File | Change type |
|------|-------------|
| `knowledge/sources/company.yaml` | Extend: add `task_queries` |
| `knowledge/sources/market.yaml` | Extend: add `task_queries` |
| `knowledge/sources/buyer.yaml` | Extend: add `task_queries` |
| `knowledge/sources/contact.yaml` | Extend: add `task_queries` |
| `src/research/query_resolver.py` | **New**: central query resolution path |
| `src/agents/worker.py` | Refactor: replace `_build_queries()` |
| `src/research/search.py` | Cleanup: deprecate `build_*_queries()` |
| `src/orchestration/department_knowledge.py` | Extend: sync `_DEFAULT_SOURCE_PROFILES` |
| `src/agents/lead.py` | Minimal: adjust Lead prompt guidance |
| `preflight.py` | Extend: YAML consistency check |
| `tests/` | Extend: golden-trace + consistency tests |

## Explicitly out of scope

- `perform_search()` in `search.py` — unchanged
- `_search_queries()` in `worker.py` — unchanged (cache, limits, dedup)
- `_QUERY_LIMITS` in `worker.py` — unchanged
- Policy YAMLs (`knowledge/policies/*.yaml`)
- LLM synthesis prompts in `worker.py._llm_synthesis()`
- Report/Synthesis/Meeting-Readiness layer

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

## Placeholder vocabulary

| Placeholder | Substitution | Source |
|-------------|-------------|--------|
| `{firma}` | `brief.company_name` | SupervisorBrief |
| `{company}` | `brief.company_name` | SupervisorBrief |
| `{domain}` | `brief.normalized_domain` | SupervisorBrief |
| `{branche}` | `infer_industry()` result | research/extract.py |
| `{industry}` | `infer_industry()` result | research/extract.py |
| `{produktkategorie}` | `extract_product_keywords()[:3]` joined | research/extract.py |
| `{keywords}` | `extract_product_keywords()[:3]` joined | research/extract.py |
| `{buyer}` | Buyer candidate name (loop) | current_section.buyer_candidates |

---

## Checklist

### Phase 0 — Preparation

- [ ] **0.1** Create branch `refactor/unified-query-resolution` from `refactor-architecture`
- [ ] **0.2** Confirm baseline: `pytest` (381 tests) + `python preflight.py` green
- [ ] **0.3** Record current query output: for each of the 11 task keys, capture the current `_build_queries()` output with a fixed test brief and save as `tests/fixtures/golden_queries.json`

### Phase 1 — Extend YAML schema (`task_queries`)

- [ ] **1.1** `knowledge/sources/company.yaml` — add `task_queries` block with entries for:
  - [ ] `company_fundamentals` (current: `build_company_queries()` + site queries)
  - [ ] `economic_commercial_situation` (current: 9 hardcoded queries in `worker.py:749-757`)
  - [ ] `financial_deep_dive` (current: 14 hardcoded queries in `worker.py:759-772`)
  - [ ] `product_asset_scope` (current: `build_company_queries()` + 2 additional queries)
  - [ ] `transaction_event_intelligence` (current: 8 hardcoded queries in `worker.py:785-792`)
- [ ] **1.2** `knowledge/sources/market.yaml` — add `task_queries` block with entries for:
  - [ ] `market_situation` (current: 4 hardcoded queries in `worker.py:800-804`)
- [ ] **1.3** `knowledge/sources/buyer.yaml` — add `task_queries` block with entries for:
  - [ ] `peer_companies` (current: 4 peer queries + `build_buyer_queries()` in `worker.py:873-878`)
  - [ ] `monetization_redeployment` (current: 7 hardcoded queries in `worker.py:884-890`)
- [ ] **1.4** `knowledge/sources/contact.yaml` — add `task_queries` block with entries for:
  - [ ] `contact_discovery` (current: dynamic from `buyer_candidates` in `worker.py:808-845`)
  - [ ] `target_company_contacts` (current: 13 hardcoded queries in `worker.py:847-859`)
  - [ ] `contact_qualification` (current: same logic as `contact_discovery`)
- [ ] **1.5** JSON-validate all 4 YAML files: `python -c "import json; json.loads(open(f).read())"` for each file
- [ ] **1.6** Sync `_DEFAULT_SOURCE_PROFILES` in `department_knowledge.py` with the new `task_queries`

### Phase 2 — Implement `query_resolver.py`

- [ ] **2.1** Create file `src/research/query_resolver.py`
- [ ] **2.2** Implement `resolve_queries()` with signature:
  ```python
  def resolve_queries(
      department: str,
      task_key: str,
      brief: SupervisorBrief,
      *,
      query_overrides: list[str] | None = None,
      current_section: dict[str, Any] | None = None,
  ) -> list[str]:
  ```
- [ ] **2.3** Implement core logic:
  - [ ] If `query_overrides` present → return directly (CodingSpecialist path)
  - [ ] Call `load_department_source_profile(department)`
  - [ ] Read `task_queries[task_key]`
  - [ ] If no entry: raise `KeyError` with clear message (no silent fallback)
  - [ ] Merge `queries_de` + `queries_en` (DE first)
  - [ ] Substitute placeholders (see vocabulary above)
  - [ ] Deduplicate
- [ ] **2.4** Special logic for `contact_discovery` / `contact_qualification`:
  - [ ] `{buyer}` placeholder is expanded per loop over `current_section.buyer_candidates`
  - [ ] Each buyer candidate generates N queries from the template
  - [ ] Fallback queries when no buyer candidates are available
- [ ] **2.5** Unit tests for `resolve_queries()`:
  - [ ] Test: known task key → correct queries with substituted placeholders
  - [ ] Test: unknown task key → `KeyError` with helpful message
  - [ ] Test: `query_overrides` → passed through unchanged
  - [ ] Test: empty `buyer_candidates` on contact tasks → fallback queries

### Phase 3 — Golden-trace safeguard

- [ ] **3.1** Create test `tests/test_query_migration.py`
- [ ] **3.2** For each of the 11 task keys:
  - [ ] Define a fixed `SupervisorBrief` as fixture (company_name, domain, industry_hint, product_keywords)
  - [ ] Call old `_build_queries()` with this brief → expected query list
  - [ ] Call new `resolve_queries()` with the same brief → actual query list
  - [ ] Assert: lists are **identical** (order + content)
- [ ] **3.3** Golden-trace test must be green **before** Phase 4 begins

### Phase 4 — Refactor `worker.py`

- [ ] **4.1** Extend `ResearchWorker.__init__()`: add `department` parameter
  - [ ] Update all callers in `lead.py`: `self.worker = ResearchWorker(self.researcher_name, department=self.department)`
- [ ] **4.2** Rename existing `_build_queries()` to `_build_queries_legacy()`
- [ ] **4.3** Implement new `_build_queries()`:
  ```python
  def _build_queries(self, *, brief, task_key, current_section=None):
      from src.research.query_resolver import resolve_queries
      return resolve_queries(
          department=self._department,
          task_key=task_key,
          brief=brief,
          current_section=current_section,
      )
  ```
- [ ] **4.4** Add parallel-run mode (temporary):
  - [ ] Env variable `LIQUISTO_QUERY_RESOLVER_VERIFY=1`
  - [ ] When set: both paths run, divergences are logged as warnings
  - [ ] When not set: new path only
- [ ] **4.5** Run `pytest` — all 381+ tests must pass
- [ ] **4.6** Golden-trace test from Phase 3 must still pass

### Phase 5 — Clean up `search.py`

- [ ] **5.1** Add deprecation warning to `build_company_queries()`
- [ ] **5.2** Add deprecation warning to `build_market_queries()`
- [ ] **5.3** Add deprecation warning to `build_buyer_queries()`
- [ ] **5.4** Remove all direct calls to these functions in `worker.py` (no longer needed since `_build_queries()` now routes through `resolve_queries()`)
- [ ] **5.5** `pytest` — all tests green

### Phase 6 — Extend preflight check

- [ ] **6.1** Extend `preflight.py`: load all 4 source YAMLs and verify:
  - [ ] JSON parsing succeeds
  - [ ] `task_queries` key exists
  - [ ] Every task key from `STANDARD_TASK_BACKLOG` (filtered by department) has an entry in `task_queries`
  - [ ] Every entry has at least `queries_de` OR `queries_en` with ≥1 query
- [ ] **6.2** `python preflight.py` must pass

### Phase 7 — Consistency test (permanent)

- [ ] **7.1** Create test `tests/test_query_consistency.py`:
  - [ ] Extract all task keys from `STANDARD_TASK_BACKLOG` (11 research tasks, excluding synthesis)
  - [ ] For each task key: verify that `load_department_source_profile(department)["task_queries"][task_key]` exists
  - [ ] For each entry: verify that `queries_de` or `queries_en` is not empty
  - [ ] For each query string: verify that only known placeholders are used (`{firma}`, `{company}`, `{domain}`, `{branche}`, `{industry}`, `{produktkategorie}`, `{keywords}`, `{buyer}`)
- [ ] **7.2** This test runs on every `pytest` and catches missing YAML entries when new tasks are added

### Phase 8 — Adjust Lead prompt

- [ ] **8.1** `lead.py:build_investigation_plan()` — `recommended_sources` stays (source metadata for the Lead)
- [ ] **8.2** Lead system prompt: adjust "Source knowledge base" section — clarify that source guidance is informational, queries are centrally controlled
- [ ] **8.3** Existing `search_patterns_de/en` in source records remain as provenance metadata (no deletion)

### Phase 9 — Remove legacy code

> **Prerequisite:** At least one successful production run with the new path.

- [ ] **9.1** Remove `_build_queries_legacy()` from `worker.py`
- [ ] **9.2** Remove parallel-run code (`LIQUISTO_QUERY_RESOLVER_VERIFY`)
- [ ] **9.3** Remove `build_company_queries()`, `build_market_queries()`, `build_buyer_queries()` from `search.py`
- [ ] **9.4** Remove all imports of these functions in `worker.py`
- [ ] **9.5** `pytest` — all tests green
- [ ] **9.6** `python preflight.py` — green

### Phase 10 — Finalization

- [ ] **10.1** `pytest` — all tests green (target: 381+ tests)
- [ ] **10.2** `python preflight.py` — green
- [ ] **10.3** Update README: document query resolution architecture
- [ ] **10.4** Update `prompts/quality_gate_designer.md`: document `task_queries` schema
- [ ] **10.5** Commit + push
- [ ] **10.6** Create PR with change summary

---

## Risk mitigation (summary)

| Risk | Safeguard | When it triggers |
|------|-----------|-----------------|
| YAML broken / unparsable | Preflight check (Phase 6) + `RuntimeError` in `resolve_queries()` | Before run + at runtime |
| New task without YAML entry | `KeyError` in `resolve_queries()` + consistency test (Phase 7) | On `pytest` + at runtime |
| Query migration changes search behavior | Golden-trace test (Phase 3) + parallel-run mode (Phase 4.4) | On `pytest` + on first production run |
| Placeholder typo in YAML | Consistency test validates allowed placeholders (Phase 7.1) | On `pytest` |

**No risk is masked by a silent fallback. Every failure is loud.**

---

## Effort estimate

| Phase | Estimated effort |
|-------|-----------------|
| Phase 0 — Preparation | 30 min |
| Phase 1 — Extend YAMLs | 1.5 h |
| Phase 2 — query_resolver.py | 45 min |
| Phase 3 — Golden-trace | 45 min |
| Phase 4 — worker.py refactor | 1 h |
| Phase 5 — Clean up search.py | 15 min |
| Phase 6 — Preflight | 20 min |
| Phase 7 — Consistency test | 20 min |
| Phase 8 — Lead prompt | 15 min |
| Phase 9 — Remove legacy | 15 min (after production run) |
| Phase 10 — Finalization | 20 min |
| **Total** | **~6 h** |
