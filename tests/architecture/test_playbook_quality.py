from __future__ import annotations

import json
from pathlib import Path

from src.orchestration.synthesis import build_contact_briefing_assets, build_playbook_assets


BENCHMARK = json.loads(
    Path("tests/golden/quality_reference/ziehl_abegg_playbook_benchmark.json").read_text()
)


def _sample_contact_intelligence() -> dict:
    return {
        "target_company_contacts": [
            {
                "name": "Joachim Ley",
                "firma": "ZIEHL-ABEGG SE",
                "rolle_titel": "CEO and COO",
                "funktion": "Executive",
                "standort": "Künzelsau",
                "quelle": "https://www.ziehl-abegg.com/company/press",
                "confidence": "high",
                "relevance_reason": "Executive sponsor for inventory and working-capital agenda.",
            },
            {
                "name": "Marco Altherr",
                "firma": "ZIEHL-ABEGG SE",
                "rolle_titel": "CFO",
                "funktion": "Finance",
                "standort": "Künzelsau",
                "quelle": "https://www.ziehl-abegg.com/company/press",
                "confidence": "high",
                "relevance_reason": "Economic buyer for cash, margin pressure, and inventory release.",
            },
        ],
        "prioritized_contacts": [
            {
                "name": "OEM Buyer",
                "firma": "Cooling OEM",
                "rolle_titel": "Head of Procurement",
                "funktion": "Procurement / Supply Chain",
                "quelle": "https://example.com/oem-buyer",
                "confidence": "medium",
                "relevance_reason": "Buyer category aligned with HVAC redeployment path.",
            }
        ],
        "coverage_quality": "medium",
    }


def _sample_company_profile() -> dict:
    return {
        "company_name": "ZIEHL-ABEGG SE",
        "headquarters": "Künzelsau",
        "financial_deep_dive": {
            "assessment": "Primary-source financial evidence captures revenue, inventories, working capital, and margin pressure.",
            "key_financials": ["Revenue 2025: EUR 1.0bn", "Margin pressure cited by management"],
            "inventory_positions": ["HVAC inventories and plant overhang in Europe"],
            "inventory_risks": ["Risk of obsolescence in legacy motor generation"],
            "balance_sheet_signals": ["Working capital pressure in Europe"],
        },
    }


def test_benchmark_file_exists_and_has_required_sections():
    assert BENCHMARK["target_company_contacts"]["required_fields"]
    assert BENCHMARK["critical_open_questions"]["required_labels"]
    assert BENCHMARK["recommended_next_steps"]["required_fields"]


def test_target_contact_assets_match_benchmark_structure():
    assets = build_contact_briefing_assets(
        company_profile=_sample_company_profile(),
        contact_intelligence=_sample_contact_intelligence(),
    )

    assert assets["target_company_contact_cards"]
    first = assets["target_company_contact_cards"][0]
    for field in BENCHMARK["target_company_contacts"]["required_fields"]:
        assert first.get(field, "n/v") != "n/v"

    role_names = {item["role_name"] for item in assets["target_company_missing_roles"]}
    assert any(required in role_names for required in BENCHMARK["target_company_contacts"]["required_role_gaps"])
    assert assets["target_company_access_path"]
    assert "no placeholder" in assets["target_company_summary"].lower()
    assert "cold outreach" in assets["target_company_summary"].lower()
    assert all(card.get("verification_status") != "unverified_excluded_from_pdf" for card in assets["target_company_contact_cards"])


def test_playbook_open_questions_match_benchmark():
    contacts = build_contact_briefing_assets(
        company_profile=_sample_company_profile(),
        contact_intelligence=_sample_contact_intelligence(),
    )
    assets = build_playbook_assets(
        company_profile=_sample_company_profile(),
        market_network={"downstream_buyers": {"companies": [{"name": "Cooling OEM"}]}},
        contact_intelligence=contacts,
        synthesis={"recommended_engagement_paths": ["excess_inventory"]},
    )

    questions = assets["critical_open_questions"]
    assert len(questions) <= BENCHMARK["critical_open_questions"]["max_items"]
    labels = {q["label"] for q in questions}
    assert "Bestandsvolumen" in labels
    assert all(q.get("meeting_criticality", "n/v") != "n/v" for q in questions)
    forbidden = BENCHMARK["critical_open_questions"]["forbidden_generic_topics"]
    for question in questions:
        text = f"{question.get('label', '')} {question.get('question', '')}".lower()
        assert not any(token in text for token in forbidden)


def test_playbook_next_steps_match_benchmark():
    contacts = build_contact_briefing_assets(
        company_profile=_sample_company_profile(),
        contact_intelligence=_sample_contact_intelligence(),
    )
    assets = build_playbook_assets(
        company_profile=_sample_company_profile(),
        market_network={"downstream_buyers": {"companies": [{"name": "Cooling OEM"}]}},
        contact_intelligence=contacts,
        synthesis={"recommended_engagement_paths": ["excess_inventory"]},
    )

    steps = assets["recommended_next_steps"]
    phases = {step["phase"] for step in steps}
    assert {"pre_meeting", "during_meeting", "post_meeting", "post_meeting_under_nda"} <= phases
    for step in steps:
        for field in BENCHMARK["recommended_next_steps"]["required_fields"]:
            assert step.get(field, "n/v") != "n/v"
        combined = " ".join(str(step.get(field, "")) for field in ("action", "goal", "expected_output")).lower()
        assert not any(phrase in combined for phrase in BENCHMARK["recommended_next_steps"]["forbidden_phrases"])
    assert any(step.get("target_person", "n/v") != "n/v" for step in steps)
    assert any("sales navigator" in step.get("action", "").lower() for step in steps)
    assert any("callable escalation path" in step.get("expected_output", "").lower() or "escalation route" in step.get("expected_output", "").lower() for step in steps)


def test_playbook_legacy_analytics_path_falls_back_to_inventory_questions():
    contacts = build_contact_briefing_assets(
        company_profile=_sample_company_profile(),
        contact_intelligence=_sample_contact_intelligence(),
    )
    assets = build_playbook_assets(
        company_profile=_sample_company_profile(),
        market_network={"downstream_buyers": {"companies": [{"name": "Cooling OEM"}]}},
        contact_intelligence=contacts,
        synthesis={"recommended_engagement_paths": ["analytics"]},
    )

    questions = assets["critical_open_questions"]
    labels = {q["label"] for q in questions}
    assert "Bestandsvolumen" in labels
    assert "Transparenzlücke" not in labels
    assert any("inventory" in q["why_critical"].lower() or "stock" in q["why_critical"].lower() for q in questions)
