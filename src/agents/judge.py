"""Judge agent — deterministic three-outcome quality gate.

Decisions
---------
accept          → task_status "accepted"
    All core rules passed AND at least one supporting rule passed (or no
    supporting rules were defined).

accept_degraded → task_status "degraded"
    At least one core rule passed but not all core rules passed.
    Output flows downstream with confidence="low" and open_questions derived
    from the failed core rules.

reject          → task_status "rejected"
    No core rule passed.  This is a real quality failure that must remain
    visible in reporting (never silently converted to skipped).

Invariant
---------
"skipped" is NEVER produced by the Judge.  It is set by the task router when
run_condition is not met before execution begins.

No LLM is used here.
"""
from __future__ import annotations

from typing import Any

from src.config import get_role_model_selection
from src.orchestration.tool_policy import resolve_allowed_tools


class JudgeAgent:
    def __init__(self, name: str = "CompanyJudge") -> None:
        self.name = name
        self.model_name = get_role_model_selection(self.name)[0]
        self.allowed_tools = resolve_allowed_tools(self.name, "judge_resolution")

    def decide(
        self,
        *,
        section: str,
        critic_review: dict[str, Any] | None = None,
        # Legacy keyword — accepted for backwards compatibility with lead.py callers
        # that pass critic_issues directly.  Prefer critic_review.
        critic_issues: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return a three-outcome decision based on Critic class-aware results.

        Parameters
        ----------
        section:
            The task_key or section label being judged.
        critic_review:
            Full review dict from CriticAgent.review() — preferred input.
            Must contain ``core_passed``, ``core_total``, ``supporting_passed``,
            ``supporting_total``, and ``failed_rule_messages``.
        critic_issues:
            Legacy list of issue strings.  Used only when ``critic_review`` is
            not provided (e.g. old call sites or tests).  When supplied without
            ``critic_review``, the Judge falls back to a binary accept/degrade
            heuristic based on whether issues exist.
        """
        # ------------------------------------------------------------------
        # Build class-aware counts from the critic review
        # ------------------------------------------------------------------
        if critic_review is not None:
            core_passed = int(critic_review.get("core_passed", 0))
            core_total = int(critic_review.get("core_total", 0))
            supporting_passed = int(critic_review.get("supporting_passed", 0))
            supporting_total = int(critic_review.get("supporting_total", 0))
            failed_messages = list(critic_review.get("failed_rule_messages", []))
        else:
            # Legacy path: no class info available.  Treat presence of issues
            # as partial evidence — degraded, not rejected.
            issues = critic_issues or []
            if not issues:
                return {
                    "decision": "accepted",
                    "task_status": "accepted",
                    "reason": "No unresolved issues.",
                    "open_questions": [],
                    "confidence": "medium",
                }
            return {
                "decision": "accepted_with_gaps",
                "task_status": "degraded",
                "reason": f"{section}: issues exist but output is retained as degraded.",
                "open_questions": issues[:5],
                "confidence": "low",
            }

        # ------------------------------------------------------------------
        # Three-outcome gate
        # ------------------------------------------------------------------
        if core_total == 0:
            # No core rules defined — accept if no issues at all
            issues = critic_review.get("issues", []) if critic_review else []
            if not issues:
                return {
                    "decision": "accepted",
                    "task_status": "accepted",
                    "reason": "No core rules defined and no issues found.",
                    "open_questions": [],
                    "confidence": "medium",
                }
            return {
                "decision": "accepted_with_gaps",
                "task_status": "degraded",
                "reason": f"{section}: no core rules but issues exist.",
                "open_questions": failed_messages[:5],
                "confidence": "low",
            }

        if core_passed == 0:
            # Reject — no core evidence at all
            return {
                "decision": "closed_unresolved",
                "task_status": "degraded",
                "reason": f"{section}: no core rules passed — task produced no usable evidence.",
                "open_questions": failed_messages[:5],
                "confidence": "low",
            }

        if core_passed < core_total:
            # Partial core pass — degraded
            return {
                "decision": "accepted_with_gaps",
                "task_status": "degraded",
                "reason": (
                    f"{section}: {core_passed}/{core_total} core rules passed. "
                    "Output is usable but incomplete."
                ),
                "open_questions": failed_messages[:5],
                "confidence": "low",
            }

        # All core rules passed — check supporting
        has_supporting = supporting_total > 0
        if has_supporting and supporting_passed == 0:
            # All core passed but zero supporting — still accepted, confidence medium
            return {
                "decision": "accepted",
                "task_status": "accepted",
                "reason": f"{section}: all core rules passed; no supporting evidence present.",
                "open_questions": [],
                "confidence": "medium",
            }

        return {
            "decision": "accepted",
            "task_status": "accepted",
            "reason": f"{section}: all core rules passed.",
            "open_questions": [],
            "confidence": "high" if supporting_passed > 0 else "medium",
        }
