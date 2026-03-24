"""Runtime guardrail selectors for AG2 GroupChats.

CHG-04 — The selectors here are guardrail logic, NOT workflow choreographers.

Previous architecture: the selector used ``workflow_step`` as a hidden state
machine that forced the group through a rigid micro-sequence regardless of what
the agents actually said.

New architecture:
- The Department Lead drives the internal workflow through its messages.
- The selector enforces safety rails:
    1. Route tool calls to the executor agent (mandatory).
    2. After executor runs, return to the Lead — the Lead sees the result
       and decides what to do next.
    3. Prevent text-only loops: force back to Lead after too many non-tool turns.
    4. Invalid-handoff protection: ensure Lead speaks first.
    5. Termination recognition: honour TERMINATE signals.

The selector no longer reads ``workflow_step`` and no longer controls the
task ordering.  The Lead's prompt instructions and the group conversation
dynamics determine who speaks and in what order.

Synthesis selector is kept structurally similar but also simplified.
"""
from __future__ import annotations

import logging
from typing import Any

from autogen import ConversableAgent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Department GroupChat guardrails
# ---------------------------------------------------------------------------

_MAX_TEXT_TURNS = 3  # consecutive text-only turns before forcing back to Lead


def build_department_selector(
    *,
    guardrail_state: dict[str, Any],
    agent_map: dict[str, ConversableAgent],
    lead_name: str,
    researcher_name: str,
    critic_name: str,
    judge_name: str,
    coding_name: str,
    executor_name: str = "",
):
    """Return a callable suitable for ``speaker_selection_method``.

    ``guardrail_state`` is a plain dict (typically ``DepartmentRunState.guardrail_state()``)
    that the selector uses only for loop-prevention counters.  It does NOT
    contain workflow_step — the Lead owns the workflow.
    """
    name_to_role: dict[str, str] = {
        lead_name:       "lead",
        researcher_name: "researcher",
        critic_name:     "critic",
        judge_name:      "judge",
        coding_name:     "coding",
    }
    if executor_name:
        name_to_role[executor_name] = "executor"
    role_to_agent = {v: agent_map[k] for k, v in name_to_role.items()}

    # Initialise loop-prevention counters
    guardrail_state.setdefault("_consecutive_text_turns", {})
    text_turns: dict[str, int] = guardrail_state["_consecutive_text_turns"]

    def _selector(
        last_speaker: ConversableAgent,
        groupchat,
    ) -> ConversableAgent | str:
        last_role = name_to_role.get(last_speaker.name, "lead")

        if not groupchat.messages:
            # Valid first speaker: Lead
            return role_to_agent["lead"]

        last_msg = groupchat.messages[-1]
        last_content = str(last_msg.get("content") or "")

        # ── GUARDRAIL 1: route tool calls to executor ────────────────────────
        if last_msg.get("tool_calls") and "executor" in role_to_agent:
            text_turns[last_role] = 0
            logger.debug("Selector: tool_call from %s → executor", last_role)
            return role_to_agent["executor"]

        # ── GUARDRAIL 2: after executor, return to Lead ──────────────────────
        # The Lead sees the tool result and decides next action.
        if last_role == "executor":
            logger.debug("Selector: executor done → lead")
            return role_to_agent["lead"]

        # ── GUARDRAIL 3: text-only loop prevention ───────────────────────────
        if last_role in ("researcher", "critic", "judge", "coding"):
            text_turns[last_role] = text_turns.get(last_role, 0) + 1
            if text_turns[last_role] >= _MAX_TEXT_TURNS:
                logger.warning(
                    "Selector: loop guard triggered for %s (%d text turns) → lead",
                    last_role, text_turns[last_role],
                )
                text_turns[last_role] = 0
                return role_to_agent["lead"]
        else:
            # Lead or other spoke — reset non-lead counters
            for r in ("researcher", "critic", "judge", "coding"):
                text_turns[r] = 0

        # ── GUARDRAIL 4: termination recognition ─────────────────────────────
        if "TERMINATE" in last_content:
            logger.debug("Selector: TERMINATE detected → lead (chat will end)")
            return role_to_agent["lead"]

        # ── ROUTING: Lead spoke → parse who it addressed ─────────────────────
        # The Lead drives the workflow by explicitly naming the next agent.
        # We look for the agent name or tool name in the Lead's message.
        if last_role == "lead":
            low = last_content.lower()
            if researcher_name.lower() in low or "run_research" in low:
                logger.debug("Selector: lead addressed researcher")
                return role_to_agent["researcher"]
            if critic_name.lower() in low or "review_research" in low:
                logger.debug("Selector: lead addressed critic")
                return role_to_agent["critic"]
            if judge_name.lower() in low or "judge_decision" in low:
                logger.debug("Selector: lead addressed judge")
                return role_to_agent["judge"]
            if coding_name.lower() in low or "suggest_refined" in low:
                logger.debug("Selector: lead addressed coding specialist")
                return role_to_agent["coding"]
            # Default: researcher (most common next action)
            return role_to_agent["researcher"]

        # ── DEFAULT: non-lead agent spoke (text, no tool) → Lead responds ────
        logger.debug("Selector: %s spoke text → lead", last_role)
        return role_to_agent["lead"]

    return _selector


# ---------------------------------------------------------------------------
# Synthesis GroupChat guardrails
# ---------------------------------------------------------------------------

def build_synthesis_selector(
    *,
    run_state: dict[str, Any],
    agent_map: dict[str, ConversableAgent],
    lead_name: str,
    analyst_name: str,
    critic_name: str,
    judge_name: str,
    executor_name: str = "",
):
    """Return a callable suitable for ``speaker_selection_method``.

    The synthesis selector is kept similar to the department selector in
    spirit: guardrail-based, with the Lead (strategic analyst) driving the
    internal flow.  A lightweight ``synthesis_step`` is retained only to
    preserve the read-before-critique semantics (the analyst must read all
    segments before the critic reviews).
    """
    run_state.setdefault("synthesis_step", "start")
    run_state.setdefault("_consecutive_text_turns", {})

    name_to_role: dict[str, str] = {
        lead_name:    "lead",
        analyst_name: "analyst",
        critic_name:  "critic",
        judge_name:   "judge",
    }
    if executor_name:
        name_to_role[executor_name] = "executor"
    role_to_agent = {v: agent_map[k] for k, v in name_to_role.items()}
    text_turns: dict[str, int] = run_state["_consecutive_text_turns"]

    def _selector(
        last_speaker: ConversableAgent,
        groupchat,
    ) -> ConversableAgent | str:
        last_role = name_to_role.get(last_speaker.name, "lead")
        step = run_state.get("synthesis_step", "start")

        if not groupchat.messages:
            return role_to_agent["lead"]

        last_msg = groupchat.messages[-1]
        last_content = str(last_msg.get("content") or "")

        # GUARDRAIL 1: tool calls → executor
        if last_msg.get("tool_calls") and "executor" in role_to_agent:
            text_turns[last_role] = 0
            return role_to_agent["executor"]

        # GUARDRAIL 2: after executor → lead
        if last_role == "executor":
            if step == "read":
                # Analyst may still need to read more segments — return to analyst
                return role_to_agent["analyst"]
            return role_to_agent["lead"]

        # GUARDRAIL 3: loop prevention
        if last_role in ("analyst", "critic", "judge"):
            text_turns[last_role] = text_turns.get(last_role, 0) + 1
            if text_turns[last_role] >= _MAX_TEXT_TURNS:
                text_turns[last_role] = 0
                return role_to_agent["lead"]
        else:
            for r in ("analyst", "critic", "judge"):
                text_turns[r] = 0

        # GUARDRAIL 4: termination
        if "TERMINATE" in last_content:
            return role_to_agent["lead"]

        # State-aware routing for synthesis (reading phase must precede critique)
        if step == "start":
            run_state["synthesis_step"] = "read"
            return role_to_agent["analyst"]

        if step == "read" and last_role == "analyst":
            if "read_report_segment" in last_content:
                return role_to_agent["analyst"]
            run_state["synthesis_step"] = "critique"
            return role_to_agent["critic"]

        if step == "critique" and last_role == "critic":
            run_state["synthesis_step"] = "decide"
            return role_to_agent["lead"]

        if step == "decide":
            if "request_department_followup" in last_content or "back_request" in last_content.lower():
                run_state["synthesis_step"] = "back_request"
                return role_to_agent["lead"]
            if "finalize_synthesis" in last_content or "TERMINATE" in last_content:
                run_state["synthesis_step"] = "finalize"
                return role_to_agent["lead"]
            if "reject" in last_content.lower():
                run_state["synthesis_step"] = "judge"
                return role_to_agent["judge"]
            run_state["synthesis_step"] = "finalize"
            return role_to_agent["lead"]

        if step == "back_request" and last_role == "lead":
            run_state["synthesis_step"] = "read"
            return role_to_agent["analyst"]

        if step == "judge" and last_role == "judge":
            run_state["synthesis_step"] = "decide"
            return role_to_agent["lead"]

        # Safety fallback
        run_state["synthesis_step"] = "decide"
        return role_to_agent["lead"]

    return _selector
