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
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.config.settings import ROOT
from src.orchestration.contracts import DepartmentPolicy

# Set LIQUISTO_STRICT_PROFILE_LOADING=1 to disable silent fallback for
# source profiles and policies.  In strict mode a missing or malformed
# file raises immediately instead of returning a hardcoded default.
_STRICT_PROFILE_LOADING = os.getenv("LIQUISTO_STRICT_PROFILE_LOADING", "").strip() == "1"

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
            "goods_classification",
            "financial_deep_dive.assessment",
            "financial_deep_dive.key_financials",
            "financial_deep_dive.inventory_positions",
            "transaction_event_intelligence.assessment",
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
            "missing_field_next_step": "Run focused primary-source follow-up for missing company, financial, product/asset scope, goods classification, or transaction event intelligence fields.",
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
            "trend_direction",
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
            "peer_competitors.assessment",
            "downstream_buyers.companies",
            "downstream_buyers.assessment",
            "monetization_paths",
            "redeployment_paths",
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
            "missing_field_next_step": "Expand peer/buyer map and redeployment paths with role-specific and marketplace search variants.",
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
            "coverage_quality",
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
            "missing_field_next_step": "Apply DE/EN role-based search patterns across Board / Geschäftsführung, Finance / CFO / Controlling, Procurement / Einkauf, Operations / Werk / Supply Chain, Aftermarket / Service, and Divisional / BU leadership. Verify at least one reachable channel.",
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
                "search_patterns_de": ["<firma> unternehmensregister jahresabschluss", "<firma> bilanz unternehmensregister", "<firma> inventar anlagevermögen unternehmensregister"],
                "search_patterns_en": ["<company> annual filing german commercial register", "<company> balance sheet register filing"],
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
                "search_patterns_de": ["<firma> bundesanzeiger jahresabschluss", "<firma> inventar abschreibung bundesanzeiger", "<firma> vorräte warenbestand bundesanzeiger"],
                "search_patterns_en": ["<company> federal gazette annual filing", "<company> inventory positions germany"],
                "fallback_label": "keine freien Quellen",
            },
            {
                "name": "OpenCorporates",
                "url": "https://opencorporates.com/",
                "department": "CompanyDepartment",
                "priority": "primary",
                "free_access": "public",
                "evidence_type": "hard",
                "confidence_weight": 0.85,
                "search_patterns_de": ["<firma> opencorporates handelsregister international", "<firma> firmenprofil ausland register"],
                "search_patterns_en": ["<company> opencorporates company filing", "<company> corporate registry international"],
                "fallback_label": "keine freien Quellen",
            },
            {
                "name": "Northdata Firmenauskunft",
                "url": "https://www.northdata.de/",
                "department": "CompanyDepartment",
                "priority": "official_secondary",
                "free_access": "public",
                "evidence_type": "hard",
                "confidence_weight": 0.9,
                "search_patterns_de": ["northdata <firma> finanzlage umsatz mitarbeiter", "northdata <firma> geschäftsführung jahresabschluss", "northdata <firma> warenklassifikation branche"],
                "search_patterns_en": ["northdata <company> company profile financials", "northdata <company> management annual report"],
                "fallback_label": "keine freien Quellen",
            },
            {
                "name": "BMWK Branchenberichte",
                "url": "https://www.bmwk.de/",
                "department": "CompanyDepartment",
                "priority": "industry_secondary",
                "free_access": "public",
                "evidence_type": "indicative",
                "confidence_weight": 0.7,
                "search_patterns_de": ["bmwk <branche> branchenbericht lage konjunktur", "bmwk <branche> umsatz beschäftigung sektoranalyse", "bmwk <branche> strukturbericht wettbewerbsfähigkeit"],
                "search_patterns_en": ["bmwk <industry> sector report germany", "bmwk <industry> market analysis competitiveness"],
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
                "search_patterns_de": ["destatis <branche> produktion auftragseingang index", "destatis <branche> erzeugerpreisindex preisdruck", "destatis <branche> kapazitätsauslastung überkapazität"],
                "search_patterns_en": ["destatis <industry> output order intake index germany", "destatis <industry> producer price supply pressure"],
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
                "search_patterns_de": ["eurostat <branche> eu produktion nachfragerückgang", "eurostat <branche> kapazitätsauslastung europa rückgang"],
                "search_patterns_en": ["eurostat <industry> demand decline growth EU", "eurostat <industry> overcapacity utilisation rate"],
                "fallback_label": "keine freien Quellen",
            },
            {
                "name": "ifo Institut Konjunkturumfrage",
                "url": "https://www.ifo.de/",
                "department": "MarketDepartment",
                "priority": "industry_publications",
                "free_access": "public",
                "evidence_type": "hard",
                "confidence_weight": 0.8,
                "search_patterns_de": ["ifo <branche> geschäftsklima konjunktur lage", "ifo <branche> auftragseingang erwartungen nachfrage", "ifo <branche> überkapazitäten preiserwartungen rückgang"],
                "search_patterns_en": ["ifo <industry> business climate survey germany", "ifo <industry> demand outlook capacity utilisation", "ifo <industry> order intake expectations decline growth"],
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
                "search_patterns_de": ["<produktkategorie> nachfrage rückgang überkapazität", "<produktkategorie> gebraucht ersatzteile restbestand", "<firma> bestand lager überschuss"],
                "search_patterns_en": ["<product category> demand decline growth trend", "<product category> surplus aftermarket used equipment", "<company> overcapacity inventory surplus"],
                "fallback_label": "keine freien Quellen",
            },
        ],
    },
    "buyer": {
        "department": "BuyerDepartment",
        "source_priority": ["company_disclosures", "trade_sources", "marketplaces"],
        "sources": [
            {
                "name": "DGAP Corporate News",
                "url": "https://www.dgap.de/",
                "department": "BuyerDepartment",
                "priority": "company_disclosures",
                "free_access": "public",
                "evidence_type": "hard",
                "confidence_weight": 0.85,
                "search_patterns_de": ["<buyer> pressemitteilung restposten ankauf lager", "<buyer> unternehmensnachricht inventar übernahme", "<buyer> akquisition gebrauchtanlage asset deal"],
                "search_patterns_en": ["<buyer> press release inventory acquisition surplus", "<buyer> corporate announcement asset purchase deal", "<buyer> used equipment acquisition redeployment"],
                "fallback_label": "keine freien Quellen",
            },
            {
                "name": "Maschinenmarkt",
                "url": "https://www.maschinenmarkt.vogel.de/",
                "department": "BuyerDepartment",
                "priority": "trade_sources",
                "free_access": "public",
                "evidence_type": "indicative",
                "confidence_weight": 0.65,
                "search_patterns_de": ["<branche> händler restposten gebrauchtmaschinen ankauf", "<branche> aftermarket partner wiederverwendung redeployment", "<branche> liquidation sekundärmarkt surplus"],
                "search_patterns_en": ["<industry> aftermarket distributor used equipment resale", "<industry> secondary market buyers redeployment channels", "<industry> liquidation surplus disposal"],
                "fallback_label": "keine freien Quellen",
            },
            {
                "name": "Surplex Industrial Auctions",
                "url": "https://www.surplex.com/",
                "department": "BuyerDepartment",
                "priority": "marketplaces",
                "free_access": "public",
                "evidence_type": "indicative",
                "confidence_weight": 0.6,
                "search_patterns_de": ["surplex <anlagenkategorie> auktion gebraucht ankauf", "surplex <branche> maschinenauktion restbestand", "<anlagenkategorie> industrieauktion wiederverkauf redeployment"],
                "search_patterns_en": ["surplex <asset category> industrial auction used", "surplex <industry> machinery surplus sale", "<asset category> auction aftermarket redeployment secondary"],
                "fallback_label": "keine freien Quellen",
            },
        ],
    },
    "contact": {
        "department": "ContactDepartment",
        "source_priority": ["official_people_pages", "linkedin_public", "trade_mentions"],
        "sources": [
            {
                "name": "Handelsregister Führungspersonen",
                "url": "https://www.handelsregister.de/",
                "department": "ContactDepartment",
                "priority": "official_people_pages",
                "free_access": "public",
                "evidence_type": "hard",
                "confidence_weight": 0.9,
                "search_patterns_de": ["handelsregister <firma> geschäftsführer vorstand", "handelsregister <firma> prokuristen leitungsorgane", "<firma> hr-nummer geschäftsführer amtsgericht"],
                "search_patterns_en": ["<company> german commercial register managing director", "<company> handelsregister board officers germany"],
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
                "search_patterns_de": ["site:linkedin.com <firma> geschäftsführer CEO vorstand", "site:linkedin.com <firma> leiter einkauf procurement", "site:linkedin.com <firma> cfo finanzvorstand controlling", "site:linkedin.com <firma> operations leiter werk supply chain", "site:linkedin.com <firma> aftermarket service leiter", "site:linkedin.com <firma> bereichsleiter sparte divisional"],
                "search_patterns_en": ["site:linkedin.com <company> managing director CEO board", "site:linkedin.com <company> head procurement CFO finance", "site:linkedin.com <company> operations director plant manager", "site:linkedin.com <company> aftermarket service lead", "site:linkedin.com <company> divisional business unit head"],
                "fallback_label": "keine freien Quellen",
            },
            {
                "name": "Wer liefert was B2B-Verzeichnis",
                "url": "https://www.wlw.de/",
                "department": "ContactDepartment",
                "priority": "trade_mentions",
                "free_access": "public",
                "evidence_type": "indicative",
                "confidence_weight": 0.6,
                "search_patterns_de": ["wlw <firma> ansprechpartner kontakt einkauf", "wlw <branche> lieferant geschäftsführer kontakt", "<firma> messe sprecher branchenveranstaltung kontakt", "<firma> pressemitteilung ansprechpartner verantwortlich"],
                "search_patterns_en": ["wlw <company> contact person procurement trade", "<company> trade show speaker contact", "<company> press contact spokesperson"],
                "fallback_label": "keine freien Quellen",
            },
        ],
    },
}


def _slug_for_department(department: str) -> str:
    if department not in _DEPARTMENT_TO_SLUG:
        raise KeyError(f"Unknown department: {department}")
    return _DEPARTMENT_TO_SLUG[department]


def _read_json_payload(path: Path, *, strict: bool = False, department: str = "") -> dict[str, Any]:
    if not path.exists():
        if strict:
            raise FileNotFoundError(f"KB file not found for {department or 'unknown department'}: {path}")
        return {}
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        if strict:
            raise OSError(f"Cannot read KB file for {department or 'unknown department'}: {path}: {exc}") from exc
        return {}
    if not raw:
        if strict:
            raise ValueError(f"KB file is empty for {department or 'unknown department'}: {path}")
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        if strict:
            raise ValueError(f"Cannot parse KB file for {department or 'unknown department'}: {path}: {exc}") from exc
        logger.warning("Could not parse KB payload %s: %s", path, exc)
        return {}
    if not isinstance(parsed, dict):
        if strict:
            raise ValueError(f"KB file must contain a JSON object for {department or 'unknown department'}: {path}")
        return {}
    return parsed


@lru_cache(maxsize=8)
def load_department_policy(department: str) -> DepartmentPolicy:
    slug = _slug_for_department(department)
    path = ROOT / "knowledge" / "policies" / f"{slug}.yaml"
    raw_payload = _read_json_payload(path, strict=_STRICT_PROFILE_LOADING, department=department)
    if not raw_payload:
        if _STRICT_PROFILE_LOADING:
            raise RuntimeError(
                f"Department policy file missing or unparsable: {path}. "
                "Fix the file or unset LIQUISTO_STRICT_PROFILE_LOADING."
            )
        logger.warning("Policy file %s missing or empty — using hardcoded default.", path)
        raw_payload = dict(_DEFAULT_POLICIES[slug])
    payload = raw_payload
    payload.setdefault("department", department)
    return DepartmentPolicy.from_dict(payload)


@lru_cache(maxsize=8)
def load_department_source_profile(department: str) -> dict[str, Any]:
    slug = _slug_for_department(department)
    path = ROOT / "knowledge" / "sources" / f"{slug}.yaml"
    raw_payload = _read_json_payload(path, strict=_STRICT_PROFILE_LOADING, department=department)
    if not raw_payload:
        if _STRICT_PROFILE_LOADING:
            raise RuntimeError(
                f"Department source profile file missing or unparsable: {path}. "
                "Fix the file or unset LIQUISTO_STRICT_PROFILE_LOADING."
            )
        logger.warning("Source profile %s missing or empty — using hardcoded default.", path)
        raw_payload = dict(_DEFAULT_SOURCE_PROFILES[slug])
    payload = raw_payload
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

