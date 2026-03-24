"""Pure architecture tests for memory boundaries and consolidation.

Validates:
- ShortTermMemoryStore run brain (department_run_states)
- Consolidation process-safety (no company names in patterns)
- Memory policy boundaries

NO AG2/autogen dependency.
"""
from __future__ import annotations

from src.memory.short_term_store import ShortTermMemoryStore
from src.memory.consolidation import (
    consolidate_role_patterns,
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
