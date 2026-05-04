"""Failure-mode regression tests for audit-critical runtime paths."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from src.domain.intake import IntakeRequest, SupervisorBrief
from src.memory.consolidation import consolidate_role_patterns
from src.orchestration.contracts import DepartmentRunState, TaskArtifact, TaskDecisionArtifact
from src.orchestration.follow_up import answer_follow_up
from src.orchestration.report_runtime import ReportWriterRuntime
from src.orchestration.synthesis_runtime import SynthesisRuntime
from src.orchestration.task_router import build_initial_assignments, evaluate_run_conditions
from src.research.query_resolver import resolve_queries, validate_query_overrides


def _brief() -> SupervisorBrief:
    return SupervisorBrief(
        submitted_company_name="ACME GmbH",
        submitted_web_domain="acme.de",
        verified_company_name="ACME",
        verified_legal_name="ACME GmbH",
        name_confidence="high",
        website_reachable=True,
        homepage_url="https://www.acme.de/",
        page_title="ACME",
        meta_description="Manufacturing",
        raw_homepage_excerpt="Manufacturing company",
        normalized_domain="acme.de",
        industry_hint="Manufacturing",
    )


def test_fm1_initial_intake_rejects_empty_company_or_domain() -> None:
    with pytest.raises(ValueError, match="company_name is required"):
        IntakeRequest(company_name="", web_domain="acme.de")

    with pytest.raises(ValueError, match="web_domain is required"):
        IntakeRequest(company_name="ACME GmbH", web_domain="")


def test_fm2_department_run_conditions_skip_contact_tasks_without_buyer_package() -> None:
    assignments = [
        assignment
        for assignment in build_initial_assignments(_brief())
        if assignment.assignee == "ContactDepartment"
    ]

    runnable, skipped = evaluate_run_conditions(
        assignments,
        pipeline_state={"department_packages": {}, "task_statuses": {}},
    )

    skipped_keys = {item["task_key"] for item in skipped}
    runnable_keys = {assignment.task_key for assignment in runnable}
    assert "contact_qualification" in skipped_keys
    assert "contact_qualification" not in runnable_keys


def test_fm3_closed_unresolved_decision_does_not_satisfy_dependency() -> None:
    state = DepartmentRunState(department="CompanyDepartment")
    state.record_task_artifact(
        TaskArtifact(
            task_key="company_fundamentals",
            attempt=1,
            facts=["Public company profile exists"],
        )
    )
    state.record_decision_artifact(
        TaskDecisionArtifact(
            task_key="company_fundamentals",
            attempt=1,
            outcome="closed_unresolved",
            task_status="degraded",
            open_questions=["Revenue not evidenced"],
        )
    )

    assert state.is_dependency_satisfied("company_fundamentals") is False


def test_fm3_lead_finalize_contains_negative_review_and_decision_fallback_guards() -> None:
    source = Path("src/agents/lead.py").read_text(encoding="utf-8")

    assert "Cannot finalize package before all assigned tasks have at least one research result" in source
    assert "contract review escalation" in source
    assert "inline judge fallback" in source


def test_fm4_query_resolver_rejects_free_form_override_and_expands_kb_variant() -> None:
    with pytest.raises(ValueError):
        validate_query_overrides(["ACME GmbH Umsatz Mitarbeiter freie Suche"])

    queries = resolve_queries(
        "company_fundamentals",
        _brief(),
        query_overrides=["strategy:company_fundamentals:method_refinement"],
    )
    assert queries
    assert all("ACME GmbH" in query or "acme.de" in query for query in queries)


def test_fm5_synthesis_and_report_writer_are_separate_runtime_nodes() -> None:
    synthesis_signature = inspect.signature(SynthesisRuntime.run)
    report_signature = inspect.signature(ReportWriterRuntime.run)

    assert "supervisor" not in synthesis_signature.parameters
    assert "department_packages" in synthesis_signature.parameters
    assert "pipeline_data" in report_signature.parameters
    assert "department_packages" in report_signature.parameters

    pipeline_source = Path("src/pipeline_runner.py").read_text(encoding="utf-8")
    assert pipeline_source.index('agents["synthesis"].run') < pipeline_source.index(
        'agents["report_writer"].run'
    )


def test_fm6_follow_up_persists_answer_artifact_after_run_brain_routing(tmp_path) -> None:
    import src.orchestration.follow_up as fu_mod

    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    original_runs = fu_mod.RUNS_DIR
    fu_mod.RUNS_DIR = tmp_path
    try:
        result = answer_follow_up(
            run_id="run-1",
            route="CompanyDepartment",
            question="What is known?",
            pipeline_data={"company_profile": {"company_name": "ACME GmbH", "description": "Producer"}},
            run_context={
                "short_term_memory": {
                    "department_run_states": {
                        "CompanyDepartment": {
                            "task_artifacts": {
                                "company_fundamentals": [
                                    {"facts": ["Run brain fact"], "open_questions": []}
                                ]
                            },
                            "review_artifacts": {
                                "company_fundamentals": [{"approved": True, "accepted_points": []}]
                            },
                            "decision_artifacts": {
                                "company_fundamentals": [{"outcome": "accepted", "open_questions": []}]
                            },
                        }
                    },
                    "department_packages": {},
                }
            },
        )
        history = json.loads((run_dir / "follow_up_history.json").read_text(encoding="utf-8"))
    finally:
        fu_mod.RUNS_DIR = original_runs

    assert result["evidence_used"][0] == "Run brain fact"
    assert history[-1]["run_id"] == "run-1"
    assert history[-1]["routed_to"] == "CompanyDepartment"


def test_fm7_long_term_consolidation_scrubs_case_specific_process_patterns() -> None:
    patterns = consolidate_role_patterns(
        run_context={
            "intake": {"company_name": "ACME GmbH", "web_domain": "acme.de"},
            "short_term_memory": {
                "task_statuses": {"company_fundamentals": "accepted"},
                "worker_reports": [
                    {
                        "worker": "CompanyResearcher",
                        "task_key": "company_fundamentals",
                        "queries_used": ['"ACME GmbH" revenue site:acme.de annual report'],
                    }
                ],
                "sources": [],
            },
        },
        pipeline_data={"company_profile": {"company_name": "ACME GmbH", "website": "acme.de"}},
        status="meeting_ready",
        usable=True,
    )

    serialized = json.dumps(patterns, ensure_ascii=False)
    assert "ACME" not in serialized
    assert "acme.de" not in serialized
    assert "{company}" in serialized or "{domain}" in serialized


def test_fm8_architecture_test_layer_blocks_runtime_heavy_modules() -> None:
    importorskip = "importorskip"
    forbidden_tokens = (
        f'{importorskip}("openai")',
        f'{importorskip}("pypdf")',
        f'{importorskip}("reportlab")',
        ".".join(("src", "exporters", "pdf_report")),
        ".".join(("src", "agents", "worker")),
    )
    offenders: dict[str, list[str]] = {}
    for path in Path("tests/architecture").glob("test_*.py"):
        if path.name in {"test_000_import_layering.py", Path(__file__).name}:
            continue
        text = path.read_text(encoding="utf-8")
        found = [token for token in forbidden_tokens if token in text]
        if found:
            offenders[str(path)] = found

    assert offenders == {}
