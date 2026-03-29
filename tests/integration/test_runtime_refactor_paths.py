from __future__ import annotations

import json
from pathlib import Path

from src.exporters.json_export import export_run
from src.orchestration.run_context import RunContext


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
