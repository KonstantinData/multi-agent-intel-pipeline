"""Tests for the ADR-004 shadow observation extraction script."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


def _load_script() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "analysis"
        / "adr004_shadow_extract.py"
    )
    spec = importlib.util.spec_from_file_location("adr004_shadow_extract", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_run_context(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    payload = {
        "run_id": "fixture-run",
        "status": "blocked_not_meeting_ready",
        "short_term_memory": {
            "department_run_states": {
                "CompanyDepartment": {
                    "review_artifacts": {
                        "company_fundamentals": [
                            {
                                "task_key": "company_fundamentals",
                                "attempt": 1,
                                "approved": True,
                                "assurance_shadow": {
                                    "gate_verdict": {
                                        "confidence_score": 0.72,
                                        "requires_critic": False,
                                        "requires_judge": False,
                                        "would_auto_accept": False,
                                    },
                                    "gate_signals": {
                                        "required_fields_score": 1.0,
                                        "source_mix_score": None,
                                        "source_freshness_score": None,
                                        "contradiction_score": 1.0,
                                        "evidence_strength_score": None,
                                        "task_criticality": "medium",
                                        "ltm_pattern_match": False,
                                        "ltm_pattern_precision": None,
                                        "ltm_pattern_qualified": False,
                                    },
                                    "actual_critic_delta": {
                                        "changed_outcome": False,
                                        "rejected_points_count": 0,
                                        "failed_core_rules": [],
                                        "critic_severity": "none",
                                        "would_have_blocked_auto_accept": False,
                                    },
                                },
                            },
                        ],
                    },
                },
                "MarketDepartment": {
                    "review_artifacts": {
                        "market_situation": [
                            {
                                "task_key": "market_situation",
                                "attempt": 1,
                                "approved": False,
                            },
                        ],
                    },
                },
            },
        },
    }
    (run_dir / "run_context.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def test_extract_run_rows_include_shadow_presence_and_signal_none_flags(tmp_path: Path) -> None:
    module = _load_script()
    run_dir = tmp_path / "fixture-run"
    _write_run_context(run_dir)

    extracted = module.extract_run(run_dir)

    assert extracted["run_id"] == "fixture-run"
    assert extracted["run_status"] == "blocked_not_meeting_ready"
    assert extracted["summary"]["review_count"] == 2
    assert extracted["summary"]["shadow_present_count"] == 1
    assert extracted["summary"]["shadow_coverage"] == 0.5

    rows = sorted(extracted["rows"], key=lambda row: row["department"])
    company_row = rows[0]
    assert company_row["department"] == "CompanyDepartment"
    assert company_row["shadow_present"] is True
    assert company_row["confidence_score"] == 0.72
    assert company_row["requires_critic"] is False
    assert company_row["would_auto_accept"] is False
    assert company_row["actual_critic_delta_present"] is True
    assert company_row["critic_severity"] == "none"
    assert company_row["source_mix_score_is_none"] is True
    assert company_row["contradiction_score_is_none"] is False

    market_row = rows[1]
    assert market_row["department"] == "MarketDepartment"
    assert market_row["shadow_present"] is False
    assert market_row["confidence_score"] is None
    assert market_row["required_fields_score_is_none"] is True


def test_build_report_aggregates_signal_none_fraction(tmp_path: Path) -> None:
    module = _load_script()
    run_dir = tmp_path / "fixture-run"
    _write_run_context(run_dir)

    report = module.build_report([run_dir])

    assert report["schema_version"] == "2026-05-21.1"
    assert report["run_count"] == 1
    assert report["aggregate"]["review_count"] == 2
    assert report["aggregate"]["signal_none_fraction"]["required_fields_score"] == 0.5
    assert report["aggregate"]["signal_none_fraction"]["source_mix_score"] == 1.0
    assert report["aggregate"]["signal_none_fraction"]["contradiction_score"] == 0.5


def test_main_writes_json_for_run_id(tmp_path: Path) -> None:
    module = _load_script()
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "fixture-run"
    output = tmp_path / "summary.json"
    _write_run_context(run_dir)

    exit_code = module.main(
        [
            "fixture-run",
            "--runs-root",
            str(runs_root),
            "--output",
            str(output),
        ],
    )

    assert exit_code == 0
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["aggregate"]["shadow_coverage"] == 0.5
    assert len(written["rows"]) == 2
