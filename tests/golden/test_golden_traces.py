"""RA-09: Golden-trace regression tests.

These tests verify that the baseline run artifacts conform to the expected
contract shape and that changes to the runtime model are detected.
"""
from __future__ import annotations

import json
from pathlib import Path

GOLDEN_DIR = Path("tests/golden")
BASELINE_DIR = GOLDEN_DIR / "runs" / "baseline_run_20260329"


# ---------------------------------------------------------------------------
# Contract shape regression: run_meta.json
# ---------------------------------------------------------------------------

def test_golden_run_meta_has_required_keys() -> None:
    meta = json.loads((BASELINE_DIR / "run_meta.json").read_text(encoding="utf-8"))
    assert "run_id" in meta
    assert "status" in meta
    assert meta["status"] in {
        "meeting_ready", "discovery_ready_not_execution_ready", "blocked_not_meeting_ready", "needs_user_selection",
        "completed", "completed_partial", "completed_but_not_usable", "failed",
    }


def test_golden_run_meta_unresolved_only_allowed_classes() -> None:
    meta = json.loads((BASELINE_DIR / "run_meta.json").read_text(encoding="utf-8"))
    unresolved = meta.get("unresolved", {})
    allowed = {"customer_confirmation_items", "optional_depth_not_selected"}
    for key in unresolved:
        assert key in allowed, f"Unexpected unresolved class in golden run_meta: {key}"


# ---------------------------------------------------------------------------
# Contract shape regression: run_context.json
# ---------------------------------------------------------------------------

def test_golden_run_context_has_answer_matrix() -> None:
    ctx = json.loads((BASELINE_DIR / "run_context.json").read_text(encoding="utf-8"))
    assert "answer_matrix" in ctx
    matrix = ctx["answer_matrix"]
    assert isinstance(matrix, dict)
    for qid, entry in matrix.items():
        assert qid.startswith("q_"), f"Question ID must start with q_: {qid}"
        assert "status" in entry


def test_golden_run_context_has_resolution_state() -> None:
    ctx = json.loads((BASELINE_DIR / "run_context.json").read_text(encoding="utf-8"))
    assert "resolution_state" in ctx
    rs = ctx["resolution_state"]
    assert "resume_entrypoint" in rs
    assert "first_round_resolution" in rs
    assert "bucket" in rs["first_round_resolution"]


def test_golden_run_context_answer_matrix_statuses_are_canonical() -> None:
    ctx = json.loads((BASELINE_DIR / "run_context.json").read_text(encoding="utf-8"))
    canonical = {"answered", "partially_answered", "blocked", "pending"}
    for qid, entry in ctx.get("answer_matrix", {}).items():
        assert entry["status"] in canonical, (
            f"Non-canonical answer status '{entry['status']}' for {qid}"
        )


# ---------------------------------------------------------------------------
# Contract shape regression: pipeline_data.json
# ---------------------------------------------------------------------------

def test_golden_pipeline_data_has_all_sections() -> None:
    pd = json.loads((BASELINE_DIR / "pipeline_data.json").read_text(encoding="utf-8"))
    required = {
        "company_profile", "industry_analysis", "market_network",
        "contact_intelligence", "quality_review", "synthesis",
        "research_readiness",
    }
    for section in required:
        assert section in pd, f"Missing section in golden pipeline_data: {section}"


def test_golden_pipeline_data_synthesis_has_generation_mode() -> None:
    pd = json.loads((BASELINE_DIR / "pipeline_data.json").read_text(encoding="utf-8"))
    synthesis = pd.get("synthesis", {})
    assert "generation_mode" in synthesis
    assert synthesis["generation_mode"] in {"normal", "fallback", "blocked"}


def test_golden_pipeline_data_readiness_has_usable() -> None:
    pd = json.loads((BASELINE_DIR / "pipeline_data.json").read_text(encoding="utf-8"))
    readiness = pd.get("research_readiness", {})
    assert "usable" in readiness
    assert isinstance(readiness["usable"], bool)


# ---------------------------------------------------------------------------
# Quality reference regression
# ---------------------------------------------------------------------------

def test_golden_answer_matrix_reference_covers_key_questions() -> None:
    ref = json.loads(
        (GOLDEN_DIR / "quality_reference" / "answer_matrix_reference.json")
        .read_text(encoding="utf-8")
    )
    assert "q_company_fundamentals" in ref
    assert ref["q_company_fundamentals"] == "answered"


def test_golden_resolution_buckets_reference_has_all_buckets() -> None:
    ref = json.loads(
        (GOLDEN_DIR / "quality_reference" / "resolution_buckets_reference.json")
        .read_text(encoding="utf-8")
    )
    expected_buckets = {
        "AUTO_CLOSE_REQUIRED",
        "USER_DECISION_REQUIRED",
        "CUSTOMER_CONFIRMATION_REQUIRED",
        "NOT_MEETING_CRITICAL",
        "BLOCKING_FAILURE",
    }
    actual_values = set(ref.values())
    assert expected_buckets == actual_values, (
        f"Resolution bucket reference drift: expected {expected_buckets}, got {actual_values}"
    )
