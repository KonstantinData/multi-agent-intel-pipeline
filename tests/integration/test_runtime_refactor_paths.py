from __future__ import annotations

import json
from pathlib import Path

from src.models.meeting_ready import MeetingReadinessAssessment
from src.exporters.json_export import export_run
from src.orchestration.run_context import RunContext


def test_export_run_persists_pdf_reports(tmp_path, monkeypatch):
    import src.exporters.pdf_report as pdf_report

    run_dir = tmp_path / "pdf_export"

    def _fake_generate_pdf(pipeline_data: dict, *, lang: str = "de") -> bytes:
        return f"%PDF-{lang}".encode("utf-8")

    monkeypatch.setattr(pdf_report, "generate_pdf", _fake_generate_pdf)

    export_run(
        run_dir=run_dir,
        run_id="pdf_export",
        company_name="PdfCo",
        web_domain="pdf.example",
        status="meeting_ready",
        messages=[],
        pipeline_data={"synthesis": {"executive_summary": "summary"}},
        run_context={"short_term_memory": {}},
    )

    assert (run_dir / "reports" / "liquisto_briefing_pdf_export_DE.pdf").read_bytes() == b"%PDF-de"
    assert (run_dir / "reports" / "liquisto_briefing_pdf_export_EN.pdf").read_bytes() == b"%PDF-en"


def test_runtime_path_pause_resume_and_export_contracts(tmp_path):
    run_id = "integration_baseline"
    run_dir = tmp_path / run_id

    run_context = RunContext(
        run_id=run_id,
        intake={"company_name": "IntegrationCo", "web_domain": "integration.example"},
    )
    run_context.status = "needs_user_selection"
    run_context.resolution_state = {
        "resume_entrypoint": "supervisor_resume_after_user_selection",
        "dashboard_state": {
            "pending_user_selection": True,
            "resume_entrypoint": "supervisor_resume_after_user_selection",
        },
        "resolution_plan": {
            "unresolved": {
                "customer_confirmation_items": ["Validate contact ownership"],
                "optional_depth_not_selected": ["q_market_situation"],
                "meeting_critical_public_gaps": ["MUST_BE_STRIPPED_ON_SUCCESS"],
            }
        },
    }

    export_run(
        run_dir=run_dir,
        run_id=run_id,
        company_name="IntegrationCo",
        web_domain="integration.example",
        status="meeting_ready",
        messages=[{"agent": "Supervisor", "content": "{}"}],
        pipeline_data={"synthesis": {"open_questions": ["should be removed"]}},
        run_context=run_context.snapshot(),
        usage={"total": {}},
        budget={"elapsed_seconds": 0.1},
    )

    run_meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    pipeline_data = json.loads((run_dir / "pipeline_data.json").read_text(encoding="utf-8"))
    run_context_export = json.loads((run_dir / "run_context.json").read_text(encoding="utf-8"))
    memory_snapshot = json.loads((run_dir / "memory_snapshot.json").read_text(encoding="utf-8"))

    assert run_context_export["resolution_state"]["resume_entrypoint"] == "supervisor_resume_after_user_selection"
    assert run_meta["unresolved"] == {
        "customer_confirmation_items": ["Validate contact ownership"],
        "optional_depth_not_selected": ["q_market_situation"],
    }
    assert "open_questions" not in pipeline_data.get("synthesis", {})
    assert isinstance(memory_snapshot, dict)
    assert "short_term_memory" not in memory_snapshot


def test_export_run_syncs_finalization_fields_into_pipeline_data(tmp_path):
    run_dir = tmp_path / "finalization_sync"

    export_run(
        run_dir=run_dir,
        run_id="finalization_sync",
        company_name="SyncCo",
        web_domain="sync.example",
        status="meeting_ready",
        messages=[],
        pipeline_data={"synthesis": {"executive_summary": "summary"}},
        run_context={
            "meeting_readiness_assessment": {
                "run_status": "meeting_ready",
                "meeting_ready": True,
                "blocked_reasons": [],
                "unresolved_gaps": [],
                "confidence": "medium",
            },
            "final_briefing": {
                "run_id": "finalization_sync",
                "company_name": "SyncCo",
                "status": "meeting_ready",
                "executive_summary": "summary",
                "evidence_packets": [],
                "answer_matrix_updates": [],
                "readiness": {
                    "run_status": "meeting_ready",
                    "meeting_ready": True,
                    "blocked_reasons": [],
                    "unresolved_gaps": [],
                    "confidence": "medium",
                },
                "recommended_actions": [],
                "metadata": {},
            },
            "short_term_memory": {},
        },
    )

    pipeline_data = json.loads((run_dir / "pipeline_data.json").read_text(encoding="utf-8"))
    assert pipeline_data["meeting_readiness_assessment"]["run_status"] == "meeting_ready"
    assert pipeline_data["final_briefing"]["status"] == "meeting_ready"


def test_runtime_path_run_context_snapshot_roundtrip_with_resolution_state(tmp_path):
    ctx = RunContext(
        run_id="integration-roundtrip",
        intake={"company_name": "X", "web_domain": "x.example"},
    )
    ctx.resolution_state = {
        "first_round_resolution": {"bucket": "AUTO_CLOSE_REQUIRED"},
        "auto_close": {"triggered": True, "attempted_questions": 2, "remaining_public_gaps": []},
    }
    snap = ctx.snapshot()
    restored = RunContext.from_snapshot(snap)

    assert restored.resolution_state["first_round_resolution"]["bucket"] == "AUTO_CLOSE_REQUIRED"
    assert restored.resolution_state["auto_close"]["attempted_questions"] == 2

    run_dir = Path(tmp_path) / "integration-roundtrip"
    export_run(
        run_dir=run_dir,
        run_id="integration-roundtrip",
        company_name="X",
        web_domain="x.example",
        status="blocked_not_meeting_ready",
        messages=[],
        pipeline_data={},
        run_context=restored.snapshot(),
    )
    assert (run_dir / "run_context.json").exists()


def test_resume_pipeline_applies_user_selections_and_re_evaluates(tmp_path, monkeypatch):
    """RA-05: resume_pipeline loads paused run, applies selections, re-evaluates gate."""
    import src.pipeline_runner as pr

    run_id = "resume_test_run"
    run_dir = tmp_path / run_id

    ctx = RunContext(
        run_id=run_id,
        intake={"company_name": "ResumeCo", "web_domain": "resume.example"},
    )
    ctx.status = "needs_user_selection"
    ctx.answer_matrix = {
        "q_company_fundamentals": {"status": "answered", "answer": "ok", "notes": "", "source_tasks": []},
        "q_product_asset_scope": {"status": "answered", "answer": "ok", "notes": "", "source_tasks": []},
        "q_peer_companies": {"status": "answered", "answer": "ok", "notes": "", "source_tasks": []},
        "q_monetization_redeployment": {"status": "answered", "answer": "ok", "notes": "", "source_tasks": []},
        "q_market_situation": {"status": "pending", "answer": "", "notes": "", "source_tasks": []},
    }
    ctx.resolution_state = {
        "first_round_resolution": {"bucket": "USER_DECISION_REQUIRED"},
        "auto_close": {"remaining_public_gaps": []},
        "dashboard_state": {"pending_user_selection": True, "resume_entrypoint": "supervisor_resume_after_user_selection"},
        "resolution_plan": {"unresolved": {"optional_depth_not_selected": ["q_market_situation"]}},
    }

    export_run(
        run_dir=run_dir,
        run_id=run_id,
        company_name="ResumeCo",
        web_domain="resume.example",
        status="needs_user_selection",
        messages=[],
        pipeline_data={
            "research_readiness": {"usable": True},
            "quality_review": {"evidence_health": "high"},
        },
        run_context=ctx.snapshot(),
    )

    monkeypatch.setattr(pr, "RUNS_DIR", tmp_path)

    result = pr.resume_pipeline(
        run_id=run_id,
        user_selections={
            "selected_questions": ["q_market_situation"],
            "skipped_questions": [],
        },
    )

    assert result["error"] is None
    assert result["status"] == "meeting_ready"
    restored_ctx = result["run_context"]
    assert restored_ctx["answer_matrix"]["q_market_situation"]["status"] == "partially_answered"
    assert restored_ctx["resolution_state"]["dashboard_state"]["pending_user_selection"] is False
    assert restored_ctx["resolution_state"]["user_selections"]["selected_questions"] == ["q_market_situation"]
    assert result["pipeline_data"]["meeting_readiness_assessment"]["run_status"] == "meeting_ready"
    assert result["pipeline_data"]["final_briefing"]["status"] == "meeting_ready"


def test_sync_finalization_artifacts_backfills_blocked_reasons():
    import src.pipeline_runner as pr

    ctx = RunContext(
        run_id="blocked_sync",
        intake={"company_name": "BlockedCo", "web_domain": "blocked.example"},
    )
    ctx.meeting_readiness_assessment = MeetingReadinessAssessment(
        run_status="blocked_not_meeting_ready",
        meeting_ready=False,
        blocked_reasons=[],
        confidence="medium",
    )
    ctx.resolution_state = {"finalization_blocked": {"reason": "meeting_not_ready", "open_gaps": []}}

    pipeline_data = {
        "synthesis": {"executive_summary": "blocked"},
        "research_readiness": {
            "usable": False,
            "score": 38,
            "reasons": [
                "Company profile is still incomplete.",
                "Buyer landscape is incomplete.",
            ],
        },
        "quality_review": {"evidence_health": "medium"},
    }

    pr._sync_finalization_artifacts(
        run_context=ctx,
        pipeline_data=pipeline_data,
        run_id="blocked_sync",
        company_name="BlockedCo",
        status="blocked_not_meeting_ready",
        meeting_actions=[],
    )

    assert pipeline_data["meeting_readiness_assessment"]["blocked_reasons"] == [
        "Company profile is still incomplete.",
        "Buyer landscape is incomplete.",
    ]
    assert pipeline_data["meeting_readiness_assessment"]["confidence"] == "low"
