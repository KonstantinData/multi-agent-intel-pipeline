"""Department Lead / Analyst — real AG2 GroupChat orchestration.

Each domain department runs as a genuine AG2 GroupChat:

    Lead (CompanyLead)
        ├── CompanyResearcher   — tool: run_research
        ├── CompanyCritic       — tool: review_research
        ├── CompanyJudge        — tool: judge_decision
        └── CompanyCodingSpecialist — tool: suggest_refined_queries

    Lead also holds two tools of its own:
        request_supervisor_revision  — callback to the Supervisor
        finalize_package             — terminates the group chat

The Lead initiates the chat with the investigation plan, directs each
agent explicitly, and calls finalize_package when all tasks are done.
The GroupChatManager (with speaker_selection_method="auto") routes turns
based on who the Lead addresses.
"""
from __future__ import annotations

import json
from typing import Annotated, Any, Callable, Literal

from autogen import ConversableAgent, GroupChat, GroupChatManager, UserProxyAgent, register_function

from src.agents.coding_assistant import CodingAssistantAgent
from src.orchestration.speaker_selector import build_department_selector
from src.agents.critic import CriticAgent
from src.agents.judge import JudgeAgent
from src.agents.worker import ResearchWorker
from src.config.settings import get_openai_api_key, get_role_model_selection
from src.domain.intake import SupervisorBrief
from src.models.schemas import DepartmentPackage, DomainReportSegment
from src.orchestration.task_router import Assignment, DEPARTMENT_RESEARCHERS
from src.orchestration.tool_policy import resolve_allowed_tools
from src.research.extract import extract_product_keywords, infer_industry


MessageHook = Callable[[dict[str, Any]], None] | None

_DEPARTMENT_PREFIX = {
    "CompanyDepartment": "Company",
    "MarketDepartment": "Market",
    "BuyerDepartment": "Buyer",
    "ContactDepartment": "Contact",
}

_VISUAL_FOCUS = {
    "CompanyDepartment": [
        "Verified company identity and visible business model",
        "Made vs distributed vs held-in-stock classification",
        "Economic pressure or inventory stress signals",
    ],
    "MarketDepartment": [
        "Demand and supply pressure summary",
        "Repurposing and circularity opportunities",
        "Analytics and operational friction signals",
    ],
    "BuyerDepartment": [
        "Peer company map",
        "Buyer and secondary-market pathways",
        "Redeployment and aftermarket fit",
    ],
    "ContactDepartment": [
        "Decision-maker map at prioritized buyer firms",
        "Seniority and function of identified contacts",
        "Outreach angles per contact",
    ],
}

_CLASSIFICATION_FRAME = {
    "CompanyDepartment": "made_vs_distributed_vs_held_in_stock",
    "MarketDepartment": "demand_supply_circularity_analytics",
    "BuyerDepartment": "peers_buyers_redeployment_aftermarket",
    "ContactDepartment": "decision_makers_by_function_and_seniority",
}

_INVESTIGATION_FOCUS = {
    "CompanyDepartment": [
        "Classify the company as manufacturer, distributor, or mixed model",
        "Identify visible goods, materials, spare parts, and inventory positions",
        "Assess economic pressure and commercial situation signals",
    ],
    "MarketDepartment": [
        "Define market hypotheses and assess demand / supply pressure",
        "Evaluate repurposing, circularity, and adjacent reuse paths",
        "Surface analytics and operational improvement signals",
    ],
    "BuyerDepartment": [
        "Map peer and competitor companies",
        "Identify plausible downstream buyers and secondary-market paths",
        "Assess monetization and redeployment options",
    ],
    "ContactDepartment": [
        "Identify publicly visible decision-makers at prioritized buyer firms",
        "Classify contacts by function (procurement, operations, asset management) and seniority",
        "Derive a concrete outreach angle per contact based on Liquisto's business model",
    ],
}

_TASK_GUIDANCE_TEMPLATES: dict[str, str] = {
    "contact_discovery": (
        "Search for publicly visible decision-makers at buyer firms relevant to {company}. "
        "Focus on: Head of Procurement, Head of Asset Management, COO, VP Operations, "
        "Supply Chain Director. Use LinkedIn, company websites, press releases."
    ),
    "contact_qualification": (
        "For each identified contact at buyer firms for {company}, assess: "
        "seniority level, decision-making authority, relevance to Liquisto's business model "
        "(excess inventory, remarketing, redeployment). "
        "Suggest a specific outreach angle per contact."
    ),
    "company_fundamentals": (
        "Confirm company identity, legal name, website, and industry classification for {company}. "
        "Establish whether it manufactures, distributes, or holds stock of: {keywords}."
    ),
    "economic_commercial_situation": (
        "Surface economic pressure signals for {company}: revenue trends, inventory stress, "
        "restructuring signals. Focus on public-web evidence."
    ),
    "product_asset_scope": (
        "Classify the visible product and asset scope: made vs distributed vs held-in-stock. "
        "Keywords to anchor on: {keywords}. Identify which are commercially movable."
    ),
    "market_situation": (
        "Assess demand/supply dynamics for {industry}. Surface key trends, capacity signals, "
        "and market pressure relevant to {company}."
    ),
    "repurposing_circularity": (
        "Identify repurposing and circular-economy paths for products in scope: {keywords}. "
        "Focus on reuse, refurbishment, or materials recovery."
    ),
    "analytics_operational_improvement": (
        "Surface operational and analytics improvement signals for {company}: "
        "planning gaps, inventory visibility, forecasting bottlenecks."
    ),
    "peer_companies": (
        "Map peer and competitor companies in {industry}. "
        "Focus on companies handling similar goods: {keywords}."
    ),
    "monetization_redeployment": (
        "Identify downstream buyers, distributors, and redeployment paths for {keywords}. "
        "Assess monetization and aftermarket potential."
    ),
}


class DepartmentLeadAgent:
    """Lead / Analyst agent for one domain department.

    Builds a real AG2 GroupChat on every ``run()`` call. The tools are
    Python closures so they capture the per-run brief, assignments,
    supervisor handle, and shared run_state dict.
    """

    def __init__(self, department: str) -> None:
        self.department = department
        self.prefix = _DEPARTMENT_PREFIX[department]
        self.name = f"{self.prefix}Lead"
        self.researcher_name = DEPARTMENT_RESEARCHERS[department]
        self.critic_name = f"{self.prefix}Critic"
        self.judge_name = f"{self.prefix}Judge"
        self.coding_name = f"{self.prefix}CodingSpecialist"
        self.model_name = get_role_model_selection(self.name)[0]
        self.allowed_tools = resolve_allowed_tools(self.name, "lead_planning")

        # Python implementations — tools delegate to these
        self.worker = ResearchWorker(self.researcher_name)
        self.critic = CriticAgent(self.critic_name)
        self.judge = JudgeAgent(self.judge_name)
        self.coding_assistant = CodingAssistantAgent(self.coding_name)

        self._completed_package: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def build_investigation_plan(
        self,
        brief: SupervisorBrief,
        assignments: list[Assignment],
    ) -> dict[str, Any]:
        """Translate the supervisor brief into a structured domain investigation plan."""
        product_keywords = extract_product_keywords(brief.raw_homepage_excerpt)
        industry_hint = infer_industry(
            brief.page_title, brief.meta_description, brief.raw_homepage_excerpt
        )
        task_sequence = [
            {
                "task_key": a.task_key,
                "label": a.label,
                "lead_guidance": self._task_guidance(
                    a.task_key, brief, product_keywords, industry_hint
                ),
            }
            for a in assignments
        ]
        return {
            "department": self.department,
            "lead": self.name,
            "classification_frame": _CLASSIFICATION_FRAME[self.department],
            "investigation_focus": _INVESTIGATION_FOCUS[self.department],
            "domain_hypothesis": self._domain_hypothesis(
                brief, product_keywords, industry_hint
            ),
            "task_sequence": task_sequence,
            "company_name": brief.company_name,
            "industry_hint": industry_hint or "n/v",
            "product_keywords": product_keywords[:6],
        }

    def autogen_group_spec(self) -> dict[str, Any]:
        return {
            "framework": "AutoGen",
            "group_name": f"{self.department}Group",
            "lead": self.name,
            "members": [
                self.name,
                self.researcher_name,
                self.critic_name,
                self.judge_name,
                self.coding_name,
                f"{self.prefix}Executor",
            ],
            "max_round": 8,
            "speaker_selection_method": "state_machine",
        }

    def run(
        self,
        *,
        brief: SupervisorBrief,
        assignments: list[Assignment],
        current_section: dict[str, Any] | None,
        supervisor,
        memory_store=None,
        role_memory: dict[str, list[dict[str, Any]]] | None = None,
        on_message: MessageHook = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        """Build a fresh AG2 GroupChat, run the investigation, return the domain package."""
        self._completed_package = None

        if memory_store is not None:
            memory_store.open_department_workspace(self.department)

        # Shared mutable state across all tool closures for this run
        run_state: dict[str, Any] = {
            "current_payload": dict(current_section or {}),
            "query_overrides": {},   # task_key → list[str]
            "revision_requests": {}, # task_key → dict
            "last_reviews": {},      # task_key → review dict (set by review_research)
            "attempts": {},          # task_key → int
            "task_results": {},      # task_key → worker report
            "workflow_step": "start",  # state-machine phase
            "tool_errors": [],       # structured error log
        }

        investigation_plan = self.build_investigation_plan(brief, assignments)

        # ── ConversableAgents ──────────────────────────────────────────────
        lead_ca = ConversableAgent(
            name=self.name,
            system_message=self._lead_system_prompt(investigation_plan, assignments),
            llm_config=self._llm_config(self.name),
            human_input_mode="NEVER",
        )
        researcher_ca = ConversableAgent(
            name=self.researcher_name,
            system_message=self._researcher_system_prompt(),
            llm_config=self._llm_config(self.researcher_name),
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
        coding_ca = ConversableAgent(
            name=self.coding_name,
            system_message=self._coding_system_prompt(),
            llm_config=self._llm_config(self.coding_name),
            human_input_mode="NEVER",
        )
        # Tool executor: executes all tool calls in the GroupChat.
        # In AG2 GroupChat, caller!=executor is required — the caller
        # proposes the tool call (via LLM), the executor runs it.
        executor_name = f"{self.prefix}Executor"
        executor_ca = UserProxyAgent(
            name=executor_name,
            human_input_mode="NEVER",
            code_execution_config=False,
        )

        # ── Tool closures ──────────────────────────────────────────────────

        def run_research(
            task_key: Annotated[str, "The task_key to investigate"],
        ) -> str:
            """Run web research for the given task_key. Returns a research summary."""
            assignment = next((a for a in assignments if a.task_key == task_key), None)
            if not assignment:
                return json.dumps({"error": f"Unknown task_key: {task_key}"})
            try:
                report = self.worker.run(
                    brief=brief,
                    task_key=task_key,
                    target_section=assignment.target_section,
                    objective=assignment.objective,
                    current_sections={assignment.target_section: run_state["current_payload"]},
                    query_overrides=run_state["query_overrides"].get(task_key),
                    allowed_tools=list(assignment.allowed_tools),
                    model_name=assignment.model_name,
                    revision_request=run_state["revision_requests"].get(task_key),
                    role_memory=(role_memory or {}).get(self.researcher_name, []),
                )
            except Exception as exc:
                err = {"tool": "run_research", "task_key": task_key, "error": str(exc)}
                run_state["tool_errors"].append(err)
                return json.dumps({"error": f"run_research failed: {exc}", "task_key": task_key})
            run_state["current_payload"] = dict(report["payload"])
            run_state["task_results"][task_key] = report
            run_state["workflow_step"] = "review"  # advance state-machine
            if memory_store is not None:
                memory_store.ingest_worker_report(report, department=self.department)
            return json.dumps(
                {
                    "task_key": task_key,
                    "status": "research_complete",
                    "facts": report.get("facts", [])[:5],
                    "open_questions": report.get("open_questions", [])[:3],
                    "payload_keys": list(report.get("payload", {}).keys()),
                },
                ensure_ascii=False,
            )

        def review_research(
            task_key: Annotated[str, "The task_key to review"],
        ) -> str:
            """Review the current research result for the given task_key."""
            assignment = next((a for a in assignments if a.task_key == task_key), None)
            if not assignment:
                return json.dumps({"error": f"Unknown task_key: {task_key}"})
            report = run_state["task_results"].get(task_key)
            if not report:
                return json.dumps({"error": f"No research result yet for: {task_key}"})
            try:
                review = self.critic.review(
                    task_key=task_key,
                    section=assignment.target_section,
                    objective=assignment.objective,
                    payload=report["payload"],
                    report=report,
                    role_memory=(role_memory or {}).get(self.critic_name, []),
                )
            except Exception as exc:
                err = {"tool": "review_research", "task_key": task_key, "error": str(exc)}
                run_state["tool_errors"].append(err)
                return json.dumps({"error": f"review_research failed: {exc}", "task_key": task_key})
            run_state["last_reviews"][task_key] = review
            run_state["workflow_step"] = "decide"  # advance state-machine
            if memory_store is not None:
                memory_store.mark_critic_review(
                    task_key,
                    bool(review["approved"]),
                    review["issues"],
                    review=review,
                    department=self.department,
                )
            return json.dumps(
                {
                    "task_key": task_key,
                    "approved": review["approved"],
                    "accepted_points": review.get("accepted_points", []),
                    "rejected_points": review.get("rejected_points", []),
                    "issues": review.get("issues", []),
                    "evidence_strength": review.get("evidence_strength", "weak"),
                    "method_issue": review.get("method_issue", False),
                },
                ensure_ascii=False,
            )

        def request_supervisor_revision(
            task_key: Annotated[str, "The task_key requiring revision"],
        ) -> str:
            """Ask the Supervisor whether to retry the task or accept conservative output."""
            review = run_state["last_reviews"].get(task_key, {})
            attempt = run_state["attempts"].get(task_key, 0)
            run_state["attempts"][task_key] = attempt + 1
            try:
                decision = supervisor.decide_revision(
                    task_key=task_key, review=review, attempt=attempt
                )
            except Exception as exc:
                err = {"tool": "request_supervisor_revision", "task_key": task_key, "error": str(exc)}
                run_state["tool_errors"].append(err)
                decision = {"retry": False, "reason": f"Supervisor revision failed: {exc}"}
            if decision.get("retry"):
                run_state["revision_requests"][task_key] = {
                    "accepted_points": review.get("accepted_points", []),
                    "rejected_points": review.get("rejected_points", []),
                    "missing_points": review.get("missing_points", []),
                    "feedback_to_worker": review.get("feedback_to_worker", []),
                    "revision_instructions": review.get("revision_instructions", []),
                }
                run_state["workflow_step"] = "research"  # back to research
            else:
                run_state["workflow_step"] = "decide"  # Lead decides next
            return json.dumps(decision, ensure_ascii=False)

        def suggest_refined_queries(
            task_key: Annotated[str, "The task_key that needs better queries"],
        ) -> str:
            """Suggest refined search queries to unblock a stuck research task."""
            assignment = next((a for a in assignments if a.task_key == task_key), None)
            if not assignment:
                return json.dumps({"error": f"Unknown task_key: {task_key}"})
            review = run_state["last_reviews"].get(task_key, {})
            try:
                support = self.coding_assistant.suggest_queries(
                    section=assignment.target_section,
                    brief=brief,
                    issues=review.get("issues", []),
                    review=review,
                    coding_brief=review.get("coding_brief"),
                )
            except Exception as exc:
                err = {"tool": "suggest_refined_queries", "task_key": task_key, "error": str(exc)}
                run_state["tool_errors"].append(err)
                return json.dumps({"error": f"suggest_refined_queries failed: {exc}", "task_key": task_key})
            run_state["query_overrides"][task_key] = support["query_overrides"]
            run_state["workflow_step"] = "research"  # after coding → research
            return json.dumps(
                {
                    "task_key": task_key,
                    "query_overrides": support["query_overrides"],
                    "summary": support["summary"],
                },
                ensure_ascii=False,
            )

        def judge_decision(
            task_key: Annotated[str, "The task_key to decide on"],
        ) -> str:
            """Make a final edge-case decision when retries are exhausted."""
            review = run_state["last_reviews"].get(task_key, {})
            try:
                result = self.judge.decide(
                    section=task_key,
                    critic_review=review if review else None,
                    critic_issues=review.get("issues", []) if review else [],
                )
            except Exception as exc:
                err = {"tool": "judge_decision", "task_key": task_key, "error": str(exc)}
                run_state["tool_errors"].append(err)
                result = {"task_status": "degraded", "reason": f"Judge failed: {exc}", "open_questions": [str(exc)]}
            run_state["workflow_step"] = "decide"  # back to Lead
            return json.dumps(result, ensure_ascii=False)

        def finalize_package(
            summary: Annotated[str, "Full narrative summary of the completed investigation — written as a domain expert report section. Include key findings, confidence assessment, and what remains open."],
        ) -> str:
            """Assemble and submit the domain package. Terminates the group chat."""
            task_summaries: list[dict[str, Any]] = []
            accepted_points: list[str] = []
            open_questions: list[str] = []
            sources: list[dict[str, Any]] = []

            for assignment in assignments:
                report = run_state["task_results"].get(assignment.task_key)
                if report:
                    # Reuse cached review from the chat cycle instead of re-running
                    cached_review = run_state["last_reviews"].get(assignment.task_key)
                    final_review = cached_review if cached_review else self.critic.review(
                        task_key=assignment.task_key,
                        section=assignment.target_section,
                        objective=assignment.objective,
                        payload=report["payload"],
                    )
                    judge_result = self.judge.decide(
                        section=assignment.task_key,
                        critic_review=final_review,
                    )
                    task_status = judge_result["task_status"]  # accepted | degraded | rejected
                    judge_open_questions = judge_result.get("open_questions", [])
                    accepted_points.extend(final_review.get("accepted_points", []))
                    open_questions.extend(report.get("open_questions", []))
                    open_questions.extend(judge_open_questions)
                    sources.extend(report.get("sources", []))
                    task_summaries.append(
                        {
                            "task_key": assignment.task_key,
                            "label": assignment.label,
                            "status": task_status,
                            "accepted_points": final_review.get("accepted_points", []),
                            "open_points": list(
                                dict.fromkeys(
                                    report.get("open_questions", [])
                                    + final_review.get("missing_points", [])
                                    + judge_open_questions
                                )
                            ),
                            "summary": report.get("objective", assignment.objective),
                        }
                    )
                else:
                    task_summaries.append(
                        {
                            "task_key": assignment.task_key,
                            "label": assignment.label,
                            "status": "rejected",
                            "accepted_points": [],
                            "open_points": ["No research result produced."],
                            "summary": assignment.objective,
                        }
                    )

            # Derive package confidence from task statuses
            accepted_count = sum(1 for t in task_summaries if t.get("status") == "accepted")
            degraded_count = sum(1 for t in task_summaries if t.get("status") == "degraded")
            total_count = len(task_summaries) or 1
            if accepted_count == total_count:
                confidence = "high"
            elif accepted_count + degraded_count > 0:
                confidence = "medium"
            else:
                confidence = "low"

            report_segment = DomainReportSegment(
                department=self.department,
                narrative_summary=summary or f"{self.department} investigation completed by {self.name}.",
                confidence=confidence,
                key_findings=list(dict.fromkeys(accepted_points))[:10],
                open_questions=list(dict.fromkeys(open_questions))[:6],
                sources=[],
            ).model_dump(mode="json")

            package = DepartmentPackage.model_validate(
                {
                    "department": self.department,
                    "target_section": assignments[0].target_section if assignments else "n/v",
                    "summary": summary or f"{self.department} domain package assembled by {self.name}.",
                    "section_payload": run_state["current_payload"],
                    "completed_tasks": task_summaries,
                    "accepted_points": list(dict.fromkeys(accepted_points)),
                    "open_questions": list(dict.fromkeys(open_questions)),
                    "visual_focus": _VISUAL_FOCUS.get(self.department, []),
                    "sources": sources[:12],
                    "autogen_group": self.autogen_group_spec(),
                    "report_segment": report_segment,
                    "confidence": confidence,
                }
            ).model_dump(mode="json")

            # Log tool errors as open_questions for traceability
            for err in run_state.get("tool_errors", []):
                package["open_questions"] = list(dict.fromkeys(
                    package.get("open_questions", []) + [f"Tool error ({err['tool']}): {err['error']}"]
                ))

            self._completed_package = package
            if memory_store is not None:
                memory_store.store_department_package(self.department, package)

            return "PACKAGE_READY\nTERMINATE"

        # ── Register tools with AG2 ────────────────────────────────────────
        # caller = agent whose LLM proposes the tool call
        # executor = agent that runs the function (always executor_ca)
        register_function(
            run_research,
            caller=researcher_ca,
            executor=executor_ca,
            name="run_research",
            description=(
                "Run web research for a given task_key. "
                "Returns facts, open questions, and payload key summary."
            ),
        )
        register_function(
            review_research,
            caller=critic_ca,
            executor=executor_ca,
            name="review_research",
            description=(
                "Review the research result for a given task_key. "
                "Returns approval status, accepted/rejected points, and issues."
            ),
        )
        register_function(
            request_supervisor_revision,
            caller=lead_ca,
            executor=executor_ca,
            name="request_supervisor_revision",
            description=(
                "Ask the Supervisor whether to retry the task or accept conservative output. "
                "Returns retry: true/false and whether to authorize the CodingSpecialist."
            ),
        )
        register_function(
            suggest_refined_queries,
            caller=coding_ca,
            executor=executor_ca,
            name="suggest_refined_queries",
            description=(
                "Suggest refined search queries to unblock a stuck research task. "
                "Returns a list of query_overrides for the Researcher."
            ),
        )
        register_function(
            judge_decision,
            caller=judge_ca,
            executor=executor_ca,
            name="judge_decision",
            description=(
                "Make a final edge-case decision when retries are exhausted. "
                "Returns accept_conservative_output and reason."
            ),
        )
        register_function(
            finalize_package,
            caller=lead_ca,
            executor=executor_ca,
            name="finalize_package",
            description=(
                "Assemble and submit the completed domain package. "
                "Call this only when ALL assigned tasks are done. Terminates the group chat."
            ),
        )

        # ── GroupChat and Manager ──────────────────────────────────────────
        agent_map = {
            self.name: lead_ca,
            self.researcher_name: researcher_ca,
            self.critic_name: critic_ca,
            self.judge_name: judge_ca,
            self.coding_name: coding_ca,
            executor_name: executor_ca,
        }
        speaker_selector = build_department_selector(
            run_state=run_state,
            agent_map=agent_map,
            lead_name=self.name,
            researcher_name=self.researcher_name,
            critic_name=self.critic_name,
            judge_name=self.judge_name,
            coding_name=self.coding_name,
            executor_name=executor_name,
        )
        groupchat = GroupChat(
            agents=[lead_ca, researcher_ca, critic_ca, judge_ca, coding_ca, executor_ca],
            messages=[],
            max_round=len(assignments) * 15,
            speaker_selection_method=speaker_selector,
        )
        manager = GroupChatManager(
            groupchat=groupchat,
            llm_config=self._llm_config(self.name),
            is_termination_msg=lambda msg: "TERMINATE" in str(msg.get("content", "")),
        )

        # ── Initiate chat ──────────────────────────────────────────────────
        initiation_message = json.dumps(
            {
                "status": "department_started",
                "investigation_plan": investigation_plan,
                "tasks_to_complete": [a.task_key for a in assignments],
            },
            ensure_ascii=False,
        )
        lead_ca.initiate_chat(manager, message=initiation_message)

        # ── Convert AG2 message history to event stream ────────────────────
        package_messages: list[dict[str, Any]] = []
        for msg in groupchat.messages:
            content = msg.get("content") or ""
            event = {
                "agent": msg.get("name") or msg.get("role", "unknown"),
                "content": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False),
                "type": "agent_message",
            }
            package_messages.append(event)
            if on_message:
                on_message(event)

        # Fallback: if finalize_package was never called (e.g. max_round hit)
        if self._completed_package is None:
            self._completed_package = self._build_fallback_package(assignments, run_state)
            if memory_store is not None:
                memory_store.store_department_package(
                    self.department, self._completed_package
                )

        if memory_store is not None:
            memory_store.append_department_conversation(self.department, package_messages)

        return run_state["current_payload"], package_messages, self._completed_package

    def run_followup(
        self,
        *,
        question: str,
        context: str,
        brief: SupervisorBrief,
        memory_store=None,
        on_message: MessageHook = None,
    ) -> dict[str, Any]:
        """Run a focused mini-GroupChat to answer a specific follow-up question.

        Returns a dict with an updated ``report_segment`` key.
        """
        run_state: dict[str, Any] = {
            "current_payload": {},
            "query_overrides": {},
            "revision_requests": {},
            "last_reviews": {},
            "attempts": {},
            "task_results": {},
        }

        followup_assignment = Assignment(
            task_key="followup_question",
            assignee=self.researcher_name,
            target_section="followup",
            label="Follow-up investigation",
            objective=f"{question}. Context: {context}",
            model_name=self.model_name,
            allowed_tools=("web_search", "page_fetch"),
        )

        if memory_store is not None:
            memory_store.open_department_workspace(f"{self.department}_followup")

        lead_ca = ConversableAgent(
            name=self.name,
            system_message=self._followup_lead_system_prompt(question, context),
            llm_config=self._llm_config(self.name),
            human_input_mode="NEVER",
        )
        researcher_ca = ConversableAgent(
            name=self.researcher_name,
            system_message=self._researcher_system_prompt(),
            llm_config=self._llm_config(self.researcher_name),
            human_input_mode="NEVER",
        )
        critic_ca = ConversableAgent(
            name=self.critic_name,
            system_message=self._critic_system_prompt(),
            llm_config=self._llm_config(self.critic_name),
            human_input_mode="NEVER",
        )

        result_holder: dict[str, Any] = {}

        def run_research(task_key: Annotated[str, "task key"]) -> str:
            report = self.worker.run(
                brief=brief,
                task_key=task_key,
                target_section="followup",
                objective=followup_assignment.objective,
                current_sections={},
                query_overrides=None,
                allowed_tools=list(followup_assignment.allowed_tools),
                model_name=followup_assignment.model_name,
                revision_request=None,
                role_memory=[],
            )
            run_state["task_results"][task_key] = report
            if memory_store is not None:
                memory_store.ingest_worker_report(report, department=f"{self.department}_followup")
            return json.dumps({
                "task_key": task_key,
                "facts": report.get("facts", [])[:5],
                "open_questions": report.get("open_questions", [])[:3],
            }, ensure_ascii=False)

        def finalize_followup(
            summary: Annotated[str, "Updated findings that answer the follow-up question"],
        ) -> str:
            report = run_state["task_results"].get("followup_question", {})
            facts = report.get("facts", [])
            result_holder["report_segment"] = {
                "department": self.department,
                "narrative_summary": summary,
                "confidence": "medium" if facts else "low",
                "key_findings": facts[:8],
                "open_questions": report.get("open_questions", [])[:4],
                "sources": [],
            }
            return "FOLLOWUP_READY\nTERMINATE"

        register_function(run_research, caller=researcher_ca, executor=researcher_ca,
                          name="run_research", description="Run research for the follow-up question.")
        register_function(finalize_followup, caller=lead_ca, executor=lead_ca,
                          name="finalize_followup", description="Submit the follow-up answer.")

        groupchat = GroupChat(
            agents=[lead_ca, researcher_ca, critic_ca],
            messages=[],
            max_round=8,
            speaker_selection_method="auto",
        )
        manager = GroupChatManager(
            groupchat=groupchat,
            llm_config=self._llm_config(self.name),
            is_termination_msg=lambda msg: "TERMINATE" in str(msg.get("content", "")),
        )
        lead_ca.initiate_chat(
            manager,
            message=json.dumps({
                "status": "followup_started",
                "question": question,
                "context": context,
                "task_key": "followup_question",
            }, ensure_ascii=False),
        )

        for msg in groupchat.messages:
            if on_message:
                on_message({
                    "agent": msg.get("name") or "unknown",
                    "content": str(msg.get("content") or ""),
                    "type": "followup_message",
                })

        return result_holder if result_holder else {
            "report_segment": {
                "department": self.department,
                "narrative_summary": f"Follow-up for '{question}' could not be completed.",
                "confidence": "low",
                "key_findings": [],
                "open_questions": [question],
                "sources": [],
            }
        }

    # ------------------------------------------------------------------
    # System prompts
    # ------------------------------------------------------------------

    def _lead_system_prompt(
        self, investigation_plan: dict[str, Any], assignments: list[Assignment]
    ) -> str:
        task_list = "\n".join(
            f"  {i + 1}. {a.task_key} — {a.label}\n"
            f"     Guidance: {t['lead_guidance']}"
            for i, (a, t) in enumerate(
                zip(assignments, investigation_plan["task_sequence"])
            )
        )
        domain_hypothesis = investigation_plan.get("domain_hypothesis", "")
        classification_frame = investigation_plan.get("classification_frame", "")
        return f"""You are {self.name}, the Lead / Analyst of the {self.department} in the Liquisto intelligence platform.

## Your role
You lead a domain group that investigates a target company and delivers a structured domain package to the Supervisor.
You do NOT conduct research yourself — you direct your group and make decisions.

## Investigation context
Domain hypothesis: {domain_hypothesis}
Classification frame: {classification_frame}

## Your group members
- {self.researcher_name}: Runs web research. Triggered by you, calls run_research(task_key).
- {self.critic_name}: Reviews research quality. Triggered by you or after Researcher reports, calls review_research(task_key).
- {self.judge_name}: Resolves final edge cases. Triggered by you when retries are exhausted, calls judge_decision(task_key).
- {self.coding_name}: Refines blocked search paths. Triggered by you when Supervisor authorizes it, calls suggest_refined_queries(task_key).

## Tasks assigned to this department
{task_list}

## Workflow — follow this strictly
For each task, in order:
1. Tell {self.researcher_name}: "Please run_research for task_key: <key>"
2. Tell {self.critic_name}: "Please review_research for task_key: <key>"
3. Read the review result:
   - APPROVED → note it, move to the next task
   - REJECTED → call request_supervisor_revision(task_key)
     - If retry=true AND authorize_coding_specialist=true: tell {self.coding_name} to suggest_refined_queries, then ask {self.researcher_name} to run_research again
     - If retry=true AND authorize_coding_specialist=false: ask {self.researcher_name} to run_research again directly
     - If retry=false: tell {self.judge_name} to judge_decision(task_key), then move to next task

## Completing the run
When ALL tasks are done (approved or conservatively accepted):
- Call finalize_package(summary) with a full narrative report section written as a domain expert.
- The summary must cover: what was found, confidence level, key findings, what remains open.
- Write it as a briefing-ready paragraph — not a bullet list, not a sentence fragment.
- The chat will end after this call.

## Rules
- Always explicitly name the next agent in your message (e.g., "{self.researcher_name}, please...")
- Never skip a task — complete them all before finalizing
- Keep your messages short and structured
"""

    def _researcher_system_prompt(self) -> str:
        return f"""You are {self.researcher_name} in the Liquisto intelligence platform.

Your job is to investigate the target company using web search and page fetching.

When {self.name} directs you to a task:
1. Call run_research(task_key) with the exact task_key provided
2. Report the result concisely to the group: key facts found, open questions, payload coverage

Be factual and conservative. Never invent companies, URLs, or claims.
If evidence is weak, say so clearly.
"""

    def _critic_system_prompt(self) -> str:
        return f"""You are {self.critic_name} in the Liquisto intelligence platform.

Your job is to review research quality and completeness with domain rigor.

When {self.name} or after {self.researcher_name} presents results:
1. Call review_research(task_key) for the task that was just researched
2. Report to the group:
   - If APPROVED: "Task <key> approved. Accepted: <points>"
   - If REJECTED: "Task <key> rejected. Issues: <issues>. Rejected points: <points>"

Check whether the supervisor's questions were answered with sufficient evidence.
Do not approve weak or unsupported findings.
"""

    def _judge_system_prompt(self) -> str:
        return f"""You are {self.judge_name} in the Liquisto intelligence platform.

Your job is to make final decisions on tasks that cannot be improved further.

When {self.name} asks you to decide on a task:
1. Call judge_decision(task_key) for the given task
2. Report your decision: "Judge decision for <key>: accept conservative output — <reason>"

Your decisions are final. You accept that some evidence gaps will remain.
"""

    def _followup_lead_system_prompt(self, question: str, context: str) -> str:
        return f"""You are {self.name}, leading a targeted follow-up investigation.

A follow-up question has been submitted that requires additional research.

Question: {question}
Context: {context}

Your workflow:
1. Tell {self.researcher_name}: "Please run_research for task_key: followup_question"
2. Tell {self.critic_name} to review the result
3. Call finalize_followup(summary) with your updated findings

Keep it focused. Answer the specific question. Do not run a full department investigation.
"""

    def _coding_system_prompt(self) -> str:
        return f"""You are {self.coding_name} in the Liquisto intelligence platform.

Your job is to unblock stuck research by suggesting better search queries.

When {self.name} asks you to help with a blocked task:
1. Call suggest_refined_queries(task_key) for the given task
2. Report back: "Refined queries for <key>: <query list>"

Your query suggestions will be used by {self.researcher_name} on the next research attempt.
"""

    # ------------------------------------------------------------------
    # LLM config
    # ------------------------------------------------------------------

    def _llm_config(self, role: str) -> dict[str, Any] | Literal[False]:
        model, _ = get_role_model_selection(role)
        api_key = get_openai_api_key()
        if not api_key:
            return False
        return {
            "config_list": [{"model": model, "api_key": api_key}],
            "temperature": 0.1,
        }

    # ------------------------------------------------------------------
    # Investigation plan helpers
    # ------------------------------------------------------------------

    def _domain_hypothesis(
        self,
        brief: SupervisorBrief,
        product_keywords: list[str],
        industry_hint: str,
    ) -> str:
        keywords = (
            ", ".join(product_keywords[:3]) if product_keywords else "unspecified products"
        )
        industry = industry_hint or "unspecified industry"
        return (
            f"{brief.company_name} appears to operate in {industry} "
            f"with visible goods or services including: {keywords}. "
            f"Classification and economic signals require domain investigation."
        )

    def _task_guidance(
        self,
        task_key: str,
        brief: SupervisorBrief,
        product_keywords: list[str],
        industry_hint: str,
    ) -> str:
        template = _TASK_GUIDANCE_TEMPLATES.get(
            task_key, "Investigate {task_key} for {company}."
        )
        keywords = (
            ", ".join(product_keywords[:3]) if product_keywords else brief.company_name
        )
        return template.format(
            company=brief.company_name,
            keywords=keywords,
            industry=industry_hint or "n/v",
            task_key=task_key,
        )

    # ------------------------------------------------------------------
    # Fallback package (if max_round hit before finalize_package called)
    # ------------------------------------------------------------------

    def _build_fallback_package(
        self, assignments: list[Assignment], run_state: dict[str, Any]
    ) -> dict[str, Any]:
        task_summaries = []
        accepted_points: list[str] = []
        open_questions: list[str] = []
        sources: list[dict[str, Any]] = []

        for assignment in assignments:
            report = run_state["task_results"].get(assignment.task_key)
            if report:
                final_review = self.critic.review(
                    task_key=assignment.task_key,
                    section=assignment.target_section,
                    objective=assignment.objective,
                    payload=report["payload"],
                )
                judge_result = self.judge.decide(
                    section=assignment.task_key,
                    critic_review=final_review,
                )
                task_status = judge_result["task_status"]
                judge_open_questions = judge_result.get("open_questions", [])
                accepted_points.extend(final_review.get("accepted_points", []))
                open_questions.extend(report.get("open_questions", []))
                open_questions.extend(judge_open_questions)
                sources.extend(report.get("sources", []))
                task_summaries.append(
                    {
                        "task_key": assignment.task_key,
                        "label": assignment.label,
                        "status": task_status,
                        "accepted_points": final_review.get("accepted_points", []),
                        "open_points": list(
                            dict.fromkeys(
                                final_review.get("missing_points", [])
                                + judge_open_questions
                            )
                        ),
                        "summary": report.get("objective", assignment.objective),
                    }
                )
            else:
                task_summaries.append(
                    {
                        "task_key": assignment.task_key,
                        "label": assignment.label,
                        "status": "rejected",
                        "accepted_points": [],
                        "open_points": ["Research did not complete within max_round."],
                        "summary": assignment.objective,
                    }
                )

        accepted_count = sum(1 for t in task_summaries if t.get("status") == "accepted")
        degraded_count = sum(1 for t in task_summaries if t.get("status") == "degraded")
        total_count = len(task_summaries) or 1
        if accepted_count == total_count:
            fallback_confidence = "high"
        elif accepted_count + degraded_count > 0:
            fallback_confidence = "medium"
        else:
            fallback_confidence = "low"

        return DepartmentPackage.model_validate(
            {
                "department": self.department,
                "target_section": assignments[0].target_section if assignments else "n/v",
                "summary": f"{self.department} package degraded — max_round reached before finalization.",
                "section_payload": run_state["current_payload"],
                "completed_tasks": task_summaries,
                "accepted_points": list(dict.fromkeys(accepted_points)),
                "open_questions": list(dict.fromkeys(open_questions)),
                "visual_focus": _VISUAL_FOCUS.get(self.department, []),
                "sources": sources[:12],
                "autogen_group": self.autogen_group_spec(),
                "confidence": fallback_confidence,
            }
        ).model_dump(mode="json")
