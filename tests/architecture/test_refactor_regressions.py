from __future__ import annotations

import json
from pathlib import Path

from src.app.use_cases import (
    SELECTION_REQUIRED_RUN_STATUS,
    SUCCESS_RUN_STATUS,
    build_dashboard_state,
    build_resolution_plan,
    determine_final_status,
)
from src.exporters.json_export import _extract_export_unresolved, export_binary_artifact
from src.orchestration.meeting_questions import (
    build_initial_answer_matrix,
    matrix_status_for_task_status,
)
from src.orchestration.resolution_controller import ResolutionController
from src.orchestration.run_context import RunContext


def test_state_persistence_run_context_and_store_snapshot_roundtrip():
    ctx = RunContext(
        run_id="r-baseline",
        intake={"company_name": "ACME", "web_domain": "acme.example"},
    )
    ctx.answer_matrix = build_initial_answer_matrix()
    ctx.answer_matrix["q_company_fundamentals"]["status"] = "answered"
    ctx.short_term_memory.task_statuses["company_fundamentals"] = "accepted"
    ctx.short_term_memory.record_department_run_state(
        "CompanyDepartment", {"department": "CompanyDepartment", "task_artifacts": {}}
    )
    ctx.resolution_state = {
        "first_round_resolution": {"bucket": "NOT_MEETING_CRITICAL"},
        "resume_entrypoint": "supervisor_finalization_entrypoint",
    }

    snap = ctx.snapshot()
    restored = RunContext.from_snapshot(snap)

    assert restored.run_id == "r-baseline"
    assert restored.answer_matrix["q_company_fundamentals"]["status"] == "answered"
    assert restored.short_term_memory.task_statuses["company_fundamentals"] == "accepted"
    assert "CompanyDepartment" in restored.short_term_memory.department_run_states
    assert restored.resolution_state["resume_entrypoint"] == "supervisor_finalization_entrypoint"


def test_answer_matrix_lifecycle_from_task_status_mapping_and_initial_state():
    matrix = build_initial_answer_matrix()
    assert all(entry["status"] == "pending" for entry in matrix.values())

    assert matrix_status_for_task_status("accepted") == "answered"
    assert matrix_status_for_task_status("degraded") == "partially_answered"
    assert matrix_status_for_task_status("blocked") == "partially_answered"
    assert matrix_status_for_task_status("skipped") == "blocked"


def test_resolution_controller_classification_behavior_regression():
    controller = ResolutionController()
    result = controller.classify(
        sections={"company_profile": {}},
        department_packages={
            "CompanyDepartment": {
                "admission": {"decision": "accepted"},
                "raw_package": {"open_questions": ["Public revenue signal?"]},
            },
            "ContactDepartment": {
                "admission": {"decision": "accepted"},
                "raw_package": {"open_questions": []},
            },
        },
        answer_matrix={"q_company_fundamentals": {"status": "answered"}},
        task_statuses={"company_fundamentals": "accepted"},
    )

    assert result["bucket"] == "AUTO_CLOSE_REQUIRED"
    assert result["meeting_critical_public_gaps"] == ["Public revenue signal?"]


def test_pause_resume_status_and_entrypoint_for_user_selection_bucket():
    first_round_resolution = {
        "bucket": "USER_DECISION_REQUIRED",
        "rationale": "Some questions remain pending",
        "unresolved_contact_gaps": [],
        "unresolved_matrix_questions": ["q_market_situation"],
        "meeting_critical_public_gaps": [],
    }
    resolution_plan = build_resolution_plan(
        run_id="r-selection",
        first_round_resolution=first_round_resolution,
        remaining_public_gaps=[],
    )
    status = determine_final_status(
        readiness_usable=True,
        first_round_resolution=first_round_resolution,
        remaining_public_gaps=[],
    )
    resume_entrypoint = (
        "supervisor_resume_after_user_selection"
        if status == SELECTION_REQUIRED_RUN_STATUS
        else "supervisor_finalization_entrypoint"
    )
    dashboard = build_dashboard_state(
        status=status,
        run_id="r-selection",
        resolution_plan=resolution_plan,
        resume_entrypoint=resume_entrypoint,
    )

    assert status == SELECTION_REQUIRED_RUN_STATUS
    assert dashboard["pending_user_selection"] is True
    assert dashboard["resume_entrypoint"] == "supervisor_resume_after_user_selection"


def test_finalization_gate_and_export_contract_for_success_unresolved_classes():
    first_round_resolution = {
        "bucket": "CUSTOMER_CONFIRMATION_REQUIRED",
        "rationale": "Only contact gaps remain",
        "unresolved_contact_gaps": ["Need buyer-side confirmation"],
        "unresolved_matrix_questions": ["q_peer_companies"],
        "meeting_critical_public_gaps": [],
    }
    resolution_plan = build_resolution_plan(
        run_id="r-success",
        first_round_resolution=first_round_resolution,
        remaining_public_gaps=[],
    )
    run_context = {
        "resolution_state": {
            "resolution_plan": resolution_plan,
        }
    }

    unresolved = _extract_export_unresolved(status=SUCCESS_RUN_STATUS, run_context=run_context)

    assert "customer_confirmation_items" in unresolved
    assert "optional_depth_not_selected" in unresolved
    assert "meeting_critical_public_gaps" not in unresolved


def test_golden_quality_reference_files_are_valid_json():
    answer_matrix_ref = json.loads(
        open("tests/golden/quality_reference/answer_matrix_reference.json", encoding="utf-8").read()
    )
    resolution_ref = json.loads(
        open("tests/golden/quality_reference/resolution_buckets_reference.json", encoding="utf-8").read()
    )

    assert answer_matrix_ref["q_company_fundamentals"] == "answered"
    assert resolution_ref["auto_close_required"] == "AUTO_CLOSE_REQUIRED"


def test_golden_quality_rubric_and_excerpt_exist():
    from pathlib import Path

    ref_dir = Path("tests/golden/quality_reference")
    excerpt = ref_dir / "deep_research_quality_excerpt.md"
    rubric = ref_dir / "deep_research_quality_rubric.md"
    assert excerpt.exists(), "deep_research_quality_excerpt.md missing"
    assert rubric.exists(), "deep_research_quality_rubric.md missing"
    assert len(excerpt.read_text(encoding="utf-8")) > 200, "excerpt is too short to be meaningful"
    assert len(rubric.read_text(encoding="utf-8")) > 200, "rubric is too short to be meaningful"


def test_baseline_run_export_contract_stability():
    """Detect uncontrolled top-level export key drift in golden baseline."""
    baseline_meta = json.loads(
        open("tests/golden/runs/baseline_run_20260329/run_meta.json", encoding="utf-8").read()
    )
    baseline_context = json.loads(
        open("tests/golden/runs/baseline_run_20260329/run_context.json", encoding="utf-8").read()
    )
    baseline_pipeline = json.loads(
        open("tests/golden/runs/baseline_run_20260329/pipeline_data.json", encoding="utf-8").read()
    )

    # run_meta must have these keys
    assert "run_id" in baseline_meta
    assert "status" in baseline_meta

    # run_context must have answer_matrix and resolution_state
    assert "answer_matrix" in baseline_context
    assert "resolution_state" in baseline_context

    # pipeline_data must have all core sections
    for section in ("company_profile", "industry_analysis", "market_network",
                    "contact_intelligence", "quality_review", "synthesis",
                    "research_readiness"):
        assert section in baseline_pipeline, f"pipeline_data missing section: {section}"


def test_export_binary_artifact_persists_report_bytes(tmp_path: Path):
    target = export_binary_artifact(
        run_dir=tmp_path / "run-1",
        relative_path="reports/liquisto_briefing_run-1_DE.pdf",
        content=b"%PDF-test",
    )

    assert target.exists()
    assert target.name == "liquisto_briefing_run-1_DE.pdf"
    assert target.read_bytes() == b"%PDF-test"
