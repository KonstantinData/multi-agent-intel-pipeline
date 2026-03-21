"""Agent definitions for the Liquisto Market Intelligence Pipeline."""
from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import autogen
from autogen.agentchat.group import (
    AgentNameTarget,
    ContextVariables,
    ExpressionContextCondition,
    FunctionTarget,
    FunctionTargetResult,
    OnContextCondition,
    TerminateTarget,
)
from autogen.agentchat.group.context_expression import ContextExpression
from autogen.agentchat.group.patterns import DefaultPattern

from src.config import get_llm_config
from src.models.schemas import (
    CompanyProfile,
    ConciergeOutput,
    IndustryAnalysis,
    MarketNetwork,
    QualityReview,
    RepairPlan,
    ReviewFieldIssue,
    ReviewFeedback,
    SynthesisReport,
)
from src.tools import register_research_tools
from src.tools.research import buyer_source_pack, company_source_pack, fetch_page, industry_source_pack, web_search


def _env_int_with_min(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw is not None else int(default)
    except (TypeError, ValueError):
        value = int(default)
    return max(int(minimum), value)


MAX_STAGE_ATTEMPTS = _env_int_with_min("PIPELINE_MAX_STAGE_ATTEMPTS", 4, 2)
COMPANY_INTELLIGENCE_MAX_STAGE_TOOL_CALLS = _env_int_with_min(
    "PIPELINE_COMPANY_INTELLIGENCE_MAX_TOOL_CALLS",
    4,
    3,
)
STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS = _env_int_with_min(
    "PIPELINE_STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS",
    6,
    4,
)
MARKET_NETWORK_MAX_STAGE_TOOL_CALLS = _env_int_with_min(
    "PIPELINE_MARKET_NETWORK_MAX_STAGE_TOOL_CALLS",
    6,
    4,
)
WORKFLOW_COMPLETE_KEY = "workflow_complete"
ACTIVE_REPAIR_PRODUCER_KEY = "active_repair_producer"
ACTIVE_REPAIR_STAGE_KEY = "active_repair_stage"
ACTIVE_REPAIR_REVIEW_KEY = "active_repair_review"
STRATEGIC_SIGNALS_SOURCE_PACK_USED_KEY = "strategic_signals_source_pack_used"
ENFORCE_STRATEGIC_SIGNALS_SOURCE_PACK_KEY = "enforce_strategic_signals_source_pack"
STRATEGIC_SIGNALS_ATTEMPT_CYCLE_KEY = "strategic_signals_attempt_cycle"
WORKFLOW_STAGE_KEYS = [
    "concierge",
    "company_intelligence",
    "strategic_signals",
    "market_network",
    "evidence_qa",
    "synthesis",
]

SOURCE_FRESHNESS_POLICY = (
    "Prefer sources from the last 24 months for company facts and the last 18 months for "
    "industry signals. If only older evidence exists for unstable facts like revenue, "
    "profitability, market size, growth, or demand outlook, return 'n/v' instead of stale estimates. "
    "Every important numeric or economic claim must be traceable to at least one cited source."
)

TOOL_BUDGET_POLICY = (
    "Use only a small number of high-value tool calls. Prefer 1-3 focused searches or fetches, then finalize. "
    "If evidence remains incomplete after a few tool calls, stop researching and return conservative fields such as "
    "'n/v' or empty lists instead of continuing to search indefinitely."
)

BUYER_EVIDENCE_POLICY = (
    "Do not invent buyers. Each buyer must be linked to a concrete matching product or use case. "
    "Use 'candidate' for plausible but weakly evidenced buyers, 'qualified' only when there is "
    "explicit evidence of product fit, customer fit, or documented sector overlap, and 'verified' "
    "only for direct documented relationships or procurement/service evidence. If a tier has no "
    "credible buyers, return an empty companies list for that tier."
)

EVIDENCE_GOVERNANCE_POLICY = (
    "Every factual claim must be grounded in evidence available in this stage. If evidence cannot be found quickly, "
    "use 'n/v', an empty list, or a conservative assessment instead of guessing. Never turn company self-description, "
    "generic sector knowledge, or weak search intent into a sourced market or buyer claim."
)

REVISION_LOOP_POLICY = (
    "You may receive a repair brief with a primary_task and subtask_delta. Keep the primary_task stable, apply only "
    "the requested subtask_delta, and resolve unsupported points with 'n/v', empty lists, or conservative wording "
    "instead of inventing facts."
)

STAGE_PRIMARY_TASKS = {
    "concierge": "Validate the intake and produce the canonical research brief from company name and web domain.",
    "company_intelligence": "Build a grounded company profile from the research brief using a small number of primary sources.",
    "strategic_signals": "Assess industry signals relevant to excess inventory, overcapacity, and demand weakness using fresh external evidence.",
    "market_network": "Identify evidence-based buyer, competitor, service, and cross-industry tiers relevant to Liquisto.",
    "evidence_qa": "Evaluate upstream outputs for evidence quality, coverage, freshness, and cross-agent consistency without new research.",
    "synthesis": "Compile the validated upstream outputs into a concise Liquisto meeting brief without adding new facts.",
}

PRODUCER_OUTPUT_MODELS = {
    "concierge": ConciergeOutput,
    "company_intelligence": CompanyProfile,
    "strategic_signals": IndustryAnalysis,
    "market_network": MarketNetwork,
    "evidence_qa": QualityReview,
    "synthesis": SynthesisReport,
}

ALLOWED_PRODUCER_NAMES = {
    "Concierge",
    "CompanyIntelligence",
    "StrategicSignals",
    "MarketNetwork",
    "EvidenceQA",
    "Synthesis",
}


def _agent_llm_config(response_format: type, agent_name: str) -> object:
    return get_llm_config(response_format=response_format, agent_name=agent_name)


def _critic_system_message(subject: str, expectations: str) -> str:
    return (
        f"You are the critic for {subject}. "
        "Review the latest producer output against the expectations below. "
        "Approve only when the output is schema-complete, evidence-conscious, conservative about uncertainty, "
        "and internally consistent. "
        "If you reject it, provide concrete revision instructions the same producer can apply immediately. "
        "When evidence is missing or weak, instruct the producer to downgrade, remove, empty, or set fields to 'n/v' "
        "instead of asking for stronger unsupported claims. Never ask the producer to upgrade evidence tiers, invent "
        "specific citations, or fabricate verification that is not already grounded in the available context. "
        "Return only structured output matching the configured schema.\n\n"
        f"Expectations:\n{expectations}"
    )


def _context_with_updates(context_variables: ContextVariables | Any, updates: dict[str, Any]) -> ContextVariables:
    merged = {}
    if isinstance(context_variables, ContextVariables):
        merged.update(context_variables.to_dict())
    elif hasattr(context_variables, "to_dict"):
        merged.update(context_variables.to_dict())
    elif isinstance(context_variables, dict):
        merged.update(context_variables)
    merged.update(updates)
    return ContextVariables.from_dict(merged)


def _consume_company_intelligence_stage_budget(context_variables: Any, tool_name: str) -> dict[str, Any] | None:
    if context_variables is None:
        return None
    used = int(context_variables.get("company_intelligence_tool_calls", 0) or 0)
    if used >= COMPANY_INTELLIGENCE_MAX_STAGE_TOOL_CALLS:
        return {
            "error": "company intelligence stage tool budget exhausted",
            "tool_name": tool_name,
            "max_stage_tool_calls": COMPANY_INTELLIGENCE_MAX_STAGE_TOOL_CALLS,
            "instruction": "Finalize the CompanyProfile now with n/v, empty lists, or conservative text.",
        }
    context_variables.set("company_intelligence_tool_calls", used + 1)
    return None


def _company_source_pack_company_intelligence(
    company_name: str,
    domain: str = "",
    max_results: int = 10,
    context_variables: Any = None,
) -> dict[str, Any]:
    budget_error = _consume_company_intelligence_stage_budget(context_variables, "company_source_pack")
    if budget_error:
        return budget_error
    return company_source_pack(
        company_name=company_name,
        domain=domain,
        max_results=max_results,
        context_variables=context_variables,
    )


def _fetch_page_company_intelligence(
    url: str,
    max_chars: int = 4000,
    context_variables: Any = None,
) -> dict[str, Any]:
    budget_error = _consume_company_intelligence_stage_budget(context_variables, "fetch_page")
    if budget_error:
        return budget_error
    return fetch_page(url=url, max_chars=max_chars, context_variables=context_variables)


def _web_search_company_intelligence(
    query: str,
    site: str = "",
    max_results: int = 5,
    context_variables: Any = None,
) -> dict[str, Any]:
    budget_error = _consume_company_intelligence_stage_budget(context_variables, "web_search")
    if budget_error:
        return budget_error
    return web_search(query=query, site=site, max_results=max_results, context_variables=context_variables)


def _register_company_intelligence_tools(agent: autogen.ConversableAgent) -> None:
    stage_state = {"tool_calls": 0, "company_source_pack": 0, "fetch_page": 0, "web_search": 0}

    def _budgeted_company_source_pack(
        company_name: str,
        domain: str = "",
        max_results: int = 10,
        context_variables: Any = None,
    ) -> dict[str, Any]:
        if stage_state["company_source_pack"] >= 1 or stage_state["tool_calls"] >= COMPANY_INTELLIGENCE_MAX_STAGE_TOOL_CALLS:
            return {
                "error": "company intelligence stage tool budget exhausted",
                "tool_name": "company_source_pack",
                "max_stage_tool_calls": COMPANY_INTELLIGENCE_MAX_STAGE_TOOL_CALLS,
                "instruction": "Do not call company_source_pack again. Use the already known homepage or fetched evidence and finalize the CompanyProfile now with n/v, empty lists, or conservative text.",
            }
        stage_state["tool_calls"] += 1
        stage_state["company_source_pack"] += 1
        return _company_source_pack_company_intelligence(
            company_name=company_name,
            domain=domain,
            max_results=max_results,
            context_variables=context_variables,
        )

    def _budgeted_fetch_page(
        url: str,
        max_chars: int = 4000,
        context_variables: Any = None,
    ) -> dict[str, Any]:
        if stage_state["fetch_page"] >= 2 or stage_state["tool_calls"] >= COMPANY_INTELLIGENCE_MAX_STAGE_TOOL_CALLS:
            return {
                "error": "company intelligence stage tool budget exhausted",
                "tool_name": "fetch_page",
                "max_stage_tool_calls": COMPANY_INTELLIGENCE_MAX_STAGE_TOOL_CALLS,
                "instruction": "Do not fetch more pages. Use the already fetched evidence, avoid guessing more URLs, and finalize the CompanyProfile now with n/v, empty lists, or conservative text.",
            }
        stage_state["tool_calls"] += 1
        stage_state["fetch_page"] += 1
        return _fetch_page_company_intelligence(
            url=url,
            max_chars=max_chars,
            context_variables=context_variables,
        )

    def _budgeted_web_search(
        query: str,
        site: str = "",
        max_results: int = 5,
        context_variables: Any = None,
    ) -> dict[str, Any]:
        if stage_state["web_search"] >= 1 or stage_state["tool_calls"] >= COMPANY_INTELLIGENCE_MAX_STAGE_TOOL_CALLS:
            return {
                "error": "company intelligence stage tool budget exhausted",
                "tool_name": "web_search",
                "max_stage_tool_calls": COMPANY_INTELLIGENCE_MAX_STAGE_TOOL_CALLS,
                "instruction": "Do not run more fallback searches. Use the current evidence and finalize the CompanyProfile now with n/v, empty lists, or conservative text.",
            }
        stage_state["tool_calls"] += 1
        stage_state["web_search"] += 1
        return _web_search_company_intelligence(
            query=query,
            site=site,
            max_results=max_results,
            context_variables=context_variables,
        )

    tool_specs = [
        (
            "company_source_pack",
            "Run one compact batch of official and registry-style company-profile searches and return deduplicated candidate links.",
            _budgeted_company_source_pack,
        ),
        (
            "company_fetch_page",
            "Fetch a selected page and return compact normalized content for grounding company facts.",
            _budgeted_fetch_page,
        ),
        (
            "company_web_search",
            "Run one narrow fallback company search if core facts such as legal form, founded, headquarters, management, or annual report are still missing.",
            _budgeted_web_search,
        ),
    ]

    for name, description, func in tool_specs:
        llm_tool = agent.register_for_llm(name=name, description=description)(func)
        agent.register_for_execution(name=name, description=description)(llm_tool)


def _consume_strategic_signals_stage_budget(context_variables: Any, tool_name: str) -> dict[str, Any] | None:
    if context_variables is None:
        return None
    used = int(context_variables.get("strategic_signals_tool_calls", 0) or 0)
    if used >= STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS:
        return {
            "error": "strategic signals stage tool budget exhausted",
            "tool_name": tool_name,
            "max_stage_tool_calls": STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS,
            "instruction": "Finalize the IndustryAnalysis now with n/v, empty lists, or conservative text.",
        }
    context_variables.set("strategic_signals_tool_calls", used + 1)
    return None


def _industry_source_pack_strategic_signals(
    company_name: str,
    industry_hint: str = "",
    product_keywords: str = "",
    max_results: int = 10,
    context_variables: Any = None,
) -> dict[str, Any]:
    budget_error = _consume_strategic_signals_stage_budget(context_variables, "industry_source_pack")
    if budget_error:
        return budget_error
    if context_variables is not None:
        context_variables.set(STRATEGIC_SIGNALS_SOURCE_PACK_USED_KEY, True)
    return industry_source_pack(
        company_name=company_name,
        industry_hint=industry_hint,
        product_keywords=product_keywords,
        max_results=max_results,
        context_variables=context_variables,
    )


def _fetch_page_strategic_signals(
    url: str,
    max_chars: int = 4000,
    context_variables: Any = None,
) -> dict[str, Any]:
    budget_error = _consume_strategic_signals_stage_budget(context_variables, "fetch_page")
    if budget_error:
        return budget_error
    return fetch_page(url=url, max_chars=max_chars, context_variables=context_variables)


def _web_search_strategic_signals(
    query: str,
    site: str = "",
    max_results: int = 5,
    context_variables: Any = None,
) -> dict[str, Any]:
    budget_error = _consume_strategic_signals_stage_budget(context_variables, "web_search")
    if budget_error:
        return budget_error
    return web_search(query=query, site=site, max_results=max_results, context_variables=context_variables)


def _register_strategic_signals_tools(agent: autogen.ConversableAgent) -> None:
    stage_state = {"cycle": 0, "tool_calls": 0, "industry_source_pack": 0, "fetch_page": 0, "web_search": 0}

    def _sync_attempt_cycle(context_variables: Any) -> None:
        if context_variables is None:
            return
        cycle = int(context_variables.get(STRATEGIC_SIGNALS_ATTEMPT_CYCLE_KEY, 0) or 0)
        if cycle == stage_state["cycle"]:
            return
        stage_state["cycle"] = cycle
        stage_state["tool_calls"] = 0
        stage_state["industry_source_pack"] = 0
        stage_state["fetch_page"] = 0
        stage_state["web_search"] = 0

    def _budgeted_industry_source_pack(
        company_name: str,
        industry_hint: str = "",
        product_keywords: str = "",
        max_results: int = 10,
        context_variables: Any = None,
    ) -> dict[str, Any]:
        _sync_attempt_cycle(context_variables)
        if stage_state["industry_source_pack"] >= 1 or stage_state["tool_calls"] >= STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS:
            return {
                "error": "strategic signals stage tool budget exhausted",
                "tool_name": "industry_source_pack",
                "max_stage_tool_calls": STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS,
                "instruction": "Do not call industry_source_pack again. Use the current evidence and finalize the IndustryAnalysis now with n/v, empty lists, or conservative text.",
            }
        stage_state["tool_calls"] += 1
        stage_state["industry_source_pack"] += 1
        return _industry_source_pack_strategic_signals(
            company_name=company_name,
            industry_hint=industry_hint,
            product_keywords=product_keywords,
            max_results=max_results,
            context_variables=context_variables,
        )

    def _budgeted_fetch_page(
        url: str,
        max_chars: int = 4000,
        context_variables: Any = None,
    ) -> dict[str, Any]:
        _sync_attempt_cycle(context_variables)
        if stage_state["fetch_page"] >= 2 or stage_state["tool_calls"] >= STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS:
            return {
                "error": "strategic signals stage tool budget exhausted",
                "tool_name": "fetch_page",
                "max_stage_tool_calls": STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS,
                "instruction": "Do not fetch more pages. Use the current evidence and finalize the IndustryAnalysis now with n/v, empty lists, or conservative text.",
            }
        stage_state["tool_calls"] += 1
        stage_state["fetch_page"] += 1
        return _fetch_page_strategic_signals(url=url, max_chars=max_chars, context_variables=context_variables)

    def _budgeted_web_search(
        query: str,
        site: str = "",
        max_results: int = 5,
        context_variables: Any = None,
    ) -> dict[str, Any]:
        _sync_attempt_cycle(context_variables)
        if stage_state["web_search"] >= 1 or stage_state["tool_calls"] >= STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS:
            return {
                "error": "strategic signals stage tool budget exhausted",
                "tool_name": "web_search",
                "max_stage_tool_calls": STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS,
                "instruction": "Do not run more fallback searches. Finalize the IndustryAnalysis now with n/v, empty lists, or conservative text.",
            }
        stage_state["tool_calls"] += 1
        stage_state["web_search"] += 1
        return _web_search_strategic_signals(
            query=query,
            site=site,
            max_results=max_results,
            context_variables=context_variables,
        )

    tool_specs = [
        (
            "industry_source_pack",
            "Run one compact batch of industry-signal searches and return deduplicated candidate links.",
            _budgeted_industry_source_pack,
        ),
        (
            "strategic_fetch_page",
            "Fetch a selected industry page and return compact normalized content for grounding industry signals.",
            _budgeted_fetch_page,
        ),
        (
            "strategic_web_search",
            "Run one narrow fallback industry search only if the source pack is weak or off-target.",
            _budgeted_web_search,
        ),
    ]

    for name, description, func in tool_specs:
        llm_tool = agent.register_for_llm(name=name, description=description)(func)
        agent.register_for_execution(name=name, description=description)(llm_tool)


def _consume_market_network_stage_budget(context_variables: Any, tool_name: str) -> dict[str, Any] | None:
    if context_variables is None:
        return None
    used = int(context_variables.get("market_network_tool_calls", 0) or 0)
    if used >= MARKET_NETWORK_MAX_STAGE_TOOL_CALLS:
        return {
            "error": "market network stage tool budget exhausted",
            "tool_name": tool_name,
            "max_stage_tool_calls": MARKET_NETWORK_MAX_STAGE_TOOL_CALLS,
            "instruction": "Finalize the MarketNetwork now with empty tiers, candidate-only evidence, or conservative assessments.",
        }
    context_variables.set("market_network_tool_calls", used + 1)
    return None


def _buyer_source_pack_market_network(
    company_name: str,
    product_keywords: str = "",
    domain: str = "",
    max_results: int = 10,
    context_variables: Any = None,
) -> dict[str, Any]:
    budget_error = _consume_market_network_stage_budget(context_variables, "buyer_source_pack")
    if budget_error:
        return budget_error
    return buyer_source_pack(
        company_name=company_name,
        product_keywords=product_keywords,
        domain=domain,
        max_results=max_results,
        context_variables=context_variables,
    )


def _fetch_page_market_network(
    url: str,
    max_chars: int = 4000,
    context_variables: Any = None,
) -> dict[str, Any]:
    budget_error = _consume_market_network_stage_budget(context_variables, "fetch_page")
    if budget_error:
        return budget_error
    return fetch_page(url=url, max_chars=max_chars, context_variables=context_variables)


def _web_search_market_network(
    query: str,
    site: str = "",
    max_results: int = 5,
    context_variables: Any = None,
) -> dict[str, Any]:
    budget_error = _consume_market_network_stage_budget(context_variables, "web_search")
    if budget_error:
        return budget_error
    return web_search(query=query, site=site, max_results=max_results, context_variables=context_variables)


def _register_market_network_tools(agent: autogen.ConversableAgent) -> None:
    stage_state = {"tool_calls": 0, "buyer_source_pack": 0, "fetch_page": 0, "web_search": 0}

    def _budgeted_buyer_source_pack(
        company_name: str,
        product_keywords: str = "",
        domain: str = "",
        max_results: int = 10,
        context_variables: Any = None,
    ) -> dict[str, Any]:
        if stage_state["buyer_source_pack"] >= 1 or stage_state["tool_calls"] >= MARKET_NETWORK_MAX_STAGE_TOOL_CALLS:
            return {
                "error": "market network stage tool budget exhausted",
                "tool_name": "buyer_source_pack",
                "max_stage_tool_calls": MARKET_NETWORK_MAX_STAGE_TOOL_CALLS,
                "instruction": "Do not call buyer_source_pack again. Use the current evidence and finalize the MarketNetwork now with empty tiers, candidate-only evidence, or conservative assessments.",
            }
        stage_state["tool_calls"] += 1
        stage_state["buyer_source_pack"] += 1
        return _buyer_source_pack_market_network(
            company_name=company_name,
            product_keywords=product_keywords,
            domain=domain,
            max_results=max_results,
            context_variables=context_variables,
        )

    def _budgeted_fetch_page(
        url: str,
        max_chars: int = 4000,
        context_variables: Any = None,
    ) -> dict[str, Any]:
        if stage_state["fetch_page"] >= 2 or stage_state["tool_calls"] >= MARKET_NETWORK_MAX_STAGE_TOOL_CALLS:
            return {
                "error": "market network stage tool budget exhausted",
                "tool_name": "fetch_page",
                "max_stage_tool_calls": MARKET_NETWORK_MAX_STAGE_TOOL_CALLS,
                "instruction": "Do not fetch more buyer pages. Use the current evidence and finalize the MarketNetwork now with empty tiers, candidate-only evidence, or conservative assessments.",
            }
        stage_state["tool_calls"] += 1
        stage_state["fetch_page"] += 1
        return _fetch_page_market_network(url=url, max_chars=max_chars, context_variables=context_variables)

    def _budgeted_web_search(
        query: str,
        site: str = "",
        max_results: int = 5,
        context_variables: Any = None,
    ) -> dict[str, Any]:
        if stage_state["web_search"] >= 1 or stage_state["tool_calls"] >= MARKET_NETWORK_MAX_STAGE_TOOL_CALLS:
            return {
                "error": "market network stage tool budget exhausted",
                "tool_name": "web_search",
                "max_stage_tool_calls": MARKET_NETWORK_MAX_STAGE_TOOL_CALLS,
                "instruction": "Do not run more fallback searches. Finalize the MarketNetwork now with empty tiers, candidate-only evidence, or conservative assessments.",
            }
        stage_state["tool_calls"] += 1
        stage_state["web_search"] += 1
        return _web_search_market_network(
            query=query,
            site=site,
            max_results=max_results,
            context_variables=context_variables,
        )

    tool_specs = [
        (
            "buyer_source_pack",
            "Run one compact batch of buyer-network searches and return deduplicated competitor, customer, service, and aftermarket candidates.",
            _budgeted_buyer_source_pack,
        ),
        (
            "market_fetch_page",
            "Fetch a selected buyer-network page and return compact normalized content for grounding buyer claims.",
            _budgeted_fetch_page,
        ),
        (
            "market_web_search",
            "Run one narrow fallback buyer search only if the source pack is weak or off-target.",
            _budgeted_web_search,
        ),
    ]

    for name, description, func in tool_specs:
        llm_tool = agent.register_for_llm(name=name, description=description)(func)
        agent.register_for_execution(name=name, description=description)(llm_tool)


def create_agents() -> dict[str, autogen.ConversableAgent]:
    """Create and return all pipeline agents."""

    admin = autogen.ConversableAgent(
        name="Admin",
        system_message=(
            "You are the Admin of a Liquisto market intelligence pipeline. "
            "Acknowledge the task, start the workflow, and close the orchestration once the final review has passed."
        ),
        description="Admin. Starts the AG2 workflow and closes it after the final approved review.",
        code_execution_config=False,
        llm_config=False,
        human_input_mode="NEVER",
        default_auto_reply="Admin acknowledged. Proceed with the configured workflow.",
    )

    concierge = autogen.ConversableAgent(
        name="Concierge",
        system_message=(
            "# Role\n"
            "You are the Case Concierge agent. Validate the intake input (company name + web domain), "
            "clarify the case basis, and produce the initial structured research brief.\n\n"
            "# Workflow\n"
            "1. Start with exactly one check_domain call on the provided web_domain.\n"
            "2. If the domain is reachable, fetch at most one root or homepage URL to ground the result.\n"
            "3. From the available evidence, confirm whether the visible company name appears to match the intake "
            "and determine the primary visible language.\n"
            "4. Record only conservative, factual observations from the intake, domain check, or fetched homepage.\n\n"
            "# Constraints\n"
            "- Do not infer products, services, industry, or company situation at this stage.\n"
            "- Do not search broadly or use any research workflow beyond the available intake-level tools.\n"
            "- Keep observations factual, concise, and limited to obvious site-level cues.\n"
            "- If content details are unclear, keep observations minimal or empty.\n\n"
            "# Error Handling\n"
            "- If check_domain fails or shows the domain is unreachable, do not call fetch_page.\n"
            "- If the domain is unreachable or the visible language cannot be determined confidently, set language to 'n/v'.\n"
            "- If the visible company name appears to mismatch the intake, mention that conservatively in observations "
            "but keep the original company_name and web_domain from the intake.\n\n"
            "# Output Contract\n"
            "Return only structured output matching ConciergeOutput with exactly these fields:\n"
            "- company_name\n"
            "- web_domain\n"
            "- language\n"
            "- observations\n\n"
            "# Tool Budget\n"
            "- check_domain: exactly 1 call\n"
            "- fetch_page: at most 1 call\n"
            f"- Global policy: {TOOL_BUDGET_POLICY}\n\n"
            "# Revision Loop\n"
            f"- {REVISION_LOOP_POLICY}"
        ),
        description="Validates a new company intake and produces the initial research brief.",
        llm_config=_agent_llm_config(ConciergeOutput, "concierge"),
    )

    company_intelligence = autogen.ConversableAgent(
        name="CompanyIntelligence",
        system_message=(
            "# Role\n"
            "You are the Company Intelligence agent. Use primary sources to build a structured company profile "
            "from the research brief.\n\n"
            "# Workflow\n"
            "1. Call company_source_pack(company_name, domain) exactly once to gather initial candidate sources.\n"
            "2. From that pack, identify at most 1-2 relevant official, report-style, or registry-style pages.\n"
            "3. If the source pack is too homepage-heavy or still misses core basics such as legal_form, founded, headquarters, or key leadership, "
            "run at most one narrow company_web_search focused on those missing basics.\n"
            "4. Fetch only the strongest 1-2 pages with company_fetch_page and extract grounded company facts from them.\n"
            "5. Compile the CompanyProfile using only supported facts. For unsupported or unclear fields, return 'n/v', "
            "empty lists, or conservative text as appropriate.\n"
            "6. Populate the sources field only with the concrete pages actually fetched and used.\n\n"
            "# Source Priorities\n"
            "- Prefer official company pages, Impressum/about pages, annual or sustainability reports, press releases, "
            "and registry/profile pages.\n"
            "- If the source pack is weak, use the single fallback company_web_search to look for legal form, founding year, headquarters, "
            "management, or annual-report evidence, then stop.\n"
            "- Do not keep searching for missing revenue, employee, founding, or management data after one focused pass and one fallback search.\n\n"
            "# Field Guidance\n"
            "- products_and_services should list concrete product categories, technologies, or named service areas that "
            "are visibly supported by sources. Do not expand vague marketing wording into specific offerings.\n"
            "- key_people should include only clearly named leaders or board members found in the available sources.\n"
            "- If no verifiable people are found, return key_people as an empty list. Do not create placeholder entries such as 'n/v'.\n"
            "- economic_situation should include only directly stated or conservatively evidenced signals. Do not infer "
            "trends, profitability, or financial pressure from a single weak hint.\n"
            "- description should stay factual and compact, summarizing what the company does without adding unsupported framing.\n\n"
            "# Error Handling\n"
            "- If company_source_pack is weak or empty, use the single fallback company_web_search before finalizing.\n"
            "- If fetched pages are inaccessible, empty, or not clearly relevant, skip them and continue with the remaining evidence.\n"
            "- If evidence remains weak after the focused pass and one fallback search, finalize immediately with 'n/v', empty lists, and empty sources as needed.\n\n"
            "# Tool Budget\n"
            "- company_source_pack: exactly 1 call\n"
            "- company_fetch_page: at most 2 calls\n"
            "- company_web_search: at most 1 narrow fallback call\n"
            "- total stage budget: at most 4 tool calls\n"
            f"- Global policy: {TOOL_BUDGET_POLICY}\n\n"
            "# Source Freshness\n"
            f"- {SOURCE_FRESHNESS_POLICY}\n\n"
            "# Revision Loop\n"
            f"- {REVISION_LOOP_POLICY}\n\n"
            "# Output Contract\n"
            "Return only structured output matching CompanyProfile, including the sources field for the pages used."
        ),
        description="CompanyIntelligence. Researches and builds the full company profile.",
        llm_config=_agent_llm_config(CompanyProfile, "company_intelligence"),
    )

    strategic_signals = autogen.ConversableAgent(
        name="StrategicSignals",
        system_message=(
            "# Role\n"
            "You are the Strategic Signals agent. Identify industry-level signals that indicate potential excess "
            "inventory, overproduction, demand weakness, or related surplus conditions relevant to Liquisto.\n\n"
            "# Input\n"
            "Use the available company profile, especially company_name, industry, website, and products_and_services, "
            "to scope the industry research.\n\n"
            "# Workflow\n"
            "1. Start with exactly one industry_source_pack(company_name, industry_hint, product_keywords).\n"
            "2. From the results, choose at most 1-2 clearly relevant industry-specific pages such as trade publications, "
            "sector reports, or focused market analyses.\n"
            "3. Fetch only those pages with strategic_fetch_page and extract grounded industry signals.\n"
            "4. Populate IndustryAnalysis using source-backed observations for key_trends, overcapacity_signals, and "
            "excess_stock_indicators.\n"
            "5. Use trend_direction and assessment only for conservative synthesis of the observed signals. If the "
            "observations are weak, the synthesis must stay weak as well.\n"
            "6. Populate the sources field with the concrete pages used. If a field is not supported by the fetched "
            "sources, set it to 'n/v', an empty list, or TrendDirection.UNCERTAIN as appropriate.\n"
            "7. If you finish with no credible fresh industry sources, say that explicitly in assessment and keep sources empty.\n\n"
            "# Research Scope\n"
            "- Focus on industry signals that matter for Liquisto: excess inventory, overcapacity, demand softening, "
            "surplus stock pressure, and adjacent market shifts that can create unsold goods.\n"
            "- Prefer industry-specific sources over generic macro commentary or broad business news.\n"
            "- Market size, growth_rate, and demand_outlook require fresh, explicit evidence; otherwise keep them at 'n/v'.\n"
            "- Use company pages only for company strategy context. Do not present company strategy as external market evidence.\n\n"
            "# Signal Quality\n"
            "- key_trends, overcapacity_signals, and excess_stock_indicators should describe observed evidence, not inflated conclusions.\n"
            "- trend_direction and assessment may synthesize the evidence, but must remain conservative and uncertainty-aware.\n"
            "- Do not infer overcapacity, demand collapse, or inventory stress from generic economic reasoning alone.\n"
            "- Empty key_trends and empty overcapacity_signals are acceptable if no credible source-backed signals were found.\n"
            f"- {EVIDENCE_GOVERNANCE_POLICY}\n\n"
            "# Error Handling\n"
            "- If industry_source_pack returns few or off-target results, use any clearly relevant hit it provides before considering "
            "a single strategic_web_search fallback.\n"
            "- If no clearly relevant industry page can be grounded quickly, finalize conservatively with 'n/v' and empty lists.\n"
            "- Do not perform repeated broad market searches once the source pack and one fallback search fail.\n"
            "- Do not broaden the research into a generic industry report-writing exercise.\n\n"
            "# Tool Budget\n"
            "- industry_source_pack: exactly 1 call\n"
            "- strategic_fetch_page: at most 2 calls\n"
            "- strategic_web_search: at most 1 narrow fallback call after the source pack\n"
            "- total stage budget: at most 4 tool calls\n"
            f"- {TOOL_BUDGET_POLICY}\n\n"
            "# Source Freshness\n"
            f"- {SOURCE_FRESHNESS_POLICY}\n\n"
            "# Revision Loop\n"
            f"- {REVISION_LOOP_POLICY}\n\n"
            "# Output Contract\n"
            "Return only structured output matching IndustryAnalysis, including the sources field for the pages used."
        ),
        description="StrategicSignals. Analyzes industry trends, overcapacity, and market signals.",
        llm_config=_agent_llm_config(IndustryAnalysis, "strategic_signals"),
    )

    market_network = autogen.ConversableAgent(
        name="MarketNetwork",
        system_message=(
            "# Role\n"
            "You are the Market Network agent. Identify concrete potential buyers for surplus inventory from the target "
            "company, organized into four evidence-based tiers relevant to Liquisto.\n\n"
            "# Input\n"
            "Use the available company profile and industry analysis, especially target company identity, website, "
            "products_and_services, key_trends, and overcapacity_signals, to scope buyer research.\n\n"
            "# Buyer Tiers\n"
            "1. PEER COMPETITORS: Companies producing the same or closely similar products and potentially buying parts "
            "or components for their own production.\n"
            "2. DOWNSTREAM BUYERS: Companies that buy finished products from the target company or comparable peers, "
            "including plausible spare-parts users when there is concrete product-use evidence.\n"
            "3. SERVICE PROVIDERS: Companies that maintain, repair, or service the target company's products or close "
            "substitutes and therefore may need spare parts.\n"
            "4. CROSS-INDUSTRY BUYERS: Companies in different sectors that could credibly repurpose the products or "
            "parts for another documented use case.\n\n"
            "# Workflow\n"
            "1. Start with buyer_source_pack(company_name, product_keywords, domain).\n"
            "2. Triage the pack in this order: peer competitors first, then downstream/aftermarket and service evidence, then cross-industry repurposing.\n"
            "3. Review the results and identify the strongest candidate pages such as competitor listings, customer references, "
            "case studies, distributor pages, service pages, aftermarket pages, or clearly documented alternative-use pages.\n"
            "4. Fetch only the strongest 2-3 candidate pages with market_fetch_page. Skip generic, weak, or off-topic results.\n"
            "5. Reserve any fallback market_web_search for the single highest-value unresolved tier rather than running a broad sweep for all tiers.\n"
            "6. If a tier remains unsupported after the focused pass, stop and leave that tier empty.\n"
            "7. For each buyer you include, fill the Buyer entry only from source-backed facts: name, website, city, country, "
            "relevance, matching_products, evidence_tier, and source.\n"
            "8. Set source on each buyer to the concrete page that supports that buyer. If a buyer does not have a concrete "
            "supporting page, do not include that buyer.\n"
            "9. Populate each tier's sources field with the set of sources used across that tier, and keep the tier assessment "
            "honest about evidence strength.\n"
            "10. If a tier has no source-backed candidates, return an empty companies list for that tier and say so explicitly in the tier assessment.\n\n"
            "# Matching Rules\n"
            "- matching_products must list only products, parts, or use cases that are directly supported by the buyer source or "
            "clearly grounded in the upstream company profile. Do not infer product matches from vague company descriptions alone.\n"
            "- relevance should explain why the buyer fits the tier based on the source-backed product fit, service fit, customer fit, "
            "or documented use case.\n"
            "- target_company must name the company being analyzed and should stay aligned with the upstream company profile.\n"
            "- Tier assessments should state whether the tier is supported by direct buyer evidence, indirect product-fit evidence, or no credible evidence.\n\n"
            "# Error Handling\n"
            "- If buyer_source_pack returns mostly generic or off-topic results, prefer fewer buyers and empty tiers over speculative matches.\n"
            "- If a result does not clearly map to one tier, skip it instead of forcing it into a category.\n"
            "- If evidence is stale or generic, reflect that in evidence_tier and tier assessment rather than upgrading the buyer.\n"
            "- Do not keep searching just because one or more tiers stay empty; empty tiers are a valid final answer.\n"
            "- Do not use vague directories, broad lists of suppliers, or generic industry overlap as the sole basis for a buyer entry.\n\n"
            "# Evidence Quality\n"
            f"- {BUYER_EVIDENCE_POLICY}\n"
            "- A single buyer with concrete evidence is better than a longer speculative list.\n"
            "- Generic directories or broad sector overlap are weak evidence and should usually remain candidate-level at most.\n"
            f"- {EVIDENCE_GOVERNANCE_POLICY}\n\n"
            "# Tool Budget\n"
            "- buyer_source_pack: exactly 1 call\n"
            "- market_fetch_page: at most 2 calls\n"
            "- market_web_search: at most 1 narrow fallback call after the source pack\n"
            "- total stage budget: at most 4 tool calls\n"
            f"- {TOOL_BUDGET_POLICY}\n\n"
            "# Source Freshness\n"
            f"- {SOURCE_FRESHNESS_POLICY}\n"
            "- Prefer fresh buyer evidence. If a tier is supported only by stale or generic evidence, state that in the assessment "
            "and keep evidence_tier conservative.\n\n"
            "# Revision Loop\n"
            f"- {REVISION_LOOP_POLICY}\n\n"
            "# Output Contract\n"
            "Return only structured output matching MarketNetwork, including target_company, buyer-level source fields, and tier-level sources."
        ),
        description=(
            "MarketNetwork. Identifies buyers across 4 tiers: "
            "Peer Competitors, Downstream Buyers, Service Providers, Cross-Industry Buyers."
        ),
        llm_config=_agent_llm_config(MarketNetwork, "market_network"),
    )

    evidence_qa = autogen.ConversableAgent(
        name="EvidenceQA",
        system_message=(
            "# Role\n"
            "You are the Evidence QA agent. Review upstream outputs for evidence quality, completeness, freshness, "
            "and cross-agent consistency. Do not conduct additional research. Evaluate only what prior agents delivered.\n\n"
            "# Input\n"
            "You receive structured outputs from CompanyProfile, IndustryAnalysis, and MarketNetwork.\n\n"
            "# Review Workflow\n"
            "1. Review CompanyProfile for source coverage, unsupported volatile facts, and missing fields that would weaken downstream buyer research.\n"
            "2. Review IndustryAnalysis for source freshness, unsupported market claims, and whether the industry signals match the company profile.\n"
            "3. Review MarketNetwork for buyer-level source quality, matching_products traceability, evidence_tier discipline, and tier-level source coverage.\n"
            "4. Check cross-agent consistency, especially product matching, industry alignment, and whether buyer claims fit the documented company offering.\n"
            "5. For each important issue, create one gap_details entry with agent, field_path, issue_type, severity "
            "(critical/significant/minor), summary, and recommendation.\n"
            "6. Derive open_gaps and recommendations from the most important gap_details instead of listing every minor issue.\n"
            "7. Set evidence_health as the overall quality judgment of the run, based on the severity and concentration of the issues found.\n\n"
            "# Review Priorities\n"
            "- Treat unsupported or stale market and economic claims as high priority.\n"
            "- Treat buyer entries without concrete buyer-level sources or with speculative matching_products as high priority.\n"
            "- Treat cross-agent inconsistencies as material when they affect sales relevance or buyer fit.\n"
            "- Minor cosmetic omissions may stay out of open_gaps if they do not affect the meeting-readiness of the run.\n\n"
            "# Revision Loop\n"
            f"- {REVISION_LOOP_POLICY}\n\n"
            "# Output Contract\n"
            "Return only structured output matching QualityReview, including validated_agents, evidence_health, open_gaps, "
            "recommendations, and gap_details."
        ),
        description="EvidenceQA. Reviews evidence quality and identifies gaps across all agent outputs.",
        llm_config=_agent_llm_config(QualityReview, "evidence_qa"),
    )

    synthesis = autogen.ConversableAgent(
        name="Synthesis",
        system_message=(
            "# Role\n"
            "You are the Synthesis agent. Compile the upstream research into a concise briefing for the Liquisto sales team "
            "to use in a customer evaluation meeting. Write for decision-makers: clear, direct, compact, and evidence-aware.\n\n"
            "# Input\n"
            "Use the validated upstream outputs from CompanyProfile, IndustryAnalysis, MarketNetwork, and QualityReview. "
            "Do not introduce new facts or external information.\n\n"
            "# Section Mapping\n"
            "1. executive_summary: combine the target company identity, products_and_services, economic_situation, and the most relevant "
            "industry signals into a short meeting-ready summary. If evidence_health is weak or important gaps remain, state that clearly here.\n"
            "2. liquisto_service_relevance: assess each service area using only upstream evidence.\n"
            "   - excess_inventory: use overcapacity_signals, excess_stock_indicators, economic_situation, and buyer evidence.\n"
            "   - repurposing: use product breadth, cross-industry buyer evidence, and any documented alternative-use signals.\n"
            "   - analytics: use data availability, complexity of the documented product and buyer landscape, and QA gaps that limit certainty.\n"
            "   Use hoch only when multiple concrete signals support the service area, mittel for partial but real support, niedrig when evidence points away from it, and unklar when evidence is too weak.\n"
            "3. case_assessments: create one entry each for kaufen, kommission, and ablehnen. Each argument must stay evidence-based and must populate based_on with the upstream section, signal, or artifact it relies on.\n"
            "4. buyer_market_summary: summarize buyer strength across the four tiers, reflecting both tier coverage and evidence quality.\n"
            "5. key_risks and next_steps: derive these from QualityReview gaps, weak buyer evidence, stale market evidence, and unresolved commercial uncertainty.\n\n"
            "# Output Rules\n"
            "- target_company must match the analyzed company from upstream outputs.\n"
            "- total_peer_competitors, total_downstream_buyers, total_service_providers, and total_cross_industry_buyers should match the counts from MarketNetwork.\n"
            "- case_assessments must stay balanced: include pro and contra arguments where evidence allows, and do not turn uncertainty into a recommendation.\n"
            "- based_on should reference the relevant upstream basis such as CompanyProfile, IndustryAnalysis, MarketNetwork, QualityReview, or a specific documented signal from them.\n"
            "- sources should include the key upstream source records that materially support the synthesis.\n\n"
            "# QA Integration\n"
            "- QualityReview should shape the synthesis structurally, not as an afterthought.\n"
            "- If evidence_health is weak, buyer evidence is candidate-heavy, or important gaps remain, reflect that directly in executive_summary, buyer_market_summary, key_risks, next_steps, and the relevant case arguments.\n"
            "- Do not present stale or weak evidence as firm conclusions.\n\n"
            "# Revision Loop\n"
            f"- {REVISION_LOOP_POLICY}\n\n"
            "# Output Contract\n"
            "Return only structured output matching SynthesisReport."
        ),
        description=(
            "Synthesis. Compiles final briefing with pro/contra assessments "
            "for each Liquisto option."
        ),
        llm_config=_agent_llm_config(SynthesisReport, "synthesis"),
    )

    repair_planner = autogen.ConversableAgent(
        name="RepairPlanner",
        system_message=(
            "# Role\n"
            "You are the Repair Planner agent. Translate the latest critic feedback into a focused, structured repair plan "
            "for exactly one producer. You do not research, you do not invent facts, and you do not change the producer's "
            "primary task.\n\n"
            "# Workflow\n"
            "1. Read the latest critic feedback and the prior producer output in the conversation.\n"
            "2. Preserve the producer's primary_task exactly as given.\n"
            "3. Convert the critic feedback into a small subtask_delta that can be applied in the next producer pass.\n"
            "4. Add constraints that prevent over-correction, speculation, or unsupported upgrades.\n"
            "5. Add done_when criteria that define when the repair is complete.\n\n"
            "# Rules\n"
            "- Do not ask for broad rework when the critic only flagged a few fields.\n"
            "- If a field cannot be fixed from the currently available evidence, instruct the producer to return 'n/v', "
            "an empty list, or a conservative assessment.\n"
            "- Never invent sources, buyers, market data, or executives.\n"
            "- Keep subtask_delta action-oriented and bounded.\n"
            "- Return only structured output matching RepairPlan."
        ),
        description="RepairPlanner. Turns critic feedback into a bounded repair plan for the same producer.",
        llm_config=_agent_llm_config(RepairPlan, "repair_planner"),
    )

    concierge_critic = autogen.ConversableAgent(
        name="ConciergeCritic",
        system_message=_critic_system_message(
            "Concierge",
            "- company_name and web_domain must match the intake\n"
            "- language should reflect the visible site language when that can be determined confidently; otherwise n/v is acceptable\n"
            "- observations must be factual, concise, non-speculative, and limited to intake/domain-level cues\n"
            "- unreachable domains or visible company-name mismatches should be captured conservatively in observations\n"
            "- do not require product, service, or industry claims in this stage",
        ),
        description="Critic for Concierge output.",
        llm_config=_agent_llm_config(ReviewFeedback, "concierge_critic"),
    )

    company_intelligence_critic = autogen.ConversableAgent(
        name="CompanyIntelligenceCritic",
        system_message=_critic_system_message(
            "CompanyIntelligence",
            "- core company facts such as company_name, headquarters, legal_form, and founded should be grounded in cited sources\n"
            "- products_and_services must reflect concrete categories or offerings visible in sources and must not inflate vague marketing language\n"
            "- key_people should be verifiable in the cited sources rather than inferred from general knowledge\n"
            "- if no verifiable people were found, key_people should be an empty list; do not require placeholder values like 'n/v' inside list items\n"
            "- economic_situation must not infer trends, profitability, or pressure from a single weak hint\n"
            "- description should stay factual and compact and must not frame the company more strongly than the sources support\n"
            "- sources should include the concrete pages used for supported company claims\n"
            "- volatile metrics without fresh evidence must be n/v\n"
            "- products, people, and economic statements must not be invented\n"
            "- sources should be recent enough for the claims being made\n"
            "- a sparse profile is acceptable when the source pack is weak, as long as unsupported fields are downgraded to n/v or empty lists instead of being invented",
        ),
        description="Critic for CompanyIntelligence output.",
        llm_config=_agent_llm_config(ReviewFeedback, "company_intelligence_critic"),
    )

    strategic_signals_critic = autogen.ConversableAgent(
        name="StrategicSignalsCritic",
        system_message=_critic_system_message(
            "StrategicSignals",
            "- market size, growth, and demand outlook need fresh evidence or n/v\n"
            "- sources should include the concrete industry pages used for supported claims\n"
            "- company-homepage or company-report sources alone are not sufficient support for external market claims, overcapacity relief, or demand-strength conclusions\n"
            "- when sources are company-only, keep market_size, growth_rate, and demand_outlook at n/v and limit key_trends to clearly labeled company strategy context or remove them\n"
            "- trends and overcapacity signals must be relevant to the target industry\n"
            "- key_trends, overcapacity_signals, and excess_stock_indicators should stay observational and source-backed\n"
            "- trend_direction and assessment may synthesize, but must not overstate weak observations\n"
            "- if no credible fresh industry sources were found, empty signal lists and empty sources are acceptable only when assessment states that explicitly\n"
            "- company strategy or product messaging must not be reframed as external market evidence\n"
            "- do not reject a conservative sparse output merely because the market was hard to source\n"
            "- avoid generic macro statements unless they are tied to the sector",
        ),
        description="Critic for StrategicSignals output.",
        llm_config=_agent_llm_config(ReviewFeedback, "strategic_signals_critic"),
    )

    market_network_critic = autogen.ConversableAgent(
        name="MarketNetworkCritic",
        system_message=_critic_system_message(
            "MarketNetwork",
            "- buyers must have concrete product fit or use-case fit\n"
            "- evidence_tier must be conservative and justified\n"
            "- each buyer should have its own concrete source; unsupported buyers should be removed\n"
            "- matching_products must be source-backed and must not be inferred from vague company descriptions alone\n"
            "- tier-level sources should reflect the sources actually used across that tier\n"
            "- empty tiers are better than speculative buyer lists\n"
            "- approve empty tiers when the agent searched conservatively and the tier assessment explicitly states no credible evidence was found\n"
            "- do not reject solely because no buyers were found; reject when unsupported buyers are included or when assessments overstate weak evidence\n"
            "- tier assessments should reflect evidence strength honestly",
        ),
        description="Critic for MarketNetwork output.",
        llm_config=_agent_llm_config(ReviewFeedback, "market_network_critic"),
    )

    evidence_qa_critic = autogen.ConversableAgent(
        name="EvidenceQACritic",
        system_message=_critic_system_message(
            "EvidenceQA",
            "- approve EvidenceQA when it accurately identifies upstream gaps; do not reject it merely because upstream evidence is weak or incomplete\n"
            "- gap_details should capture the most important issues with agent, issue_type, severity, summary, and actionable recommendation\n"
            "- field_path should be specific when the affected field or tier is identifiable\n"
            "- open_gaps should capture the most important missing evidence\n"
            "- recommendations should be actionable and target the right producer\n"
            "- evidence_health should reflect the real quality of the run\n"
            "- do not ask for new research by EvidenceQA itself; route remediation to the producer that owns the issue",
        ),
        description="Critic for EvidenceQA output.",
        llm_config=_agent_llm_config(ReviewFeedback, "evidence_qa_critic"),
    )

    synthesis_critic = autogen.ConversableAgent(
        name="SynthesisCritic",
        system_message=_critic_system_message(
            "Synthesis",
            "- no new facts beyond prior validated outputs\n"
            "- target_company and buyer totals must stay aligned with upstream outputs, especially MarketNetwork\n"
            "- liquisto_service_relevance must use conservative, evidence-based reasoning and reflect weak evidence as unklar or lower confidence\n"
            "- case_assessments must include evidence-based arguments with meaningful based_on references\n"
            "- uncertainty and QA findings must be reflected in the summary, risks, and next steps\n"
            "- buyer-market strength must not exceed the actual evidence quality\n"
            "- option assessments must stay balanced and evidence-based",
        ),
        description="Critic for Synthesis output.",
        llm_config=_agent_llm_config(ReviewFeedback, "synthesis_critic"),
    )

    register_research_tools(concierge, ["check_domain", "fetch_page"])
    _register_company_intelligence_tools(company_intelligence)
    _register_strategic_signals_tools(strategic_signals)
    _register_market_network_tools(market_network)

    return {
        "admin": admin,
        "concierge": concierge,
        "concierge_critic": concierge_critic,
        "repair_planner": repair_planner,
        "company_intelligence": company_intelligence,
        "company_intelligence_critic": company_intelligence_critic,
        "strategic_signals": strategic_signals,
        "strategic_signals_critic": strategic_signals_critic,
        "market_network": market_network,
        "market_network_critic": market_network_critic,
        "evidence_qa": evidence_qa,
        "evidence_qa_critic": evidence_qa_critic,
        "synthesis": synthesis,
        "synthesis_critic": synthesis_critic,
    }


def create_group_pattern(agents: dict[str, autogen.ConversableAgent]) -> DefaultPattern:
    """Create the AG2-native producer/critic workflow as a handoff-driven pattern."""
    _configure_workflow_handoffs(agents)
    max_round = 1 + (len(WORKFLOW_STAGE_KEYS) * MAX_STAGE_ATTEMPTS * 3) + 2
    return DefaultPattern(
        initial_agent=agents["admin"],
        agents=list(agents.values()),
        context_variables=ContextVariables.from_dict({WORKFLOW_COMPLETE_KEY: False}),
        group_manager_args={
            "llm_config": False,
            "human_input_mode": "NEVER",
            "silent": True,
            "max_consecutive_auto_reply": max_round,
            "system_message": (
                "You are the AG2 workflow manager. Enforce agent handoffs, tool execution, and termination."
            ),
        },
    )


def _configure_workflow_handoffs(agents: dict[str, autogen.ConversableAgent]) -> None:
    for agent in agents.values():
        agent.handoffs.clear()

    agents["admin"].handoffs.add_after_works(
        [
            OnContextCondition(
                target=TerminateTarget(),
                condition=ExpressionContextCondition(ContextExpression(f"${{{WORKFLOW_COMPLETE_KEY}}} == True")),
            ),
            OnContextCondition(target=AgentNameTarget(agents["concierge"].name), condition=None),
        ]
    )

    ordered_pairs = [
        ("concierge", "concierge_critic"),
        ("company_intelligence", "company_intelligence_critic"),
        ("strategic_signals", "strategic_signals_critic"),
        ("market_network", "market_network_critic"),
        ("evidence_qa", "evidence_qa_critic"),
        ("synthesis", "synthesis_critic"),
    ]

    agents["repair_planner"].handoffs.set_after_work(
        FunctionTarget(
            _route_repair_plan,
        )
    )

    for index, (producer_key, critic_key) in enumerate(ordered_pairs):
        producer = agents[producer_key]
        critic = agents[critic_key]
        next_target_name = (
            agents["admin"].name if index == len(ordered_pairs) - 1 else agents[ordered_pairs[index + 1][0]].name
        )
        is_final_stage = index == len(ordered_pairs) - 1

        producer.handoffs.set_after_work(
            FunctionTarget(
                _pre_critic_check,
                extra_args={
                    "stage_key": producer_key,
                    "producer_name": producer.name,
                    "critic_name": critic.name,
                    "next_target_name": next_target_name,
                    "attempts_key": f"{producer_key}_attempts",
                    "complete_workflow": is_final_stage,
                },
            )
        )
        critic.handoffs.set_after_work(
            FunctionTarget(
                _route_stage_review,
                extra_args={
                    "stage_key": producer_key,
                    "producer_name": producer.name,
                    "next_target_name": next_target_name,
                    "attempts_key": f"{producer_key}_attempts",
                    "complete_workflow": is_final_stage,
                    "repair_planner_name": agents["repair_planner"].name,
                },
            )
        )


def _parse_review_feedback_message(content: str) -> dict[str, Any]:
    payload = _extract_json_payload(content)
    if payload is None:
        return {
            "approved": False,
            "issues": [],
            "revision_instructions": [],
            "field_issues": [],
        }

    try:
        review = ReviewFeedback.model_validate(payload)
    except Exception:
        return {
            "approved": False,
            "issues": [],
            "revision_instructions": [],
            "field_issues": [],
        }

    return {
        "approved": bool(review.approved),
        "issues": list(review.issues),
        "revision_instructions": list(review.revision_instructions),
        "field_issues": [item.model_dump(mode="json") for item in review.field_issues],
    }


def _parse_repair_plan_message(content: str) -> dict[str, Any] | None:
    payload = _extract_json_payload(content)
    if payload is None:
        return None

    try:
        plan = RepairPlan.model_validate(payload)
    except Exception:
        return None

    return plan.model_dump(mode="json")


def _is_upstream_owned_evidence_qa_feedback(review: dict[str, Any]) -> bool:
    """Detect critic rejections that complain about upstream gaps instead of QA-output defects."""
    field_issues = review.get("field_issues", [])
    if not isinstance(field_issues, list):
        field_issues = []

    evidence_qa_owned_prefixes = (
        "validated_agents",
        "evidence_health",
        "open_gaps",
        "recommendations",
        "gap_details",
        "root",
    )
    upstream_owned_prefixes = (
        "CompanyIntelligence.",
        "StrategicSignals.",
        "MarketNetwork.",
        "Concierge.",
        "Synthesis.",
    )

    has_upstream_only_field_issues = False
    for item in field_issues:
        if not isinstance(item, dict):
            continue
        field_path = str(item.get("field_path", "") or "").strip()
        if not field_path:
            continue
        if field_path.startswith(evidence_qa_owned_prefixes):
            return False
        if field_path.startswith(upstream_owned_prefixes):
            has_upstream_only_field_issues = True

    combined_text = " ".join(
        [
            *[str(value) for value in review.get("issues", []) if value],
            *[str(value) for value in review.get("revision_instructions", []) if value],
        ]
    ).lower()

    qa_output_markers = (
        "gap_details",
        "open_gaps",
        "recommendations",
        "validated_agents",
        "evidence_health",
        "field_path",
        "summary",
        "schema",
        "structured output",
    )
    upstream_gap_markers = (
        "companyintelligence",
        "strategicsignals",
        "marketnetwork",
        "founding year",
        "key leadership",
        "key executives",
        "market size",
        "growth rate",
        "demand outlook",
        "peer competitors",
        "downstream buyers",
        "service providers",
    )

    if any(marker in combined_text for marker in qa_output_markers):
        return False
    if has_upstream_only_field_issues:
        return True
    return any(marker in combined_text for marker in upstream_gap_markers)


def _pre_critic_check(
    output: str,
    context_variables: ContextVariables,
    stage_key: str,
    producer_name: str,
    critic_name: str,
    next_target_name: str,
    attempts_key: str,
    complete_workflow: bool = False,
) -> FunctionTargetResult:
    field_issues = _validate_pre_critic_output(stage_key, output)
    field_issues.extend(_validate_runtime_stage_requirements(stage_key, context_variables, output))
    if not field_issues:
        return FunctionTargetResult(target=AgentNameTarget(critic_name))

    attempts = int(context_variables.get(attempts_key, 0) or 0) + 1
    updated_context = _context_with_updates(
        context_variables,
        {
            attempts_key: attempts,
            f"{producer_name}_approved": False,
            WORKFLOW_COMPLETE_KEY: False,
            **(
                {
                    STRATEGIC_SIGNALS_ATTEMPT_CYCLE_KEY: int(
                        context_variables.get(STRATEGIC_SIGNALS_ATTEMPT_CYCLE_KEY, 0) or 0
                    )
                    + 1,
                    "strategic_signals_tool_calls": 0,
                }
                if stage_key == "strategic_signals"
                else {}
            ),
        },
    )

    if attempts >= MAX_STAGE_ATTEMPTS:
        return FunctionTargetResult(
            messages=(
                f"Terminate workflow. {producer_name} exhausted {MAX_STAGE_ATTEMPTS} attempts "
                "without a schema-valid producer output."
            ),
            context_variables=updated_context,
            target=TerminateTarget(),
        )

    return FunctionTargetResult(
        messages=_build_pre_critic_feedback(field_issues),
        context_variables=updated_context,
        target=AgentNameTarget(producer_name),
    )


def _route_stage_review(
    output: str,
    context_variables: ContextVariables,
    stage_key: str,
    producer_name: str,
    next_target_name: str,
    attempts_key: str,
    complete_workflow: bool = False,
    repair_planner_name: str = "RepairPlanner",
) -> FunctionTargetResult:
    review = _parse_review_feedback_message(output)
    if producer_name == "EvidenceQA" and not review["approved"] and _is_upstream_owned_evidence_qa_feedback(review):
        review["approved"] = True
    attempts = int(context_variables.get(attempts_key, 0) or 0) + 1

    updated_context = _context_with_updates(
        context_variables,
        {
            attempts_key: attempts,
            f"{producer_name}_approved": bool(review["approved"]),
            WORKFLOW_COMPLETE_KEY: bool(complete_workflow and review["approved"]),
        },
    )

    if review["approved"] and complete_workflow:
        updated_context.set(WORKFLOW_COMPLETE_KEY, True)
        return FunctionTargetResult(
            messages=None,
            context_variables=updated_context,
            target=TerminateTarget(),
        )

    if review["approved"] or attempts >= MAX_STAGE_ATTEMPTS:
        return FunctionTargetResult(
            messages=(
                None
                if review["approved"]
                else (
                    f"Terminate workflow. {producer_name} exhausted {MAX_STAGE_ATTEMPTS} attempts "
                    "without critic approval."
                )
            ),
            context_variables=updated_context,
            target=AgentNameTarget(next_target_name) if review["approved"] else TerminateTarget(),
        )

    updated_context.set(ACTIVE_REPAIR_PRODUCER_KEY, producer_name)
    updated_context.set(ACTIVE_REPAIR_STAGE_KEY, stage_key)
    updated_context.set(ACTIVE_REPAIR_REVIEW_KEY, output)
    return FunctionTargetResult(
        messages=_build_repair_planning_message(
            review_content=output,
            producer_name=producer_name,
            stage_key=stage_key,
        ),
        context_variables=updated_context,
        target=AgentNameTarget(repair_planner_name),
    )


def _route_repair_plan(
    output: str,
    context_variables: ContextVariables,
) -> FunctionTargetResult:
    producer_name = str(context_variables.get(ACTIVE_REPAIR_PRODUCER_KEY, "") or "").strip()
    stage_key = str(context_variables.get(ACTIVE_REPAIR_STAGE_KEY, "") or "").strip()
    review_content = str(context_variables.get(ACTIVE_REPAIR_REVIEW_KEY, "") or "")
    plan = _parse_repair_plan_message(output)

    if producer_name not in ALLOWED_PRODUCER_NAMES:
        return FunctionTargetResult(
            messages=(
                "Terminate workflow. RepairPlanner did not receive a valid producer target in context."
            ),
            context_variables=_context_with_updates(context_variables, {WORKFLOW_COMPLETE_KEY: False}),
            target=TerminateTarget(),
        )

    if not plan or plan.get("producer_name") != producer_name or plan.get("stage_key") != stage_key:
        repair_message = _build_revision_message(review_content or output)
    else:
        repair_message = _build_repair_execution_message(plan)

    updated_context = _context_with_updates(
        context_variables,
        {
            ACTIVE_REPAIR_PRODUCER_KEY: "",
            ACTIVE_REPAIR_STAGE_KEY: "",
            ACTIVE_REPAIR_REVIEW_KEY: "",
        },
    )
    return FunctionTargetResult(
        messages=repair_message,
        context_variables=updated_context,
        target=AgentNameTarget(producer_name),
    )


def _build_revision_message(content: str) -> str:
    try:
        payload = _extract_json_payload(content)
        if payload is None:
            raise ValueError("No structured review payload found.")
        review = ReviewFeedback.model_validate(payload)
    except Exception:
        return (
            "Revise your previous structured output. The critic did not approve it. "
            "Be more conservative, fix missing required fields, and do not invent unsupported evidence."
        )

    parts: list[str] = ["Revise your previous structured output using the critic feedback below."]
    if review.issues:
        parts.append("Issues: " + " | ".join(review.issues))
    if review.revision_instructions:
        parts.append("Instructions: " + " | ".join(review.revision_instructions))
    if review.field_issues:
        parts.append(
            "Field issues: "
            + " | ".join(
                f"{item.field_path or 'general'} -> {item.summary}"
                for item in review.field_issues
            )
        )
        focus_fields = [item.field_path for item in review.field_issues if item.field_path]
        if focus_fields:
            parts.append("Focus especially on: " + ", ".join(dict.fromkeys(focus_fields)))
        targeted_actions = [item.recommendation for item in review.field_issues if item.recommendation]
        if targeted_actions:
            parts.append("Targeted fixes: " + " | ".join(dict.fromkeys(targeted_actions)))
    parts.append("Keep the same schema and stay conservative about uncertainty.")
    return "\n".join(parts)


def _build_repair_planning_message(review_content: str, producer_name: str, stage_key: str) -> str:
    primary_task = STAGE_PRIMARY_TASKS.get(stage_key, "Keep the original producer task stable.")
    base_feedback = _build_revision_message(review_content)
    return (
        f"Prepare a RepairPlan for producer '{producer_name}'.\n"
        f"stage_key: {stage_key}\n"
        f"primary_task: {primary_task}\n\n"
        "Turn the critic feedback below into a bounded repair plan. Preserve the primary_task, keep the "
        "repair focused, and use n/v or empty lists for unresolved points instead of escalating unsupported claims.\n\n"
        f"{base_feedback}"
    )


def _build_repair_execution_message(plan: dict[str, Any]) -> str:
    producer_name = str(plan.get("producer_name", "") or "").strip()
    primary_task = str(plan.get("primary_task", "") or "").strip()
    subtask_delta = [str(item).strip() for item in plan.get("subtask_delta", []) if str(item).strip()]
    constraints = [str(item).strip() for item in plan.get("constraints", []) if str(item).strip()]
    done_when = [str(item).strip() for item in plan.get("done_when", []) if str(item).strip()]

    parts = [
        f"Revise your previous structured output as {producer_name}.",
        f"Primary task: {primary_task}",
    ]
    if subtask_delta:
        parts.append("Subtask delta: " + " | ".join(dict.fromkeys(subtask_delta)))
    if constraints:
        parts.append("Constraints: " + " | ".join(dict.fromkeys(constraints)))
    if done_when:
        parts.append("Done when: " + " | ".join(dict.fromkeys(done_when)))
    parts.append("Keep the same schema. Stay conservative and use n/v, empty lists, or explicit uncertainty when evidence is still missing.")
    return "\n".join(parts)


def _validate_pre_critic_output(stage_key: str, content: str) -> list[ReviewFieldIssue]:
    model = PRODUCER_OUTPUT_MODELS.get(stage_key)
    if model is None:
        return []

    try:
        payload = _extract_json_payload(content)
        if payload is None:
            raise ValueError("No structured JSON object found in the agent output.")
        validated = model.model_validate(payload)
    except Exception as exc:
        return [
            ReviewFieldIssue(
                field_path="root",
                issue_type="schema_validation_error",
                summary=f"Structured output failed validation: {exc}",
                recommendation="Return valid structured JSON matching the configured schema.",
            )
        ]

    issues: list[ReviewFieldIssue] = []
    payload = validated.model_dump(mode="json")
    if stage_key == "strategic_signals":
        issues.extend(_validate_strategic_signals_pre_critic(payload))
    elif stage_key == "market_network":
        issues.extend(_validate_market_network_pre_critic(payload))
    elif stage_key == "synthesis":
        issues.extend(_validate_synthesis_pre_critic(payload))
    elif stage_key == "evidence_qa":
        issues.extend(_validate_evidence_qa_pre_critic(payload))
    return issues


def _validate_runtime_stage_requirements(
    stage_key: str,
    context_variables: ContextVariables,
    content: str,
) -> list[ReviewFieldIssue]:
    return []


def _validate_strategic_signals_pre_critic(payload: dict[str, object]) -> list[ReviewFieldIssue]:
    issues: list[ReviewFieldIssue] = []
    sources = payload.get("sources", [])
    if not isinstance(sources, list):
        return issues

    if _sources_lack_external_market_evidence(sources):
        issues.append(
            ReviewFieldIssue(
                field_path="sources",
                issue_type="missing_external_market_sources",
                summary="StrategicSignals needs at least one external market or trade-publication source; company and encyclopedia sources alone are not enough.",
                recommendation="Add a direct external market source or leave sources empty and finalize with n/v and explicitly limited assessment.",
            )
        )
        if any(str(item).strip() for item in payload.get("key_trends", []) if str(item).strip()):
            issues.append(
                ReviewFieldIssue(
                    field_path="key_trends",
                    issue_type="unsupported_market_trends",
                    summary="key_trends should not be presented as industry trends when only company or encyclopedia sources are available.",
                    recommendation="Remove unsupported industry trend claims or replace them with conservative n/v/empty outputs until external market evidence is available.",
                )
            )
        if any(str(item).strip() for item in payload.get("overcapacity_signals", []) if str(item).strip()):
            issues.append(
                ReviewFieldIssue(
                    field_path="overcapacity_signals",
                    issue_type="unsupported_overcapacity_signals",
                    summary="Overcapacity signals require external industry evidence and should not be asserted from company or encyclopedia sources alone.",
                    recommendation="Keep overcapacity_signals empty unless a direct external industry source supports them.",
                )
            )
        if str(payload.get("excess_stock_indicators", "") or "").strip() not in {"", "n/v"}:
            issues.append(
                ReviewFieldIssue(
                    field_path="excess_stock_indicators",
                    issue_type="unsupported_excess_stock_indicators",
                    summary="Excess stock indicators need external market evidence and should stay at n/v without it.",
                    recommendation="Set excess_stock_indicators to n/v until direct market evidence is available.",
                )
            )
    return issues


def _sources_lack_external_market_evidence(sources: list[object]) -> bool:
    if not sources:
        return False
    saw_source = False
    for source in sources:
        if not isinstance(source, dict):
            return False
        url = str(source.get("url", "") or "").strip()
        host = _host_for_url(url).removeprefix("www.")
        if not host:
            return False
        saw_source = True
        if host.endswith("wikipedia.org"):
            continue
        if _looks_like_company_or_owned_source(source, host):
            continue
        return False
    return saw_source


def _looks_like_company_or_owned_source(source: dict[str, object], host: str) -> bool:
    publisher = str(source.get("publisher", "") or "").strip().lower()
    title = str(source.get("title", "") or "").strip().lower()
    if any(marker in publisher for marker in ("official website", "homepage", "press center", "press release")):
        return True
    if any(marker in title for marker in ("homepage", "press center", "annual report", "sustainability report")):
        return True
    companyish_hosts = (
        "zf.com",
        "aftermarket.zf.com",
    )
    return any(host == item or host.endswith(f".{item}") for item in companyish_hosts)


def _host_for_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    candidate = text if "://" in text else f"https://{text}"
    try:
        return urlparse(candidate).netloc.strip().lower()
    except ValueError:
        return ""


def _validate_market_network_pre_critic(payload: dict[str, object]) -> list[ReviewFieldIssue]:
    issues: list[ReviewFieldIssue] = []
    for tier_name in (
        "peer_competitors",
        "downstream_buyers",
        "service_providers",
        "cross_industry_buyers",
    ):
        tier = payload.get(tier_name, {})
        if not isinstance(tier, dict):
            continue
        companies = tier.get("companies", [])
        if not isinstance(companies, list):
            continue
        for index, buyer in enumerate(companies):
            if not isinstance(buyer, dict):
                continue
            source = buyer.get("source")
            if not isinstance(source, dict) or not str(source.get("url", "") or "").strip():
                issues.append(
                    ReviewFieldIssue(
                        field_path=f"{tier_name}.companies[{index}].source",
                        issue_type="missing_buyer_source",
                        summary=f"{buyer.get('name', 'Buyer')} is missing a concrete buyer-level source.",
                        recommendation="Add a concrete source for this buyer or remove the buyer from the tier.",
                    )
                )
    return issues


def _validate_synthesis_pre_critic(payload: dict[str, object]) -> list[ReviewFieldIssue]:
    issues: list[ReviewFieldIssue] = []
    case_assessments = payload.get("case_assessments", [])
    if isinstance(case_assessments, list):
        for case_index, case in enumerate(case_assessments):
            if not isinstance(case, dict):
                continue
            arguments = case.get("arguments", [])
            if not isinstance(arguments, list):
                continue
            for arg_index, argument in enumerate(arguments):
                if not isinstance(argument, dict):
                    continue
                if not str(argument.get("based_on", "") or "").strip():
                    issues.append(
                        ReviewFieldIssue(
                            field_path=f"case_assessments[{case_index}].arguments[{arg_index}].based_on",
                            issue_type="missing_based_on",
                            summary="Case assessment argument is missing its based_on reference.",
                            recommendation="Populate based_on with the upstream section, signal, or artifact supporting this argument.",
                        )
                    )
    return issues


def _validate_evidence_qa_pre_critic(payload: dict[str, object]) -> list[ReviewFieldIssue]:
    issues: list[ReviewFieldIssue] = []
    gap_details = payload.get("gap_details", [])
    if isinstance(gap_details, list):
        for index, detail in enumerate(gap_details):
            if not isinstance(detail, dict):
                continue
            if not str(detail.get("summary", "") or "").strip():
                issues.append(
                    ReviewFieldIssue(
                        field_path=f"gap_details[{index}].summary",
                        issue_type="missing_gap_summary",
                        summary="QA gap detail is missing a summary.",
                        recommendation="Provide a concise summary for each structured QA gap detail.",
                    )
                )
    return issues


def _build_pre_critic_feedback(field_issues: list[ReviewFieldIssue]) -> str:
    parts = [
        "Revise your previous structured output before critic review.",
        "The deterministic pre-check found fixable schema or field issues.",
    ]
    parts.append(
        "Issues: " + " | ".join(
            f"{item.field_path or 'general'} -> {item.summary}"
            for item in field_issues
        )
    )
    recommendations = [item.recommendation for item in field_issues if item.recommendation]
    if recommendations:
        parts.append("Fixes: " + " | ".join(dict.fromkeys(recommendations)))
    parts.append("Keep the same schema and stay conservative about uncertainty.")
    return "\n".join(parts)


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    objects = _extract_json_objects(text)
    if not objects:
        return None
    for payload in reversed(objects):
        if isinstance(payload, dict):
            return payload
    return None


def _extract_json_objects(text: str) -> list[Any]:
    if not text:
        return []

    objects: list[Any] = []
    decoder = json.JSONDecoder()
    index = 0
    length = len(text)

    while index < length:
        start = text.find("{", index)
        if start < 0:
            break
        try:
            payload, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        objects.append(payload)
        index = start + end

    if objects:
        return objects

    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if not match:
        return []
    try:
        payload = json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError):
        return []
    return [payload]


def _contains_multiple_json_objects(text: str) -> bool:
    return len(_extract_json_objects(text)) > 1
