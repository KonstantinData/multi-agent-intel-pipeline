# ruff: noqa: E402
"""Department Lead / Analyst — contract-driven, execution-autonomous AG2 GroupChat.

Departments are **question-coverage contributors**, not final-briefing owners.
Their primary outputs are evidence packets, gap candidates, and answer-matrix
updates for mapped meeting questions.  Narrative summaries exist for human
readability but do not drive closure or readiness logic.

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

import html
import json
import logging
import re
from collections.abc import Callable
from typing import Annotated, Any, Literal

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _safe_prompt_text(value: Any) -> str:
    """Neutralize untrusted text before embedding it in prompt/HTML-like traces."""
    text = _CONTROL_CHARS_RE.sub("", str(value or ""))
    return html.escape(text, quote=True)


def _safe_output_value(value: Any) -> Any:
    """HTML-encode strings in dynamic package output while preserving shape."""
    if isinstance(value, str):
        return _safe_prompt_text(value)
    if isinstance(value, list):
        return [_safe_output_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _safe_output_value(item) for key, item in value.items()}
    return value


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


def _dedup_model_dump(items: list[Any]) -> list[dict[str, Any]]:
    """Deduplicate Pydantic-like objects by their JSON representation."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        payload = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        key = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            out.append(payload)
    return out

from autogen import ConversableAgent, GroupChat, GroupChatManager, UserProxyAgent, register_function

from src.agents.coding_assistant import CodingAssistantAgent
from src.agents.critic import CriticAgent
from src.agents.judge import JudgeAgent
from src.agents.worker import ResearchWorker
from src.config.settings import (
    MAX_TASK_RETRIES,
    get_openai_api_key,
    get_role_model_selection,
    resolve_model_temperature,
)
from src.domain.intake import SupervisorBrief
from src.models.meeting_ready import AnswerMatrixUpdate, EvidencePacket, GapCandidate
from src.models.schemas import DepartmentPackage, DomainReportSegment
from src.orchestration.contract_validation import validate_payload_against_task_schema
from src.orchestration.contracts import (
    DepartmentPolicy,
    DepartmentRunState,
    TaskArtifact,
    TaskDecisionArtifact,
    TaskReviewArtifact,
)
from src.orchestration.department_knowledge import (
    evaluate_department_policy_gate,
    load_department_policy,
    load_department_source_profile,
)
from src.orchestration.followup_config import FOLLOWUP_TARGET_SECTION_BY_DEPARTMENT
from src.orchestration.speaker_selector import build_department_selector
from src.orchestration.task_router import DEPARTMENT_RESEARCHERS, Assignment
from src.orchestration.tool_policy import resolve_allowed_tools
from src.research.extract import extract_product_keywords, infer_industry
from src.research.query_resolver import validate_query_overrides

logger = logging.getLogger(__name__)

_FOLLOWUP_TARGET_SECTION_BY_DEPARTMENT = FOLLOWUP_TARGET_SECTION_BY_DEPARTMENT


_validate_payload_against_task_schema = validate_payload_against_task_schema

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
        "Primary-source financial and working-capital facts",
        "Made vs distributed vs held-in-stock classification",
        "Economic pressure, inventory stress, and strategic event signals",
    ],
    "MarketDepartment": [
        "Demand and supply pressure summary",
        "Overcapacity and slowdown signals",
        "Inventory-relevant market risks",
    ],
    "BuyerDepartment": [
        "Peer company map",
        "Buyer and secondary-market pathways",
        "Redeployment and aftermarket fit",
    ],
    "ContactDepartment": [
        "Decision-maker map at the target company and prioritized buyer firms",
        "Seniority and function of identified contacts",
        "Outreach angles per contact",
    ],
}

_CLASSIFICATION_FRAME = {
    "CompanyDepartment": "made_vs_distributed_vs_held_in_stock",
    "MarketDepartment": "demand_supply_capacity_inventory_pressure",
    "BuyerDepartment": "peers_buyers_redeployment_aftermarket",
    "ContactDepartment": "decision_makers_by_function_and_seniority",
}

_INVESTIGATION_FOCUS = {
    "CompanyDepartment": [
        "Classify the company as manufacturer, distributor, or mixed model",
        "Extract primary-source balance-sheet, inventory, and working-capital facts",
        "Identify visible goods, materials, spare parts, and inventory positions",
        "Assess economic pressure, commercial situation signals, and strategic events",
    ],
    "MarketDepartment": [
        "Define market hypotheses and assess demand / supply pressure",
        "Surface overcapacity, slowdown, and excess-stock indicators",
        "Ground the excess-inventory thesis in external market evidence",
    ],
    "BuyerDepartment": [
        "Map peer and competitor companies",
        "Identify plausible downstream buyers and secondary-market paths",
        "Assess monetization and redeployment options",
    ],
    "ContactDepartment": [
        "Identify publicly visible decision-makers at the target company",
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
    "target_company_contacts": (
        "Search for publicly visible leaders at {company} itself. Focus on CEO/CFO, procurement, "
        "operations, aftermarket, divisional leads, and roles tied to inventory, working capital, "
        "restructuring, or portfolio changes."
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
    "financial_deep_dive": (
        "Extract primary-source financial facts for {company}: latest annual-report figures, inventory positions, "
        "write-downs, working capital, debt, and one-off effects. Prefer annual reports, investor presentations, "
        "and audited statements."
    ),
    "product_asset_scope": (
        "Classify the visible product and asset scope: made vs distributed vs held-in-stock. "
        "Keywords to anchor on: {keywords}. Identify which are commercially movable."
    ),
    "transaction_event_intelligence": (
        "Identify strategic events for {company}: divestitures, carve-outs, JVs, restructurings, program terminations, "
        "and regulatory/accounting disclosures that could change inventory urgency or meeting angle."
    ),
    "market_situation": (
        "Assess demand/supply dynamics for {industry}. Surface key trends, capacity signals, "
        "and market pressure relevant to {company}."
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
        self.department_policy: DepartmentPolicy = load_department_policy(department)
        self.source_profile: dict[str, Any] = load_department_source_profile(department)

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
            "source_priority": list(self.source_profile.get("source_priority", [])),
            "recommended_sources": [
                {
                    "name": str(item.get("name", "n/v")),
                    "priority": str(item.get("priority", "secondary")),
                    "evidence_type": str(item.get("evidence_type", "indicative")),
                }
                for item in (self.source_profile.get("sources", []) or [])
                if isinstance(item, dict)
            ][:8],
            "policy_required_fields": list(self.department_policy.required_fields),
            "policy_min_evidence_rules": dict(self.department_policy.min_evidence_rules),
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
        current_sections: dict[str, Any] | None = None,
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
            llm_config=self._llm_config(self.name),
        )
        blocked_finalize_attempts = 0

        # ── Tool closures ──────────────────────────────────────────────────

        def run_research(
            task_key: Annotated[str, "The task_key to investigate"],
        ) -> str:
            """Run web research for the given task_key. Returns a research summary."""
            assignment = next((a for a in assignments if a.task_key == task_key), None)
            if not assignment:
                return json.dumps({"error": f"Unknown task_key: {task_key}"})

            # F4/Patch 1: Dependency guard — check before worker invocation.
            # Only check INTRA-department dependencies. Cross-department deps
            # are guaranteed by the phase architecture (parallel/sequential)
            # and cannot be resolved from the local DepartmentRunState.
            local_task_keys = {a.task_key for a in assignments}
            for dep_key in assignment.depends_on:
                if dep_key not in local_task_keys:
                    # Cross-department dependency — skip, handled by phase architecture
                    continue
                if not run_state.is_dependency_satisfied(dep_key):
                    attempt = run_state.attempts.get(task_key, 0) + 1
                    run_state.attempts[task_key] = attempt
                    blocked_artifact = TaskArtifact(
                        task_key=task_key,
                        attempt=attempt,
                        worker=self.researcher_name,
                        facts=[],
                        open_questions=[f"Blocked: dependency {dep_key} not satisfied"],
                    )
                    run_state.record_task_artifact(blocked_artifact)
                    blocked_decision = TaskDecisionArtifact(
                        task_key=task_key,
                        attempt=attempt,
                        outcome="blocked_by_dependency",
                        task_status="blocked",
                        decided_by="runtime",
                        reason=f"Dependency {dep_key} not satisfied",
                    )
                    run_state.record_decision_artifact(blocked_decision)
                    logger.info(
                        "run_research: task=%s blocked by dependency %s",
                        task_key, dep_key,
                    )
                    return json.dumps({
                        "task_key": task_key,
                        "status": "blocked_by_dependency",
                        "blocked_by": dep_key,
                    }, ensure_ascii=False)

            # Skip duplicate execution when no revision was requested.
            # Exception: blocked_by_dependency artifacts are NOT real completions —
            # if the dependency is now satisfied, the task must re-run.
            current_attempt = run_state.attempts.get(task_key, 0)
            if (
                task_key in run_state.task_artifacts
                and task_key not in run_state.revision_requests
            ):
                latest_decision = run_state.latest_decision(task_key)
                latest_review = run_state.latest_review(task_key)
                was_blocked = (
                    latest_decision is not None
                    and latest_decision.outcome == "blocked_by_dependency"
                )
                needs_retry = latest_review is not None and not latest_review.approved
                if was_blocked:
                    # Re-check: if dependency is now satisfied, clear the block and re-run
                    all_deps_ok = all(
                        run_state.is_dependency_satisfied(dep_key)
                        for dep_key in assignment.depends_on
                    )
                    if all_deps_ok:
                        logger.info(
                            "run_research: task=%s was blocked but dependencies now satisfied — re-running",
                            task_key,
                        )
                        # Fall through to actual execution below
                    else:
                        # Still blocked
                        existing = run_state.latest_artifact(task_key)
                        return json.dumps(
                            {
                                "task_key": task_key,
                                "status": "still_blocked",
                                "facts": [],
                                "open_questions": existing.open_questions[:3] if existing else [],
                            },
                            ensure_ascii=False,
                        )
                elif needs_retry:
                    if current_attempt >= MAX_TASK_RETRIES:
                        decision = TaskDecisionArtifact(
                            task_key=task_key,
                            attempt=current_attempt,
                            outcome="closed_unresolved",
                            task_status="degraded",
                            decided_by="runtime",
                            confidence="low",
                            open_questions=list(latest_review.missing_points or latest_review.issues or latest_review.rejected_points),
                            reason=f"Retry limit reached ({MAX_TASK_RETRIES}); research closed unresolved.",
                        )
                        run_state.record_decision_artifact(decision)
                        return json.dumps(
                            {
                                "task_key": task_key,
                                "status": "retry_limit_reached",
                                "next_required_action": f"judge_decision(task_key='{task_key}')",
                                "open_questions": decision.open_questions[:5],
                            },
                            ensure_ascii=False,
                        )
                    logger.info(
                        "run_research: task=%s has rejected latest review — allowing retry",
                        task_key,
                    )
                else:
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

            run_state.attempts[task_key] = current_attempt + 1
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
                    current_sections={
                        **(current_sections or {}),
                        assignment.target_section: run_state.current_payload,
                    },
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

            # F4/Patch 2: Validate payload_updates against task-specific schema
            raw_updates = report.get("payload", {})
            violations = _validate_payload_against_task_schema(
                assignment.output_schema_key, raw_updates,
            )
            if violations:
                artifact.contract_violations = violations
                if all(v.severity == "high" for v in violations):
                    artifact.needs_contract_review = True
                logger.info(
                    "Contract violations for task=%s: %d (needs_review=%s)",
                    task_key, len(violations), artifact.needs_contract_review,
                )

            run_state.record_task_artifact(artifact)

            # P1-4: Payload loss guard — warn if worker returned fewer fields
            # than already existed, then merge defensively.
            new_payload = dict(report["payload"])
            prev_keys = set(run_state.current_payload.keys()) - {"sources"}
            new_keys = set(new_payload.keys()) - {"sources"}
            lost_keys = prev_keys - new_keys
            if lost_keys:
                non_default_lost = {
                    k for k in lost_keys
                    if run_state.current_payload.get(k) not in (None, "", "n/v", [])
                }
                if non_default_lost:
                    logger.warning(
                        "Payload loss guard: task=%s lost non-default keys %s — preserving previous values",
                        task_key, non_default_lost,
                    )
                    for k in non_default_lost:
                        new_payload.setdefault(k, run_state.current_payload[k])
            run_state.current_payload = new_payload
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
                    task_key=task_key,
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

            try:
                validated_overrides = validate_query_overrides(support.get("query_overrides", []))
            except (KeyError, ValueError) as exc:
                err = {"tool": "suggest_refined_queries", "task_key": task_key, "error": str(exc)}
                run_state.tool_errors.append(err)
                return json.dumps(
                    {"error": f"invalid query_overrides: {exc}", "task_key": task_key},
                    ensure_ascii=False,
                )

            run_state.query_overrides[task_key] = validated_overrides
            run_state.record_coding_support(task_key, validated_overrides)
            run_state.strategy_changes.append({
                "task_key": task_key,
                "attempt": run_state.attempts.get(task_key, 0),
                "agent": self.coding_name,
                "reason": "coding_specialist_query_override",
                "review_issue": list(review_dict.get("issues", []))[:5],
                "query_override_count": len(validated_overrides),
            })

            return json.dumps(
                {
                    "task_key": task_key,
                    "query_overrides": validated_overrides,
                    "summary": support["summary"],
                },
                ensure_ascii=False,
            )

        def judge_decision(
            task_key: Annotated[str, "The task_key to decide on"],
        ) -> str:
            """Make a final edge-case decision when retries are exhausted."""
            assignment = next((a for a in assignments if a.task_key == task_key), None)
            if not assignment:
                return json.dumps({
                    "error": f"Unknown task_key: {task_key}",
                    "decision": "closed_unresolved",
                    "task_status": "degraded",
                    "confidence": "low",
                    "open_questions": [f"Unknown task_key: {task_key}"],
                }, ensure_ascii=False)

            artifact = run_state.latest_artifact(task_key)
            if artifact is None:
                attempt = run_state.attempts.get(task_key, 0)
                result = {
                    "decision": "closed_unresolved",
                    "task_status": "degraded",
                    "confidence": "low",
                    "reason": "Judge cannot accept a task before a TaskArtifact exists.",
                    "open_questions": [f"Run run_research(task_key='{task_key}') before judge_decision."],
                }
                run_state.record_decision_artifact(
                    TaskDecisionArtifact.from_judge_result(
                        result, task_key=task_key, attempt=attempt
                    )
                )
                return json.dumps(result, ensure_ascii=False)

            review = run_state.latest_review(task_key)
            if review is None:
                review = TaskReviewArtifact(
                    task_key=task_key,
                    attempt=artifact.attempt,
                    approved=False,
                    reviewer="runtime_fallback",
                    issues=["No Critic review existed before judge_decision."],
                    missing_points=list(artifact.open_questions),
                    evidence_strength="weak",
                    feedback_to_worker=[
                        "Judge fallback review generated because no Critic review was stored."
                    ],
                )
                run_state.record_review_artifact(review)
            review_dict = review.to_dict()
            attempt = artifact.attempt

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
                    "decision": "closed_unresolved",
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
            nonlocal blocked_finalize_attempts
            incomplete_tasks = [
                assignment.task_key
                for assignment in assignments
                if run_state.latest_artifact(assignment.task_key) is None
                and run_state.latest_decision(assignment.task_key) is None
            ]
            if incomplete_tasks:
                blocked_finalize_attempts += 1
                logger.warning(
                    "finalize_package blocked: department=%s incomplete_tasks=%s attempt=%d",
                    self.department,
                    incomplete_tasks,
                    blocked_finalize_attempts,
                )
                return json.dumps(
                    {
                        "error": "Cannot finalize package before all assigned tasks have at least one research result.",
                        "incomplete_tasks": incomplete_tasks,
                        "next_required_task": incomplete_tasks[0],
                        "next_required_action": f"run_research(task_key='{incomplete_tasks[0]}')",
                    },
                    ensure_ascii=False,
                )

            task_summaries: list[dict[str, Any]] = []
            accepted_points: list[str] = []
            open_questions: list[str] = []
            sources: list[dict[str, Any]] = []
            evidence_packages: list[EvidencePacket] = []
            gap_candidates: list[GapCandidate] = []
            answer_matrix_updates: list[AnswerMatrixUpdate] = []

            for assignment in assignments:
                task_key = assignment.task_key
                decision = run_state.latest_decision(task_key)
                review = run_state.latest_review(task_key)
                artifact = run_state.latest_artifact(task_key)

                # F4/Patch 4: surface contract violations in package open_questions
                if artifact and artifact.contract_violations:
                    high_count = sum(1 for v in artifact.contract_violations if v.severity == "high")
                    if high_count:
                        open_questions.append(
                            f"Contract violation in {task_key}: "
                            f"{high_count} high-severity schema mismatches"
                        )

                if decision and not artifact:
                    task_status = "degraded"
                    task_accepted = []
                    task_open = _dedup(
                        decision.open_questions
                        + [f"Decision for {task_key} ignored as accepted evidence because no TaskArtifact exists."]
                    )
                    task_sources = []
                    task_summary = assignment.objective
                elif decision:
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
                    # P1-1: If artifact has needs_contract_review, force Judge escalation
                    # even if Critic approved — contract violations override Critic approval.
                    if artifact.needs_contract_review and not review.approved:
                        logger.debug(
                            "finalize_package: contract review escalation for task=%s",
                            task_key,
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
                    elif artifact.needs_contract_review and review.approved:
                        # Critic approved but contract violations exist — degrade to Judge
                        logger.debug(
                            "finalize_package: contract review override for approved task=%s",
                            task_key,
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
                    elif review.approved:
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
                    # No research at all — F7: closed_unresolved, not rejected
                    task_status = "degraded"
                    task_accepted = []
                    task_open = [f"No research result produced for {task_key}."]
                    task_sources = []
                    task_summary = assignment.objective

                accepted_points.extend(task_accepted)
                open_questions.extend(task_open)
                sources.extend(task_sources)
                task_evidence = [
                    EvidencePacket.model_validate(item)
                    for item in (artifact.evidence_packages if artifact else [])
                ]
                evidence_packages.extend(task_evidence)
                gap_candidates.extend(
                    self._build_gap_candidates_for_task(
                        department=self.department,
                        assignment=assignment,
                        task_status=task_status,
                        task_open=task_open,
                        evidence_packages=task_evidence,
                    )
                )
                answer_matrix_updates.extend(
                    self._build_answer_matrix_updates_for_task(
                        assignment=assignment,
                        task_status=task_status,
                        task_accepted=task_accepted,
                        task_open=task_open,
                        evidence_packages=task_evidence,
                    )
                )
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
            safe_department = _safe_prompt_text(self.department)
            safe_lead_name = _safe_prompt_text(self.name)
            safe_summary = (
                _safe_prompt_text(summary)
                if summary
                else f"{safe_department} investigation completed by {safe_lead_name}."
            )
            safe_package_summary = (
                _safe_prompt_text(summary)
                if summary
                else f"{safe_department} domain package assembled by {safe_lead_name}."
            )
            safe_accepted_points = _safe_output_value(_dedup(accepted_points))
            safe_open_questions = _safe_output_value(_dedup(open_questions))
            safe_task_summaries = _safe_output_value(task_summaries)
            safe_sources = _safe_output_value(sources[:12])

            # Lead-owned: classify goods for CompanyDepartment
            if self.department == "CompanyDepartment":
                run_state.current_payload["goods_classification"] = self._classify_goods(
                    run_state.current_payload
                )
                # RF3-1 Fix C: safety net for product_asset_scope in finalize_package path too
                if not run_state.current_payload.get("product_asset_scope"):
                    existing_products = run_state.current_payload.get("products_and_services", [])
                    if existing_products:
                        run_state.current_payload["product_asset_scope"] = [
                            f"{p} \u2014 classification pending" for p in existing_products[:6]
                        ]

            report_segment = DomainReportSegment(
                department=safe_department,
                narrative_summary=safe_summary,
                confidence=confidence,
                key_findings=safe_accepted_points[:10],
                open_questions=safe_open_questions[:6],
                sources=[],
            ).model_dump(mode="json")

            package = DepartmentPackage.model_validate(
                {
                    "department": safe_department,
                    "target_section": _safe_prompt_text(assignments[0].target_section if assignments else "n/v"),
                    "summary": safe_package_summary,
                    "section_payload": _safe_output_value(run_state.current_payload),
                    "completed_tasks": safe_task_summaries,
                    "accepted_points": safe_accepted_points,
                    "open_questions": safe_open_questions,
                    "visual_focus": _safe_output_value(_VISUAL_FOCUS.get(self.department, [])),
                    "sources": safe_sources,
                    "autogen_group": _safe_output_value(self.autogen_group_spec()),
                    "report_segment": report_segment,
                    "confidence": confidence,
                    "evidence_packages": _dedup_model_dump(evidence_packages),
                    "gap_candidates": _dedup_model_dump(gap_candidates),
                    "answer_matrix_updates": _dedup_model_dump(answer_matrix_updates),
                }
            ).model_dump(mode="json")

            policy_gate = evaluate_department_policy_gate(
                department=self.department,
                policy=self.department_policy,
                section_payload=run_state.current_payload,
                completed_tasks=task_summaries,
                sources=sources,
                open_questions=_dedup(open_questions),
            )
            package["department_policy"] = self.department_policy.to_dict()
            package["policy_gate"] = policy_gate
            if not policy_gate.get("passed", True):
                gate_notes = [
                    str(item.get("reason", "")).strip()
                    for item in policy_gate.get("blockers", [])
                    if isinstance(item, dict) and str(item.get("reason", "")).strip()
                ]
                package["open_questions"] = _dedup(
                    list(package.get("open_questions", [])) + gate_notes[:6]
                )

            # Append tool error traces as open_questions for traceability
            for err in run_state.tool_errors:
                package["open_questions"] = _dedup(
                    package.get("open_questions", [])
                    + [f"Tool error ({err['tool']}): {err['error']}"]
                )

            self._completed_package = package
            run_state.evidence_packages = [
                EvidencePacket.model_validate(item)
                for item in package.get("evidence_packages", [])
            ]
            run_state.gap_candidates = [
                GapCandidate.model_validate(item)
                for item in package.get("gap_candidates", [])
            ]
            run_state.answer_matrix_updates = [
                AnswerMatrixUpdate.model_validate(item)
                for item in package.get("answer_matrix_updates", [])
            ]
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
                "Returns KB-owned query variant tokens for the Researcher."
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
        try:
            lead_ca.initiate_chat(manager, message=initiation_message)
        finally:
            self.worker.close()

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
        followup_target_section = _FOLLOWUP_TARGET_SECTION_BY_DEPARTMENT.get(
            self.department, "company_profile"
        )

        followup_assignment = Assignment(
            task_key="followup_question",
            assignee=self.researcher_name,
            target_section=followup_target_section,
            label="Follow-up investigation",
            objective=f"{question}. Context: {context}",
            model_name=self.model_name,
            allowed_tools=("search", "page_fetch", "llm_structured"),
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
        blocked_finalize_attempts = 0

        def run_research(task_key: Annotated[str, "task key"]) -> str:
            attempt = run_state.attempts.get(task_key, 0) + 1
            run_state.attempts[task_key] = attempt
            report = self.worker.run(
                brief=brief,
                task_key=task_key,
                target_section=followup_assignment.target_section,
                objective=followup_assignment.objective,
                current_sections={
                    followup_assignment.target_section: run_state.current_payload
                },
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

        def review_research(task_key: Annotated[str, "task key"]) -> str:
            artifact = run_state.latest_artifact(task_key)
            if artifact is None:
                return json.dumps(
                    {
                        "error": f"No research artifact found for task '{task_key}'.",
                        "next_required_action": f"Run run_research(task_key='{task_key}') first.",
                    },
                    ensure_ascii=False,
                )
            review_dict = self.critic.review(
                task_key=task_key,
                section=followup_assignment.target_section,
                objective=followup_assignment.objective,
                payload=artifact.payload,
                report=artifact.to_dict(),
            )
            review = TaskReviewArtifact.from_critic_review(
                review_dict,
                task_key=task_key,
                attempt=artifact.attempt,
                reviewer=self.critic_name,
            )
            run_state.record_review_artifact(review)
            return json.dumps(
                {
                    "task_key": task_key,
                    "approved": review.approved,
                    "issues": review.issues[:4],
                },
                ensure_ascii=False,
            )

        def finalize_followup(
            summary: Annotated[str, "Updated findings that answer the follow-up question"],
        ) -> str:
            nonlocal blocked_finalize_attempts
            artifact = run_state.latest_artifact("followup_question")
            review = run_state.latest_review("followup_question")
            if artifact is None:
                blocked_finalize_attempts += 1
                if blocked_finalize_attempts >= 2:
                    safe_question = _safe_prompt_text(question)
                    result_holder["report_segment"] = {
                        "department": _safe_prompt_text(self.department),
                        "narrative_summary": f"Follow-up for '{safe_question}' remains unresolved after repeated finalize attempts without evidence.",
                        "confidence": "low",
                        "key_findings": [],
                        "open_questions": [safe_question],
                        "sources": [],
                    }
                    return "FOLLOWUP_READY\nTERMINATE"
                return json.dumps(
                    {
                        "error": "Cannot finalize follow-up before running research.",
                        "next_required_action": "Call run_research(task_key='followup_question').",
                    },
                    ensure_ascii=False,
                )
            if review is None:
                blocked_finalize_attempts += 1
                if blocked_finalize_attempts >= 2:
                    result_holder["report_segment"] = {
                        "department": _safe_prompt_text(self.department),
                        "narrative_summary": _safe_prompt_text(summary),
                        "confidence": "low",
                        "key_findings": _safe_output_value(artifact.facts[:6]),
                        "open_questions": _safe_output_value(artifact.open_questions[:4]),
                        "sources": _safe_output_value(artifact.sources[:8]),
                    }
                    return "FOLLOWUP_READY\nTERMINATE"
                return json.dumps(
                    {
                        "error": "Cannot finalize follow-up before critic review.",
                        "next_required_action": "Call review_research(task_key='followup_question').",
                    },
                    ensure_ascii=False,
                )
            facts = artifact.facts if artifact else []
            result_holder["report_segment"] = {
                "department": _safe_prompt_text(self.department),
                "narrative_summary": _safe_prompt_text(summary),
                "confidence": "medium" if facts and review.approved else "low",
                "key_findings": _safe_output_value(facts[:8]),
                "open_questions": _safe_output_value(artifact.open_questions[:4] if artifact else []),
                "sources": _safe_output_value(artifact.sources[:8] if artifact else []),
            }
            return "FOLLOWUP_READY\nTERMINATE"

        register_function(run_research, caller=researcher_ca, executor=researcher_ca,
                          name="run_research", description="Run research for the follow-up question.")
        register_function(review_research, caller=critic_ca, executor=critic_ca,
                          name="review_research", description="Review follow-up research quality.")
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
        try:
            lead_ca.initiate_chat(
                manager,
                message=json.dumps({
                    "status": "followup_started",
                    "question": question,
                    "context": context,
                    "task_key": "followup_question",
                }, ensure_ascii=False),
            )
        finally:
            self.worker.close()

        for msg in groupchat.messages:
            if on_message:
                on_message({
                    "agent": msg.get("name") or "unknown",
                    "content": str(msg.get("content") or ""),
                    "type": "followup_message",
                })

        return result_holder if result_holder else {
            "report_segment": {
                "department": _safe_prompt_text(self.department),
                "narrative_summary": f"Follow-up for '{_safe_prompt_text(question)}' could not be completed.",
                "confidence": "low",
                "key_findings": [],
                "open_questions": [_safe_prompt_text(question)],
                "sources": [],
            }
        }

    # ------------------------------------------------------------------
    # System prompts  (CHG-06: autonomous, contract-driven)
    # ------------------------------------------------------------------

    def _lead_system_prompt(
        self, investigation_plan: dict[str, Any], assignments: list[Assignment]
    ) -> str:
        _e = _safe_prompt_text
        s_name = _e(self.name)
        s_dept = _e(self.department)
        s_researcher = _e(self.researcher_name)
        s_critic = _e(self.critic_name)
        s_judge = _e(self.judge_name)
        s_coding = _e(self.coding_name)
        task_list = "\n".join(
            f"  {i + 1}. {_e(a.task_key)} — {_e(a.label)}\n"
            f"     Guidance: {_e(str(t['lead_guidance']))}"
            for i, (a, t) in enumerate(
                zip(assignments, investigation_plan["task_sequence"], strict=False)
            )
        )
        domain_hypothesis = _e(str(investigation_plan.get("domain_hypothesis", "")))
        classification_frame = _e(str(investigation_plan.get("classification_frame", "")))
        mandatory_count = len(assignments)
        source_priority = _e(", ".join(investigation_plan.get("source_priority", [])) or "n/v")
        recommended_source_lines = "\n".join(
            f"- {_e(str(item.get('name', 'n/v')))} [{_e(str(item.get('priority', 'secondary')))}]"
            for item in investigation_plan.get("recommended_sources", [])[:6]
        ) or "- n/v"
        required_field_lines = "\n".join(
            f"- {_e(str(field_name))}"
            for field_name in investigation_plan.get("policy_required_fields", [])[:8]
        ) or "- n/v"
        return f"""You are {s_name}, the Lead of the {s_dept} in the Liquisto intelligence platform.

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

## Source knowledge base (guidance only, not mandatory)
- Recommended source priority: {source_priority}
- Suggested free sources:
{recommended_source_lines}
- You may use any additional source if it improves evidence quality.
- No fixed dialog script is imposed by this guidance.

## Acceptance gate (checked at finalize only)
- Required output fields:
{required_field_lines}
- Minimum evidence rules are checked on package finalization, not per turn.
- If public information is exhausted, document the gap explicitly (for contacts: "keine freien Quellen").

## Your group members
- {s_researcher}: Runs web research. Calls run_research(task_key).
- {s_critic}: Reviews research quality. Calls review_research(task_key).
- {s_judge}: Final quality gate. Calls judge_decision(task_key). Use only when retries are exhausted.
- {s_coding}: Unblocks stuck searches. Calls suggest_refined_queries(task_key). Use when method/query issues remain after a retry.

## Mandatory tasks assigned to this department
{task_list}

## Department workflow protocol
For each mandatory task:
1. Tell {s_researcher} to call run_research(task_key) for the task.
2. Tell {s_critic} to call review_research(task_key).
3. Read the review result carefully — distinguish between CORE and SUPPORTING failures:
   - **APPROVED** (approved=true) → note the accepted points, move to the next task.
   - **REJECTED with core failures** (approved=false AND core_passed < core_total, attempt < {MAX_TASK_RETRIES}):
     - If method_issue=true → ask {s_coding} to suggest_refined_queries(task_key), then ask {s_researcher} to run_research again.
     - Otherwise → ask {s_researcher} to run_research again (with the rejected_points as revision context).
   - **REJECTED with only supporting failures** (approved=false BUT core_passed == core_total) → do NOT retry. Accept the task with documented gaps and move to the next task. Supporting gaps are expected and do not justify consuming retry budget.
   - **REJECTED** (approved=false, attempt ≥ {MAX_TASK_RETRIES}) → ask {s_judge} to judge_decision(task_key). The Judge's decision is final.
4. After all tasks are complete (or explicitly unresolved with justification):
   - Call finalize_package(summary) with a full narrative domain report section.
   - Write it as a briefing-ready paragraph: key findings, confidence, what remains open.
   - The chat will end after this call.

## CRITICAL: Budget discipline
- You have {mandatory_count} tasks and a limited round budget. Do NOT spend more than 2 retries on any single task.
- If a task passes all core rules but fails supporting rules, ACCEPT IT and move on.
- Completing all tasks with gaps is better than completing fewer tasks perfectly.
- You MUST call run_research for EVERY mandatory task before calling finalize_package. Skipping a task entirely is NOT acceptable — even a single research attempt with gaps is far more valuable than no attempt at all.
- Do NOT call finalize_package until you have started ALL {mandatory_count} tasks.

## Rules
- Always name the next agent explicitly in your message (e.g., "{s_researcher}, please call run_research(task_key=...)")
- Never skip a mandatory task without documenting the justification in the summary
- A task is complete when it has an accepted decision OR a justified unresolved record
- If a task cannot be answered, write that explicitly in the summary — do not hide evidence gaps
"""

    def _researcher_system_prompt(self) -> str:
        s_researcher = _safe_prompt_text(self.researcher_name)
        s_lead = _safe_prompt_text(self.name)
        return f"""You are {s_researcher} in the Liquisto intelligence platform.

Your job is to investigate the target company using web search and page fetching.

## Adaptive search behaviour
When {s_lead} directs you to a task:
1. Call run_research(task_key) with the exact task_key provided.
2. If the revision context mentions specific rejected points, adjust your search strategy to target those gaps.
3. Report the result concisely: key facts found, open questions, payload coverage.

If a previous attempt was weak, vary your query framing, try different source types, or look at trade press / registries instead of just the company website.

Be factual and conservative. Never invent companies, URLs, or claims.
If evidence is weak after genuine effort, say so clearly — that is useful information.
"""

    def _critic_system_prompt(self) -> str:
        s_critic = _safe_prompt_text(self.critic_name)
        s_lead = _safe_prompt_text(self.name)
        s_researcher = _safe_prompt_text(self.researcher_name)
        return f"""You are {s_critic} in the Liquisto intelligence platform.

Your job is to review research quality and provide defect-class feedback.

When {s_lead} or after {s_researcher} presents results:
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
        s_judge = _safe_prompt_text(self.judge_name)
        s_lead = _safe_prompt_text(self.name)
        return f"""You are {s_judge} in the Liquisto intelligence platform.

Your job is to make final principle-based quality gate decisions on tasks that cannot be improved further.

## When you are called
{s_lead} calls judge_decision(task_key) only after retries are exhausted and genuine ambiguity remains.

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
        _e = _safe_prompt_text
        return f"""You are {_e(self.name)}, leading a targeted follow-up investigation.

A follow-up question has been submitted that requires additional research.

Question: {_e(question)}
Context: {_e(context)}

Your workflow:
1. Tell {_e(self.researcher_name)}: "Please run_research for task_key: followup_question"
2. Tell {_e(self.critic_name)} to review the result
3. Call finalize_followup(summary) with your updated findings

Keep it focused. Answer the specific question. Do not run a full department investigation.
"""

    def _coding_system_prompt(self) -> str:
        s_coding = _safe_prompt_text(self.coding_name)
        s_lead = _safe_prompt_text(self.name)
        s_researcher = _safe_prompt_text(self.researcher_name)
        return f"""You are {s_coding} in the Liquisto intelligence platform.

Your job is to unblock stuck research by suggesting better search queries and methods.

When {s_lead} asks you to help with a blocked task:
1. Call suggest_refined_queries(task_key) for the given task.
2. Report back: "Refined queries for <key>: <query list>"

## Method tactics
- If the direct company search failed: try industry registry, trade publication, or filing sources.
- If broad queries returned noise: add structural operators (site:, filetype:, "exact phrase").
- If the company name is ambiguous: add location, industry, or legal form terms.
- Suggest 3-5 diverse queries that target the specific defect class the Critic identified.

Your query suggestions will be used by {s_researcher} on the next research attempt.
"""

    # ------------------------------------------------------------------
    # LLM config
    # ------------------------------------------------------------------

    def _llm_config(self, role: str) -> dict[str, Any] | Literal[False]:
        model, _ = get_role_model_selection(role)
        api_key = get_openai_api_key()
        if not api_key:
            return False
        cfg: dict[str, Any] = {
            "config_list": [{"model": model, "api_key": api_key}],
        }
        temperature = resolve_model_temperature(model, 0.1)
        if temperature is not None:
            cfg["temperature"] = temperature
        return cfg

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

    @staticmethod
    def _matrix_status_for_task_status(task_status: str) -> str:
        if task_status == "accepted":
            return "answered"
        if task_status in {"degraded", "blocked", "skipped"}:
            return "partially_answered"
        return "pending"

    def _build_gap_candidates_for_task(
        self,
        *,
        department: str,
        assignment: Assignment,
        task_status: str,
        task_open: list[str],
        evidence_packages: list[EvidencePacket],
    ) -> list[GapCandidate]:
        if task_status not in {"degraded", "blocked", "skipped"}:
            return []
        evidence_ids = [packet.packet_id for packet in evidence_packages[:5] if packet.packet_id != "n/v"]
        gaps: list[GapCandidate] = []
        for idx, question in enumerate(task_open[:6], start=1):
            text = str(question).strip()
            if not text:
                continue
            severity = "high" if task_status in {"blocked", "skipped"} else "medium"
            gaps.append(
                GapCandidate(
                    gap_id=f"{assignment.task_key}-gap-{idx}",
                    question=text,
                    severity=severity,
                    owner=department,
                    resolution_hint=f"Follow-up research for task '{assignment.task_key}'.",
                    evidence_packet_ids=evidence_ids,
                    legacy_origin="department_package",
                )
            )
        return gaps

    def _build_answer_matrix_updates_for_task(
        self,
        *,
        assignment: Assignment,
        task_status: str,
        task_accepted: list[str],
        task_open: list[str],
        evidence_packages: list[EvidencePacket],
    ) -> list[AnswerMatrixUpdate]:
        evidence_ids = [packet.packet_id for packet in evidence_packages[:5] if packet.packet_id != "n/v"]
        answer_text = "; ".join([str(item).strip() for item in task_accepted[:3] if str(item).strip()]) or "n/v"
        notes = ""
        if task_open:
            notes = "; ".join([str(item).strip() for item in task_open[:3] if str(item).strip()])
        updates: list[AnswerMatrixUpdate] = []
        for question_id in assignment.question_ids:
            updates.append(
                AnswerMatrixUpdate(
                    field_key=str(question_id),
                    answer=answer_text,
                    status=self._matrix_status_for_task_status(task_status),
                    evidence_packet_ids=evidence_ids,
                    notes=notes,
                )
            )
        return updates

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
        evidence_packages: list[EvidencePacket] = []
        gap_candidates: list[GapCandidate] = []
        answer_matrix_updates: list[AnswerMatrixUpdate] = []

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
                task_status = "degraded"  # F7: no research → closed_unresolved/degraded
                task_accepted = []
                task_open = ["Research did not complete within max_round."]
                task_sources = []

            accepted_points.extend(task_accepted)
            open_questions.extend(task_open)
            sources.extend(task_sources)
            task_evidence = [
                EvidencePacket.model_validate(item)
                for item in (artifact.evidence_packages if artifact else [])
            ]
            evidence_packages.extend(task_evidence)
            gap_candidates.extend(
                self._build_gap_candidates_for_task(
                    department=self.department,
                    assignment=assignment,
                    task_status=task_status,
                    task_open=task_open,
                    evidence_packages=task_evidence,
                )
            )
            answer_matrix_updates.extend(
                self._build_answer_matrix_updates_for_task(
                    assignment=assignment,
                    task_status=task_status,
                    task_accepted=task_accepted,
                    task_open=task_open,
                    evidence_packages=task_evidence,
                )
            )
            task_summaries.append({
                "task_key": task_key,
                "label": assignment.label,
                "status": task_status,
                "accepted_points": task_accepted,
                "open_points": task_open[:6],
                "summary": assignment.objective,
            })

        # RF3-1 Fix C: if product_asset_scope was never executed, populate from
        # current_payload.products_and_services as a safety net.
        if not run_state.current_payload.get("product_asset_scope"):
            existing_products = run_state.current_payload.get("products_and_services", [])
            if existing_products:
                run_state.current_payload["product_asset_scope"] = [
                    f"{p} \u2014 classification pending" for p in existing_products[:6]
                ]

        accepted_count = sum(1 for t in task_summaries if t.get("status") == "accepted")
        degraded_count = sum(1 for t in task_summaries if t.get("status") == "degraded")
        total_count = len(task_summaries) or 1
        if accepted_count == total_count:
            fallback_confidence = "high"
        elif accepted_count + degraded_count > 0:
            fallback_confidence = "medium"
        else:
            fallback_confidence = "low"
        safe_department = _safe_prompt_text(self.department)

        return DepartmentPackage.model_validate(
            {
                "department": safe_department,
                "target_section": _safe_prompt_text(assignments[0].target_section if assignments else "n/v"),
                "summary": f"{safe_department} package degraded — max_round reached before finalization.",
                "section_payload": _safe_output_value(run_state.current_payload),
                "completed_tasks": _safe_output_value(task_summaries),
                "accepted_points": _safe_output_value(_dedup(accepted_points)),
                "open_questions": _safe_output_value(_dedup(open_questions)),
                "visual_focus": _safe_output_value(_VISUAL_FOCUS.get(self.department, [])),
                "sources": _safe_output_value(sources[:12]),
                "autogen_group": _safe_output_value(self.autogen_group_spec()),
                "confidence": fallback_confidence,
                "evidence_packages": _dedup_model_dump(evidence_packages),
                "gap_candidates": _dedup_model_dump(gap_candidates),
                "answer_matrix_updates": _dedup_model_dump(answer_matrix_updates),
            }
        ).model_dump(mode="json")
