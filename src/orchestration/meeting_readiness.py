"""Meeting-readiness gate and final briefing composer.

RA-06: Finalization only passes when meeting-critical questions are resolved
and evidence quality meets the minimum threshold.  The composer produces
meeting_actions as the primary action output, replacing generic next_steps.
"""
from __future__ import annotations

from typing import Any

from src.models.meeting_ready import (
    MeetingAction,
    MeetingReadinessAssessment,
    MinimumPackageStatus,
    ReadinessBlocker,
)


class MeetingReadinessGate:
    """Evaluate whether a run is meeting-ready.

    Blocks finalization when:
    - publicly researchable meeting-critical questions remain unresolved
    - required dashboard decisions are missing
    - evidence quality for critical questions is below threshold
    """

    def evaluate(
        self,
        *,
        answer_matrix: dict[str, dict[str, Any]],
        resolution_state: dict[str, Any],
        evidence_health: str,
        readiness_usable: bool,
        discovery_ready: bool = False,
        minimum_package: dict[str, Any] | None = None,
        blockers: list[dict[str, Any]] | None = None,
    ) -> MeetingReadinessAssessment:
        blocked_reasons: list[str] = []
        structured_blockers: list[ReadinessBlocker] = []

        # Check for unresolved meeting-critical public gaps
        remaining_gaps = (
            resolution_state
            .get("auto_close", {})
            .get("remaining_public_gaps", [])
        )
        if remaining_gaps:
            blocked_reasons.append(
                f"{len(remaining_gaps)} meeting-critical public gap(s) remain after closure."
            )
            for idx, gap in enumerate(remaining_gaps[:8], start=1):
                structured_blockers.append(
                    ReadinessBlocker(
                        blocker_id=f"public_gap_{idx}",
                        field_key="public_evidence_gap",
                        availability="public",
                        severity="hard",
                        reason=str(gap),
                        owner="Research Department",
                        next_step="Public primary sources re-check and targeted follow-up research.",
                    )
                )

        # Check for pending user selections
        dashboard = resolution_state.get("dashboard_state", {})
        if dashboard.get("pending_user_selection"):
            blocked_reasons.append("Required user depth selections are pending.")
            structured_blockers.append(
                ReadinessBlocker(
                    blocker_id="user_selection_pending",
                    field_key="user_selection",
                    availability="public",
                    severity="hard",
                    reason="User depth selection is still pending.",
                    owner="User",
                    next_step="Select unanswered questions to continue finalization.",
                )
            )

        # Unresolved critical answer-matrix entries
        # Only "pending" and "blocked" are blockers; "partially_answered" means
        # evidence exists (degraded task) and is acceptable for meeting prep.
        hard_blocked = [
            qid for qid, entry in answer_matrix.items()
            if entry.get("status") in {"pending", "blocked"}
            and not qid.startswith("q_contact")  # contact gaps are customer-confirmation
            and not qid.startswith("q_liquisto")  # synthesis questions depend on departments
            and not qid.startswith("q_negotiation")  # synthesis questions depend on departments
        ]
        if hard_blocked:
            blocked_reasons.append(
                f"{len(hard_blocked)} core question(s) still pending/blocked: {', '.join(hard_blocked)}."
            )
            for qid in hard_blocked[:8]:
                structured_blockers.append(
                    ReadinessBlocker(
                        blocker_id=f"matrix_{qid}",
                        field_key=qid,
                        availability="public",
                        severity="hard",
                        reason="Core question unresolved in answer matrix.",
                        owner="Responsible Department Lead",
                        next_step="Complete at least one evidence-backed answer for this question.",
                    )
                )

        # Readiness score and evidence health are informational but only block
        # when no other evidence compensates. If answer_matrix shows enough
        # answered/partially_answered questions, don't double-block.
        answered_or_partial = sum(
            1 for entry in answer_matrix.values()
            if entry.get("status") in {"answered", "partially_answered"}
        )
        if not readiness_usable and answered_or_partial < 4:
            blocked_reasons.append("Research readiness score is below the usable threshold.")
            structured_blockers.append(
                ReadinessBlocker(
                    blocker_id="readiness_score_low",
                    field_key="research_readiness.score",
                    availability="public",
                    severity="hard",
                    reason="Research readiness score below usable threshold.",
                    owner="Supervisor",
                    next_step="Strengthen coverage on core evidence questions.",
                )
            )
        if evidence_health == "low" and answered_or_partial < 4:
            blocked_reasons.append("Evidence quality is too low for a confident meeting brief.")
            structured_blockers.append(
                ReadinessBlocker(
                    blocker_id="evidence_health_low",
                    field_key="quality_review.evidence_health",
                    availability="public",
                    severity="hard",
                    reason="Evidence quality is too low.",
                    owner="Research Department",
                    next_step="Replace weak sources with primary/authoritative sources.",
                )
            )

        for raw in blockers or []:
            if not isinstance(raw, dict):
                continue
            try:
                parsed = ReadinessBlocker.model_validate(raw)
                structured_blockers.append(parsed)
                if parsed.availability == "internal_customer" and parsed.severity == "hard":
                    reason_text = str(parsed.reason).strip()
                    if reason_text and reason_text not in blocked_reasons:
                        blocked_reasons.append(reason_text)
            except Exception:
                continue

        minimum_package_payload = dict(minimum_package or {})
        if not minimum_package_payload:
            minimum_package_payload = {
                "required_verified_decision_makers": 0,
                "verified_decision_makers": 0,
                "required_hard_financial_inventory_signals": 0,
                "hard_financial_inventory_signals": 0,
                "met": True,
            }
        minimum_package_model = MinimumPackageStatus.model_validate(minimum_package_payload)
        has_public_hard_blockers = any(
            item.severity == "hard" and item.availability == "public"
            for item in structured_blockers
        )
        has_internal_hard_blockers = any(
            item.severity == "hard" and item.availability == "internal_customer"
            for item in structured_blockers
        )

        meeting_ready = (
            readiness_usable
            and minimum_package_model.met
            and not has_public_hard_blockers
            and not has_internal_hard_blockers
        )
        discovery_ready_final = (
            not meeting_ready
            and discovery_ready
            and not has_public_hard_blockers
            and has_internal_hard_blockers
        )

        run_status: str
        if meeting_ready:
            run_status = "meeting_ready"
        elif discovery_ready_final:
            run_status = "discovery_ready_not_execution_ready"
        else:
            run_status = "blocked_not_meeting_ready"
        return MeetingReadinessAssessment(
            run_status=run_status,
            meeting_ready=meeting_ready,
            discovery_ready=discovery_ready_final,
            blocked_reasons=blocked_reasons,
            blockers=structured_blockers,
            minimum_package=minimum_package_model,
            confidence=(
                "high"
                if meeting_ready and evidence_health == "high"
                else "medium"
                if meeting_ready or discovery_ready_final
                else "low"
            ),
        )


class FinalBriefingComposer:
    """Compose meeting_actions from synthesis, answer matrix, and evidence.

    Replaces generic next_steps with concrete, evidence-referenced actions.
    """

    def compose(
        self,
        *,
        synthesis: dict[str, Any],
        answer_matrix: dict[str, dict[str, Any]],
        quality_review: dict[str, Any],
        resolution_state: dict[str, Any],
        company_name: str,
    ) -> list[MeetingAction]:
        actions: list[MeetingAction] = []

        structured_steps = [
            step for step in (synthesis.get("recommended_next_steps", []) or [])
            if isinstance(step, dict) and str(step.get("action", "")).strip()
        ]
        structured_questions = [
            item for item in (synthesis.get("critical_open_questions", []) or [])
            if isinstance(item, dict) and str(item.get("question", "")).strip()
        ]

        if structured_steps:
            for step in structured_steps[:3]:
                phase = str(step.get("phase", "")).strip().replace("_", " ")
                actions.append(MeetingAction(
                    action_type="prepare_meeting" if phase != "post meeting under nda" else "collect_missing_evidence",
                    title=str(step.get("action", "Further validation required"))[:120],
                    description=(
                        f"{step.get('goal', '')} "
                        f"Hypothesis: {step.get('asset_hypothesis', '')} "
                        f"Expected output: {step.get('expected_output', '')} "
                        f"Done when: {step.get('definition_of_done', '')}"
                    ).strip()[:220] or f"Advance the opportunity with {company_name}.",
                    owner=str(step.get("owner", "Liquisto Account Lead")),
                ))
            for question in structured_questions[:2]:
                actions.append(MeetingAction(
                    action_type="collect_missing_evidence",
                    title=f"Validate: {str(question.get('label', 'Open question'))[:72]}",
                    description=str(question.get("question", "")).strip()[:220],
                    owner=str(question.get("owner", "Liquisto Account Lead")),
                ))
            return actions

        # 1. Primary engagement action from synthesis
        paths = synthesis.get("recommended_engagement_paths", [])
        if paths and paths[0] != "further_validation_required":
            actions.append(MeetingAction(
                action_type="prepare_meeting",
                title=f"Lead with {paths[0]} opportunity",
                description=(
                    synthesis.get("opportunity_assessment_summary", "")
                    or f"Present {paths[0]} as the primary Liquisto engagement path for {company_name}."
                ),
                owner="Liquisto Account Lead",
            ))

        # 2. Evidence validation actions from open gaps
        open_gaps = quality_review.get("open_gaps", [])
        for gap in open_gaps[:2]:
            gap_text = str(gap).strip()
            if gap_text:
                actions.append(MeetingAction(
                    action_type="collect_missing_evidence",
                    title=f"Validate: {gap_text[:80]}",
                    description=f"Confirm or refute this gap directly in the meeting with {company_name}.",
                    owner="Liquisto Account Lead",
                ))

        # 3. Customer confirmation items
        plan = resolution_state.get("resolution_plan", {})
        unresolved = plan.get("unresolved", {})
        for item in unresolved.get("customer_confirmation_items", [])[:2]:
            item_text = str(item).strip()
            if item_text:
                actions.append(MeetingAction(
                    action_type="collect_missing_evidence",
                    title=f"Customer confirmation: {item_text[:80]}",
                    description="This item requires customer-side confirmation and cannot be resolved from public sources.",
                    owner="Liquisto Account Lead",
                ))

        # 4. Contact outreach action if contacts exist
        answered_contact = answer_matrix.get("q_contact_intelligence", {})
        if answered_contact.get("status") in {"answered", "partially_answered"}:
            actions.append(MeetingAction(
                action_type="prepare_meeting",
                title="Prepare contact outreach",
                description="Use identified contacts and outreach angles for pre-meeting or post-meeting follow-up.",
                owner="Liquisto Account Lead",
            ))

        # Fallback if no actions generated
        if not actions:
            actions.append(MeetingAction(
                action_type="hold",
                title="Further validation required",
                description=f"Evidence for {company_name} is insufficient for concrete meeting actions. Re-run or gather additional input.",
                owner="Supervisor",
            ))

        return actions
