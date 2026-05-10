from __future__ import annotations

from src.agents.report_writer import ReportWriterAgent
from src.exporters.report_utils import select_composed_report
from src.orchestration.report_knowledge import load_report_blueprint


def _base_pipeline_data() -> dict:
    return {
        "company_profile": {
            "company_name": "Ziehl-Abegg",
            "description": "Industrieunternehmen mit Fokus auf Luft- und Antriebstechnik.",
            "industry": "Maschinenbau",
            "financial_deep_dive": {
                "assessment": "Bestandsdruck sichtbar und Working-Capital-Potenzial vorhanden.",
                "key_financials": ["Umsatzrueckgang im Jahresvergleich."],
                "inventory_positions": ["Bestandsaufbau ueber mehrere Quartale."],
            },
        },
        "synthesis": {
            "executive_summary": "Fokus auf Transforming Excess Inventory mit priorisiertem Einstieg.",
            "recommended_engagement_paths": ["Transforming Excess Inventory"],
            "opportunity_assessment_summary": "Hohe Hebelwirkung bei Bestandssegmentierung und Abverkaufspfaden.",
            "confidence": "hoch",
            "key_risks": [
                "Keine bestaetigten Lageralterungskennzahlen aus freien Quellen.",
                "Unklare Entscheidungshoheit auf Werksebene.",
            ],
            "recommended_next_steps": [
                {
                    "action": "Discovery-Call mit Operations und Finance vorbereiten",
                    "goal": "Datenluecken fuer DIO und Write-downs schliessen",
                }
            ],
            "critical_open_questions": [
                {
                    "question": "Welche Lageralterungssegmente sind aktuell kritisch?",
                }
            ],
        },
        "quality_review": {
            "evidence_health": "hoch",
            "open_gaps": [],
        },
        "contact_intelligence": {
            "target_company_summary": "Zielkontakte auf C-Level verfuegbar, operative Rollen teils offen.",
            "target_company_contacts": [{"name": "Max Mustermann"}],
        },
        "market_network": {
            "downstream_buyers": {"assessment": "Abnehmerpfade in DACH und Osteuropa vorhanden."}
        },
        "final_briefing": {
            "run_id": "20260402T101500Z",
            "status": "discovery_ready_not_execution_ready",
        },
        "research_readiness": {
            "readiness_blockers": [],
        },
        "data_request_sheet": {"status": "required"},
        "outreach_playbook": {"steps": [{"title": "Kontaktpfad vorbereiten"}]},
        "meeting_actions": [{"title": "Follow-up", "description": "Datenanforderung senden"}],
    }


def test_build_report_package_fallback_is_valid_without_api_key(monkeypatch):
    monkeypatch.setattr("src.agents.report_writer.get_openai_api_key", lambda: "")
    agent = ReportWriterAgent()
    package = agent.build_report_package(
        pipeline_data=_base_pipeline_data(),
        department_packages={},
    )
    assert package["report_status"] == "ready"
    assert package["composition_validation"]["passed"] is True
    assert package["composition_validation"]["de"]["llm_used"] is False
    assert package["composed_report"]["de"]["run_id"] == "20260402T101500Z"
    assert len(package["composed_report"]["de"]["sections"]) >= 7


def test_no_free_sources_phrase_is_enforced_for_contact_gap(monkeypatch):
    monkeypatch.setattr("src.agents.report_writer.get_openai_api_key", lambda: "")
    pipeline_data = _base_pipeline_data()
    pipeline_data["research_readiness"] = {
        "readiness_blockers": [
            {
                "field_key": "minimum_package.verified_decision_makers",
                "availability": "internal_customer",
                "reason": "Kontaktdaten nur intern verfuegbar.",
            }
        ]
    }
    agent = ReportWriterAgent()
    context = agent._build_context(pipeline_data=pipeline_data)
    blueprint = load_report_blueprint("de")
    draft = agent._fallback_draft(language="de", blueprint=blueprint, context=context)
    assert "keine freien Quellen" in agent._draft_blob_text(draft)

    sanitized_sections = [
        section.model_copy(
            update={
                "summary": section.summary.replace("keine freien Quellen", "Kontaktluecke"),
                "key_points": [
                    point
                    for point in section.key_points
                    if "keine freien Quellen" not in point
                ],
            }
        )
        for section in draft.sections
    ]
    tampered = draft.model_copy(
        update={
            "blocker_summary": "Blocker: Kontaktluecke ohne Quellenhinweis",
            "sections": sanitized_sections,
        }
    )
    checks = agent._validate_draft(language="de", draft=tampered, context=context)
    assert checks["passed"] is False
    assert "missing_no_free_sources_phrase" in checks["errors"]


def test_select_composed_report_prefers_valid_language_and_falls_back():
    report_package = {
        "composed_report": {
            "de": {"executive_summary": "Zusammenfassung DE"},
            "en": {"executive_summary": "Summary EN"},
        },
        "composition_validation": {
            "de": {"passed": False},
            "en": {"passed": True},
        },
    }
    selected_de = select_composed_report(report_package, "de")
    assert selected_de.get("executive_summary") == "Zusammenfassung DE"
    selected_en = select_composed_report(report_package, "en")
    assert selected_en.get("executive_summary") == "Summary EN"
