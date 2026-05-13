"""Supervisor agent implementation."""
from __future__ import annotations

from dataclasses import asdict
from typing import TypedDict
from urllib.parse import urlparse

from src.app.use_cases import build_standard_scope
from src.config import get_role_model_selection
from src.config.settings import MAX_TASK_RETRIES
from src.domain.briefing import (
    BRIEFING_REDIRECT_DOMAIN_MISMATCH,
    BRIEFING_SCHEMA_VERSION,
    SOURCE_TYPE_OWNED_WEBSITE,
    BriefingFetchAudit,
    EvidenceItem,
    EvidenceSummary,
    MissingEvidence,
    SupervisorBriefMessage,
    classify_briefing_readiness,
    classify_identity_confidence,
    classify_industry_confidence,
    detect_identity_conflict,
    iso_now,
    validate_supervisor_brief_message,
)
from src.domain.intake import IntakeRequest, SupervisorBrief
from src.orchestration.tool_policy import resolve_allowed_tools
from src.research.contracts import CompanyResearchResult, WebsiteSnapshot
from src.research.extract import infer_industry_result
from src.research.normalize import NormalizedDomainResult, normalize_domain_result
from src.research.tools import build_company_research


def _hostname(value: str) -> str:
    host = (urlparse(str(value or "")).hostname or str(value or "")).lower()
    return host.removeprefix("www.")


def _as_mapping(value):  # noqa: ANN001
    return value.as_dict() if hasattr(value, "as_dict") else value


# F10: Typed return dicts for acceptance methods
class DepartmentAcceptanceResult(TypedDict):
    decision: str
    reason: str
    open_questions_present: bool
    substantive_content: bool
    accepted_tasks: int
    total_tasks: int
    policy_gate_passed: bool
    policy_gate_blockers: int


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

    def build_intake_brief(
        self,
        intake: IntakeRequest,
        normalized_domain: str | NormalizedDomainResult,
    ) -> tuple[SupervisorBrief, dict]:
        # `normalized_domain` is already the validated canonical hostname from
        # `_initialize_run()` (TODO 5.1). We do NOT re-run normalization here.
        domain_contract = (
            normalized_domain
            if isinstance(normalized_domain, NormalizedDomainResult)
            else normalize_domain_result(normalized_domain)
        )
        try:
            research = build_company_research(
                domain_contract,
                intake.company_name,
                language=intake.language,
            )
        except TypeError:
            # Legacy tests/extensions may monkeypatch the old two-argument
            # helper. Keep that path temporary and explicit while the runtime
            # itself uses the typed domain contract.
            research = build_company_research(domain_contract, intake.company_name)
        snapshot = research.snapshot if isinstance(research, CompanyResearchResult) else research["snapshot"]
        if isinstance(snapshot, dict):
            snapshot = WebsiteSnapshot.from_mapping(snapshot)
        snapshot_title = str(snapshot.get("title", ""))
        snapshot_meta = str(snapshot.get("meta_description", ""))
        snapshot_text = str(research.get("summary", ""))
        homepage_url = str(research["homepage_url"])
        website_reachable = bool(snapshot.get("reachable"))

        # ── Identity confidence + conflict (TODO 5.4 + 5.2) ──
        submitted_name = intake.company_name
        verified_legal_name = str(research.get("verified_legal_name", ""))
        identity_confidence, identity_reason = classify_identity_confidence(
            website_reachable=website_reachable,
            submitted_name=submitted_name,
            homepage_title=snapshot_title,
            verified_legal_name=verified_legal_name,
        )
        identity_conflict = detect_identity_conflict(
            submitted_name=submitted_name,
            homepage_title=snapshot_title,
            confidence=identity_confidence,
        )
        # When homepage clearly names a different company, do NOT silently
        # overwrite the submitted name — keep the brand visible but mark
        # the brief with a conflict flag (MVP, TODO 5.2).
        verified_company_name = str(
            research.get("verified_company_name", submitted_name)
        )

        # ── Industry inference + confidence (TODO 5.4) ──
        industry_result = (
            research.industry
            if isinstance(research, CompanyResearchResult)
            else infer_industry_result(
                title=snapshot_title,
                description=snapshot_meta,
                text=snapshot_text,
            )
        )
        industry_hint = (
            industry_result.industry_hint
            if website_reachable
            else "n/v"
        )
        industry_confidence, industry_reason = classify_industry_confidence(
            industry_hint=industry_hint,
            has_title_signal=bool(snapshot_title),
            has_meta_signal=bool(snapshot_meta),
        )

        # ── Fetch audit (TODO 5.5) ──
        fetch_audit = BriefingFetchAudit(
            reachable=website_reachable,
            final_url=str(snapshot.get("final_url", homepage_url) or homepage_url),
            redirect_chain=tuple(snapshot.get("redirect_chain", ()) or ()),
            http_status=int(snapshot.get("http_status", 0) or 0),
            content_type=str(snapshot.get("content_type", "")),
            content_length=int(snapshot.get("content_length", 0) or 0),
            content_language=str(snapshot.get("content_language", "")),
            fetched_at=str(snapshot.get("fetched_at", "")) or iso_now(),
            error_type=str(snapshot.get("error_type", "")),
            error_message=str(snapshot.get("error_message", "")),
            blocked_reason=str(snapshot.get("blocked_reason", "")),
        )
        final_hostname = _hostname(fetch_audit.final_url)
        expected_hostname = _hostname(normalized_domain)
        website_domain_mismatch = bool(
            website_reachable
            and final_hostname
            and expected_hostname
            and final_hostname != expected_hostname
        )

        # ── Evidence contract (TODO 5.3) ──
        evidence_items: list[EvidenceItem] = []
        missing_evidence: list[MissingEvidence] = []
        retrieved_at = fetch_audit.fetched_at
        if website_reachable:
            if snapshot_title:
                evidence_items.append(EvidenceItem(
                    source_type=SOURCE_TYPE_OWNED_WEBSITE,
                    url=homepage_url,
                    claim=snapshot_title[:280],
                    supports_field="verified_company_name",
                    retrieved_at=retrieved_at,
                ))
            else:
                missing_evidence.append(MissingEvidence(
                    supports_field="verified_company_name",
                    reason="homepage reachable but page title empty",
                ))
            if snapshot_meta:
                evidence_items.append(EvidenceItem(
                    source_type=SOURCE_TYPE_OWNED_WEBSITE,
                    url=homepage_url,
                    claim=snapshot_meta[:280],
                    supports_field="industry_hint",
                    retrieved_at=retrieved_at,
                ))
            evidence_items.append(EvidenceItem(
                source_type=SOURCE_TYPE_OWNED_WEBSITE,
                url=homepage_url,
                claim=f"homepage reachable at {fetch_audit.final_url or homepage_url}",
                supports_field="website_reachable",
                retrieved_at=retrieved_at,
            ))
            if website_domain_mismatch:
                missing_evidence.append(MissingEvidence(
                    supports_field="normalized_domain",
                    reason=(
                        "final homepage URL differs from validated canonical domain: "
                        f"{fetch_audit.final_url or final_hostname} expected {expected_hostname}"
                    ),
                ))
        else:
            missing_evidence.append(MissingEvidence(
                supports_field="website_reachable",
                reason=f"homepage fetch failed: {fetch_audit.error_type or 'unknown'}",
            ))
            missing_evidence.append(MissingEvidence(
                supports_field="verified_company_name",
                reason="cannot verify name without reachable homepage",
            ))
            missing_evidence.append(MissingEvidence(
                supports_field="industry_hint",
                reason="cannot infer industry without homepage signal",
            ))
        # Legal name is always Phase-2 evidence — record gap honestly.
        if not verified_legal_name:
            missing_evidence.append(MissingEvidence(
                supports_field="verified_legal_name",
                reason="register lookup is Phase 2; legal name not available in MVP",
            ))
        if isinstance(research, CompanyResearchResult):
            for issue in research.warnings:
                if issue.code == "source_gap":
                    missing_evidence.append(MissingEvidence(
                        supports_field=f"identity_source:{issue.source_type}",
                        reason=issue.message,
                    ))
            if research.snapshot.js_content_detected:
                missing_evidence.append(MissingEvidence(
                    supports_field="homepage_text",
                    reason="static homepage fetch indicates JavaScript-rendered content; browser rendering is backlog",
                ))

        # ── Briefing readiness (TODO 5.6) ──
        readiness, routing_gaps = classify_briefing_readiness(
            website_reachable=website_reachable,
            identity_conflict=identity_conflict,
            identity_confidence=identity_confidence,
            website_domain_mismatch=website_domain_mismatch,
        )
        if website_domain_mismatch and BRIEFING_REDIRECT_DOMAIN_MISMATCH not in routing_gaps:
            routing_gaps = (*routing_gaps, BRIEFING_REDIRECT_DOMAIN_MISMATCH)

        brief = SupervisorBrief(
            submitted_company_name=intake.company_name,
            submitted_web_domain=intake.web_domain,
            verified_company_name=verified_company_name,
            verified_legal_name=verified_legal_name,
            name_confidence=str(identity_confidence),
            website_reachable=website_reachable,
            homepage_url=homepage_url,
            page_title=snapshot_title,
            meta_description=snapshot_meta,
            raw_homepage_excerpt=snapshot_text,
            normalized_domain=str(research["normalized_domain"]),
            industry_hint=industry_hint,
            observations=[
                "Website reachable." if website_reachable else "Website not reachable.",
                f"Verified company name: {verified_company_name}.",
                f"Identity confidence: {identity_confidence} ({identity_reason}).",
                f"Industry confidence: {industry_confidence} ({industry_reason}).",
                f"Briefing readiness: {readiness}.",
                (
                    f"Final URL host differs from canonical domain: {final_hostname}."
                    if website_domain_mismatch else
                    "Final URL host matches canonical domain or was unavailable."
                ),
            ],
            sources=[
                # Legacy `sources` shape kept for backward compatibility with
                # consumers that haven't migrated to evidence_items yet.
                {
                    "title": str(snapshot.get("title") or verified_company_name or intake.company_name),
                    "url": homepage_url,
                    "source_type": SOURCE_TYPE_OWNED_WEBSITE,
                    "summary": snapshot_text,
                }
            ],
            fetch_error_type=fetch_audit.error_type,
            fetch_error_message=fetch_audit.error_message,
            schema_version=BRIEFING_SCHEMA_VERSION,
            name_confidence_reason=identity_reason,
            industry_confidence=str(industry_confidence),
            industry_confidence_reason=industry_reason,
            evidence_items=[asdict(item) for item in evidence_items],
            missing_evidence=[asdict(item) for item in missing_evidence],
            fetch_audit=asdict(fetch_audit),
            # Research diagnostics are intentionally not raw HTML/text and are
            # available through the versioned supervisor payload.
            briefing_readiness=str(readiness),
            routing_gaps=list(routing_gaps),
            identity_conflict=identity_conflict,
        )

        # ── Versioned supervisor_message (TODO 5.7) ──
        message_status = (
            "ready_for_department_routing"
            if readiness.value in {"ready", "ready_with_identity_gaps", "ready_with_website_gaps"}
            else "blocked_for_department_routing"
        )
        evidence_summary = EvidenceSummary(
            item_count=len(evidence_items),
            source_types=tuple(sorted({item.source_type for item in evidence_items})),
            missing_fields=tuple(item.supports_field for item in missing_evidence),
        )
        payload = asdict(brief)
        if isinstance(research, CompanyResearchResult):
            payload["intake_research"] = {
                "schema_version": research.schema_version,
                "warnings": [issue.as_dict() for issue in research.warnings],
                "errors": [issue.as_dict() for issue in research.errors],
                "timings_ms": dict(research.timings_ms),
                "snapshot": {
                    "requested_url": research.snapshot.requested_url,
                    "final_url": research.snapshot.final_url,
                    "http_status": research.snapshot.http_status,
                    "content_type": research.snapshot.content_type,
                    "language": research.snapshot.language,
                    "content_length": research.snapshot.content_length,
                    "content_hash": research.snapshot.content_hash,
                    "extraction_quality": research.snapshot.extraction_quality,
                    "js_content_detected": research.snapshot.js_content_detected,
                    "redirect_chain": list(research.snapshot.redirect_chain),
                    "about_url": research.snapshot.about_url,
                    "imprint_url": research.snapshot.imprint_url,
                },
                "identity": {
                    "brand_name": research.identity.brand_name,
                    "homepage_name_match": research.identity.homepage_name_match,
                    "confidence_reason": research.identity.confidence_reason,
                    "source_gaps": [
                        issue.as_dict() for issue in research.identity.source_gaps
                    ],
                },
                "industry": research.industry.as_dict(),
            }

        message_envelope = SupervisorBriefMessage(
            schema_version=BRIEFING_SCHEMA_VERSION,
            section="supervisor_brief",
            status=message_status,
            briefing_readiness=str(readiness),
            identity_confidence=str(identity_confidence),
            industry_confidence=str(industry_confidence),
            routing_gaps=tuple(routing_gaps),
            evidence_summary=evidence_summary,
            payload=payload,
        )
        message = message_envelope.as_dict()
        is_valid, errors = validate_supervisor_brief_message(message)
        if not is_valid:
            raise ValueError(f"invalid SupervisorBriefMessage: {', '.join(errors)}")
        return brief, message

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
        policy_gate = package.get("policy_gate", {}) if isinstance(package.get("policy_gate"), dict) else {}
        policy_gate_passed = bool(policy_gate.get("passed", True))
        policy_gate_blockers = len(
            [
                item
                for item in policy_gate.get("blockers", [])
                if isinstance(item, dict)
            ]
        )

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

        # Policy gate: all hard-severity blockers → rejected regardless of content
        all_hard_blockers = (
            not policy_gate_passed
            and policy_gate_blockers > 0
            and all(
                item.get("severity") == "hard"
                for item in policy_gate.get("blockers", [])
                if isinstance(item, dict)
            )
        )

        # Admission decision: explicit three-outcome gate
        if (
            has_payload
            and substantive
            and bool(completed_tasks)
            and not all_rejected
            and accepted_tasks > 0
            and policy_gate_passed
        ):
            decision = "accepted"
            reason = f"{department} package accepted for synthesis ({accepted_tasks}/{len(completed_tasks)} tasks accepted)."
        elif all_hard_blockers:
            decision = "rejected"
            reason = (
                f"{department} package rejected — all {policy_gate_blockers} policy gate blocker(s) are hard severity."
            )
        elif has_payload and substantive and not all_rejected:
            decision = "accepted_with_gaps"
            if not policy_gate_passed:
                reason = (
                    f"{department} package accepted with policy gaps "
                    f"({policy_gate_blockers} blocker(s) on department gate)."
                )
            else:
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
            "policy_gate_passed": policy_gate_passed,
            "policy_gate_blockers": policy_gate_blockers,
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
                ("capacity", 2), ("overcapacity", 3), ("nachfrage", 3),
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
