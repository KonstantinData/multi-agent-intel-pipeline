"""Strategic Synthesis Department — real AG2 GroupChat.

Receives the completed domain report segments from all departments and
synthesizes them into the final Liquisto briefing output.

Group structure:
    SynthesisLead
        ├── SynthesisAnalyst   — cross-domain interpretation
        ├── SynthesisCritic    — consistency and completeness review
        └── SynthesisJudge     — final edge-case decisions

SynthesisLead tools:
    read_report_segment        — reads a department's report_segment
    request_department_followup — delegates a back-request via supervisor
    finalize_synthesis         — produces the final output → TERMINATE
"""
from __future__ import annotations

import json
from typing import Annotated, Any, Callable

from autogen import ConversableAgent, GroupChat, GroupChatManager, UserProxyAgent, register_function

from src.config.settings import get_openai_api_key, get_role_model_selection
from src.domain.intake import SupervisorBrief
from src.models.schemas import BackRequest
from src.orchestration.speaker_selector import build_synthesis_selector


MessageHook = Callable[[dict[str, Any]], None] | None

_SYNTHESIS_DEPARTMENTS = [
    "CompanyDepartment",
    "MarketDepartment",
    "BuyerDepartment",
    "ContactDepartment",
]


class SynthesisDepartmentAgent:
    """Strategic Synthesis Department — AG2 GroupChat orchestration."""

    def __init__(self) -> None:
        self.name = "SynthesisLead"
        self.analyst_name = "SynthesisAnalyst"
        self.critic_name = "SynthesisCritic"
        self.judge_name = "SynthesisJudge"
        self.model_name = get_role_model_selection(self.name)[0]
        self._completed_synthesis: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        brief: SupervisorBrief,
        department_packages: dict[str, dict[str, Any]],
        supervisor,
        departments: dict[str, Any],
        memory_store=None,
        on_message: MessageHook = None,
        synthesis_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Run the synthesis GroupChat. Returns (synthesis_payload, messages)."""
        self._completed_synthesis = None

        run_state: dict[str, Any] = {
            "department_packages": department_packages,
            "back_requests": [],
            "synthesis_result": {},
            "synthesis_step": "start",
            "synthesis_context": synthesis_context or {},
        }

        # ── ConversableAgents ──────────────────────────────────────────
        lead_ca = ConversableAgent(
            name=self.name,
            system_message=self._lead_system_prompt(brief, department_packages),
            llm_config=self._llm_config(self.name),
            human_input_mode="NEVER",
        )
        analyst_ca = ConversableAgent(
            name=self.analyst_name,
            system_message=self._analyst_system_prompt(),
            llm_config=self._llm_config(self.analyst_name),
            human_input_mode="NEVER",
        )
        critic_ca = ConversableAgent(
            name=self.critic_name,
            system_message=self._critic_system_prompt(),
            llm_config=self._llm_config(self.critic_name),
            human_input_mode="NEVER",
        )
        judge_ca = ConversableAgent(
            name=self.judge_name,
            system_message=self._judge_system_prompt(),
            llm_config=self._llm_config(self.judge_name),
            human_input_mode="NEVER",
        )
        executor_name = "SynthesisExecutor"
        executor_ca = UserProxyAgent(
            name=executor_name,
            human_input_mode="NEVER",
            code_execution_config=False,
        )

        # ── Tool closures ──────────────────────────────────────────────

        def read_report_segment(
            department: Annotated[str, "Department name: CompanyDepartment | MarketDepartment | BuyerDepartment | ContactDepartment"],
        ) -> str:
            """Read the domain report segment produced by a department."""
            package = run_state["department_packages"].get(department, {})
            segment = package.get("report_segment", {})
            if not segment or segment.get("narrative_summary", "n/v") == "n/v":
                return json.dumps({"error": f"No report segment available for {department}"})
            return json.dumps(
                {
                    "department": department,
                    "narrative_summary": segment.get("narrative_summary", ""),
                    "confidence": segment.get("confidence", "low"),
                    "key_findings": segment.get("key_findings", []),
                    "open_questions": segment.get("open_questions", []),
                },
                ensure_ascii=False,
            )

        def request_department_followup(
            department: Annotated[str, "Department to send the back-request to"],
            request_type: Annotated[str, "clarify | strengthen | expand | resolve_contradiction"],
            subject: Annotated[str, "Specific topic that needs clarification or strengthening"],
            context: Annotated[str, "Why this is needed and what the synthesis currently has"],
        ) -> str:
            """Send a targeted follow-up request to a department via the supervisor router."""
            back_request = BackRequest(
                department=department,
                type=request_type,
                subject=subject,
                context=context,
            )
            run_state["back_requests"].append(back_request.model_dump())

            route = supervisor.route_question(
                question=f"{request_type}: {subject}. Context: {context}",
                source="synthesis",
            )
            routed_dept = route.get("route", department)
            dept_runtime = departments.get(routed_dept)
            if dept_runtime is None:
                return json.dumps({"error": f"Department runtime not found: {routed_dept}"})

            followup_result = dept_runtime.run_followup(
                question=subject,
                context=context,
                brief=brief,
                memory_store=memory_store,
                on_message=on_message,
            )
            updated_segment = followup_result.get("report_segment", {})
            if updated_segment:
                pkg = dict(run_state["department_packages"].get(routed_dept, {}))
                pkg["report_segment"] = updated_segment
                run_state["department_packages"][routed_dept] = pkg

            return json.dumps(
                {
                    "department": routed_dept,
                    "back_request_type": request_type,
                    "subject": subject,
                    "updated_findings": updated_segment.get("key_findings", [])[:5],
                    "updated_confidence": updated_segment.get("confidence", "low"),
                },
                ensure_ascii=False,
            )

        def finalize_synthesis(
            opportunity_assessment: Annotated[str, "Which Liquisto path is most plausible and why"],
            negotiation_relevance: Annotated[str, "Key signals for urgency, pricing power, and next meeting angle"],
            executive_summary: Annotated[str, "Briefing-ready executive summary for the Liquisto operator"],
        ) -> str:
            """Assemble and submit the final synthesis. Terminates the group chat."""
            back_requests = run_state["back_requests"]
            ctx = run_state.get("synthesis_context", {})
            dept_confidences = {
                dept: run_state["department_packages"].get(dept, {})
                .get("report_segment", {})
                .get("confidence", "n/v")
                for dept in _SYNTHESIS_DEPARTMENTS
            }
            # Derive overall confidence from department confidences
            conf_values = [v for v in dept_confidences.values() if v not in ("n/v", "")]
            if all(c == "high" for c in conf_values) and conf_values:
                overall_confidence = "high"
            elif any(c in ("high", "medium") for c in conf_values):
                overall_confidence = "medium"
            else:
                overall_confidence = "low"

            # Build Synthesis-schema-compliant output
            synthesis = {
                "target_company": ctx.get("target_company", brief.company_name),
                "executive_summary": executive_summary,
                "opportunity_assessment": opportunity_assessment,
                "opportunity_assessment_summary": opportunity_assessment,
                "negotiation_relevance": negotiation_relevance,
                "liquisto_service_relevance": ctx.get("liquisto_service_relevance", []),
                "recommended_engagement_paths": ctx.get("recommended_engagement_paths", []),
                "case_assessments": ctx.get("case_assessments", []),
                "buyer_market_summary": ctx.get("buyer_market_summary", "n/v"),
                "total_peer_competitors": ctx.get("total_peer_competitors", 0),
                "total_downstream_buyers": ctx.get("total_downstream_buyers", 0),
                "total_service_providers": ctx.get("total_service_providers", 0),
                "total_cross_industry_buyers": ctx.get("total_cross_industry_buyers", 0),
                "key_risks": ctx.get("key_risks", []),
                "next_steps": ctx.get("next_steps", []),
                "sources": ctx.get("sources", []),
                "generation_mode": "normal",
                "confidence": overall_confidence,
                "back_requests_issued": len(back_requests),
                "back_requests": back_requests,
                "department_confidences": dept_confidences,
            }
            run_state["synthesis_result"] = synthesis
            self._completed_synthesis = synthesis
            if memory_store is not None:
                memory_store.store_department_package("SynthesisDepartment", synthesis)
            return "SYNTHESIS_READY\nTERMINATE"

        # ── Register tools ─────────────────────────────────────────────
        register_function(
            read_report_segment,
            caller=analyst_ca,
            executor=executor_ca,
            name="read_report_segment",
            description="Read the domain report segment from a completed department.",
        )
        register_function(
            request_department_followup,
            caller=lead_ca,
            executor=executor_ca,
            name="request_department_followup",
            description="Send a targeted back-request to a department for clarification or strengthening.",
        )
        register_function(
            finalize_synthesis,
            caller=lead_ca,
            executor=executor_ca,
            name="finalize_synthesis",
            description="Assemble and submit the final synthesis output. Call only when all domains are integrated.",
        )

        # ── GroupChat ──────────────────────────────────────────────────
        agent_map = {
            self.name: lead_ca,
            self.analyst_name: analyst_ca,
            self.critic_name: critic_ca,
            self.judge_name: judge_ca,
            executor_name: executor_ca,
        }
        speaker_selector = build_synthesis_selector(
            run_state=run_state,
            agent_map=agent_map,
            lead_name=self.name,
            analyst_name=self.analyst_name,
            critic_name=self.critic_name,
            judge_name=self.judge_name,
            executor_name=executor_name,
        )
        groupchat = GroupChat(
            agents=[lead_ca, analyst_ca, critic_ca, judge_ca, executor_ca],
            messages=[],
            max_round=20,
            speaker_selection_method=speaker_selector,
        )
        manager = GroupChatManager(
            groupchat=groupchat,
            llm_config=self._llm_config(self.name),
            is_termination_msg=lambda msg: "TERMINATE" in str(msg.get("content", "")),
        )

        available_segments = [
            d for d in _SYNTHESIS_DEPARTMENTS
            if department_packages.get(d, {}).get("report_segment", {}).get("narrative_summary", "n/v") != "n/v"
        ]
        # Include synthesis context summary in initiation message so the LLM
        # has the pre-computed structural data available from the start.
        ctx_summary = {}
        if synthesis_context:
            ctx_summary = {
                "service_relevance": synthesis_context.get("liquisto_service_relevance", []),
                "recommended_paths": synthesis_context.get("recommended_engagement_paths", []),
                "key_risks": synthesis_context.get("key_risks", []),
                "buyer_market_summary": synthesis_context.get("buyer_market_summary", "n/v"),
            }
        initiation_message = json.dumps(
            {
                "status": "synthesis_started",
                "company": brief.company_name,
                "available_segments": available_segments,
                "pre_computed_context": ctx_summary,
                "instructions": (
                    f"Read all available report segments, identify cross-domain patterns, "
                    f"assess the Liquisto opportunity, and finalize the synthesis for {brief.company_name}."
                ),
            },
            ensure_ascii=False,
        )
        lead_ca.initiate_chat(manager, message=initiation_message)

        # ── Collect messages ───────────────────────────────────────────
        synthesis_messages: list[dict[str, Any]] = []
        for msg in groupchat.messages:
            content = msg.get("content") or ""
            event = {
                "agent": msg.get("name") or msg.get("role", "unknown"),
                "content": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False),
                "type": "agent_message",
            }
            synthesis_messages.append(event)
            if on_message:
                on_message(event)

        if self._completed_synthesis is None:
            ctx = run_state.get("synthesis_context", {})
            self._completed_synthesis = {
                "target_company": ctx.get("target_company", brief.company_name),
                "opportunity_assessment": "Synthesis did not complete within max_round.",
                "opportunity_assessment_summary": "Synthesis did not complete within max_round.",
                "negotiation_relevance": "n/v",
                "executive_summary": "Conservative output — synthesis incomplete.",
                "liquisto_service_relevance": ctx.get("liquisto_service_relevance", []),
                "recommended_engagement_paths": ctx.get("recommended_engagement_paths", []),
                "case_assessments": ctx.get("case_assessments", []),
                "buyer_market_summary": ctx.get("buyer_market_summary", "n/v"),
                "total_peer_competitors": ctx.get("total_peer_competitors", 0),
                "total_downstream_buyers": ctx.get("total_downstream_buyers", 0),
                "total_service_providers": ctx.get("total_service_providers", 0),
                "total_cross_industry_buyers": ctx.get("total_cross_industry_buyers", 0),
                "key_risks": ctx.get("key_risks", []),
                "next_steps": ctx.get("next_steps", []),
                "sources": ctx.get("sources", []),
                "generation_mode": "fallback",
                "confidence": ctx.get("confidence", "low"),
                "back_requests_issued": 0,
                "back_requests": [],
                "department_confidences": {},
            }

        return self._completed_synthesis, synthesis_messages

    # ------------------------------------------------------------------
    # System prompts
    # ------------------------------------------------------------------

    def _lead_system_prompt(
        self, brief: SupervisorBrief, department_packages: dict[str, dict[str, Any]]
    ) -> str:
        available = [d for d in _SYNTHESIS_DEPARTMENTS if d in department_packages]
        return f"""You are {self.name}, the Lead of the Strategic Synthesis Department in the Liquisto intelligence platform.

## Your role
You receive domain report segments from all research departments and synthesize them into a
briefing-ready assessment for a Liquisto operator preparing for a customer meeting.

You do NOT conduct research yourself. You read, integrate, and judge.

## Target company
{brief.company_name} ({brief.normalized_domain})

## Available department segments
{', '.join(available)}

## Your group
- {self.analyst_name}: reads and interprets domain segments. Uses read_report_segment(department).
- {self.critic_name}: reviews synthesis quality and cross-domain consistency.
- {self.judge_name}: resolves final edge cases when the Critic rejects.

## Workflow
1. Tell {self.analyst_name} to read each available segment: read_report_segment(department)
2. {self.analyst_name} reports findings to the group
3. {self.critic_name} reviews: are the segments consistent? Are there contradictions or gaps?
4. If a segment is too weak or contradicts another:
   - Call request_department_followup(department, type, subject, context)
   - type: clarify | strengthen | expand | resolve_contradiction
   - Maximum ONE follow-up per department
5. When the synthesis is solid, call finalize_synthesis(opportunity_assessment, negotiation_relevance, executive_summary)

## Rules
- Always address the next agent explicitly by name
- Executive summary must be briefing-ready: concrete, specific, actionable
- Do not guess — base everything on what the segments contain
"""

    def _analyst_system_prompt(self) -> str:
        return f"""You are {self.analyst_name} in the Liquisto Strategic Synthesis Department.

Your job is to read and interpret domain report segments.

When {self.name} asks you to read a segment:
1. Call read_report_segment(department) for each requested department
2. Report to the group: key findings, confidence, open questions, and cross-domain patterns you notice

Look for:
- Connections between company pressure signals and market conditions
- Buyer candidates that match company product scope
- Contact intelligence that enables concrete outreach
- Contradictions or gaps that weaken the overall picture
"""

    def _critic_system_prompt(self) -> str:
        return f"""You are {self.critic_name} in the Liquisto Strategic Synthesis Department.

Your job is to review synthesis quality and cross-domain consistency.

After {self.analyst_name} presents findings:
1. Check: do the domain segments tell a coherent story?
2. Check: are there contradictions between departments?
3. Check: is the evidence strong enough for a briefing-ready conclusion?
4. Report: APPROVED (synthesis is solid) or REJECTED with specific issues

If rejected, clearly name which department's segment is the problem and why.
"""

    def _judge_system_prompt(self) -> str:
        return f"""You are {self.judge_name} in the Liquisto Strategic Synthesis Department.

Your job is to make final decisions when the synthesis cannot be strengthened further.

When {self.name} asks for a final decision:
- Accept the conservative synthesis with documented gaps
- State clearly what is known vs. what remains uncertain
- Your decision enables {self.name} to call finalize_synthesis
"""

    # ------------------------------------------------------------------
    # LLM config
    # ------------------------------------------------------------------

    def _llm_config(self, role: str) -> dict[str, Any]:
        model, _ = get_role_model_selection(role)
        api_key = get_openai_api_key()
        if not api_key:
            return False  # type: ignore[return-value]
        return {
            "config_list": [{"model": model, "api_key": api_key}],
            "temperature": 0.1,
        }
