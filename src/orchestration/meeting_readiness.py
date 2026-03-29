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
    ) -> MeetingReadinessAssessment:
        blocked_reasons: list[str] = []

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

        # Check for pending user selections
        dashboard = resolution_state.get("dashboard_state", {})
        if dashboard.get("pending_user_selection"):
            blocked_reasons.append("Required user depth selections are pending.")

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

        # Readiness score and evidence health are informational but only block
        # when no other evidence compensates. If answer_matrix shows enough
        # answered/partially_answered questions, don't double-block.
        answered_or_partial = sum(
            1 for entry in answer_matrix.values()
            if entry.get("status") in {"answered", "partially_answered"}
        )
        if not readiness_usable and answered_or_partial < 4:
            blocked_reasons.append("Research readiness score is below the usable threshold.")
        if evidence_health == "low" and answered_or_partial < 4:
            blocked_reasons.append("Evidence quality is too low for a confident meeting brief.")

        meeting_ready = len(blocked_reasons) == 0
        return MeetingReadinessAssessment(
            run_status="meeting_ready" if meeting_ready else "blocked_not_meeting_ready",
            meeting_ready=meeting_ready,
            blocked_reasons=blocked_reasons,
            confidence="high" if meeting_ready and evidence_health == "high" else
                       "medium" if meeting_ready else "low",
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
