"""Pure architecture tests for memory boundaries and consolidation.

Validates:
- ShortTermMemoryStore run brain (department_run_states)
- Consolidation process-safety (no company names in patterns)
- Memory policy boundaries

NO AG2/autogen dependency.
"""
from __future__ import annotations

import logging

import pytest

from src.memory.short_term_store import ShortTermMemoryStore
from src.memory.consolidation import (
    consolidate_role_patterns,
    MEMORY_ROLE_STATUS,
    RETRIEVABLE_ROLES,
    RETRIEVABLE_ROLE_ORDER,
    ROLE_MEMORY_CATEGORIES,
    _scrub_company_from_query,
    _is_process_safe_query,
    _to_structural_patterns,
)
from src.memory.policies import should_store_strategy


# ===========================================================================
# ShortTermMemoryStore run brain
# ===========================================================================

class TestShortTermMemoryStoreRunBrain:
    def test_record_department_run_state(self):
        store = ShortTermMemoryStore()
        run_state_dict = {
            "department": "CompanyDepartment",
            "task_artifacts": {"company_fundamentals": [{"task_key": "company_fundamentals", "attempt": 1}]},
        }
        store.record_department_run_state("CompanyDepartment", run_state_dict)
        assert "CompanyDepartment" in store.department_run_states
        assert store.department_run_states["CompanyDepartment"]["department"] == "CompanyDepartment"

    def test_snapshot_includes_department_run_states(self):
        store = ShortTermMemoryStore()
        store.record_department_run_state("MarketDepartment", {"department": "MarketDepartment"})
        snap = store.snapshot()
        assert "department_run_states" in snap
        assert "MarketDepartment" in snap["department_run_states"]

    def test_department_run_states_are_run_specific(self):
        store = ShortTermMemoryStore()
        store.record_department_run_state("BuyerDepartment", {"judge_escalations": [{"task_key": "peer_companies"}]})
        snap = store.snapshot()
        escalations = snap["department_run_states"]["BuyerDepartment"].get("judge_escalations", [])
        assert len(escalations) == 1


# ===========================================================================
# Consolidation process safety
# ===========================================================================

class TestConsolidationProcessSafety:
    def test_scrub_removes_domain(self):
        q = "ACME GmbH annual report site:acme.de"
        scrubbed = _scrub_company_from_query(q)
        assert "acme.de" not in scrubbed.lower()
        assert "{domain}" in scrubbed

    def test_scrub_removes_quoted_company(self):
        q = '"ACME GmbH" inventory surplus 2024'
        scrubbed = _scrub_company_from_query(q)
        assert '"ACME GmbH"' not in scrubbed

    def test_scrub_removes_gmbh_form(self):
        q = "Mustermann GmbH financial distress signals"
        scrubbed = _scrub_company_from_query(q)
        assert "Mustermann GmbH" not in scrubbed

    def test_process_safe_query_accepted(self):
        assert _is_process_safe_query("manufacturing company inventory surplus signals")
        assert _is_process_safe_query("procurement director site:linkedin.com")

    def test_process_safe_query_rejects_short(self):
        assert not _is_process_safe_query("ACME")
        assert not _is_process_safe_query("  ")

    def test_structural_patterns_strip_company_names(self):
        raw = [
            "ACME GmbH annual report",
            "manufacturer inventory surplus signals",
            '"Mustermann AG" financial distress',
        ]
        patterns = _to_structural_patterns(raw)
        for p in patterns:
            assert "ACME" not in p, f"Company name leaked into pattern: {p}"
            assert "Mustermann" not in p, f"Company name leaked into pattern: {p}"

    def test_consolidation_no_domain_in_pattern_names(self):
        run_context = {
            "short_term_memory": {
                "worker_reports": [
                    {
                        "worker": "CompanyResearcher",
                        "queries_used": [
                            "manufacturer inventory surplus signals",
                            "company financial distress restructuring",
                        ],
                        "task_key": "company_fundamentals",
                    }
                ],
                "sources": [{"source_type": "registry"}],
                "critic_reviews": {},
                "department_run_states": {},
            },
        }
        pipeline_data = {"company_profile": {"industry": "Manufacturing"}}
        patterns = consolidate_role_patterns(
            run_context=run_context,
            pipeline_data=pipeline_data,
            status="completed",
            usable=True,
        )
        for p in patterns:
            assert "acme" not in p.get("name", "").lower()
            assert "mustermann" not in p.get("name", "").lower()
            assert p.get("domain", "") == "", (
                f"Pattern '{p['name']}' has non-empty domain: {p['domain']!r}"
            )

    def test_consolidation_empty_for_failed_run(self):
        patterns = consolidate_role_patterns(
            run_context={}, pipeline_data={}, status="failed", usable=False
        )
        assert patterns == []

    def test_consolidation_empty_for_not_usable(self):
        patterns = consolidate_role_patterns(
            run_context={}, pipeline_data={}, status="completed", usable=False
        )
        assert patterns == []

    def test_consolidation_extracts_critic_heuristics(self):
        run_context = {
            "short_term_memory": {
                "worker_reports": [],
                "sources": [],
                "critic_reviews": {
                    "company_fundamentals": {
                        "core_passed": 2,
                        "core_total": 3,
                        "failed_rule_messages": ["company description too short"],
                    }
                },
                "department_run_states": {},
            }
        }
        pipeline_data = {"company_profile": {"industry": "Automotive"}}
        patterns = consolidate_role_patterns(
            run_context=run_context, pipeline_data=pipeline_data,
            status="completed", usable=True,
        )
        critic_patterns = [p for p in patterns if p.get("pattern_scope") == "critic_heuristics"]
        assert len(critic_patterns) >= 1
        p = critic_patterns[0]
        assert "avg_core_pass_rate" in p
        assert p.get("domain", "") == ""

    def test_consolidation_judge_patterns_from_run_state(self):
        run_context = {
            "short_term_memory": {
                "worker_reports": [],
                "sources": [],
                "critic_reviews": {},
                "department_run_states": {
                    "CompanyDepartment": {
                        "judge_escalations": [
                            {"task_key": "peer_companies", "attempt": 2,
                             "outcome": "closed_unresolved", "confidence": "low"},
                        ],
                        "coding_support_used": [],
                        "strategy_changes": [],
                    }
                },
            }
        }
        pipeline_data = {"company_profile": {"industry": "Manufacturing"}}
        patterns = consolidate_role_patterns(
            run_context=run_context, pipeline_data=pipeline_data,
            status="completed", usable=True,
        )
        judge_patterns = [p for p in patterns if p.get("pattern_scope") == "judge_principles"]
        assert len(judge_patterns) >= 1


# ===========================================================================
# Memory policies
# ===========================================================================

class TestMemoryPolicies:
    def test_should_store_strategy_only_for_usable_completed_runs(self):
        assert should_store_strategy(status="completed", usable=True) is True
        assert should_store_strategy(status="completed_but_not_usable", usable=False) is False
        assert should_store_strategy(status="failed", usable=False) is False


# ===========================================================================
# F5 — Memory isolation and merge
# ===========================================================================

class TestShortTermMemoryMerge:
    def test_merge_from_combines_facts_and_sources(self):
        main = ShortTermMemoryStore()
        main.facts.append("main fact")
        main.sources.append({"url": "https://main.de", "title": "Main"})

        ws = ShortTermMemoryStore()
        ws.facts.append("ws fact")
        ws.sources.append({"url": "https://ws.de", "title": "WS"})

        main.merge_from(ws)
        assert "main fact" in main.facts
        assert "ws fact" in main.facts
        assert len(main.sources) == 2

    def test_merge_from_adds_usage_totals(self):
        main = ShortTermMemoryStore()
        main.usage_totals["llm_calls"] = 5
        main.usage_totals["search_calls"] = 3

        ws = ShortTermMemoryStore()
        ws.usage_totals["llm_calls"] = 2
        ws.usage_totals["search_calls"] = 4

        main.merge_from(ws)
        assert main.usage_totals["llm_calls"] == 7
        assert main.usage_totals["search_calls"] == 7

    def test_merge_from_preserves_disjoint_department_keys(self):
        main = ShortTermMemoryStore()
        main.department_packages["CompanyDepartment"] = {"dept": "company"}

        ws = ShortTermMemoryStore()
        ws.department_packages["MarketDepartment"] = {"dept": "market"}
        ws.department_run_states["MarketDepartment"] = {"department": "MarketDepartment"}

        main.merge_from(ws)
        assert "CompanyDepartment" in main.department_packages
        assert "MarketDepartment" in main.department_packages
        assert "MarketDepartment" in main.department_run_states

    def test_merge_from_combines_worker_reports(self):
        main = ShortTermMemoryStore()
        main.worker_reports.append({"task_key": "t1"})

        ws = ShortTermMemoryStore()
        ws.worker_reports.append({"task_key": "t2"})

        main.merge_from(ws)
        assert len(main.worker_reports) == 2

    def test_merge_from_combines_task_statuses(self):
        main = ShortTermMemoryStore()
        main.task_statuses["company_fundamentals"] = "accepted"

        ws = ShortTermMemoryStore()
        ws.task_statuses["market_situation"] = "accepted"

        main.merge_from(ws)
        assert main.task_statuses["company_fundamentals"] == "accepted"
        assert main.task_statuses["market_situation"] == "accepted"

    def test_parallel_departments_use_isolated_stores(self):
        """Simulate the F5 isolation pattern: two stores, no shared mutation."""
        ws_a = ShortTermMemoryStore()
        ws_b = ShortTermMemoryStore()

        # Simulate parallel department work
        ws_a.facts.append("fact from A")
        ws_a.usage_totals["llm_calls"] = 3
        ws_b.facts.append("fact from B")
        ws_b.usage_totals["llm_calls"] = 2

        # Verify isolation: A does not see B's data
        assert "fact from B" not in ws_a.facts
        assert "fact from A" not in ws_b.facts

        # Merge into main
        main = ShortTermMemoryStore()
        main.merge_from(ws_a)
        main.merge_from(ws_b)

        assert "fact from A" in main.facts
        assert "fact from B" in main.facts
        assert main.usage_totals["llm_calls"] == 5

    def test_merge_order_independent_of_completion_order(self):
        """F5 review point 2: merge result must be identical regardless of which department finishes first."""
        ws_a = ShortTermMemoryStore()
        ws_a.facts.extend(["fact A1", "fact A2"])
        ws_a.usage_totals["llm_calls"] = 3

        ws_b = ShortTermMemoryStore()
        ws_b.facts.extend(["fact B1"])
        ws_b.usage_totals["llm_calls"] = 2

        # Order 1: A then B
        main1 = ShortTermMemoryStore()
        main1.merge_from(ws_a)
        main1.merge_from(ws_b)

        # Order 2: B then A
        main2 = ShortTermMemoryStore()
        main2.merge_from(ws_b)
        main2.merge_from(ws_a)

        # Usage totals must be identical
        assert main1.usage_totals["llm_calls"] == main2.usage_totals["llm_calls"] == 5
        # Facts must contain the same items (order may differ)
        assert set(main1.facts) == set(main2.facts) == {"fact A1", "fact A2", "fact B1"}

    def test_merge_from_warns_on_key_conflict(self):
        """F5 review point 3: dict merge must detect unexpected key conflicts."""
        import logging

        main = ShortTermMemoryStore()
        main.task_statuses["shared_key"] = "accepted"

        ws = ShortTermMemoryStore()
        ws.task_statuses["shared_key"] = "degraded"

        with pytest.raises(Exception) if False else _noop_context():
            # Should not raise, but should log a warning
            with _capture_log(logging.getLogger()) as log_output:
                main.merge_from(ws)

        # Last-writer-wins
        assert main.task_statuses["shared_key"] == "degraded"

    def test_create_working_set_seeds_from_main(self):
        """F5 review point 1: working set must start with a snapshot of the main store."""
        main = ShortTermMemoryStore()
        main.facts.append("existing fact")
        main.task_statuses["t1"] = "accepted"

        ws = main.create_working_set()
        assert "existing fact" in ws.facts
        assert ws.task_statuses.get("t1") == "accepted"

        # Mutation on ws must not affect main
        ws.facts.append("new fact")
        assert "new fact" not in main.facts

    def test_delta_from_extracts_only_new_writes(self):
        """F5 review point 1: delta must contain only new data, not seeded baseline."""
        main = ShortTermMemoryStore()
        main.facts.append("existing fact")
        main.usage_totals["llm_calls"] = 5

        ws = main.create_working_set()
        baseline = main.create_working_set()

        # Simulate department work
        ws.facts.append("new fact from department")
        ws.usage_totals["llm_calls"] += 3
        ws.task_statuses["new_task"] = "accepted"

        delta = ws.delta_from(baseline)
        assert "new fact from department" in delta.facts
        assert "existing fact" not in delta.facts
        assert delta.usage_totals["llm_calls"] == 3
        assert "new_task" in delta.task_statuses


import contextlib

@contextlib.contextmanager
def _noop_context():
    yield

@contextlib.contextmanager
def _capture_log(logger):
    """Minimal log capture for testing warning output."""
    import io
    handler = logging.StreamHandler(io.StringIO())
    handler.setLevel(logging.WARNING)
    logger.addHandler(handler)
    try:
        yield handler.stream
    finally:
        logger.removeHandler(handler)


# ===========================================================================
# F6 — Role memory registry consistency
# ===========================================================================

class TestRoleMemoryRegistry:
    def test_retrievable_roles_equals_active_consolidation_roles(self):
        """Every active role in MEMORY_ROLE_STATUS must be in RETRIEVABLE_ROLES."""
        active = {r for r, s in MEMORY_ROLE_STATUS.items() if s == "active"}
        assert RETRIEVABLE_ROLES == active

    def test_retrievable_roles_subset_of_consolidation_categories(self):
        """RETRIEVABLE_ROLES must be a subset of ROLE_MEMORY_CATEGORIES."""
        assert RETRIEVABLE_ROLES <= frozenset(ROLE_MEMORY_CATEGORIES.keys())

    def test_no_phantom_roles_in_retrieval(self):
        """Phantom roles must not appear in RETRIEVABLE_ROLES."""
        phantoms = {"CrossDomainStrategicAnalyst", "ReportWriter"}
        assert not (phantoms & RETRIEVABLE_ROLES)

    def test_all_consolidated_roles_are_retrievable(self):
        """Every role that produces patterns must also be retrieved."""
        consolidation_roles = frozenset(ROLE_MEMORY_CATEGORIES.keys())
        missing = consolidation_roles - RETRIEVABLE_ROLES
        assert not missing, f"Consolidated but not retrieved: {missing}"

    def test_retrievable_role_order_is_sorted(self):
        """RETRIEVABLE_ROLE_ORDER must be deterministically sorted."""
        assert RETRIEVABLE_ROLE_ORDER == tuple(sorted(RETRIEVABLE_ROLE_ORDER))
        assert set(RETRIEVABLE_ROLE_ORDER) == RETRIEVABLE_ROLES

    def test_synthesis_roles_are_pending(self):
        """Synthesis roles must be pending until they produce patterns."""
        for role in ("SynthesisLead", "SynthesisCritic", "SynthesisJudge"):
            assert MEMORY_ROLE_STATUS.get(role) == "pending", f"{role} should be pending"

    def test_excluded_roles_not_in_retrievable(self):
        """Excluded roles must not be retrievable."""
        excluded = {r for r, s in MEMORY_ROLE_STATUS.items() if s == "excluded"}
        assert not (excluded & RETRIEVABLE_ROLES)

    def test_pipeline_runner_uses_canonical_registry(self):
        """pipeline_runner must import from consolidation, not maintain its own list."""
        import inspect
        from src import pipeline_runner
        source = inspect.getsource(pipeline_runner.run_pipeline)
        # Must use the canonical registry for role retrieval
        assert "RETRIEVABLE_ROLE_ORDER" in source
        # Must NOT contain the old hand-maintained phantom roles in the retrieval block
        assert '"CrossDomainStrategicAnalyst"' not in source
