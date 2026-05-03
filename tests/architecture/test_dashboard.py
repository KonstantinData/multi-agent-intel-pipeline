"""Tests for the shared dashboard visualization layer.

Validates:
- Visualization contracts are valid Pydantic models
- Dashboard composer produces a DashboardBundle from real runtime shapes
- Bundle sections contain expected content from runtime data
- Bundle is serializable and round-trippable
"""
from __future__ import annotations

from io import BytesIO

import pytest

from src.models.visualization import (
    ChartSeries,
    ChartSpec,
    DashboardBundle,
    DashboardSection,
    InsightCallout,
    KpiCard,
    TableBlock,
)
from src.orchestration.dashboard_composer import compose_dashboard


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    PdfReader = pytest.importorskip("pypdf").PdfReader
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf_bytes)).pages)


def _make_pipeline_data() -> dict:
    return {
        "company_profile": {
            "company_name": "ACME GmbH",
            "revenue": "500M EUR",
            "employees": "3000",
            "industry": "Manufacturing",
        },
        "industry_analysis": {"industry_name": "Manufacturing"},
        "market_network": {
            "peer_competitors": {"companies": [
                {"name": "Peer1", "country": "Germany", "relevance": "high"},
                {"name": "Peer2", "country": "France", "relevance": "medium"},
            ]},
            "downstream_buyers": {"companies": [
                {"name": "Buyer1", "country": "Germany", "relevance": "high"},
            ]},
        },
        "contact_intelligence": {
            "contacts": [
                {"name": "Jane Doe", "rolle_titel": "Head of Procurement", "firma": "BuyerCo", "senioritaet": "Senior"},
                {"name": "John Smith", "rolle_titel": "COO", "firma": "BuyerCo2", "senioritaet": "C-Level"},
            ],
            "target_company_contact_cards": [
                {
                    "name": "Max Mustermann",
                    "role": "CFO",
                    "organization_location": "ACME GmbH (Berlin)",
                    "relevance_buying_center": "Economic buyer for working-capital topics.",
                    "profile_contact_channel": "LinkedIn: https://linkedin.example/max",
                    "source_verification": "Partially verified via company source",
                    "confidence": "medium",
                }
            ],
            "target_company_missing_roles": [
                {
                    "role_name": "Head of Supply Chain",
                    "why_critical": "Owns inventory release decisions.",
                    "likely_org_area": "Supply Chain",
                    "best_search_channel": "LinkedIn",
                    "next_search_action": "Search local plant leadership",
                }
            ],
            "target_company_access_path": [
                "Open top-down with CFO and request handoff to supply-chain lead."
            ],
            "firms_searched": 3,
            "coverage_quality": "medium",
        },
        "quality_review": {"evidence_health": "medium"},
        "synthesis": {
            "liquisto_service_relevance": [
                {"service_area": "excess_inventory", "relevance": "high", "reasoning": "Strong signal"},
            ],
            "recommended_engagement_paths": ["excess_inventory"],
            "opportunity_assessment_summary": "Strong excess inventory opportunity.",
            "critical_open_questions": [
                {
                    "label": "Inventory Volume",
                    "question": "What is the current slow-moving inventory volume?",
                    "why_critical": "Determines commercial size.",
                    "hypothesis_tested": "Excess inventory is material.",
                    "owner": "CFO",
                    "timing": "during_meeting",
                    "decision_impact": "Decides whether Liquisto should lead with inventory-to-cash.",
                }
            ],
            "recommended_next_steps": [
                {
                    "phase": "pre_meeting",
                    "owner": "Liquisto Account Lead",
                    "action": "Prepare CFO-first outreach",
                    "target_person": "CFO",
                    "asset_hypothesis": "A senior finance sponsor will unlock the first working-capital discussion.",
                    "goal": "Secure executive sponsor",
                    "expected_output": "Tailored outreach note",
                    "success_criterion": "Meeting invitation sent",
                    "definition_of_done": "Invitation is sent and the outreach narrative is ready.",
                    "dependency": "Named sponsor exists",
                }
            ],
        },
        "research_readiness": {"score": 78, "usable": True},
        "meeting_actions": [
            {"action_type": "prepare_meeting", "title": "Lead with inventory", "description": "Present excess inventory path."},
            {"action_type": "collect_missing_evidence", "title": "Validate revenue", "description": "Confirm revenue trend."},
        ],
    }


def _make_run_context() -> dict:
    return {
        "answer_matrix": {
            "q_company_fundamentals": {"status": "answered"},
            "q_market_situation": {"status": "answered"},
            "q_peer_companies": {"status": "partially_answered"},
            "q_contact_intelligence": {"status": "pending"},
        },
        "resolution_state": {
            "resolution_plan": {"unresolved": {"customer_confirmation_items": ["Confirm ownership"]}},
        },
        "short_term_memory": {
            "evidence_packets": [
                {"packet_id": "p1", "metadata": {"task_key": "company_fundamentals"}},
                {"packet_id": "p2", "metadata": {"task_key": "company_fundamentals"}},
                {"packet_id": "p3", "metadata": {"task_key": "market_situation"}},
                {"packet_id": "p4", "metadata": {"task_key": "peer_companies"}},
            ],
            "meeting_actions": [],
        },
    }


# ---------------------------------------------------------------------------
# Contract model tests
# ---------------------------------------------------------------------------

def test_kpi_card_construction():
    kpi = KpiCard(title="Revenue", value="500M EUR", source="company_profile")
    assert kpi.title == "Revenue"
    assert kpi.value == "500M EUR"


def test_chart_spec_construction():
    chart = ChartSpec(
        chart_id="test", chart_type="bar", title="Test Chart",
        labels=["A", "B"], series=[ChartSeries(label="s1", values=[1, 2])],
    )
    assert chart.chart_type == "bar"
    assert len(chart.series) == 1


def test_dashboard_bundle_serialization_roundtrip():
    bundle = DashboardBundle(
        run_id="test-run", company_name="ACME", status="meeting_ready",
        sections=[DashboardSection(section_id="s1", title="Test", kpis=[
            KpiCard(title="KPI", value="42"),
        ])],
    )
    data = bundle.model_dump(mode="json")
    restored = DashboardBundle.model_validate(data)
    assert restored.run_id == "test-run"
    assert len(restored.sections) == 1
    assert restored.sections[0].kpis[0].value == "42"


# ---------------------------------------------------------------------------
# Composer tests
# ---------------------------------------------------------------------------

def test_compose_dashboard_produces_bundle():
    bundle = compose_dashboard(
        run_id="r-test",
        status="meeting_ready",
        pipeline_data=_make_pipeline_data(),
        run_context=_make_run_context(),
    )
    assert isinstance(bundle, DashboardBundle)
    assert bundle.run_id == "r-test"
    assert bundle.company_name == "ACME GmbH"
    assert len(bundle.sections) >= 3


def test_compose_dashboard_has_executive_kpis():
    bundle = compose_dashboard(
        run_id="r-test", status="meeting_ready",
        pipeline_data=_make_pipeline_data(), run_context=_make_run_context(),
    )
    exec_section = next((s for s in bundle.sections if s.section_id == "executive_kpis"), None)
    assert exec_section is not None
    assert len(exec_section.kpis) >= 4
    titles = [k.title for k in exec_section.kpis]
    assert "Run Status" in titles
    assert "Questions Covered" in titles
    assert "Revenue" in titles


def test_compose_dashboard_has_coverage_chart():
    bundle = compose_dashboard(
        run_id="r-test", status="meeting_ready",
        pipeline_data=_make_pipeline_data(), run_context=_make_run_context(),
    )
    coverage = next((s for s in bundle.sections if s.section_id == "coverage"), None)
    assert coverage is not None
    assert len(coverage.charts) == 1
    assert coverage.charts[0].chart_type == "donut"


def test_compose_dashboard_has_opportunity_chart():
    bundle = compose_dashboard(
        run_id="r-test", status="meeting_ready",
        pipeline_data=_make_pipeline_data(), run_context=_make_run_context(),
    )
    opp = next((s for s in bundle.sections if s.section_id == "opportunity"), None)
    assert opp is not None
    assert len(opp.charts) == 1
    assert opp.charts[0].chart_type == "bar"
    assert len(opp.callouts) >= 1


def test_compose_dashboard_has_contact_table():
    bundle = compose_dashboard(
        run_id="r-test", status="meeting_ready",
        pipeline_data=_make_pipeline_data(), run_context=_make_run_context(),
    )
    contacts = next((s for s in bundle.sections if s.section_id == "contacts"), None)
    assert contacts is not None
    assert len(contacts.tables) == 1
    assert contacts.tables[0].columns == ["Name", "Role", "Company", "Seniority"]
    assert len(contacts.tables[0].rows) == 2


def test_compose_dashboard_has_actions():
    bundle = compose_dashboard(
        run_id="r-test", status="meeting_ready",
        pipeline_data=_make_pipeline_data(), run_context=_make_run_context(),
    )
    actions = next((s for s in bundle.sections if s.section_id == "actions"), None)
    assert actions is not None
    assert len(actions.callouts) >= 2  # 2 meeting_actions + 1 customer_confirmation


def test_compose_dashboard_has_evidence_treemap():
    bundle = compose_dashboard(
        run_id="r-test", status="meeting_ready",
        pipeline_data=_make_pipeline_data(), run_context=_make_run_context(),
    )
    treemap = next((s for s in bundle.sections if s.section_id == "evidence_treemap"), None)
    assert treemap is not None
    assert len(treemap.charts) == 1
    assert treemap.charts[0].chart_type == "treemap"
    # Should have 3 task groups from the test data
    assert len(treemap.charts[0].labels) == 3


def test_compose_dashboard_has_geo_map():
    bundle = compose_dashboard(
        run_id="r-test", status="meeting_ready",
        pipeline_data=_make_pipeline_data(), run_context=_make_run_context(),
    )
    geo = next((s for s in bundle.sections if s.section_id == "geo_map"), None)
    assert geo is not None
    assert len(geo.charts) == 1
    assert geo.charts[0].chart_type == "map"
    assert "Germany" in geo.charts[0].labels
    assert "France" in geo.charts[0].labels


def test_geo_map_absent_when_no_country_data():
    pd = _make_pipeline_data()
    pd["market_network"] = {"peer_competitors": {"companies": [{"name": "X"}]}, "downstream_buyers": {"companies": []}}
    bundle = compose_dashboard(
        run_id="r-test", status="meeting_ready",
        pipeline_data=pd, run_context=_make_run_context(),
    )
    geo = next((s for s in bundle.sections if s.section_id == "geo_map"), None)
    # Section should be filtered out (no charts)
    assert geo is None


def test_treemap_absent_when_no_evidence():
    rc = _make_run_context()
    rc["short_term_memory"]["evidence_packets"] = []
    bundle = compose_dashboard(
        run_id="r-test", status="meeting_ready",
        pipeline_data=_make_pipeline_data(), run_context=rc,
    )
    treemap = next((s for s in bundle.sections if s.section_id == "evidence_treemap"), None)
    assert treemap is None


def test_compose_dashboard_with_budget_has_timings():
    budget = {"department_timings": {"CompanyDepartment": 12.5, "MarketDepartment": 8.3}}
    bundle = compose_dashboard(
        run_id="r-test", status="meeting_ready",
        pipeline_data=_make_pipeline_data(), run_context=_make_run_context(),
        budget=budget,
    )
    timings = next((s for s in bundle.sections if s.section_id == "timings"), None)
    assert timings is not None
    assert len(timings.charts) == 1
    assert timings.charts[0].chart_type == "bar"


def test_compose_dashboard_empty_data_does_not_crash():
    bundle = compose_dashboard(
        run_id="r-empty", status="failed",
        pipeline_data={}, run_context={},
    )
    assert isinstance(bundle, DashboardBundle)
    assert bundle.status == "failed"


def test_pdf_bundle_rendering_does_not_crash():
    """Verify that generate_pdf works with a dashboard_bundle in pipeline_data."""
    pytest.importorskip("reportlab")
    from src.exporters.pdf_report import generate_pdf
    pd = _make_pipeline_data()
    bundle = compose_dashboard(
        run_id="r-pdf", status="meeting_ready",
        pipeline_data=pd, run_context=_make_run_context(),
    )
    pd["dashboard_bundle"] = bundle.model_dump(mode="json")
    pdf_bytes = generate_pdf(pd, lang="en")
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000  # non-trivial PDF
    assert pdf_bytes[:5] == b"%PDF-"


def test_pdf_without_bundle_still_works():
    """Legacy fallback: PDF generation without dashboard_bundle."""
    pytest.importorskip("reportlab")
    from src.exporters.pdf_report import generate_pdf
    pd = _make_pipeline_data()
    # No dashboard_bundle key
    pdf_bytes = generate_pdf(pd, lang="en")
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:5] == b"%PDF-"


def test_pdf_localizes_core_labels_for_german_and_english():
    pytest.importorskip("reportlab")
    from src.exporters.pdf_report import generate_pdf

    pd = _make_pipeline_data()
    pdf_de = generate_pdf(pd, lang="de")
    pdf_en = generate_pdf(pd, lang="en")

    text_de = _extract_pdf_text(pdf_de)
    text_en = _extract_pdf_text(pdf_en)

    assert "Management-Übersicht" in text_de
    assert "Offene Fragen & Validierungsplan" in text_de
    assert "Fehlende Schlüsselrollen" in text_de
    assert "Telefonnummern und E-Mail-Adressen werden nur gezeigt" in text_de
    assert "Verantwortlich" in text_de
    assert "Zeitpunkt" in text_de
    assert "Hypothese" in text_de
    assert "Ergebnis" in text_de
    assert "Abschluss" in text_de
    assert "Executive Dashboard" not in text_de
    assert "Open Questions & Validation Plan" not in text_de
    assert "Owner / Timing" not in text_de
    assert "Hypothesis / output / done" not in text_de
    assert "Confidence" not in text_de

    assert "Executive Dashboard" in text_en
    assert "Open Questions & Validation Plan" in text_en
    assert "Critical missing roles" in text_en
    assert "Phone numbers and email addresses are shown only when they are publicly evidenced." in text_en
    assert "Management-Übersicht" not in text_en
    assert "Offene Fragen & Validierungsplan" not in text_en


def test_pdf_offline_localizes_structured_playbook_content(monkeypatch):
    pytest.importorskip("reportlab")
    from src.config import settings
    from src.exporters.pdf_report import generate_pdf

    monkeypatch.setattr(settings, "get_openai_api_key", lambda: "")
    pd = _make_pipeline_data()
    pd["synthesis"]["executive_summary"] = "Conservative output — synthesis incomplete."

    pdf_de = generate_pdf(pd, lang="de")
    text_de = _extract_pdf_text(pdf_de)

    assert "Konservative Ausgabe" in text_de
    assert "Wirtschaftlicher" in text_de
    assert "Teilweise" in text_de
    assert "CFO-zentrierte" in text_de
    assert "Conservative output" not in text_de
    assert "Economic buyer" not in text_de
    assert "Partially verified" not in text_de
    assert "Prepare CFO-first outreach" not in text_de


def test_pdf_falls_back_when_llm_translation_times_out(monkeypatch):
    pytest.importorskip("reportlab")
    pytest.importorskip("openai")
    import openai

    from src.config import settings
    from src.exporters.pdf_report import generate_pdf

    class _TimeoutCompletions:
        @staticmethod
        def create(*args, **kwargs):
            raise TimeoutError("translation timeout")

    class _TimeoutChat:
        completions = _TimeoutCompletions()

    class _TimeoutOpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = _TimeoutChat()

    monkeypatch.setattr(settings, "get_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(openai, "OpenAI", _TimeoutOpenAI)

    pd = _make_pipeline_data()
    pd["synthesis"]["executive_summary"] = "Conservative output — synthesis incomplete."

    pdf_de = generate_pdf(pd, lang="de")
    text_de = _extract_pdf_text(pdf_de)

    assert pdf_de[:5] == b"%PDF-"
    assert "Konservative Ausgabe" in text_de
    assert "Prepare CFO-first outreach" not in text_de


def test_pdf_german_has_no_nv_placeholders_and_no_truncated_action_text():
    pytest.importorskip("reportlab")
    from src.exporters.pdf_report import generate_pdf

    pd = _make_pipeline_data()
    long_action = (
        "Schließe die operative Kontaktlücke rund um Werkleitung Polen über LinkedIn-Recherche, "
        "Assistenz und zentrale Telefonvermittlung vollständig vor dem Erstgespräch ohne Kürzung Endemarker."
    )
    pd["synthesis"]["recommended_engagement_paths"] = []
    pd["synthesis"]["liquisto_service_relevance"] = []
    pd["synthesis"]["recommended_next_steps"] = [
        {
            "phase": "pre_meeting",
            "owner": "Liquisto Account Lead",
            "action": long_action,
            "target_person": "Werkleitung Polen",
            "asset_hypothesis": "Hypothese vorhanden",
            "goal": "Gespräch sichern",
            "expected_output": "Nächster Termin bestätigt",
            "success_criterion": "Konkreter Folgetermin",
            "definition_of_done": "Folgetermin fixiert",
            "dependency": "Kontaktpfad geklärt",
        }
    ]
    pd["meeting_actions"] = [{"title": "Follow-up", "description": long_action}]

    pdf_de = generate_pdf(pd, lang="de")
    text_de = _extract_pdf_text(pdf_de)
    text_de_lower = text_de.lower()

    assert "n/v" not in text_de_lower
    assert " endemarker" in text_de_lower
    assert "keine belastbaren öffentlichen quellen verfügbar." in text_de_lower


def test_compose_dashboard_bundle_is_json_serializable():
    bundle = compose_dashboard(
        run_id="r-test", status="meeting_ready",
        pipeline_data=_make_pipeline_data(), run_context=_make_run_context(),
    )
    data = bundle.model_dump(mode="json")
    assert isinstance(data, dict)
    assert "sections" in data
    restored = DashboardBundle.model_validate(data)
    assert restored.run_id == bundle.run_id
    assert len(restored.sections) == len(bundle.sections)

    bundle = compose_dashboard(
        run_id="r-test", status="meeting_ready",
        pipeline_data=_make_pipeline_data(), run_context=_make_run_context(),
    )
    data = bundle.model_dump(mode="json")
    assert isinstance(data, dict)
    assert "sections" in data
    # Verify full round-trip
    restored = DashboardBundle.model_validate(data)
    assert restored.run_id == bundle.run_id
    assert len(restored.sections) == len(bundle.sections)
