"""Department Lead / Analyst — contract-driven, execution-autonomous AG2 GroupChat.

CHG-03 / CHG-05 / CHG-06 / CHG-07 — Runtime refactor.

Architecture changes from previous version:

1.  **No Supervisor in the inner loop** (CHG-03)
    ``request_supervisor_revision`` is gone.  The Lead decides retry, coding
    support, and Judge escalation autonomously inside the department contract.
    The department interface has no ``supervisor`` parameter.

2.  **Artifact-based task execution** (CHG-05)
    ``run_research`` → ``TaskArtifact``
    ``review_research`` → ``TaskReviewArtifact``
    ``judge_decision`` → ``TaskDecisionArtifact``
    All attempts are stored, not only the latest result.

3.  **Autonomous role prompts** (CHG-06)
    The Lead prompt no longer scripts a fixed micro-sequence.  It provides
    the contract (mandatory questions, quality bar) and lets the group decide
    the internal strategy.

4.  **Finalization from stored decisions** (CHG-07)
    ``finalize_package`` assembles the package from already-recorded
    TaskDecisionArtifacts.  It never re-judges tasks that already have a
    decision.  Inline judge fallback is only used for tasks that completed
    research + review but never reached an explicit decision.

Each domain department runs as a genuine AG2 GroupChat:

    Lead (CompanyLead)
        ├── CompanyResearcher   — tool: run_research
        ├── CompanyCritic       — tool: review_research
        ├── CompanyJudge        — tool: judge_decision
        └── CompanyCodingSpecialist — tool: suggest_refined_queries

    Lead holds one own tool:
        finalize_package   — assembles the domain package, terminates the chat.

The selector (``build_department_selector``) is guardrail-only (CHG-04).
The Lead drives the internal workflow through its messages.
"""
from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Callable, Literal


def _dedup(items: list) -> list:
    """Deduplicate a list whose items may be dicts (unhashable by dict.fromkeys).

    Uses JSON serialization as a stable key so both strings and dicts are handled
    without raising 'unhashable type: dict'.
    """
    seen: set[str] = set()
    result = []
    for item in items:
        key = (
            json.dumps(item, sort_keys=True, ensure_ascii=False)
            if isinstance(item, (dict, list))
            else str(item)
        )
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result

from autogen import ConversableAgent, GroupChat, GroupChatManager, UserProxyAgent, register_function

from src.agents.coding_assistant import CodingAssistantAgent
from src.orchestration.speaker_selector import build_department_selector
from src.agents.critic import CriticAgent
from src.agents.judge import JudgeAgent
from src.agents.worker import ResearchWorker
from src.config.settings import get_openai_api_key, get_role_model_selection, MAX_TASK_RETRIES
from src.domain.intake import SupervisorBrief
from src.models.schemas import DepartmentPackage, DomainReportSegment
from src.orchestration.contracts import (
    DepartmentRunState,
    TaskArtifact,
    TaskDecisionArtifact,
    TaskReviewArtifact,
)
from src.orchestration.task_router import Assignment, DEPARTMENT_RESEARCHERS
from src.orchestration.tool_policy import resolve_allowed_tools
from src.research.extract import extract_product_keywords, infer_industry

logger = logging.getLogger(__name__)

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
    and shared DepartmentRunState.
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
        product_keywords = extract_product_keywords(
            brief.raw_homepage_excerpt, company_name=brief.company_name,
        )
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
            "speaker_selection_method": "guardrails",  # CHG-04
        }

    def run(
        self,
        *,
        brief: SupervisorBrief,
        assignments: list[Assignment],
        current_section: dict[str, Any] | None,
        memory_store=None,
        role_memory: dict[str, list[dict[str, Any]]] | None = None,
        on_message: MessageHook = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        """Build a fresh AG2 GroupChat, run the investigation, return the domain package.

        Returns:
            (section_payload, package_messages, department_package)
        """
        self._completed_package = None

        if memory_store is not None:
            memory_store.open_department_workspace(self.department)

        # CHG-05: Use explicit DepartmentRunState instead of a loose dict
        run_state = DepartmentRunState(
            department=self.department,
            current_payload=dict(current_section or {}),
        )

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

            # Track attempts
            attempt = run_state.attempts.get(task_key, 0)
            run_state.attempts[task_key] = attempt + 1

            # Skip duplicate execution when no revision was requested
            if (
                task_key in run_state.task_artifacts
                and task_key not in run_state.revision_requests
            ):
                existing = run_state.latest_artifact(task_key)
                logger.debug("run_research: task=%s already complete — skipping duplicate", task_key)
                return json.dumps(
                    {
                        "task_key": task_key,
                        "status": "already_completed",
                        "facts": existing.facts[:5] if existing else [],
                        "open_questions": existing.open_questions[:3] if existing else [],
                        "payload_keys": list(existing.payload.keys()) if existing else [],
                    },
                    ensure_ascii=False,
                )

            logger.info(
                "run_research: task=%s attempt=%d department=%s",
                task_key, run_state.attempts[task_key], self.department,
            )
            try:
                report = self.worker.run(
                    brief=brief,
                    task_key=task_key,
                    target_section=assignment.target_section,
                    objective=assignment.objective,
                    current_sections={assignment.target_section: run_state.current_payload},
                    query_overrides=run_state.query_overrides.get(task_key),
                    allowed_tools=list(assignment.allowed_tools),
                    model_name=assignment.model_name,
                    revision_request=run_state.revision_requests.get(task_key),
                    role_memory=(role_memory or {}).get(self.researcher_name, []),
                )
            except Exception as exc:
                err = {"tool": "run_research", "task_key": task_key, "error": str(exc)}
                run_state.tool_errors.append(err)
                logger.error("run_research failed: task=%s error=%s", task_key, exc)
                return json.dumps({"error": f"run_research failed: {exc}", "task_key": task_key})

            # CHG-05: record as TaskArtifact
            artifact = TaskArtifact.from_worker_report(
                report, attempt=run_state.attempts[task_key]
            )
            run_state.record_task_artifact(artifact)

            # Keep current_payload updated (for backward compat with finalize_payload assembly)
            run_state.current_payload = dict(report["payload"])
            run_state.revision_requests.pop(task_key, None)  # consumed

            if memory_store is not None:
                memory_store.ingest_worker_report(report, department=self.department)

            return json.dumps(
                {
                    "task_key": task_key,
                    "attempt": run_state.attempts[task_key],
                    "status": "research_complete",
                    "facts": artifact.facts[:5],
                    "open_questions": artifact.open_questions[:3],
                    "payload_keys": list(artifact.payload.keys()),
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
            artifact = run_state.latest_artifact(task_key)
            if not artifact:
                return json.dumps({"error": f"No research result yet for: {task_key}"})

            logger.info(
                "review_research: task=%s attempt=%d department=%s",
                task_key, artifact.attempt, self.department,
            )
            try:
                review = self.critic.review(
                    task_key=task_key,
                    section=assignment.target_section,
                    objective=assignment.objective,
                    payload=artifact.payload,
                    report=artifact.to_dict(),
                    role_memory=(role_memory or {}).get(self.critic_name, []),
                )
            except Exception as exc:
                err = {"tool": "review_research", "task_key": task_key, "error": str(exc)}
                run_state.tool_errors.append(err)
                logger.error("review_research failed: task=%s error=%s", task_key, exc)
                return json.dumps({"error": f"review_research failed: {exc}", "task_key": task_key})

            # CHG-05: record as TaskReviewArtifact
            review_artifact = TaskReviewArtifact.from_critic_review(
                review,
                task_key=task_key,
                attempt=artifact.attempt,
                reviewer=self.critic_name,
            )
            run_state.record_review_artifact(review_artifact)

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
                    "attempt": artifact.attempt,
                    "approved": review_artifact.approved,
                    "core_passed": review_artifact.core_passed,
                    "core_total": review_artifact.core_total,
                    "accepted_points": review_artifact.accepted_points,
                    "rejected_points": review_artifact.rejected_points,
                    "issues": review_artifact.issues,
                    "evidence_strength": review_artifact.evidence_strength,
                    "method_issue": review_artifact.method_issue,
                },
                ensure_ascii=False,
            )

        # CHG-03: request_supervisor_revision is REMOVED.
        # The Lead decides retry autonomously based on attempt count and review.
        # See _lead_system_prompt for the retry policy communicated to the LLM.

        def suggest_refined_queries(
            task_key: Annotated[str, "The task_key that needs better queries"],
        ) -> str:
            """Suggest refined search queries to unblock a stuck research task."""
            assignment = next((a for a in assignments if a.task_key == task_key), None)
            if not assignment:
                return json.dumps({"error": f"Unknown task_key: {task_key}"})
            review = run_state.latest_review(task_key)
            review_dict = review.to_dict() if review else {}
            logger.info(
                "suggest_refined_queries: task=%s department=%s", task_key, self.department
            )
            try:
                support = self.coding_assistant.suggest_queries(
                    section=assignment.target_section,
                    brief=brief,
                    issues=review_dict.get("issues", []),
                    review=review_dict,
                    coding_brief=review_dict.get("coding_brief"),
                )
            except Exception as exc:
                err = {"tool": "suggest_refined_queries", "task_key": task_key, "error": str(exc)}
                run_state.tool_errors.append(err)
                logger.error("suggest_refined_queries failed: task=%s error=%s", task_key, exc)
                return json.dumps({"error": f"suggest_refined_queries failed: {exc}", "task_key": task_key})

            run_state.query_overrides[task_key] = support["query_overrides"]
            run_state.record_coding_support(task_key, support["query_overrides"])

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
            review = run_state.latest_review(task_key)
            review_dict = review.to_dict() if review else {}
            attempt = run_state.attempts.get(task_key, 0)

            logger.info(
                "judge_decision: task=%s attempt=%d department=%s",
                task_key, attempt, self.department,
            )
            try:
                result = self.judge.decide(
                    section=task_key,
                    critic_review=review_dict if review_dict else None,
                    critic_issues=review_dict.get("issues", []) if review_dict else [],
                )
            except Exception as exc:
                err = {"tool": "judge_decision", "task_key": task_key, "error": str(exc)}
                run_state.tool_errors.append(err)
                result = {
                    "task_status": "degraded",
                    "reason": f"Judge failed: {exc}",
                    "open_questions": [str(exc)],
                    "confidence": "low",
                }

            # CHG-05: record as TaskDecisionArtifact
            decision = TaskDecisionArtifact.from_judge_result(
                result, task_key=task_key, attempt=attempt
            )
            run_state.record_decision_artifact(decision)

            return json.dumps(result, ensure_ascii=False)

        def finalize_package(
            summary: Annotated[
                str,
                "Full narrative summary of the completed investigation — "
                "written as a domain expert report section. Include key findings, "
                "confidence assessment, and what remains open.",
            ],
        ) -> str:
            """Assemble and submit the domain package. Terminates the group chat.

            CHG-07: assembles from stored TaskDecisionArtifacts.
            Never re-judges tasks that already have an explicit decision.
            Inline fallback is used only for tasks with research+review but no decision.
            """
            task_summaries: list[dict[str, Any]] = []
            accepted_points: list[str] = []
            open_questions: list[str] = []
            sources: list[dict[str, Any]] = []

            for assignment in assignments:
                task_key = assignment.task_key
                decision = run_state.latest_decision(task_key)
                review = run_state.latest_review(task_key)
                artifact = run_state.latest_artifact(task_key)

                if decision:
                    # Primary path (CHG-07): use stored decision — no re-judging
                    task_status = decision.task_status
                    task_accepted = review.accepted_points if review else []
                    task_open = _dedup(
                        decision.open_questions
                        + (artifact.open_questions if artifact else [])
                    )
                    task_sources = artifact.sources if artifact else []
                    task_summary = artifact.objective or assignment.objective if artifact else assignment.objective

                elif artifact and review:
                    # Fallback path: research + review exist but Lead never called judge_decision.
                    # If critic approved, accept. If rejected, degrade (one inline judge call).
                    if review.approved:
                        # Critic approved → implicit Lead-accepted decision
                        implicit_decision = TaskDecisionArtifact.lead_accepted(
                            task_key=task_key,
                            attempt=artifact.attempt,
                            review=review,
                        )
                        run_state.record_decision_artifact(implicit_decision)
                        task_status = "accepted"
                        task_accepted = review.accepted_points
                        task_open = artifact.open_questions
                    else:
                        # Critic rejected but no judge called — run inline judge
                        logger.debug(
                            "finalize_package: inline judge fallback for task=%s "
                            "(critic rejected, no judge decision stored)", task_key,
                        )
                        inline_result = self.judge.decide(
                            section=task_key,
                            critic_review=review.to_dict(),
                        )
                        inline_decision = TaskDecisionArtifact.from_judge_result(
                            inline_result, task_key=task_key, attempt=artifact.attempt
                        )
                        run_state.record_decision_artifact(inline_decision)
                        task_status = inline_result["task_status"]
                        task_accepted = review.accepted_points
                        task_open = _dedup(
                            inline_result.get("open_questions", [])
                            + artifact.open_questions
                        )
                    task_sources = artifact.sources
                    task_summary = artifact.objective or assignment.objective

                elif artifact:
                    # Research exists but no review — run critic + judge inline
                    logger.debug(
                        "finalize_package: full inline fallback (no review, no decision) "
                        "for task=%s", task_key,
                    )
                    fallback_review = self.critic.review(
                        task_key=task_key,
                        section=assignment.target_section,
                        objective=assignment.objective,
                        payload=artifact.payload,
                    )
                    inline_result = self.judge.decide(
                        section=task_key,
                        critic_review=fallback_review,
                    )
                    inline_decision = TaskDecisionArtifact.from_judge_result(
                        inline_result, task_key=task_key, attempt=artifact.attempt
                    )
                    run_state.record_decision_artifact(inline_decision)
                    task_status = inline_result["task_status"]
                    task_accepted = fallback_review.get("accepted_points", [])
                    task_open = _dedup(
                        inline_result.get("open_questions", [])
                        + artifact.open_questions
                        + fallback_review.get("missing_points", [])
                    )
                    task_sources = artifact.sources
                    task_summary = artifact.objective or assignment.objective

                else:
                    # No research at all
                    task_status = "rejected"
                    task_accepted = []
                    task_open = [f"No research result produced for {task_key}."]
                    task_sources = []
                    task_summary = assignment.objective

                accepted_points.extend(task_accepted)
                open_questions.extend(task_open)
                sources.extend(task_sources)
                task_summaries.append({
                    "task_key": task_key,
                    "label": assignment.label,
                    "status": task_status,
                    "accepted_points": task_accepted,
                    "open_points": task_open[:6],
                    "summary": task_summary,
                })

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

            # Lead-owned: classify goods for CompanyDepartment
            if self.department == "CompanyDepartment":
                run_state.current_payload["goods_classification"] = self._classify_goods(
                    run_state.current_payload
                )

            report_segment = DomainReportSegment(
                department=self.department,
                narrative_summary=summary or f"{self.department} investigation completed by {self.name}.",
                confidence=confidence,
                key_findings=_dedup(accepted_points)[:10],
                open_questions=_dedup(open_questions)[:6],
                sources=[],
            ).model_dump(mode="json")

            package = DepartmentPackage.model_validate(
                {
                    "department": self.department,
                    "target_section": assignments[0].target_section if assignments else "n/v",
                    "summary": summary or f"{self.department} domain package assembled by {self.name}.",
                    "section_payload": run_state.current_payload,
                    "completed_tasks": task_summaries,
                    "accepted_points": _dedup(accepted_points),
                    "open_questions": _dedup(open_questions),
                    "visual_focus": _VISUAL_FOCUS.get(self.department, []),
                    "sources": sources[:12],
                    "autogen_group": self.autogen_group_spec(),
                    "report_segment": report_segment,
                    "confidence": confidence,
                }
            ).model_dump(mode="json")

            # Append tool error traces as open_questions for traceability
            for err in run_state.tool_errors:
                package["open_questions"] = _dedup(
                    package.get("open_questions", [])
                    + [f"Tool error ({err['tool']}): {err['error']}"]
                )

            self._completed_package = package
            if memory_store is not None:
                memory_store.store_department_package(self.department, package)
                # CHG-02: persist the full run state (artifact history) in the run brain
                memory_store.record_department_run_state(
                    self.department, run_state.to_dict()
                )

            logger.info(
                "finalize_package: %s confidence=%s tasks=%d judge_escalations=%d coding_used=%d",
                self.department, confidence, len(task_summaries),
                len(run_state.judge_escalations), len(run_state.coding_support_used),
            )
            return "PACKAGE_READY\nTERMINATE"

        # ── Register tools with AG2 ────────────────────────────────────────
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
                "Returns approval status, core/supporting pass counts, "
                "accepted/rejected points, and issues."
            ),
        )
        # CHG-03: request_supervisor_revision is NOT registered.
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
                "Make a final quality gate decision on a task after retries are exhausted. "
                "Returns task_status (accepted|degraded|rejected), confidence, and open_questions."
            ),
        )
        register_function(
            finalize_package,
            caller=lead_ca,
            executor=executor_ca,
            name="finalize_package",
            description=(
                "Assemble and submit the completed domain package from stored task decisions. "
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
        # CHG-04: guardrail_state is the minimal dict the selector needs
        speaker_selector = build_department_selector(
            guardrail_state=run_state.guardrail_state(),
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
                "mandatory_items": len(assignments),
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
            logger.warning(
                "%s: max_round hit without finalize_package — building fallback package",
                self.department,
            )
            self._completed_package = self._build_fallback_package(assignments, run_state)
            if memory_store is not None:
                memory_store.store_department_package(
                    self.department, self._completed_package
                )
                memory_store.record_department_run_state(
                    self.department, run_state.to_dict()
                )

        if memory_store is not None:
            memory_store.append_department_conversation(self.department, package_messages)

        return run_state.current_payload, package_messages, self._completed_package

    def run_followup(
        self,
        *,
        question: str,
        context: str,
        brief: SupervisorBrief,
        memory_store=None,
        on_message: MessageHook = None,
    ) -> dict[str, Any]:
        """Run a focused mini-GroupChat to answer a specific follow-up question."""
        run_state = DepartmentRunState(department=f"{self.department}_followup")

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
            attempt = run_state.attempts.get(task_key, 0) + 1
            run_state.attempts[task_key] = attempt
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
            artifact = TaskArtifact.from_worker_report(report, attempt=attempt)
            run_state.record_task_artifact(artifact)
            if memory_store is not None:
                memory_store.ingest_worker_report(report, department=f"{self.department}_followup")
            return json.dumps({
                "task_key": task_key,
                "facts": artifact.facts[:5],
                "open_questions": artifact.open_questions[:3],
            }, ensure_ascii=False)

        def finalize_followup(
            summary: Annotated[str, "Updated findings that answer the follow-up question"],
        ) -> str:
            artifact = run_state.latest_artifact("followup_question")
            facts = artifact.facts if artifact else []
            result_holder["report_segment"] = {
                "department": self.department,
                "narrative_summary": summary,
                "confidence": "medium" if facts else "low",
                "key_findings": facts[:8],
                "open_questions": artifact.open_questions[:4] if artifact else [],
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
    # System prompts  (CHG-06: autonomous, contract-driven)
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
        mandatory_count = len(assignments)
        return f"""You are {self.name}, the Lead of the {self.department} in the Liquisto intelligence platform.

## Your contract (fixed by Supervisor)
- **Mandatory tasks**: all {mandatory_count} assigned tasks must either be answered with sufficient evidence, or explicitly documented as unresolved with a justified reason.
- **Domain hypothesis**: {domain_hypothesis}
- **Classification frame**: {classification_frame}
- **Quality bar**: accepted evidence must pass core validation rules. Weak or unsupported findings must be flagged.

## Your autonomy (owned by you, not the Supervisor)
You choose:
- the order in which you work on tasks
- whether to retry, seek coding support, or escalate to the Judge
- when to use the Critic's feedback actively rather than passively
- when to involve the Coding Specialist (query method problems)
- when to involve the Judge (genuine decision ambiguity after retries)
- how to summarise and package the results

The Supervisor sees only the contract handoff and the final package. It does NOT participate in your internal decisions.

## Your group members
- {self.researcher_name}: Runs web research. Calls run_research(task_key).
- {self.critic_name}: Reviews research quality. Calls review_research(task_key).
- {self.judge_name}: Final quality gate. Calls judge_decision(task_key). Use only when retries are exhausted.
- {self.coding_name}: Unblocks stuck searches. Calls suggest_refined_queries(task_key). Use when method/query issues remain after a retry.

## Mandatory tasks assigned to this department
{task_list}

## Department workflow protocol
For each mandatory task:
1. Tell {self.researcher_name} to call run_research(task_key) for the task.
2. Tell {self.critic_name} to call review_research(task_key).
3. Read the review result:
   - **APPROVED** (approved=true) → note the accepted points, move to the next task.
   - **REJECTED** (approved=false, attempt=1):
     - If method_issue=true → ask {self.coding_name} to suggest_refined_queries(task_key), then ask {self.researcher_name} to run_research again.
     - Otherwise → ask {self.researcher_name} to run_research again (with the rejected_points as revision context in the initiation message).
   - **REJECTED** (approved=false, attempt ≥ {MAX_TASK_RETRIES}) → ask {self.judge_name} to judge_decision(task_key). The Judge's decision is final.
4. After all tasks are complete (or explicitly unresolved with justification):
   - Call finalize_package(summary) with a full narrative domain report section.
   - Write it as a briefing-ready paragraph: key findings, confidence, what remains open.
   - The chat will end after this call.

## Rules
- Always name the next agent explicitly in your message (e.g., "{self.researcher_name}, please call run_research(task_key=...)")
- Never skip a mandatory task without documenting the justification in the summary
- A task is complete when it has an accepted decision OR a justified unresolved record
- If a task cannot be answered, write that explicitly in the summary — do not hide evidence gaps
"""

    def _researcher_system_prompt(self) -> str:
        return f"""You are {self.researcher_name} in the Liquisto intelligence platform.

Your job is to investigate the target company using web search and page fetching.

## Adaptive search behaviour
When {self.name} directs you to a task:
1. Call run_research(task_key) with the exact task_key provided.
2. If the revision context mentions specific rejected points, adjust your search strategy to target those gaps.
3. Report the result concisely: key facts found, open questions, payload coverage.

If a previous attempt was weak, vary your query framing, try different source types, or look at trade press / registries instead of just the company website.

Be factual and conservative. Never invent companies, URLs, or claims.
If evidence is weak after genuine effort, say so clearly — that is useful information.
"""

    def _critic_system_prompt(self) -> str:
        return f"""You are {self.critic_name} in the Liquisto intelligence platform.

Your job is to review research quality and provide defect-class feedback.

When {self.name} or after {self.researcher_name} presents results:
1. Call review_research(task_key) for the task that was just researched.
2. Report your findings to the group:
   - **APPROVED**: "Task <key> approved. Core rules passed: <count>/<total>. Accepted: <points>"
   - **REJECTED**: "Task <key> rejected. Core failures: <count>. Defect class: <category>. Issues: <specific issues>. Method issue: <yes/no>"

## Defect classes to identify
- **missing_core_fact**: A required field was not populated (e.g. company_name still n/v)
- **weak_evidence**: Finding present but without supporting sources
- **placeholder_remaining**: Field still contains n/v or empty default
- **list_too_short**: min_items rule failed
- **method_issue**: The search approach itself was flawed (wrong source type, query too narrow)

Do not approve weak or unsupported findings. Your feedback must be actionable.
"""

    def _judge_system_prompt(self) -> str:
        return f"""You are {self.judge_name} in the Liquisto intelligence platform.

Your job is to make final principle-based quality gate decisions on tasks that cannot be improved further.

## When you are called
{self.name} calls judge_decision(task_key) only after retries are exhausted and genuine ambiguity remains.

## Your decision principles
1. Call judge_decision(task_key) for the given task.
2. Apply three-outcome logic:
   - **accept** (all core rules passed): the evidence is sufficient despite gaps
   - **accept_degraded** (partial core): usable with documented gaps — still valuable for the report
   - **reject** (no core rules passed): evidence is insufficient to support this section
3. Report your decision: "Judge decision for <key>: <outcome> — <principle-based reason>"

Your decisions are final and traceable. Accept that some evidence gaps will remain — document them clearly.
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

Your job is to unblock stuck research by suggesting better search queries and methods.

When {self.name} asks you to help with a blocked task:
1. Call suggest_refined_queries(task_key) for the given task.
2. Report back: "Refined queries for <key>: <query list>"

## Method tactics
- If the direct company search failed: try industry registry, trade publication, or filing sources.
- If broad queries returned noise: add structural operators (site:, filetype:, "exact phrase").
- If the company name is ambiguous: add location, industry, or legal form terms.
- Suggest 3-5 diverse queries that target the specific defect class the Critic identified.

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

    def _classify_goods(self, payload: dict[str, Any]) -> str:
        """Classify company goods as made/distributed/held_in_stock/mixed/unclear."""
        scope_texts = payload.get("product_asset_scope", [])
        services_texts = payload.get("products_and_services", [])
        description = str(payload.get("description", ""))
        all_text = " ".join(
            [description]
            + [str(s) for s in scope_texts]
            + [str(s) for s in services_texts]
        ).lower()

        made_signals = any(kw in all_text for kw in (
            "manufactur", "produc", "assembl", " made ", "fabricat", "machining",
        ))
        distributed_signals = any(kw in all_text for kw in (
            "distribut", "wholesal", "trading", "trade", "resell", "import", "export",
        ))
        stock_signals = any(kw in all_text for kw in (
            "held-in-stock", "held in stock", "inventory", "excess stock", "surplus",
            "warehouse", "overstock", "stock",
        ))

        active = [label for flag, label in [
            (made_signals, "manufacturer"),
            (distributed_signals, "distributor"),
            (stock_signals, "held_in_stock"),
        ] if flag]

        if len(active) == 1:
            return active[0]
        if len(active) > 1:
            return "mixed"
        return "unclear"

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
        self, assignments: list[Assignment], run_state: DepartmentRunState
    ) -> dict[str, Any]:
        """Build a degraded package using whatever artifacts were recorded.

        CHG-07: Uses the same decision-artifact-first logic as finalize_package.
        """
        task_summaries = []
        accepted_points: list[str] = []
        open_questions: list[str] = []
        sources: list[dict[str, Any]] = []

        for assignment in assignments:
            task_key = assignment.task_key
            decision = run_state.latest_decision(task_key)
            review = run_state.latest_review(task_key)
            artifact = run_state.latest_artifact(task_key)

            if decision:
                task_status = decision.task_status
                task_accepted = review.accepted_points if review else []
                task_open = decision.open_questions + (artifact.open_questions if artifact else [])
                task_sources = artifact.sources if artifact else []
            elif artifact:
                fallback_review = self.critic.review(
                    task_key=task_key,
                    section=assignment.target_section,
                    objective=assignment.objective,
                    payload=artifact.payload,
                )
                judge_result = self.judge.decide(
                    section=task_key,
                    critic_review=fallback_review,
                )
                task_status = judge_result["task_status"]
                task_accepted = fallback_review.get("accepted_points", [])
                task_open = _dedup(
                    judge_result.get("open_questions", [])
                    + artifact.open_questions
                    + fallback_review.get("missing_points", [])
                )
                task_sources = artifact.sources
            else:
                task_status = "rejected"
                task_accepted = []
                task_open = ["Research did not complete within max_round."]
                task_sources = []

            accepted_points.extend(task_accepted)
            open_questions.extend(task_open)
            sources.extend(task_sources)
            task_summaries.append({
                "task_key": task_key,
                "label": assignment.label,
                "status": task_status,
                "accepted_points": task_accepted,
                "open_points": task_open[:6],
                "summary": assignment.objective,
            })

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
                "section_payload": run_state.current_payload,
                "completed_tasks": task_summaries,
                "accepted_points": _dedup(accepted_points),
                "open_questions": _dedup(open_questions),
                "visual_focus": _VISUAL_FOCUS.get(self.department, []),
                "sources": sources[:12],
                "autogen_group": self.autogen_group_spec(),
                "confidence": fallback_confidence,
            }
        ).model_dump(mode="json")
