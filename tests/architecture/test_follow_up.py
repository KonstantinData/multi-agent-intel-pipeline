"""Pure architecture tests for follow-up answer routing.

Validates answer_follow_up() per department route.
Uses tmp_path for file I/O — NO AG2/autogen dependency.
"""
from __future__ import annotations

from src.models.schemas import empty_pipeline_data


def _make_pipeline_data():
    data = empty_pipeline_data()
    data["company_profile"]["company_name"] = "TestCo"
    data["company_profile"]["description"] = "A test company"
    data["company_profile"]["economic_situation"]["assessment"] = "Stable"
    data["industry_analysis"]["assessment"] = "Growing market"
    data["industry_analysis"]["demand_outlook"] = "Positive"
    data["market_network"]["peer_competitors"]["assessment"] = "Competitive"
    data["market_network"]["downstream_buyers"]["assessment"] = "Active"
    data["contact_intelligence"]["narrative_summary"] = "3 contacts found"
    data["contact_intelligence"]["coverage_quality"] = "medium"
    data["synthesis"]["executive_summary"] = "Strong opportunity"
    data["synthesis"]["opportunity_assessment_summary"] = "Excess inventory path"
    return data


def _make_run_context():
    return {
        "short_term_memory": {
            "department_packages": {
                "CompanyDepartment": {"open_questions": ["Q1"]},
                "MarketDepartment": {"open_questions": ["Q2"]},
                "BuyerDepartment": {"open_questions": ["Q3"]},
                "ContactDepartment": {"open_questions": ["Q4"]},
                "SynthesisDepartment": {"opportunity_assessment": "test"},
            },
            "department_run_states": {},
        }
    }


def test_follow_up_company_route(tmp_path):
    from src.orchestration.follow_up import answer_follow_up
    import src.orchestration.follow_up as fu_mod
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()
    original_runs = fu_mod.RUNS_DIR
    fu_mod.RUNS_DIR = tmp_path
    try:
        result = answer_follow_up(
            run_id="test_run", route="CompanyDepartment",
            question="What does the company do?",
            pipeline_data=_make_pipeline_data(), run_context=_make_run_context(),
        )
        assert result["routed_to"] == "CompanyDepartment"
        assert "TestCo" in result["answer"]
    finally:
        fu_mod.RUNS_DIR = original_runs


def test_follow_up_market_route(tmp_path):
    from src.orchestration.follow_up import answer_follow_up
    import src.orchestration.follow_up as fu_mod
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()
    original_runs = fu_mod.RUNS_DIR
    fu_mod.RUNS_DIR = tmp_path
    try:
        result = answer_follow_up(
            run_id="test_run", route="MarketDepartment",
            question="Market outlook?",
            pipeline_data=_make_pipeline_data(), run_context=_make_run_context(),
        )
        assert result["routed_to"] == "MarketDepartment"
        assert "Positive" in result["answer"]
    finally:
        fu_mod.RUNS_DIR = original_runs


def test_follow_up_buyer_route(tmp_path):
    from src.orchestration.follow_up import answer_follow_up
    import src.orchestration.follow_up as fu_mod
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()
    original_runs = fu_mod.RUNS_DIR
    fu_mod.RUNS_DIR = tmp_path
    try:
        result = answer_follow_up(
            run_id="test_run", route="BuyerDepartment",
            question="Who are the buyers?",
            pipeline_data=_make_pipeline_data(), run_context=_make_run_context(),
        )
        assert result["routed_to"] == "BuyerDepartment"
        assert "Competitive" in result["answer"] or "Active" in result["answer"]
    finally:
        fu_mod.RUNS_DIR = original_runs


def test_follow_up_contact_route(tmp_path):
    from src.orchestration.follow_up import answer_follow_up
    import src.orchestration.follow_up as fu_mod
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()
    original_runs = fu_mod.RUNS_DIR
    fu_mod.RUNS_DIR = tmp_path
    try:
        result = answer_follow_up(
            run_id="test_run", route="ContactDepartment",
            question="Who are the contacts?",
            pipeline_data=_make_pipeline_data(), run_context=_make_run_context(),
        )
        assert result["routed_to"] == "ContactDepartment"
        assert "3 contacts" in result["answer"]
    finally:
        fu_mod.RUNS_DIR = original_runs


def test_follow_up_synthesis_route(tmp_path):
    from src.orchestration.follow_up import answer_follow_up
    import src.orchestration.follow_up as fu_mod
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()
    original_runs = fu_mod.RUNS_DIR
    fu_mod.RUNS_DIR = tmp_path
    try:
        result = answer_follow_up(
            run_id="test_run", route="SynthesisDepartment",
            question="What is the opportunity?",
            pipeline_data=_make_pipeline_data(), run_context=_make_run_context(),
        )
        assert result["routed_to"] == "SynthesisDepartment"
        assert "Strong opportunity" in result["answer"] or "Excess" in result["answer"]
    finally:
        fu_mod.RUNS_DIR = original_runs


def test_follow_up_unknown_route_defaults_to_company(tmp_path):
    from src.orchestration.follow_up import answer_follow_up
    import src.orchestration.follow_up as fu_mod
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()
    original_runs = fu_mod.RUNS_DIR
    fu_mod.RUNS_DIR = tmp_path
    try:
        result = answer_follow_up(
            run_id="test_run", route="UnknownDepartment",
            question="Random question",
            pipeline_data=_make_pipeline_data(), run_context=_make_run_context(),
        )
        assert result["routed_to"] == "CompanyDepartment"
    finally:
        fu_mod.RUNS_DIR = original_runs


def test_long_term_store_has_lock(tmp_path):
    from src.memory.long_term_store import FileLongTermMemoryStore
    store = FileLongTermMemoryStore(tmp_path / "memory.json")
    assert hasattr(store, "_lock")
    store.upsert_strategy({"name": "test_pattern", "score": 1.0})
    items = store.load()
    assert len(items) == 1
    assert items[0]["name"] == "test_pattern"


def test_long_term_store_concurrent_writes(tmp_path):
    from src.memory.long_term_store import FileLongTermMemoryStore
    path = tmp_path / "shared.json"
    store_a = FileLongTermMemoryStore(path)
    store_b = FileLongTermMemoryStore(path)
    store_a.upsert_strategy({"name": "pattern_a", "score": 1.0})
    store_b.upsert_strategy({"name": "pattern_b", "score": 2.0})
    items = store_a.load()
    names = {item["name"] for item in items}
    assert "pattern_a" in names
    assert "pattern_b" in names
