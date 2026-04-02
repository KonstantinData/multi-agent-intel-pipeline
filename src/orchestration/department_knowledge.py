"""Department-specific source/policy knowledge base helpers.

Knowledge files live under:
- knowledge/sources/<department>.yaml
- knowledge/policies/<department>.yaml

Note: Files are parsed as JSON payloads (YAML-compatible because JSON is a
subset of YAML). This avoids an extra YAML dependency in runtime.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.config.settings import ROOT
from src.orchestration.contracts import DepartmentPolicy

logger = logging.getLogger(__name__)

_DEPARTMENT_TO_SLUG = {
    "CompanyDepartment": "company",
    "MarketDepartment": "market",
    "BuyerDepartment": "buyer",
    "ContactDepartment": "contact",
}

_PLACEHOLDERS = {"", "n/v", "n/a", "unknown", "none", "null"}
_PRIMARY_SOURCE_HINTS = (
    "primary",
    "annual report",
    "geschäftsbericht",
    "geschaeftsbericht",
    "10-k",
    "20-f",
    "filing",
    "sec",
    "bundesanzeiger",
    "unternehmensregister",
    "register",
)

_DEFAULT_POLICIES: dict[str, dict[str, Any]] = {
    "company": {
        "department": "CompanyDepartment",
        "required_fields": [
            "company_name",
            "description",
            "product_asset_scope",
            "financial_deep_dive.assessment",
            "financial_deep_dive.key_financials",
            "financial_deep_dive.inventory_positions",
        ],
        "source_priority": ["primary", "official_secondary", "industry_secondary"],
        "min_evidence_rules": {
            "min_sources": 3,
            "min_primary_sources": 1,
            "min_completed_tasks": 3,
        },
        "gate_rules": {
            "require_any_accepted_task": True,
            "missing_field_availability": "public",
            "missing_field_owner": "Company Department",
            "missing_field_next_step": "Run focused primary-source follow-up for missing company/financial fields.",
        },
        "blocker_templates": {
            "missing_required_field": "Required field '{field}' is missing or placeholder.",
            "insufficient_sources": "Insufficient source coverage ({actual}/{required}).",
            "insufficient_primary_sources": "Insufficient primary-source coverage ({actual}/{required}).",
            "insufficient_completed_tasks": "Insufficient completed tasks ({actual}/{required}).",
            "no_accepted_task": "No task reached accepted status.",
        },
    },
    "market": {
        "department": "MarketDepartment",
        "required_fields": [
            "industry_name",
            "assessment",
            "key_trends",
            "demand_outlook",
        ],
        "source_priority": ["official_statistics", "industry_publications", "search_trends"],
        "min_evidence_rules": {
            "min_sources": 2,
            "min_completed_tasks": 2,
        },
        "gate_rules": {
            "require_any_accepted_task": True,
            "missing_field_availability": "public",
            "missing_field_owner": "Market Department",
            "missing_field_next_step": "Widen market scan across official statistics and industry associations.",
        },
        "blocker_templates": {
            "missing_required_field": "Required market field '{field}' is missing or placeholder.",
            "insufficient_sources": "Insufficient market-source coverage ({actual}/{required}).",
            "insufficient_completed_tasks": "Insufficient completed market tasks ({actual}/{required}).",
            "no_accepted_task": "No market task reached accepted status.",
        },
    },
    "buyer": {
        "department": "BuyerDepartment",
        "required_fields": [
            "target_company",
            "peer_competitors.companies",
            "downstream_buyers.companies",
            "monetization_paths",
        ],
        "source_priority": ["company_disclosures", "trade_sources", "marketplaces"],
        "min_evidence_rules": {
            "min_sources": 2,
            "min_completed_tasks": 2,
        },
        "gate_rules": {
            "require_any_accepted_task": True,
            "missing_field_availability": "public",
            "missing_field_owner": "Buyer Department",
            "missing_field_next_step": "Expand peer/buyer map with role-specific search variants.",
        },
        "blocker_templates": {
            "missing_required_field": "Required buyer field '{field}' is missing or placeholder.",
            "insufficient_sources": "Insufficient buyer-source coverage ({actual}/{required}).",
            "insufficient_completed_tasks": "Insufficient completed buyer tasks ({actual}/{required}).",
            "no_accepted_task": "No buyer task reached accepted status.",
        },
    },
    "contact": {
        "department": "ContactDepartment",
        "required_fields": [
            "target_company_summary",
            "target_company_contacts",
            "target_company_access_path",
        ],
        "source_priority": ["official_people_pages", "linkedin_public", "trade_mentions"],
        "min_evidence_rules": {
            "min_sources": 1,
            "min_completed_tasks": 2,
        },
        "gate_rules": {
            "require_any_accepted_task": False,
            "missing_field_availability": "public",
            "missing_field_owner": "Contact Department",
            "missing_field_next_step": "Apply DE/EN role-based search patterns and verify at least one channel.",
        },
        "blocker_templates": {
            "missing_required_field": "Required contact field '{field}' is missing; if public search is exhausted, mark as 'keine freien Quellen'.",
            "insufficient_sources": "Insufficient contact-source coverage ({actual}/{required}).",
            "insufficient_completed_tasks": "Insufficient completed contact tasks ({actual}/{required}).",
        },
    },
}

_DEFAULT_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "company": {
        "department": "CompanyDepartment",
        "source_priority": ["primary", "official_secondary", "industry_secondary"],
        "sources": [
            {
                "name": "Unternehmensregister",
                "url": "https://www.unternehmensregister.de/",
                "department": "CompanyDepartment",
                "priority": "primary",
                "free_access": "public",
                "evidence_type": "hard",
                "confidence_weight": 1.0,
                "search_patterns_de": ["<firma> unternehmensregister jahresabschluss", "<firma> bilanz unternehmensregister"],
                "search_patterns_en": ["<company> annual filing register"],
                "fallback_label": "keine freien Quellen",
            },
            {
                "name": "Bundesanzeiger",
                "url": "https://www.bundesanzeiger.de/",
                "department": "CompanyDepartment",
                "priority": "primary",
                "free_access": "public",
                "evidence_type": "hard",
                "confidence_weight": 0.95,
                "search_patterns_de": ["<firma> bundesanzeiger jahresabschluss", "<firma> inventar abschreibung"],
                "search_patterns_en": ["<company> federal gazette filing"],
                "fallback_label": "keine freien Quellen",
            },
            {
                "name": "Investor Relations",
                "url": "https://",
                "department": "CompanyDepartment",
                "priority": "official_secondary",
                "free_access": "public",
                "evidence_type": "hard",
                "confidence_weight": 0.9,
                "search_patterns_de": ["<firma> investor relations geschäftsbericht", "<firma> annual report pdf"],
                "search_patterns_en": ["<company> investor relations annual report"],
                "fallback_label": "keine freien Quellen",
            },
        ],
    },
    "market": {
        "department": "MarketDepartment",
        "source_priority": ["official_statistics", "industry_publications", "search_trends"],
        "sources": [
            {
                "name": "Destatis GENESIS",
                "url": "https://www-genesis.destatis.de/",
                "department": "MarketDepartment",
                "priority": "official_statistics",
                "free_access": "public",
                "evidence_type": "hard",
                "confidence_weight": 0.95,
                "search_patterns_de": ["destatis <branche> produktion index", "destatis <branche> preisindex"],
                "search_patterns_en": ["destatis <industry> index germany"],
                "fallback_label": "keine freien Quellen",
            },
            {
                "name": "Eurostat",
                "url": "https://ec.europa.eu/eurostat",
                "department": "MarketDepartment",
                "priority": "official_statistics",
                "free_access": "public",
                "evidence_type": "hard",
                "confidence_weight": 0.9,
                "search_patterns_de": ["eurostat <branche> eu produktion", "eurostat demand supply <industry>"],
                "search_patterns_en": ["eurostat <industry> demand supply EU"],
                "fallback_label": "keine freien Quellen",
            },
            {
                "name": "Google Trends",
                "url": "https://trends.google.com/",
                "department": "MarketDepartment",
                "priority": "search_trends",
                "free_access": "public",
                "evidence_type": "indicative",
                "confidence_weight": 0.55,
                "search_patterns_de": ["<produktkategorie>", "<firma> ersatzteile"],
                "search_patterns_en": ["<product category>", "<company> aftermarket"],
                "fallback_label": "keine freien Quellen",
            },
        ],
    },
    "buyer": {
        "department": "BuyerDepartment",
        "source_priority": ["company_disclosures", "trade_sources", "marketplaces"],
        "sources": [
            {
                "name": "Company Websites / Press",
                "url": "https://",
                "department": "BuyerDepartment",
                "priority": "company_disclosures",
                "free_access": "public",
                "evidence_type": "hard",
                "confidence_weight": 0.85,
                "search_patterns_de": ["<buyer> pressemitteilung lager", "<buyer> ankauf restposten"],
                "search_patterns_en": ["<buyer> inventory acquisition", "<buyer> surplus parts"],
                "fallback_label": "keine freien Quellen",
            },
            {
                "name": "Trade Publications",
                "url": "https://",
                "department": "BuyerDepartment",
                "priority": "trade_sources",
                "free_access": "public",
                "evidence_type": "indicative",
                "confidence_weight": 0.65,
                "search_patterns_de": ["<branche> händler netzwerk", "<branche> aftermarket partner"],
                "search_patterns_en": ["<industry> aftermarket distributors", "<industry> secondary market buyers"],
                "fallback_label": "keine freien Quellen",
            },
        ],
    },
    "contact": {
        "department": "ContactDepartment",
        "source_priority": ["official_people_pages", "linkedin_public", "trade_mentions"],
        "sources": [
            {
                "name": "Company Leadership Pages",
                "url": "https://",
                "department": "ContactDepartment",
                "priority": "official_people_pages",
                "free_access": "public",
                "evidence_type": "hard",
                "confidence_weight": 0.9,
                "search_patterns_de": ["<firma> leitung einkauf", "<firma> operations leiter"],
                "search_patterns_en": ["<company> procurement head", "<company> operations director"],
                "fallback_label": "keine freien Quellen",
            },
            {
                "name": "LinkedIn Public Profiles",
                "url": "https://www.linkedin.com/",
                "department": "ContactDepartment",
                "priority": "linkedin_public",
                "free_access": "public",
                "evidence_type": "indicative",
                "confidence_weight": 0.7,
                "search_patterns_de": ["site:linkedin.com <firma> leiter einkauf", "site:linkedin.com <firma> supply chain"],
                "search_patterns_en": ["site:linkedin.com <company> head procurement", "site:linkedin.com <company> operations director"],
                "fallback_label": "keine freien Quellen",
            },
        ],
    },
}


def _slug_for_department(department: str) -> str:
    if department not in _DEPARTMENT_TO_SLUG:
        raise KeyError(f"Unknown department: {department}")
    return _DEPARTMENT_TO_SLUG[department]


def _read_json_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return {}
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Could not parse KB payload %s: %s", path, exc)
        return {}
    return parsed if isinstance(parsed, dict) else {}


@lru_cache(maxsize=8)
def load_department_policy(department: str) -> DepartmentPolicy:
    slug = _slug_for_department(department)
    path = ROOT / "knowledge" / "policies" / f"{slug}.yaml"
    payload = _read_json_payload(path) or dict(_DEFAULT_POLICIES[slug])
    payload.setdefault("department", department)
    return DepartmentPolicy.from_dict(payload)


@lru_cache(maxsize=8)
def load_department_source_profile(department: str) -> dict[str, Any]:
    slug = _slug_for_department(department)
    path = ROOT / "knowledge" / "sources" / f"{slug}.yaml"
    payload = _read_json_payload(path) or dict(_DEFAULT_SOURCE_PROFILES[slug])
    payload["department"] = department
    payload.setdefault("source_priority", [])
    payload.setdefault("sources", [])
    return payload


def _field_value(payload: dict[str, Any], dotted_field: str) -> Any:
    current: Any = payload
    for token in dotted_field.split("."):
        if isinstance(current, dict):
            current = current.get(token)
        else:
            return None
    return current


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in _PLACEHOLDERS
    if isinstance(value, list):
        if not value:
            return False
        return any(_is_present(item) for item in value)
    if isinstance(value, dict):
        if not value:
            return False
        return any(_is_present(item) for item in value.values())
    return True


def _is_primary_source(source: dict[str, Any]) -> bool:
    source_type = str(source.get("source_type", "") or "").strip().lower()
    if source_type == "primary":
        return True
    text = " ".join(
        str(source.get(field, "") or "").strip().lower()
        for field in ("title", "url", "summary")
    )
    return any(token in text for token in _PRIMARY_SOURCE_HINTS)


def evaluate_department_policy_gate(
    *,
    department: str,
    policy: DepartmentPolicy,
    section_payload: dict[str, Any],
    completed_tasks: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    open_questions: list[str] | None = None,
) -> dict[str, Any]:
    """Evaluate final package quality against department-specific policy."""
    missing_fields = [
        field_name
        for field_name in policy.required_fields
        if not _is_present(_field_value(section_payload, field_name))
    ]
    open_questions_text = " ".join(str(item) for item in (open_questions or [])).lower()
    availability = str(policy.gate_rules.get("missing_field_availability", "public") or "public")
    owner = str(policy.gate_rules.get("missing_field_owner", f"{department} Lead") or f"{department} Lead")
    next_step = str(
        policy.gate_rules.get(
            "missing_field_next_step",
            "Run targeted follow-up to close mandatory department fields.",
        )
    )
    if department == "ContactDepartment" and (
        "keine freien quellen" in open_questions_text or "no public" in open_questions_text
    ):
        availability = "internal_customer"

    blockers: list[dict[str, Any]] = []
    missing_field_template = policy.blocker_templates.get(
        "missing_required_field",
        "Required field '{field}' is missing or placeholder.",
    )
    for idx, field_name in enumerate(missing_fields, start=1):
        blockers.append(
            {
                "blocker_id": f"{department.lower()}_missing_field_{idx}",
                "field_key": field_name,
                "availability": availability,
                "severity": "hard",
                "reason": missing_field_template.format(field=field_name),
                "owner": owner,
                "next_step": next_step,
            }
        )

    accepted_tasks = sum(1 for item in completed_tasks if str(item.get("status", "")).lower() == "accepted")
    completed_count = sum(
        1
        for item in completed_tasks
        if str(item.get("status", "")).lower() in {"accepted", "degraded", "blocked", "skipped"}
    )
    total_sources = len([item for item in sources if isinstance(item, dict)])
    primary_sources = len([item for item in sources if isinstance(item, dict) and _is_primary_source(item)])

    evidence_checks = {
        "min_sources": {
            "required": int(policy.min_evidence_rules.get("min_sources", 0)),
            "actual": total_sources,
        },
        "min_primary_sources": {
            "required": int(policy.min_evidence_rules.get("min_primary_sources", 0)),
            "actual": primary_sources,
        },
        "min_completed_tasks": {
            "required": int(policy.min_evidence_rules.get("min_completed_tasks", 0)),
            "actual": completed_count,
        },
    }

    for key, values in evidence_checks.items():
        required = int(values.get("required", 0) or 0)
        actual = int(values.get("actual", 0) or 0)
        if required <= 0 or actual >= required:
            continue
        template = policy.blocker_templates.get(
            key.replace("min_", "insufficient_"),
            "Minimum threshold not met for '{field}' ({actual}/{required}).",
        )
        blockers.append(
            {
                "blocker_id": f"{department.lower()}_{key}",
                "field_key": key,
                "availability": availability,
                "severity": "hard",
                "reason": template.format(field=key, actual=actual, required=required),
                "owner": owner,
                "next_step": next_step,
            }
        )

    if bool(policy.gate_rules.get("require_any_accepted_task", True)) and accepted_tasks < 1:
        blockers.append(
            {
                "blocker_id": f"{department.lower()}_accepted_task",
                "field_key": "accepted_tasks",
                "availability": availability,
                "severity": "hard",
                "reason": policy.blocker_templates.get(
                    "no_accepted_task",
                    "No task reached accepted status.",
                ),
                "owner": owner,
                "next_step": next_step,
            }
        )

    return {
        "department": department,
        "passed": not blockers,
        "missing_required_fields": missing_fields,
        "accepted_tasks": accepted_tasks,
        "completed_tasks": completed_count,
        "total_tasks": len(completed_tasks),
        "source_counts": {
            "total": total_sources,
            "primary": primary_sources,
        },
        "source_priority": list(policy.source_priority),
        "blockers": blockers,
    }

