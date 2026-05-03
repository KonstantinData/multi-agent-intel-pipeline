"""Knowledge-base helpers for report composition."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.config.settings import ROOT

_REPORT_KB_ROOT = ROOT / "knowledge" / "report"

_DEFAULT_BLUEPRINT_DE: dict[str, Any] = {
    "language": "de",
    "sections": [
        {"section_id": "executive_dashboard", "heading": "Executive-Dashboard"},
        {"section_id": "opportunity_thesis", "heading": "Opportunity-These"},
        {"section_id": "company_snapshot", "heading": "Unternehmens-Snapshot"},
        {"section_id": "financial_inventory", "heading": "Finanz- und Inventarsignale"},
        {"section_id": "buyer_map", "heading": "Käufer- und Weiterverwendungslandkarte"},
        {"section_id": "stakeholder_map", "heading": "Stakeholder-Map"},
        {"section_id": "validation_plan", "heading": "Offene Fragen und Validierungsplan"},
    ],
}

_DEFAULT_BLUEPRINT_EN: dict[str, Any] = {
    "language": "en",
    "sections": [
        {"section_id": "executive_dashboard", "heading": "Executive Dashboard"},
        {"section_id": "opportunity_thesis", "heading": "Opportunity Thesis"},
        {"section_id": "company_snapshot", "heading": "Company Snapshot"},
        {"section_id": "financial_inventory", "heading": "Financial and Inventory Signals"},
        {"section_id": "buyer_map", "heading": "Buyer and Redeployment Map"},
        {"section_id": "stakeholder_map", "heading": "Stakeholder Map"},
        {"section_id": "validation_plan", "heading": "Open Questions and Validation Plan"},
    ],
}

_DEFAULT_RULES: dict[str, Any] = {
    "pdf_rules": {
        "hide_evidence_register": True,
        "hide_long_source_list": True,
        "runtime_fields": ["run_id", "run_status"],
    },
    "phrases": {
        "de": {"no_free_sources": "keine freien Quellen"},
        "en": {"no_free_sources": "no free public sources"},
    },
    "language_rules": {
        "de": {
            "prefer_terms": ["und", "mit", "für", "nicht", "daten", "kontakt", "unternehmen"],
            "avoid_terms": ["the", "with", "and", "for", "company", "contact"],
        },
        "en": {
            "prefer_terms": ["and", "with", "for", "not", "data", "contact", "company"],
            "avoid_terms": ["und", "mit", "für", "unternehmen", "kontakt", "daten"],
        },
    },
}

_DEFAULT_QUALITY_GATES: dict[str, Any] = {
    "required_global_fields": [
        "run_id",
        "run_status",
        "company_name",
        "report_title",
        "executive_summary",
        "primary_opportunity_path",
    ],
    "min_sections": 7,
    "max_top_risks": 3,
    "max_next_steps": 5,
}


def _read_json_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


@lru_cache(maxsize=4)
def load_report_blueprint(language: str) -> dict[str, Any]:
    lang = "de" if language == "de" else "en"
    payload = _read_json_payload(_REPORT_KB_ROOT / f"blueprint_{lang}.yaml")
    if payload:
        return payload
    return _DEFAULT_BLUEPRINT_DE if lang == "de" else _DEFAULT_BLUEPRINT_EN


@lru_cache(maxsize=1)
def load_report_rules() -> dict[str, Any]:
    payload = _read_json_payload(_REPORT_KB_ROOT / "rules.yaml")
    return payload or _DEFAULT_RULES


@lru_cache(maxsize=1)
def load_report_quality_gates() -> dict[str, Any]:
    payload = _read_json_payload(_REPORT_KB_ROOT / "quality_gates.yaml")
    return payload or _DEFAULT_QUALITY_GATES
