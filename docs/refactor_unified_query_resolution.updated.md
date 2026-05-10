# Unified Query Resolution Pipeline

**Status:** Implemented  
**Current owner modules:** `src/research/query_resolver.py`, `src/agents/worker.py`  
**Strategy files:** `knowledge/query_strategies/*.yaml`  
**Last reviewed:** 2026-05-03

## Purpose

This document records the current query-resolution architecture after the
unified resolver migration. It supersedes the earlier planning checklist that
described the resolver, strategy files, and parity tests as future work.

The runtime now has one central query-resolution path for research tasks:

```text
knowledge/query_strategies/*.yaml
    -> src/research/query_resolver.py
    -> src/agents/worker.py::_build_queries()
    -> worker._search_queries()
    -> src/research/search.py::perform_search()
```

Source metadata and runtime query strategy are deliberately separate.

```text
knowledge/sources/*.yaml          source registry metadata only
knowledge/policies/*.yaml         department acceptance policy
knowledge/query_strategies/*.yaml runtime query templates per task
```

## Current Implementation

### Strategy Files

The runtime strategy files exist for all four domain departments:

| File | Scope |
| --- | --- |
| `knowledge/query_strategies/company.yaml` | Company tasks |
| `knowledge/query_strategies/market.yaml` | Market tasks |
| `knowledge/query_strategies/buyer.yaml` | Buyer and redeployment tasks |
| `knowledge/query_strategies/contact.yaml` | Contact discovery and qualification tasks |

Important implementation detail: these files currently use a `.yaml` extension
but contain JSON and are parsed with `json.loads()` in
`src/research/query_resolver.py`. Do not switch the file syntax to YAML unless
the parser, tests, and preflight checks are changed at the same time.

### Resolver

`src/research/query_resolver.py` is the single runtime authority for task query
construction. It:

- maps task keys to owning department strategy files;
- loads and caches strategy files;
- expands canonical placeholders;
- validates query templates and overrides;
- expands buyer-specific contact queries;
- preserves legacy `query_overrides` behavior;
- exposes strategy validation for preflight and tests;
- supports verify mode through `LIQUISTO_QUERY_RESOLVER_VERIFY=1`.

The resolver has a zero-silent-fallback error model:

| Failure | Behavior |
| --- | --- |
| Missing strategy file | `FileNotFoundError` |
| Empty or unparsable strategy file | `ValueError` |
| Missing task entry | `KeyError` |
| Unknown placeholder | `ValueError` |
| Legacy angle-bracket placeholder | `ValueError` |

### Worker Integration

`ResearchWorker._build_queries()` delegates to `resolve_queries()`.

`ResearchWorker._build_queries_legacy()` is still present as a compatibility and
verification path. When `LIQUISTO_QUERY_RESOLVER_VERIFY=1`, the worker computes
both resolver and legacy query lists and logs divergences.

The legacy path should not be extended with new behavior. New query behavior
belongs in `knowledge/query_strategies/*.yaml` and `query_resolver.py`.

## Task Coverage

The resolver covers the 11 standard research tasks:

| Task key | Department strategy |
| --- | --- |
| `company_fundamentals` | company |
| `economic_commercial_situation` | company |
| `financial_deep_dive` | company |
| `product_asset_scope` | company |
| `transaction_event_intelligence` | company |
| `market_situation` | market |
| `peer_companies` | buyer |
| `monetization_redeployment` | buyer |
| `contact_discovery` | contact |
| `target_company_contacts` | contact |
| `contact_qualification` | contact |

Every strategy task key must appear in the resolver mapping, and every mapped
task must have a strategy entry.

## Placeholder Contract

Strategy templates use canonical curly-brace placeholders only:

| Placeholder | Meaning |
| --- | --- |
| `{company}` | `SupervisorBrief.company_name` |
| `{domain}` | `SupervisorBrief.normalized_domain` |
| `{industry}` | inferred industry from homepage/title/metadata |
| `{keywords}` | extracted product keywords joined into a short query string |
| `{buyer}` | buyer candidate name for contact expansion |

Forbidden in strategy files:

- angle-bracket placeholders such as `<firma>` or `<company>`;
- unknown placeholders such as `{branche}` or `{target}`;
- empty task strategies;
- runtime query templates in `knowledge/sources/*.yaml`.

`query_resolver.py` still contains a temporary migration alias shim for some
legacy German placeholder names, but permanent consistency tests enforce
canonical placeholders in the strategy files. Treat the shim as defensive
compatibility, not as supported strategy syntax.

## Query Override Semantics

The resolver intentionally preserves the legacy `query_overrides` behavior:

| Value | Runtime behavior |
| --- | --- |
| `None` | Resolve from strategy file |
| `[]` | Resolve from strategy file because an empty list is falsy |
| Non-empty list | Validate and use the override list directly |

Overrides may be concrete queries or canonical placeholder templates. Empty
strings, unknown placeholders, and angle-bracket placeholders are rejected.

## Contact Query Expansion

`contact_discovery` and `contact_qualification` expand `{buyer}` per buyer
candidate from `current_section["buyer_candidates"]`.

Accepted buyer candidate shapes:

- plain string firm names;
- dictionaries with `company_name`;
- dictionaries with `name`.

Invalid placeholder-like candidates such as `n/v`, `n/a`, `target_company`, or
dot-path strings are ignored. If no valid buyer candidates exist, the contact
strategy falls back to industry-scoped queries.

## Validation and Tests

The implemented guardrails are:

| Check | Location |
| --- | --- |
| Strategy file existence and content validation in preflight | `preflight.py` |
| Resolver-vs-legacy parity tests | `tests/test_query_migration.py` |
| Permanent strategy structure tests | `tests/test_query_consistency.py` |
| Source KB contains no runtime query templates | `tests/test_query_consistency.py` |
| Query override semantics and validation | `tests/test_query_migration.py` |
| Unknown task key failure | `tests/test_query_migration.py` |

Expected focused validation:

```bash
python preflight.py
pytest -q tests/test_query_migration.py tests/test_query_consistency.py
```

Full CI also runs architecture, runtime-contract, smoke, governance, SBOM, and
AI-BOM gates.

## Current Migration State

Completed:

- dedicated query strategy files exist;
- `query_resolver.py` exists and is used by the worker;
- parity tests exist;
- consistency tests exist;
- preflight validates strategy files;
- source KB query-pattern drift is guarded by tests;
- verify mode exists for divergence monitoring.

Still intentionally retained:

- `ResearchWorker._build_queries_legacy()` for parity and verify mode;
- old helper builders in `src/research/search.py` for legacy path support;
- temporary placeholder alias normalization inside the resolver.

Cleanup candidates after enough real-run confidence:

1. remove `_build_queries_legacy()` from `ResearchWorker`;
2. remove `LIQUISTO_QUERY_RESOLVER_VERIFY`;
3. remove legacy query builders from `src/research/search.py` if no other caller
   still uses them;
4. remove the temporary migration alias shim from `query_resolver.py`;
5. either rename strategy files to `.json` or switch to a real YAML parser.

## Maintenance Rules

- Add new research tasks by updating the task-to-department mapping,
  the owning strategy file, and consistency tests together.
- Do not put executable query templates in `knowledge/sources/*.yaml`.
- Keep strategy file syntax JSON-compatible until parser behavior changes.
- Preserve deterministic query ordering because query caps make order observable.
- Treat resolver validation failures as configuration defects, not soft warnings.
- Update `README.md`, `AGENTS.md`, and `docs/drawio/target_runtime_architecture.md`
  when query ownership or placeholder semantics change.
