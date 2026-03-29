"""Architecture tests for meeting-question catalog wiring."""
from __future__ import annotations

from src.domain.intake import SupervisorBrief
from src.orchestration.meeting_questions import (
    TASK_TO_QUESTION_IDS,
    build_initial_answer_matrix,
    build_question_registry,
)
from src.orchestration.task_router import build_initial_assignments


def test_question_registry_has_stable_ids():
    registry = build_question_registry()
    assert "q_company_fundamentals" in registry
    assert "q_contact_intelligence" in registry
    assert all(key.startswith("q_") for key in registry)


def test_task_router_assignments_have_question_ids():
    brief = SupervisorBrief(
        submitted_company_name="Acme",
        submitted_web_domain="acme.example",
        verified_company_name="Acme",
        verified_legal_name="Acme Inc.",
        name_confidence="high",
        website_reachable=True,
        homepage_url="https://acme.example",
        page_title="Acme",
        meta_description="Acme",
        raw_homepage_excerpt="Acme excerpt",
        normalized_domain="acme.example",
    )
    assignments = build_initial_assignments(brief)
    assert assignments
    for assignment in assignments:
        assert assignment.question_ids == TASK_TO_QUESTION_IDS.get(assignment.task_key, ())


def test_initial_answer_matrix_starts_pending():
    matrix = build_initial_answer_matrix()
    assert matrix["q_market_situation"]["status"] == "pending"
    assert matrix["q_market_situation"]["source_tasks"] == []
