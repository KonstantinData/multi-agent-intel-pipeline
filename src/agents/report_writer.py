"""Report writer agent for final operator-facing report packaging."""
from __future__ import annotations

import json
import logging
from typing import Any

from src.config.settings import (
    get_openai_api_key,
    get_openai_max_retries,
    get_openai_timeout_seconds,
    get_role_model_selection,
    resolve_model_temperature,
)
from src.models.report_writer import ReportDraft, ReportSectionDraft
from src.orchestration.envelope import resolve_visual_focus
from src.orchestration.report_knowledge import (
    load_report_blueprint,
    load_report_quality_gates,
    load_report_rules,
)
from src.security.secret_guard import assert_no_secrets_in_payload

logger = logging.getLogger(__name__)

_PLACEHOLDERS = {"", "n/v", "n/a", "unknown", "none", "null"}


def _safe_text(value: Any, default: str = "n/v") -> str:
    text = str(value or "").strip()
    return text if text else default


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _PLACEHOLDERS
    if isinstance(value, list):
        return len([item for item in value if not _is_missing(item)]) == 0
    return False


class ReportWriterAgent:
    """Hybrid report composer: LLM composition + hard validation + stable payload."""

    def __init__(self) -> None:
        self.chat_model, self.structured_model = get_role_model_selection("ReportWriter")
        self.rules = load_report_rules()
        self.quality_gates = load_report_quality_gates()

    def build_report_package(
        self,
        *,
        pipeline_data: dict[str, Any],
        department_packages: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        synthesis = dict(pipeline_data.get("synthesis", {}) or {})
        company = dict(pipeline_data.get("company_profile", {}) or {})
        quality = dict(pipeline_data.get("quality_review", {}) or {})
        data_request_sheet = dict(pipeline_data.get("data_request_sheet", {}) or {})
        outreach_playbook = dict(pipeline_data.get("outreach_playbook", {}) or {})
        context = self._build_context(pipeline_data=pipeline_data)

        composed_report: dict[str, Any] = {}
        validation: dict[str, Any] = {}
        for language in ("de", "en"):
            draft, checks = self._compose_for_language(
                language=language,
                context=context,
                pipeline_data=pipeline_data,
            )
            composed_report[language] = draft.model_dump(mode="json")
            validation[language] = checks

        passed = all(
            bool(item.get("passed", False))
            for item in validation.values()
            if isinstance(item, dict)
        )
        report_title = composed_report.get("en", {}).get(
            "report_title",
            f"Liquisto Briefing - {company.get('company_name', 'n/v')}",
        )
        return {
            "report_status": "ready" if passed else "ready_with_warnings",
            "report_title": report_title,
            "executive_summary": composed_report.get("en", {}).get(
                "executive_summary",
                synthesis.get("executive_summary", "n/v"),
            ),
            "department_visual_focus": {
                name: resolve_visual_focus(package)
                for name, package in department_packages.items()
            },
            "recommended_sections": [
                str(section.get("heading", "n/v"))
                for section in load_report_blueprint("en").get("sections", [])
                if isinstance(section, dict)
            ],
            "open_gaps": quality.get("open_gaps", []),
            "data_request_sheet": data_request_sheet,
            "outreach_playbook": outreach_playbook,
            "composed_report": composed_report,
            "composition_validation": {
                "passed": passed,
                **validation,
            },
        }

    def _build_context(self, *, pipeline_data: dict[str, Any]) -> dict[str, Any]:
        company = dict(pipeline_data.get("company_profile", {}) or {})
        synthesis = dict(pipeline_data.get("synthesis", {}) or {})
        readiness = dict(pipeline_data.get("research_readiness", {}) or {})
        final_briefing = dict(pipeline_data.get("final_briefing", {}) or {})
        quality = dict(pipeline_data.get("quality_review", {}) or {})
        contacts = dict(pipeline_data.get("contact_intelligence", {}) or {})
        market = dict(pipeline_data.get("market_network", {}) or {})
        deep_dive = dict(company.get("financial_deep_dive", {}) or {})
        blockers = [
            item for item in (readiness.get("readiness_blockers", []) or [])
            if isinstance(item, dict)
        ]
        has_no_free_sources_gap = any(
            str(item.get("availability", "")).strip().lower() == "internal_customer"
            and str(item.get("field_key", "")).strip() == "minimum_package.verified_decision_makers"
            for item in blockers
        )
        return {
            "run_id": _safe_text(final_briefing.get("run_id", "")),
            "run_status": _safe_text(
                final_briefing.get("status")
                or (pipeline_data.get("meeting_readiness_assessment", {}) or {}).get("run_status")
                or "n/v"
            ),
            "company_name": _safe_text(company.get("company_name", "n/v")),
            "executive_summary": _safe_text(synthesis.get("executive_summary", "n/v")),
            "primary_opportunity_path": _safe_text((synthesis.get("recommended_engagement_paths", []) or ["n/v"])[0]),
            "primary_opportunity_reasoning": _safe_text(synthesis.get("opportunity_assessment_summary", "n/v")),
            "confidence": _safe_text(synthesis.get("confidence") or quality.get("evidence_health") or "n/v"),
            "top_risks": [
                str(item).strip()
                for item in (synthesis.get("key_risks", []) or [])
                if str(item).strip()
            ][:6],
            "next_steps": [
                str(item.get("action", "")).strip()
                for item in (synthesis.get("recommended_next_steps", []) or [])
                if isinstance(item, dict) and str(item.get("action", "")).strip()
            ][:6],
            "meeting_actions": [
                str(item.get("title", "")).strip()
                for item in (pipeline_data.get("meeting_actions", []) or [])
                if isinstance(item, dict) and str(item.get("title", "")).strip()
            ][:6],
            "company_description": _safe_text(company.get("description", "n/v")),
            "industry": _safe_text(company.get("industry", "n/v")),
            "financial_assessment": _safe_text(deep_dive.get("assessment", "n/v")),
            "financial_signals": [
                str(item).strip()
                for item in (deep_dive.get("key_financials", []) or [])[:4]
                if str(item).strip()
            ],
            "inventory_signals": [
                str(item).strip()
                for item in (deep_dive.get("inventory_positions", []) or [])[:4]
                if str(item).strip()
            ],
            "buyer_assessment": _safe_text((market.get("downstream_buyers", {}) or {}).get("assessment", "n/v")),
            "contact_summary": _safe_text(contacts.get("target_company_summary", "n/v")),
            "target_contact_count": len(contacts.get("target_company_prioritized_contacts", []) or contacts.get("target_company_contacts", [])),
            "blockers": blockers,
            "critical_open_questions": [
                str(item.get("question", "")).strip()
                for item in (synthesis.get("critical_open_questions", []) or [])
                if isinstance(item, dict) and str(item.get("question", "")).strip()
            ][:6],
            "data_request_sheet": dict(pipeline_data.get("data_request_sheet", {}) or {}),
            "outreach_playbook": dict(pipeline_data.get("outreach_playbook", {}) or {}),
            "has_no_free_sources_gap": has_no_free_sources_gap,
        }

    def _compose_for_language(
        self,
        *,
        language: str,
        context: dict[str, Any],
        pipeline_data: dict[str, Any],
    ) -> tuple[ReportDraft, dict[str, Any]]:
        blueprint = load_report_blueprint(language)
        fallback = self._fallback_draft(language=language, blueprint=blueprint, context=context)
        notes: list[str] = []
        draft = fallback
        llm_used = False
        if get_openai_api_key():
            try:
                llm_payload = self._compose_with_llm(
                    language=language,
                    blueprint=blueprint,
                    context=context,
                )
                llm_draft = ReportDraft.model_validate(llm_payload)
                draft = self._merge_missing_fields(preferred=llm_draft, fallback=fallback)
                llm_used = True
            except Exception as exc:
                notes.append(f"LLM composition fallback used: {exc}")
                logger.warning("ReportWriter LLM composition failed (%s): %s", language, exc)
        checks = self._validate_draft(language=language, draft=draft, context=context)
        if not checks["passed"]:
            draft = self._merge_missing_fields(preferred=draft, fallback=fallback)
            checks = self._validate_draft(language=language, draft=draft, context=context)
        checks["llm_used"] = llm_used
        checks["notes"] = notes + list(draft.validation_notes)
        return draft, checks

    def _fallback_draft(
        self,
        *,
        language: str,
        blueprint: dict[str, Any],
        context: dict[str, Any],
    ) -> ReportDraft:
        labels = {
            "de": {
                "title": f"Liquisto Briefing - {context['company_name']}",
                "exec": "Executive-Dashboard für die Terminvorbereitung.",
                "thesis": "Fokussierte Opportunity-These aus den Department-Ergebnissen.",
                "snapshot": "Kompakter Unternehmensüberblick mit den relevanten Fakten.",
                "fin": "Finanz- und Inventarsignale für die Liquisto-Relevanz.",
                "buyer": "Buyer- und Redeployment-Karte mit priorisierten Pfaden.",
                "stakeholder": "Stakeholder-Map mit Zielkontakten und Gesprächseinstieg.",
                "validation": "Kritische offene Fragen und Validierungsplan.",
                "blockers_prefix": "Blocker: ",
                "data_request_required": "Datenanforderung erforderlich.",
                "outreach_ready": "Outreach-Playbook verfügbar.",
            },
            "en": {
                "title": f"Liquisto Briefing - {context['company_name']}",
                "exec": "Executive dashboard for meeting preparation.",
                "thesis": "Focused opportunity thesis from department evidence.",
                "snapshot": "Compact company snapshot with relevant facts.",
                "fin": "Financial and inventory signals for Liquisto relevance.",
                "buyer": "Buyer and redeployment map with prioritized paths.",
                "stakeholder": "Stakeholder map with target contacts and opening angles.",
                "validation": "Critical open questions and validation plan.",
                "blockers_prefix": "Blockers: ",
                "data_request_required": "Data request required.",
                "outreach_ready": "Outreach playbook available.",
            },
        }[language]
        no_free_phrase = self.rules.get("phrases", {}).get(language, {}).get(
            "no_free_sources",
            "keine freien Quellen" if language == "de" else "no free public sources",
        )
        blocker_reason = "; ".join(
            str(item.get("reason", "")).strip()
            for item in context.get("blockers", [])[:3]
            if str(item.get("reason", "")).strip()
        )
        if context.get("has_no_free_sources_gap"):
            blocker_reason = (
                f"{blocker_reason}; {no_free_phrase}"
                if blocker_reason
                else no_free_phrase
            )
        section_summaries = {
            "executive_dashboard": labels["exec"],
            "opportunity_thesis": f"{labels['thesis']} {_safe_text(context.get('primary_opportunity_reasoning'))}",
            "company_snapshot": f"{labels['snapshot']} {_safe_text(context.get('company_description'))}",
            "financial_inventory": f"{labels['fin']} {_safe_text(context.get('financial_assessment'))}",
            "buyer_map": f"{labels['buyer']} {_safe_text(context.get('buyer_assessment'))}",
            "stakeholder_map": f"{labels['stakeholder']} {_safe_text(context.get('contact_summary'))}",
            "validation_plan": f"{labels['validation']} {labels['blockers_prefix']}{blocker_reason or 'n/v'}",
        }
        sections: list[ReportSectionDraft] = []
        for section in blueprint.get("sections", []):
            if not isinstance(section, dict):
                continue
            section_id = _safe_text(section.get("section_id"))
            heading = _safe_text(section.get("heading"))
            summary = _safe_text(section_summaries.get(section_id, labels["validation"]))
            key_points: list[str] = []
            if section_id == "financial_inventory":
                key_points = list(context.get("financial_signals", [])) + list(context.get("inventory_signals", []))
            elif section_id == "validation_plan":
                key_points = list(context.get("critical_open_questions", [])) + [
                    str(item.get("reason", "")).strip()
                    for item in context.get("blockers", [])
                    if isinstance(item, dict) and str(item.get("reason", "")).strip()
                ]
            elif section_id == "stakeholder_map" and context.get("has_no_free_sources_gap"):
                key_points = [no_free_phrase]
            sections.append(
                ReportSectionDraft(
                    section_id=section_id,
                    heading=heading,
                    summary=summary,
                    key_points=[item for item in key_points[:4] if item],
                    decision_impact=_safe_text(
                        context.get("primary_opportunity_reasoning"),
                        "n/v",
                    ),
                )
            )
        next_steps = list(context.get("next_steps", [])) or list(context.get("meeting_actions", []))
        draft = ReportDraft(
            language=language,
            run_id=_safe_text(context.get("run_id")),
            run_status=_safe_text(context.get("run_status")),
            company_name=_safe_text(context.get("company_name")),
            report_title=labels["title"],
            executive_summary=_safe_text(context.get("executive_summary")),
            primary_opportunity_path=_safe_text(context.get("primary_opportunity_path")),
            primary_opportunity_reasoning=_safe_text(context.get("primary_opportunity_reasoning")),
            confidence=_safe_text(context.get("confidence")),
            top_risks=list(context.get("top_risks", []))[:3],
            next_steps=[item for item in next_steps[:5] if str(item).strip()],
            blocker_summary=(labels["blockers_prefix"] + blocker_reason) if blocker_reason else "",
            data_request_summary=labels["data_request_required"]
            if str((context.get("data_request_sheet", {}) or {}).get("status", "")).lower() == "required"
            else "",
            outreach_playbook_summary=labels["outreach_ready"]
            if (context.get("outreach_playbook", {}) or {}).get("steps")
            else "",
            sections=sections[: max(int(self.quality_gates.get("min_sections", 7)), 7)],
        )
        return draft

    def _compose_with_llm(
        self,
        *,
        language: str,
        blueprint: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        from openai import OpenAI

        model_name = self.structured_model or self.chat_model
        client = OpenAI(
            api_key=get_openai_api_key(),
            timeout=get_openai_timeout_seconds(),
            max_retries=get_openai_max_retries(),
        )
        system_prompt = (
            "You are ReportWriter in the Liquisto runtime. "
            "Compose concise, meeting-ready report drafts from structured runtime context. "
            "Return valid JSON only, matching the given schema. "
            "Do not include evidence register text or long source lists. "
            "Preserve run_id and run_status explicitly."
        )
        user_payload = {
            "language": language,
            "blueprint": blueprint,
            "rules": self.rules,
            "quality_gates": self.quality_gates,
            "context": context,
        }
        params: dict[str, Any] = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "report_draft",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "language": {"type": "string", "enum": ["de", "en"]},
                            "run_id": {"type": "string"},
                            "run_status": {"type": "string"},
                            "company_name": {"type": "string"},
                            "report_title": {"type": "string"},
                            "executive_summary": {"type": "string"},
                            "primary_opportunity_path": {"type": "string"},
                            "primary_opportunity_reasoning": {"type": "string"},
                            "confidence": {"type": "string"},
                            "top_risks": {"type": "array", "items": {"type": "string"}},
                            "next_steps": {"type": "array", "items": {"type": "string"}},
                            "blocker_summary": {"type": "string"},
                            "data_request_summary": {"type": "string"},
                            "outreach_playbook_summary": {"type": "string"},
                            "validation_notes": {"type": "array", "items": {"type": "string"}},
                            "sections": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "section_id": {"type": "string"},
                                        "heading": {"type": "string"},
                                        "summary": {"type": "string"},
                                        "key_points": {"type": "array", "items": {"type": "string"}},
                                        "decision_impact": {"type": "string"},
                                    },
                                    "required": ["section_id", "heading", "summary", "key_points", "decision_impact"],
                                },
                            },
                        },
                        "required": [
                            "language",
                            "run_id",
                            "run_status",
                            "company_name",
                            "report_title",
                            "executive_summary",
                            "primary_opportunity_path",
                            "primary_opportunity_reasoning",
                            "confidence",
                            "top_risks",
                            "next_steps",
                            "blocker_summary",
                            "data_request_summary",
                            "outreach_playbook_summary",
                            "validation_notes",
                            "sections",
                        ],
                    },
                },
            },
        }
        assert_no_secrets_in_payload(
            params["messages"],
            context=f"report_writer:{language}",
        )
        temperature = resolve_model_temperature(model_name, 0.2)
        if temperature is not None:
            params["temperature"] = temperature
        try:
            resp = client.chat.completions.create(**params)
        finally:
            client.close()
        content = str(resp.choices[0].message.content or "{}")
        return json.loads(content)

    def _merge_missing_fields(self, *, preferred: ReportDraft, fallback: ReportDraft) -> ReportDraft:
        merged = preferred.model_dump(mode="json")
        fallback_payload = fallback.model_dump(mode="json")
        for key, value in fallback_payload.items():
            if key == "sections":
                continue
            if _is_missing(merged.get(key)):
                merged[key] = value
        sections = merged.get("sections", [])
        if not isinstance(sections, list) or len(sections) < len(fallback.sections):
            merged["sections"] = fallback_payload["sections"]
        return ReportDraft.model_validate(merged)

    def _validate_draft(
        self,
        *,
        language: str,
        draft: ReportDraft,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        errors: list[str] = []
        for field_name in self.quality_gates.get("required_global_fields", []):
            value = getattr(draft, field_name, "")
            if _is_missing(value):
                errors.append(f"missing_required_field:{field_name}")
        min_sections = int(self.quality_gates.get("min_sections", 7) or 7)
        if len(draft.sections) < min_sections:
            errors.append("insufficient_sections")
        max_top_risks = int(self.quality_gates.get("max_top_risks", 3) or 3)
        if len(draft.top_risks) > max_top_risks:
            errors.append("too_many_top_risks")
        max_next_steps = int(self.quality_gates.get("max_next_steps", 5) or 5)
        if len(draft.next_steps) > max_next_steps:
            errors.append("too_many_next_steps")
        lang_ok, lang_reason = self._validate_language(language=language, draft=draft)
        if not lang_ok:
            errors.append(f"language_validation_failed:{lang_reason}")
        if context.get("has_no_free_sources_gap"):
            required_phrase = self.rules.get("phrases", {}).get(language, {}).get(
                "no_free_sources",
                "keine freien Quellen" if language == "de" else "no free public sources",
            ).lower()
            blob = self._draft_blob_text(draft).lower()
            if required_phrase not in blob:
                errors.append("missing_no_free_sources_phrase")
        return {"passed": not errors, "errors": errors}

    def _validate_language(self, *, language: str, draft: ReportDraft) -> tuple[bool, str]:
        rules = self.rules.get("language_rules", {}).get(language, {})
        prefer_terms = [str(item).lower() for item in rules.get("prefer_terms", [])]
        avoid_terms = [str(item).lower() for item in rules.get("avoid_terms", [])]
        blob = self._draft_blob_text(draft).lower()
        prefer_hits = sum(1 for token in prefer_terms if token in blob)
        avoid_hits = sum(1 for token in avoid_terms if token in blob)
        if prefer_hits == 0:
            return False, "no_preferred_language_markers"
        if avoid_hits > prefer_hits + 3:
            return False, "too_many_foreign_language_markers"
        return True, "ok"

    @staticmethod
    def _draft_blob_text(draft: ReportDraft) -> str:
        section_text = " ".join(
            f"{section.heading} {section.summary} {' '.join(section.key_points)} {section.decision_impact}"
            for section in draft.sections
        )
        return " ".join(
            [
                draft.report_title,
                draft.executive_summary,
                draft.primary_opportunity_reasoning,
                " ".join(draft.top_risks),
                " ".join(draft.next_steps),
                draft.blocker_summary,
                draft.data_request_summary,
                draft.outreach_playbook_summary,
                section_text,
            ]
        )
