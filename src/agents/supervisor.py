"""Supervisor agent implementation."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, TypedDict

from src.app.use_cases import build_standard_scope
from src.config import get_role_model_selection
from src.config.settings import MAX_TASK_RETRIES
from src.domain.intake import IntakeRequest, SupervisorBrief
from src.orchestration.tool_policy import resolve_allowed_tools
from src.research.extract import infer_industry
from src.research.tools import build_company_research


# F10: Typed return dicts for acceptance methods
class DepartmentAcceptanceResult(TypedDict):
    decision: str
    reason: str
    open_questions_present: bool
    substantive_content: bool
    accepted_tasks: int
    total_tasks: int


class SynthesisAcceptanceResult(TypedDict):
    decision: str
    reason: str
    generation_mode: str


class SupervisorAgent:
    name = "Supervisor"

    def __init__(self) -> None:
        self.model_name = get_role_model_selection(self.name)[0]
        self.allowed_tools = resolve_allowed_tools(self.name, "intake_normalization")

    def opening_message(self) -> str:
        return build_standard_scope()

    def build_intake_brief(self, intake: IntakeRequest) -> tuple[SupervisorBrief, dict]:
        research = build_company_research(intake.web_domain, intake.company_name)
        snapshot = research["snapshot"]
        industry_hint = infer_industry(
            title=str(snapshot.get("title", "")),
            description=str(snapshot.get("meta_description", "")),
            text=str(research.get("summary", "")),
        )
        brief = SupervisorBrief(
            submitted_company_name=intake.company_name,
            submitted_web_domain=intake.web_domain,
            verified_company_name=str(research.get("verified_company_name", intake.company_name)),
            verified_legal_name=str(research.get("verified_legal_name", "")),
            name_confidence=str(research.get("name_confidence", "low")),
            website_reachable=bool(snapshot.get("reachable")),
            homepage_url=str(research["homepage_url"]),
            page_title=str(snapshot.get("title", "")),
            meta_description=str(snapshot.get("meta_description", "")),
            raw_homepage_excerpt=str(research["summary"]),
            normalized_domain=str(research["normalized_domain"]),
            industry_hint=industry_hint,
            observations=[
                "Website reachable." if snapshot.get("reachable") else "Website not reachable.",
                f"Verified company name: {research.get('verified_company_name', intake.company_name)}.",
                f"Name confidence: {research.get('name_confidence', 'low')}.",
            ],
            sources=[
                {
                    "title": str(snapshot.get("title") or research.get("verified_company_name") or intake.company_name),
                    "url": str(research["homepage_url"]),
                    "source_type": "owned",
                    "summary": str(research["summary"]),
                }
            ],
        )
        message_payload = {
            "section": "supervisor_brief",
            "payload": asdict(brief),
            "status": "ready_for_department_routing",
        }
        return brief, message_payload

    def decide_revision(self, *, task_key: str, review: dict, attempt: int) -> dict[str, str | bool]:
        rejected_points = list(review.get("rejected_points", []))
        method_issue = bool(review.get("method_issue"))
        if rejected_points and attempt < MAX_TASK_RETRIES:
            return {
                "retry": True,
                "same_department": True,
                "authorize_coding_specialist": method_issue,
                "reason": f"Revise {task_key} for unresolved points: {', '.join(rejected_points)}.",
            }
        return {
            "retry": False,
            "same_department": True,
            "authorize_coding_specialist": False,
            "reason": f"Keep {task_key} conservative and document the remaining gap.",
        }

    def accept_department_package(self, *, department: str, package: dict) -> DepartmentAcceptanceResult:
        completed_tasks = package.get("completed_tasks", [])
        open_questions = package.get("open_questions", [])
        section_payload = package.get("section_payload", {})
        has_payload = bool(section_payload)

        # Substantive content check: payload must contain non-empty data
        # beyond just default/skeleton fields
        substantive = False
        if has_payload:
            for key, value in section_payload.items():
                if key == "sources":
                    continue
                if isinstance(value, str) and value not in ("", "n/v"):
                    substantive = True
                    break
                if isinstance(value, list) and value:
                    substantive = True
                    break
                if isinstance(value, dict):
                    companies = value.get("companies", [])
                    if isinstance(companies, list) and companies:
                        substantive = True
                        break
                    inner_vals = [v for k, v in value.items() if k not in ("assessment", "sources")]
                    if any(v for v in inner_vals if v and v != "n/v"):
                        substantive = True
                        break

        # Task quality check: at least one task must be accepted
        accepted_tasks = sum(1 for t in completed_tasks if t.get("status") == "accepted")
        rejected_tasks = sum(1 for t in completed_tasks if t.get("status") == "rejected")
        all_rejected = rejected_tasks == len(completed_tasks) and len(completed_tasks) > 0

        # Admission decision: explicit three-outcome gate
        if has_payload and substantive and bool(completed_tasks) and not all_rejected and accepted_tasks > 0:
            decision = "accepted"
            reason = f"{department} package accepted for synthesis ({accepted_tasks}/{len(completed_tasks)} tasks accepted)."
        elif has_payload and substantive and not all_rejected:
            decision = "accepted_with_gaps"
            reason = f"{department} package accepted with gaps ({accepted_tasks}/{len(completed_tasks)} tasks accepted)."
        else:
            decision = "rejected"
            if all_rejected:
                reason = f"{department} package rejected — all tasks failed."
            elif not substantive and has_payload:
                reason = f"{department} package rejected — payload structure present but lacks substantive content."
            else:
                reason = f"{department} package rejected — incomplete."
        return {
            "decision": decision,
            "reason": reason,
            "open_questions_present": bool(open_questions),
            "substantive_content": substantive,
            "accepted_tasks": accepted_tasks,
            "total_tasks": len(completed_tasks),
        }

    def accept_synthesis(self, *, synthesis_payload: dict) -> SynthesisAcceptanceResult:
        """Three-outcome gate for synthesis output (F3)."""
        target_company = str(synthesis_payload.get("target_company", "n/v"))
        executive_summary = str(synthesis_payload.get("executive_summary", ""))
        generation_mode = str(synthesis_payload.get("generation_mode", "unknown"))
        has_target = target_company not in ("n/v", "")
        has_summary = len(executive_summary) > 20 and executive_summary != "n/v"

        if has_target and has_summary and generation_mode == "normal":
            decision = "accepted"
            reason = "Cross-domain synthesis accepted."
        elif has_target and generation_mode == "fallback":
            decision = "accepted_with_gaps"
            reason = "Synthesis accepted with gaps — fallback generation mode."
        elif has_target:
            decision = "accepted_with_gaps"
            reason = "Synthesis accepted with gaps — evidence quality uncertain."
        else:
            decision = "rejected"
            reason = (
                "Cross-domain synthesis rejected — no target company identified."
                if not has_target
                else "Cross-domain synthesis rejected — executive summary insufficient."
            )
        return {
            "decision": decision,
            "reason": reason,
            "generation_mode": generation_mode,
        }

    def route_follow_up(self, *, question: str) -> dict[str, str]:
        """Route a UI follow-up question to the responsible department."""
        return self.route_question(question=question, source="user_ui")

    def route_question(self, *, question: str, source: str = "user_ui") -> dict[str, str]:
        """Unified router for both synthesis back-requests and UI follow-up questions.

        Uses weighted keyword scoring with priority tiers. Highest-scoring
        department wins. Ties are broken by specificity (Contact > Buyer >
        Market > Synthesis > Company).

        source: "synthesis" | "user_ui"
        """
        lowered = question.lower()

        # (department, keywords_with_weights) — higher weight = more specific
        _ROUTING_RULES: list[tuple[str, list[tuple[str, int]]]] = [
            ("ContactDepartment", [
                ("contact", 3), ("ansprechpartner", 3), ("entscheider", 3),
                ("linkedin", 3), ("outreach", 2), ("person", 1), ("name", 1),
                ("rolle", 2), ("procurement lead", 3), ("decision-maker", 3),
                ("einkäufer", 3), ("einkauf", 2),
            ]),
            ("BuyerDepartment", [
                ("buyer", 3), ("buyers", 3), ("käufer", 3), ("resale", 3),
                ("redeployment", 3), ("aftermarket", 3), ("competitor", 2),
                ("peer", 2), ("downstream", 2), ("monetization", 2),
                ("wiederverkauf", 3), ("wettbewerber", 2),
            ]),
            ("MarketDepartment", [
                ("market", 2), ("markt", 2), ("demand", 3), ("supply", 3),
                ("capacity", 2), ("circular", 3), ("analytics", 2),
                ("repurposing", 3), ("overcapacity", 3), ("nachfrage", 3),
                ("angebot", 2), ("trend", 1),
            ]),
            ("SynthesisDepartment", [
                ("opportunity", 3), ("liquisto", 3), ("meeting", 2),
                ("next step", 3), ("synthesis", 3), ("briefing", 3),
                ("zusammenfassung", 3), ("gesamtbild", 3), ("strategie", 2),
            ]),
            ("CompanyDepartment", [
                ("company", 2), ("firma", 2), ("unternehmen", 2),
                ("revenue", 2), ("umsatz", 2), ("product", 1), ("produkt", 1),
                ("economic", 2), ("wirtschaftlich", 2), ("inventory", 2),
                ("bestand", 2), ("founded", 1), ("gegründet", 1),
            ]),
        ]

        scores: dict[str, int] = {}
        for dept, keywords in _ROUTING_RULES:
            score = sum(weight for kw, weight in keywords if kw in lowered)
            scores[dept] = score

        max_score = max(scores.values()) if scores else 0
        if max_score > 0:
            # Pick highest score; list order breaks ties (Contact > Buyer > ...)
            route = next(dept for dept, _ in _ROUTING_RULES if scores[dept] == max_score)
        else:
            # No keyword matched at all — default to CompanyDepartment
            route = "CompanyDepartment"

        return {
            "route": route,
            "reason": f"Question routed to {route} (score: {scores.get(route, 0)}).",
            "source": source,
        }
