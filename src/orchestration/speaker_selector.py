"""Deterministic state-machine speaker selectors for AG2 GroupChats.

Decision C: Custom callable replaces ``speaker_selection_method="auto"``.
Each GroupChat type has its own state-machine that returns the next speaker
based on ``run_state["workflow_step"]``.

Department state-machine (per task):
    RESEARCH → REVIEW → DECIDE → (RETRY | NEXT | FINALIZE)

Synthesis state-machine:
    READ → CRITIQUE → DECIDE → (BACK_REQUEST | FINALIZE)

``"auto"`` is never reached — it exists only as an unreachable safety fallback
inside the GroupChat constructor.
"""
from __future__ import annotations

from typing import Any

from autogen import ConversableAgent


# ── Department GroupChat ──────────────────────────────────────────────────

# Workflow steps for a single task cycle
_DEPT_STEP_SPEAKER: dict[str, str] = {
    "start":       "researcher",   # Lead kicks off → Researcher runs research
    "research":    "critic",       # After research → Critic reviews
    "review":      "lead",         # After review → Lead decides next action
    "retry":       "researcher",   # Lead decided retry → Researcher re-runs
    "coding":      "coding",       # Lead authorized coding specialist
    "judge":       "lead",         # After judge → Lead moves on
    "finalize":    "lead",         # All tasks done → Lead finalizes
}


def build_department_selector(
    *,
    run_state: dict[str, Any],
    agent_map: dict[str, ConversableAgent],
    lead_name: str,
    researcher_name: str,
    critic_name: str,
    judge_name: str,
    coding_name: str,
    executor_name: str = "",
):
    """Return a callable suitable for ``speaker_selection_method``."""

    # Initialize workflow tracking in run_state
    run_state.setdefault("workflow_step", "start")

    name_to_role = {
        lead_name: "lead",
        researcher_name: "researcher",
        critic_name: "critic",
        judge_name: "judge",
        coding_name: "coding",
    }
    if executor_name:
        name_to_role[executor_name] = "executor"
    role_to_agent = {v: agent_map[k] for k, v in name_to_role.items()}

    def _selector(
        last_speaker: ConversableAgent,
        groupchat,
    ) -> ConversableAgent | str:
        last_role = name_to_role.get(last_speaker.name, "lead")
        step = run_state.get("workflow_step", "start")
        last_content = ""
        if groupchat.messages:
            last_msg = groupchat.messages[-1]
            last_content = str(last_msg.get("content", ""))
            # If the last message contains tool_calls, route to executor
            if last_msg.get("tool_calls") and "executor" in role_to_agent:
                return role_to_agent["executor"]
            # If executor just ran a tool, route back to the caller's
            # next step based on the workflow state machine
            if last_role == "executor":
                # After tool execution, advance based on current step
                if step in ("start", "research"):
                    # run_research just executed → advance to review
                    run_state["workflow_step"] = "review"
                    return role_to_agent["critic"]
                if step == "review":
                    # review_research just executed → Lead decides
                    run_state["workflow_step"] = "decide"
                    return role_to_agent["lead"]
                if step == "judge":
                    run_state["workflow_step"] = "post_judge"
                    return role_to_agent["lead"]
                if step == "coding":
                    run_state["workflow_step"] = "research"
                    return role_to_agent["researcher"]
                if step == "finalize":
                    return role_to_agent["lead"]
                # decide step: supervisor revision or finalize executed
                return role_to_agent["lead"]

        # Determine next step based on current step + who just spoke
        if step == "start":
            run_state["workflow_step"] = "research"
            return role_to_agent["researcher"]

        if step == "research" and last_role == "researcher":
            # Researcher spoke (text, not tool_call) — prompt to use tool
            return role_to_agent["researcher"]

        if step == "review" and last_role == "critic":
            # Critic spoke (text, not tool_call) — prompt to use tool
            return role_to_agent["critic"]

        if step in ("decide", "post_judge", "post_coding"):
            # Lead is deciding — parse intent from content
            if "request_supervisor_revision" in last_content or "retry" in last_content.lower():
                if "coding" in last_content.lower() or "suggest_refined" in last_content:
                    run_state["workflow_step"] = "coding"
                    return role_to_agent["coding"]
                run_state["workflow_step"] = "research"
                return role_to_agent["researcher"]
            if "judge_decision" in last_content or "judge" in last_content.lower():
                run_state["workflow_step"] = "judge"
                return role_to_agent["judge"]
            if "finalize_package" in last_content or "TERMINATE" in last_content:
                run_state["workflow_step"] = "finalize"
                return role_to_agent["lead"]
            # Default: Lead is moving to next task → Researcher
            run_state["workflow_step"] = "research"
            return role_to_agent["researcher"]

        if step == "judge" and last_role == "judge":
            # Judge spoke text — prompt to use tool
            return role_to_agent["judge"]

        if step == "coding" and last_role == "coding":
            # Coding spoke text — prompt to use tool
            return role_to_agent["coding"]

        # Safety: return Lead for any unhandled state
        run_state["workflow_step"] = "decide"
        return role_to_agent["lead"]

    return _selector


# ── Synthesis GroupChat ───────────────────────────────────────────────────

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
    """Return a callable suitable for ``speaker_selection_method``."""

    run_state.setdefault("synthesis_step", "start")

    name_to_role = {
        lead_name: "lead",
        analyst_name: "analyst",
        critic_name: "critic",
        judge_name: "judge",
    }
    if executor_name:
        name_to_role[executor_name] = "executor"
    role_to_agent = {v: agent_map[k] for k, v in name_to_role.items()}

    def _selector(
        last_speaker: ConversableAgent,
        groupchat,
    ) -> ConversableAgent | str:
        last_role = name_to_role.get(last_speaker.name, "lead")
        step = run_state.get("synthesis_step", "start")
        last_content = ""
        if groupchat.messages:
            last_msg = groupchat.messages[-1]
            last_content = str(last_msg.get("content", ""))
            # If the last message contains tool_calls, route to executor
            if last_msg.get("tool_calls") and "executor" in role_to_agent:
                return role_to_agent["executor"]
            # After executor runs a tool, route based on workflow state
            if last_role == "executor":
                if step == "read":
                    # read_report_segment executed → analyst continues or critic reviews
                    return role_to_agent["analyst"]
                if step == "back_request":
                    run_state["synthesis_step"] = "read"
                    return role_to_agent["analyst"]
                if step == "finalize":
                    return role_to_agent["lead"]
                if step == "decide":
                    return role_to_agent["lead"]
                return role_to_agent["lead"]

        if step == "start":
            run_state["synthesis_step"] = "read"
            return role_to_agent["analyst"]

        if step == "read" and last_role == "analyst":
            # Analyst may need to read multiple segments — check if done
            if "read_report_segment" in last_content and last_content.count("read_report_segment") < 2:
                # Still reading — let analyst continue
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
            # Default: Lead finalizes
            run_state["synthesis_step"] = "finalize"
            return role_to_agent["lead"]

        if step == "back_request" and last_role == "lead":
            # After back-request executed → re-read updated segment
            run_state["synthesis_step"] = "read"
            return role_to_agent["analyst"]

        if step == "judge" and last_role == "judge":
            run_state["synthesis_step"] = "decide"
            return role_to_agent["lead"]

        # Safety fallback
        run_state["synthesis_step"] = "decide"
        return role_to_agent["lead"]

    return _selector
