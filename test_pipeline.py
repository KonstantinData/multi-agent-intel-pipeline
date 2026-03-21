"""Targeted tests for the AG2-native Liquisto pipeline."""
from __future__ import annotations

import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import autogen
from autogen.exception_utils import NoEligibleSpeakerError
from autogen.agentchat.group import ContextVariables

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.agents.definitions import (
    ENFORCE_STRATEGIC_SIGNALS_SOURCE_PACK_KEY,
    MARKET_NETWORK_MAX_STAGE_TOOL_CALLS,
    MAX_STAGE_ATTEMPTS,
    STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS,
    _extract_json_payload,
    _pre_critic_check,
    _build_revision_message,
    _env_int_with_min as _definitions_env_int_with_min,
    _validate_pre_critic_output,
    _web_search_market_network,
    _web_search_strategic_signals,
    create_agents,
    create_group_pattern,
)
from src.exporters.pdf_report import generate_pdf
from src.pipeline_runner import (
    COMPANY_INTELLIGENCE_MAX_STAGE_TOOL_CALLS,
    COMPANY_INTELLIGENCE_MAX_CONSECUTIVE_TOOL_TURNS,
    PreparedGroupChat,
    _assess_research_usability,
    _build_incomplete_run_message,
    _count_tool_calls_from_chat_messages,
    _detect_duplicate_structured_producer_turn,
    _detect_stalled_tool_agent,
    _env_int_with_min as _runner_env_int_with_min,
    _inject_missing_critic_turn,
    _collect_usage_summary,
    _extract_pipeline_data,
    _prepare_group_chat,
    _request_group_chat_stop,
    _resolve_group_chat_entrypoint,
    _should_auto_resume_groupchat,
    _try_parse_json,
    _workflow_completed,
)
from src.tools.research import _build_buyer_queries, _build_company_queries, _build_industry_queries
import src.tools.research as research_module
from src.config.settings import get_llm_config, get_model_selection


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _concierge_reply() -> str:
    return json.dumps(
        {
            "company_name": "imsgear SE",
            "web_domain": "imsgear.com",
            "language": "de",
            "observations": ["Website reachable."],
        }
    )


def _company_reply(revenue: str = "n/v") -> str:
    return json.dumps(
        {
            "company_name": "IMS Gear SE & Co. KGaA",
            "legal_form": "SE & Co. KGaA",
            "founded": "1863",
            "headquarters": "Donaueschingen, Germany",
            "website": "https://www.imsgear.com",
            "industry": "Machinery/Mechanical Engineering",
            "employees": "2775",
            "revenue": revenue,
            "products_and_services": ["Gear components", "Transmission systems"],
            "key_people": [{"name": "Bernd Schilling", "role": "Managing Director"}],
            "description": "IMS Gear manufactures gears and transmission technology.",
            "economic_situation": {
                "revenue_trend": "n/v",
                "profitability": "n/v",
                "recent_events": [],
                "inventory_signals": [],
                "financial_pressure": "n/v",
                "assessment": "n/v",
            },
            "sources": [],
        }
    )


def _invalid_company_reply() -> str:
    payload = json.loads(_company_reply())
    payload.pop("company_name", None)
    return json.dumps(payload)


def _industry_reply() -> str:
    return json.dumps(
        {
            "industry_name": "Machinery/Mechanical Engineering",
            "market_size": "n/v",
            "trend_direction": "unsicher",
            "growth_rate": "n/v",
            "key_trends": [],
            "overcapacity_signals": [],
            "excess_stock_indicators": "n/v",
            "demand_outlook": "n/v",
            "assessment": "n/v",
            "sources": [],
        }
    )


def _market_reply() -> str:
    empty_tier = {"companies": [], "assessment": "n/v", "sources": []}
    return json.dumps(
        {
            "target_company": "IMS Gear SE & Co. KGaA",
            "peer_competitors": empty_tier,
            "downstream_buyers": empty_tier,
            "service_providers": empty_tier,
            "cross_industry_buyers": empty_tier,
        }
    )


def _qa_reply() -> str:
    return json.dumps(
        {
            "validated_agents": ["Concierge", "CompanyIntelligence"],
            "evidence_health": "mittel",
            "open_gaps": ["No fresh revenue evidence."],
            "recommendations": ["Keep unsupported values at n/v."],
            "gap_details": [
                {
                    "agent": "CompanyIntelligence",
                    "field_path": "revenue",
                    "issue_type": "stale_sources",
                    "severity": "significant",
                    "summary": "Revenue is unsupported by fresh primary sources.",
                    "recommendation": "Refresh revenue evidence or set the field to n/v.",
                }
            ],
        }
    )


def _synthesis_reply() -> str:
    return json.dumps(
        {
            "target_company": "IMS Gear SE & Co. KGaA",
            "executive_summary": "IMS Gear is a mechanical engineering company with limited current financial evidence.",
            "liquisto_service_relevance": [
                {"service_area": "excess_inventory", "relevance": "unklar", "reasoning": "Insufficient proof."}
            ],
            "case_assessments": [
                {
                    "option": "kaufen",
                    "arguments": [
                        {
                            "argument": "Potential aftermarket relevance exists.",
                            "direction": "pro",
                            "based_on": "MarketNetwork",
                        }
                    ],
                    "summary": "Only a tentative case can be made.",
                }
            ],
            "buyer_market_summary": "Buyer evidence is weak.",
            "total_peer_competitors": 0,
            "total_downstream_buyers": 0,
            "total_service_providers": 0,
            "total_cross_industry_buyers": 0,
            "key_risks": ["Evidence is weak."],
            "next_steps": ["Research fresh primary sources."],
            "sources": [],
        }
    )


def _review(approved: bool, issue: str = "", instruction: str = "", field_issues=None) -> str:
    payload = {
        "approved": approved,
        "issues": [issue] if issue else [],
        "revision_instructions": [instruction] if instruction else [],
        "field_issues": field_issues or [],
    }
    return json.dumps(payload)


def _repair_reply(producer_name: str, stage_key: str) -> str:
    return json.dumps(
        {
            "producer_name": producer_name,
            "stage_key": stage_key,
            "primary_task": f"Repair the {stage_key} submission without changing its overall mandate.",
            "subtask_delta": ["Fix only the critic-flagged gaps.", "Downgrade unsupported fields to n/v or empty lists."],
            "constraints": ["Do not invent evidence.", "Keep the schema unchanged."],
            "done_when": ["The flagged fields are corrected conservatively.", "No unsupported upgrade remains."],
        }
    )


class SequenceAgent(autogen.ConversableAgent):
    def __init__(self, name: str, replies: list[str]):
        super().__init__(name=name, llm_config=False, human_input_mode="NEVER")
        self._replies = list(replies)
        self.calls = 0

    def generate_reply(self, messages=None, sender=None, exclude=()):  # type: ignore[override]
        self.calls += 1
        if not self._replies:
            raise RuntimeError(f"{self.name} has no reply configured for call {self.calls}")
        return self._replies.pop(0)


class FakeUsageAgent:
    def __init__(self, actual=None, total=None):
        self._actual = actual
        self._total = total

    def get_actual_usage(self):
        return self._actual

    def get_total_usage(self):
        return self._total


def _workflow_agents(*, company_replies=None, company_critic_replies=None) -> dict[str, autogen.ConversableAgent]:
    return {
        "admin": autogen.ConversableAgent(
            name="Admin",
            llm_config=False,
            human_input_mode="NEVER",
            default_auto_reply="Admin acknowledged. Proceed with the configured workflow.",
        ),
        "concierge": SequenceAgent("Concierge", [_concierge_reply()]),
        "concierge_critic": SequenceAgent("ConciergeCritic", [_review(True)]),
        "repair_planner": SequenceAgent("RepairPlanner", [_repair_reply("CompanyIntelligence", "company_intelligence")]),
        "company_intelligence": SequenceAgent(
            "CompanyIntelligence",
            company_replies or [_company_reply()],
        ),
        "company_intelligence_critic": SequenceAgent(
            "CompanyIntelligenceCritic",
            company_critic_replies or [_review(True)],
        ),
        "strategic_signals": SequenceAgent("StrategicSignals", [_industry_reply()]),
        "strategic_signals_critic": SequenceAgent("StrategicSignalsCritic", [_review(True)]),
        "market_network": SequenceAgent("MarketNetwork", [_market_reply()]),
        "market_network_critic": SequenceAgent("MarketNetworkCritic", [_review(True)]),
        "evidence_qa": SequenceAgent("EvidenceQA", [_qa_reply()]),
        "evidence_qa_critic": SequenceAgent("EvidenceQACritic", [_review(True)]),
        "synthesis": SequenceAgent("Synthesis", [_synthesis_reply()]),
        "synthesis_critic": SequenceAgent("SynthesisCritic", [_review(True)]),
    }


def _run_pattern_chat(agents: dict[str, autogen.ConversableAgent], message: str):
    pattern = create_group_pattern(agents)
    prepared_chat = _prepare_group_chat(pattern, max_rounds=20, messages=message)
    sender, initial_message, clear_history = _resolve_group_chat_entrypoint(
        prepared_chat,
        fallback_message=message,
    )
    return sender.initiate_chat(
        prepared_chat.manager,
        message=initial_message,
        clear_history=clear_history,
        summary_method=pattern.summary_method,
        silent=True,
    )


def test_groupchat_routes_full_workflow_in_order():
    agents = _workflow_agents()
    result = _run_pattern_chat(agents, "Research imsgear.com")

    workflow_names = {
        "Admin",
        "Concierge",
        "ConciergeCritic",
        "RepairPlanner",
        "CompanyIntelligence",
        "CompanyIntelligenceCritic",
        "StrategicSignals",
        "StrategicSignalsCritic",
        "MarketNetwork",
        "MarketNetworkCritic",
        "EvidenceQA",
        "EvidenceQACritic",
        "Synthesis",
        "SynthesisCritic",
    }
    actual_order = [msg["name"] for msg in result.chat_history if msg.get("name") in workflow_names]
    expected_order = [
        "Admin",
        "Concierge",
        "ConciergeCritic",
        "CompanyIntelligence",
        "CompanyIntelligenceCritic",
        "StrategicSignals",
        "StrategicSignalsCritic",
        "MarketNetwork",
        "MarketNetworkCritic",
        "EvidenceQA",
        "EvidenceQACritic",
        "Synthesis",
        "SynthesisCritic",
    ]
    assert actual_order == expected_order
    assert actual_order[-1] == "SynthesisCritic"


def test_groupchat_retries_same_producer_after_critic_rejection():
    agents = _workflow_agents(
        company_replies=[_company_reply("EUR 124m"), _company_reply("n/v")],
        company_critic_replies=[
            _review(False, "Revenue unsupported.", "Set unsupported revenue to n/v."),
            _review(True),
        ],
    )
    agents["repair_planner"] = SequenceAgent(
        "RepairPlanner",
        [_repair_reply("CompanyIntelligence", "company_intelligence")],
    )
    result = _run_pattern_chat(agents, "Research imsgear.com")

    workflow_names = {
        "Admin",
        "Concierge",
        "ConciergeCritic",
        "RepairPlanner",
        "CompanyIntelligence",
        "CompanyIntelligenceCritic",
        "StrategicSignals",
        "StrategicSignalsCritic",
        "MarketNetwork",
        "MarketNetworkCritic",
        "EvidenceQA",
        "EvidenceQACritic",
        "Synthesis",
        "SynthesisCritic",
    }
    order = [msg["name"] for msg in result.chat_history if msg.get("name") in workflow_names]
    company_indexes = [index for index, name in enumerate(order) if name == "CompanyIntelligence"]
    assert len(company_indexes) == 2
    assert order[company_indexes[0] + 1] == "CompanyIntelligenceCritic"
    assert order[company_indexes[0] + 2] == "RepairPlanner"
    assert order[company_indexes[1] - 1] == "RepairPlanner"
    assert "StrategicSignals" in order[company_indexes[1] + 1 :]


def test_groupchat_retries_same_producer_before_critic_on_precheck_failure():
    agents = _workflow_agents(
        company_replies=[_invalid_company_reply(), _company_reply()],
        company_critic_replies=[_review(True)],
    )
    result = _run_pattern_chat(agents, "Research imsgear.com")

    workflow_names = {
        "Admin",
        "Concierge",
        "ConciergeCritic",
        "CompanyIntelligence",
        "CompanyIntelligenceCritic",
        "StrategicSignals",
        "StrategicSignalsCritic",
        "MarketNetwork",
        "MarketNetworkCritic",
        "EvidenceQA",
        "EvidenceQACritic",
        "Synthesis",
        "SynthesisCritic",
    }
    order = [msg["name"] for msg in result.chat_history if msg.get("name") in workflow_names]
    company_indexes = [index for index, name in enumerate(order) if name == "CompanyIntelligence"]
    assert len(company_indexes) == 2
    assert order[company_indexes[0] + 1] == "CompanyIntelligence"
    assert order[company_indexes[1] + 1] == "CompanyIntelligenceCritic"


def test_groupchat_terminates_after_repeated_precheck_failures():
    agents = _workflow_agents(
        company_replies=[_invalid_company_reply() for _ in range(MAX_STAGE_ATTEMPTS)],
    )
    result = _run_pattern_chat(agents, "Research imsgear.com")

    workflow_names = {
        "Admin",
        "Concierge",
        "ConciergeCritic",
        "CompanyIntelligence",
        "CompanyIntelligenceCritic",
        "StrategicSignals",
    }
    order = [msg["name"] for msg in result.chat_history if msg.get("name") in workflow_names]
    assert order.count("CompanyIntelligence") == MAX_STAGE_ATTEMPTS
    assert "CompanyIntelligenceCritic" not in order
    assert "StrategicSignals" not in order


def test_groupchat_terminates_after_repeated_critic_rejections():
    agents = _workflow_agents(
        company_replies=[_company_reply() for _ in range(MAX_STAGE_ATTEMPTS)],
        company_critic_replies=[_review(False, issue="Unsupported.", instruction="Tighten.") for _ in range(MAX_STAGE_ATTEMPTS)],
    )
    agents["repair_planner"] = SequenceAgent(
        "RepairPlanner",
        [_repair_reply("CompanyIntelligence", "company_intelligence") for _ in range(MAX_STAGE_ATTEMPTS - 1)],
    )
    result = _run_pattern_chat(agents, "Research imsgear.com")

    workflow_names = {
        "Admin",
        "Concierge",
        "ConciergeCritic",
        "CompanyIntelligence",
        "CompanyIntelligenceCritic",
        "StrategicSignals",
    }
    order = [msg["name"] for msg in result.chat_history if msg.get("name") in workflow_names]
    assert order.count("CompanyIntelligence") == MAX_STAGE_ATTEMPTS
    assert order.count("CompanyIntelligenceCritic") == MAX_STAGE_ATTEMPTS
    assert "StrategicSignals" not in order


def test_evidence_qa_upstream_gap_rejection_does_not_block_synthesis():
    agents = _workflow_agents()
    agents["evidence_qa_critic"] = SequenceAgent(
        "EvidenceQACritic",
        [
            _review(
                False,
                issue="CompanyIntelligence output is missing foundational information such as the founding year.",
                instruction="For CompanyIntelligence, add the founding year and key executive information.",
                field_issues=[
                    {
                        "field_path": "CompanyIntelligence.founded",
                        "issue_type": "missing_information",
                        "summary": "Missing founding year of the company.",
                        "recommendation": "Add founding year.",
                    },
                    {
                        "field_path": "MarketNetwork.peer_competitors.companies",
                        "issue_type": "missing_evidence",
                        "summary": "No verified peer competitors identified.",
                        "recommendation": "Add documented peer competitors.",
                    },
                ],
            )
        ],
    )

    result = _run_pattern_chat(agents, "Research imsgear.com")

    workflow_names = {
        "Admin",
        "Concierge",
        "ConciergeCritic",
        "CompanyIntelligence",
        "CompanyIntelligenceCritic",
        "StrategicSignals",
        "StrategicSignalsCritic",
        "MarketNetwork",
        "MarketNetworkCritic",
        "EvidenceQA",
        "EvidenceQACritic",
        "Synthesis",
        "SynthesisCritic",
    }
    order = [msg["name"] for msg in result.chat_history if msg.get("name") in workflow_names]
    assert "Synthesis" in order
    assert order[-1] == "SynthesisCritic"


def test_company_intelligence_tools_stay_narrow():
    agents = create_agents()
    tool_names = set(agents["company_intelligence"].function_map.keys())
    assert tool_names == {"company_source_pack", "company_fetch_page", "company_web_search"}


def test_stage_specific_tool_names_are_unique_across_agents():
    agents = create_agents()
    assert set(agents["strategic_signals"].function_map.keys()) == {
        "industry_source_pack",
        "strategic_fetch_page",
        "strategic_web_search",
    }
    assert set(agents["market_network"].function_map.keys()) == {
        "buyer_source_pack",
        "market_fetch_page",
        "market_web_search",
    }


def test_company_intelligence_agent_local_tool_cap_blocks_repeated_source_pack():
    agents = create_agents()
    company_source_pack_tool = agents["company_intelligence"].function_map["company_source_pack"]

    first = ast.literal_eval(
        company_source_pack_tool(company_name="IMS Gear", domain="imsgear.com", max_results=1)
    )
    second = ast.literal_eval(
        company_source_pack_tool(company_name="IMS Gear", domain="imsgear.com", max_results=1)
    )

    assert "error" not in first or first["error"] != "company intelligence stage tool budget exhausted"
    assert second["error"] == "company intelligence stage tool budget exhausted"
    assert second["tool_name"] == "company_source_pack"


def test_strategic_signals_stage_budget_stops_extra_tool_turns_before_network():
    class DummyContext:
        def __init__(self):
            self.values = {"strategic_signals_tool_calls": STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS}

        def get(self, key, default=None):
            return self.values.get(key, default)

        def set(self, key, value):
            self.values[key] = value

    result = _web_search_strategic_signals(
        query="gear market report",
        context_variables=DummyContext(),
    )

    assert result["error"] == "strategic signals stage tool budget exhausted"
    assert result["tool_name"] == "web_search"
    assert result["max_stage_tool_calls"] == STRATEGIC_SIGNALS_MAX_STAGE_TOOL_CALLS


def test_company_source_pack_returns_homepage_seed_when_search_results_are_empty(monkeypatch):
    def fake_run_query_pack(queries, max_results, context_variables=None):
        return {"queries": queries, "results": []}

    monkeypatch.setattr(research_module, "_run_query_pack", fake_run_query_pack)

    result = research_module.company_source_pack("ZF Friedrichshafen", domain="zf.com", max_results=5)

    assert result["results"]
    queries = {item["query"] for item in result["results"]}
    urls = {item["url"] for item in result["results"]}
    assert "domain_homepage_seed" in queries
    assert "https://zf.com" in urls
    assert "domain_impressum_seed" in queries
    assert "https://zf.com/impressum" in urls
    assert "domain_company_seed" in queries or "domain_company_en_seed" in queries


def test_check_domain_consumes_one_tool_budget(monkeypatch):
    monkeypatch.setattr(
        research_module,
        "_http_get_text",
        lambda url: ("<html><title>Example</title><body>hello</body></html>", url, 200),
    )
    context = ContextVariables.from_dict({"tool_calls_used": 0})

    result = research_module.check_domain("example.com", context_variables=context)

    assert result["reachable"] is True
    assert context.get("tool_calls_used") == 1


def test_company_source_pack_consumes_one_tool_budget(monkeypatch):
    monkeypatch.setattr(
        research_module,
        "_web_search_impl",
        lambda query, site="", max_results=5: {"query": query, "site": site, "results": []},
    )
    monkeypatch.setattr(research_module, "_find_wikipedia_candidate", lambda company_name: None)
    monkeypatch.setattr(research_module, "_official_company_page_seeds", lambda company_name, domain: [])
    context = ContextVariables.from_dict({"tool_calls_used": 0})

    research_module.company_source_pack("ZF Friedrichshafen", domain="zf.com", max_results=5, context_variables=context)

    assert context.get("tool_calls_used") == 1


def test_market_network_stage_budget_stops_extra_tool_turns_before_qa():
    class DummyContext:
        def __init__(self):
            self.values = {"market_network_tool_calls": MARKET_NETWORK_MAX_STAGE_TOOL_CALLS}

        def get(self, key, default=None):
            return self.values.get(key, default)

        def set(self, key, value):
            self.values[key] = value

    result = _web_search_market_network(
        query="zf friedrichshafen aftermarket service providers",
        context_variables=DummyContext(),
    )

    assert result["error"] == "market network stage tool budget exhausted"
    assert result["tool_name"] == "web_search"
    assert result["max_stage_tool_calls"] == MARKET_NETWORK_MAX_STAGE_TOOL_CALLS


def test_research_query_builders_are_agent_specific():
    current_year = datetime.now(timezone.utc).year
    previous_year = current_year - 1
    company_queries = _build_company_queries("IMS Gear SE & Co. KGaA", "imsgear.com")
    industry_queries = _build_industry_queries(
        "IMS Gear SE & Co. KGaA",
        "Transmission Technology",
        "Planetary gear systems, Low Noise Gear Systems",
    )
    buyer_queries = _build_buyer_queries(
        "IMS Gear SE & Co. KGaA",
        "Planetary gear systems, Low Noise Gear Systems",
        "imsgear.com",
    )

    assert any("site:imsgear.com" in query for query in company_queries)
    assert any("rechtsform" in query.lower() for query in company_queries)
    assert any("hauptsitz" in query.lower() for query in company_queries)
    assert any("geschäftsbericht" in query.lower() or "annual report" in query.lower() for query in company_queries)
    assert any("vorstand" in query.lower() for query in company_queries)
    assert any("planetary gear" in query.lower() or "gearbox" in query.lower() for query in industry_queries)
    assert any("market size" in query.lower() for query in industry_queries)
    assert any("growth" in query.lower() or "wachstum" in query.lower() for query in industry_queries)
    assert any("inventory" in query.lower() for query in industry_queries)
    assert any(str(current_year) in query for query in industry_queries)
    assert any(str(previous_year) in query for query in industry_queries)
    assert any("industries served" in query.lower() for query in buyer_queries)
    assert any("customer reference" in query.lower() for query in buyer_queries)
    assert any("competitors" in query.lower() for query in buyer_queries)
    assert any("aftermarket" in query.lower() for query in buyer_queries)
    assert any("spare parts" in query.lower() for query in buyer_queries)
    assert any("site:imsgear.com" in query for query in buyer_queries)


def test_run_query_pack_filters_low_value_and_off_topic_results(monkeypatch):
    def fake_web_search(query: str, max_results: int = 3, context_variables=None):
        if "customer reference" in query.lower():
            return {
                "results": [
                    {
                        "title": "IMS ist was? - Zhihu",
                        "url": "https://www.zhihu.com/question/359103699",
                        "snippet": "IMS network explanation",
                    },
                    {
                        "title": "IMS Gear applications for e-bike drive systems",
                        "url": "https://www.imsgear.com/en/applications/e-bike",
                        "snippet": "Applications in e-bike drive systems and automotive actuators.",
                    },
                ]
            }
        return {
            "results": [
                {
                    "title": "Convertio — file converter",
                    "url": "https://convertio.com/",
                    "snippet": "Online converter.",
                },
                {
                    "title": "Planetary gearbox OEM applications",
                    "url": "https://publisher.example.com/planetary-gearbox-oem-applications",
                    "snippet": "OEM applications for planetary gearbox suppliers.",
                },
            ]
        }

    monkeypatch.setattr(research_module, "_web_search_impl", fake_web_search)

    result = research_module._run_query_pack(
        [
            '"IMS Gear SE" customer reference case study',
            '"planetary gearbox" OEM application',
        ],
        max_results=5,
    )

    urls = [item["url"] for item in result["results"]]
    assert "https://www.zhihu.com/question/359103699" not in urls
    assert "https://convertio.com/" not in urls
    assert "https://www.imsgear.com/en/applications/e-bike" in urls
    assert "https://publisher.example.com/planetary-gearbox-oem-applications" in urls


def test_web_search_filters_low_value_and_off_topic_results_globally(monkeypatch):
    bing_payload = """<?xml version="1.0" encoding="utf-8" ?>
    <rss version="2.0"><channel>
      <item>
        <title>IMS ist was? - Zhihu</title>
        <link>https://www.zhihu.com/question/359103699</link>
        <description>Off-topic result about IMS networking.</description>
      </item>
      <item>
        <title>IMS Gear company and applications</title>
        <link>https://www.imsgear.com/en/company</link>
        <description>Official company page for IMS Gear.</description>
      </item>
    </channel></rss>
    """

    def fake_http_get_text(url: str):
        if "html.duckduckgo.com" in url:
            raise Exception("HTTP Error 403: Forbidden")
        if "www.bing.com/search?format=rss" in url:
            return bing_payload, url, 200
        raise AssertionError(url)

    monkeypatch.setattr(research_module, "_http_get_text", fake_http_get_text)

    result = research_module.web_search(
        'site:imsgear.com ims gear se impressum unternehmen management jahresabschluss',
        site="imsgear.com",
        max_results=5,
    )

    urls = [item["url"] for item in result["results"]]
    assert "https://www.zhihu.com/question/359103699" not in urls
    assert "https://www.imsgear.com/en/company" in urls


def test_web_search_falls_back_to_google_news_rss(monkeypatch):
    rss_payload = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>ZF cuts debt - Example Trade</title>
      <link>https://example.com/zf-cuts-debt</link>
      <description><![CDATA[<a href="https://example.com/zf-cuts-debt">ZF Friedrichshafen debt and outlook</a>]]></description>
    </item>
  </channel>
</rss>"""

    def fake_http_get_text(url: str):
        if "news.google.com" in url:
            return rss_payload, url, 200
        raise Exception("HTTP Error 403: Forbidden")

    monkeypatch.setattr(research_module, "_http_get_text", fake_http_get_text)

    result = research_module.web_search('"ZF Friedrichshafen" debt', max_results=3)

    assert result["results"]
    assert result["search_backend"] == "google_news_rss_fallback"
    assert result["results"][0]["url"] == "https://example.com/zf-cuts-debt"


def test_web_search_falls_back_to_bing_html(monkeypatch):
    bing_payload = """<?xml version="1.0" encoding="utf-8" ?>
    <rss version="2.0"><channel>
      <item>
        <title>Example Report</title>
        <link>https://example.com/report</link>
        <description>Automotive supplier market report.</description>
      </item>
    </channel></rss>
    """

    def fake_http_get_text(url: str):
        if "html.duckduckgo.com" in url:
            raise Exception("HTTP Error 403: Forbidden")
        if "www.bing.com/search?format=rss" in url:
            return bing_payload, url, 200
        raise AssertionError(url)

    monkeypatch.setattr(research_module, "_http_get_text", fake_http_get_text)

    result = research_module.web_search('"automotive supplier" market report', max_results=3)

    assert result["search_backend"] == "bing_html_fallback"
    assert result["results"][0]["url"] == "https://example.com/report"
    assert "market report" in result["results"][0]["snippet"].lower()


def test_web_search_filters_google_news_wrappers_before_bing_fallback(monkeypatch):
    ddg_payload = """
    <html><body>
      <a class="result__a" href="https://news.google.com/rss/articles/example-1">Wrapped result</a>
    </body></html>
    """
    bing_payload = """<?xml version="1.0" encoding="utf-8" ?>
    <rss version="2.0"><channel>
      <item>
        <title>ZF Friedrichshafen industry outlook</title>
        <link>https://publisher.example.com/article</link>
        <description>Industry outlook for ZF Friedrichshafen suppliers.</description>
      </item>
    </channel></rss>
    """

    def fake_http_get_text(url: str):
        if "html.duckduckgo.com" in url:
            return ddg_payload, url, 200
        if "www.bing.com/search?format=rss" in url:
            return bing_payload, url, 200
        raise AssertionError(url)

    monkeypatch.setattr(research_module, "_http_get_text", fake_http_get_text)

    result = research_module.web_search('"ZF Friedrichshafen" industry outlook', max_results=3)

    assert result["search_backend"] == "bing_html_fallback"
    assert result["results"][0]["url"] == "https://publisher.example.com/article"


def test_fetch_page_rejects_google_news_wrapper_shell(monkeypatch):
    wrapper_html = """
    <html>
      <head><title>Google News</title></head>
      <body>DotsSplashUi news.google.com google news</body>
    </html>
    """

    monkeypatch.setattr(
        research_module,
        "_http_get_text",
        lambda url: (wrapper_html, "https://news.google.com/rss/articles/example-1", 200),
    )

    result = research_module.fetch_page("https://news.google.com/rss/articles/example-1")

    assert result["ok"] is False
    assert "google news wrapper" in result["error"].lower()


def test_company_source_pack_appends_wikipedia_seed(monkeypatch):
    monkeypatch.setattr(research_module, "_run_query_pack", lambda *args, **kwargs: {"queries": ["x"], "results": []})
    monkeypatch.setattr(
        research_module,
        "_find_wikipedia_candidate",
        lambda company_name: {
            "query": "wikipedia_search_seed",
            "title": "ZF Friedrichshafen",
            "url": "https://en.wikipedia.org/wiki/ZF_Friedrichshafen",
            "snippet": "Wikipedia page candidate",
        },
    )

    result = research_module.company_source_pack("ZF Friedrichshafen", "zf.com", max_results=5)

    urls = [item["url"] for item in result["results"]]
    assert "https://en.wikipedia.org/wiki/ZF_Friedrichshafen" in urls


def test_company_source_pack_respects_max_results_after_appending_seeds(monkeypatch):
    monkeypatch.setattr(
        research_module,
        "_run_query_pack",
        lambda *args, **kwargs: {
            "queries": ["x"],
            "results": [{"query": "search", "title": "A", "url": "https://a.example", "snippet": ""}],
        },
    )
    monkeypatch.setattr(
        research_module,
        "_find_wikipedia_candidate",
        lambda company_name: {
            "query": "wikipedia_search_seed",
            "title": "ZF Friedrichshafen",
            "url": "https://en.wikipedia.org/wiki/ZF_Friedrichshafen",
            "snippet": "Wikipedia page candidate",
        },
    )
    monkeypatch.setattr(
        research_module,
        "_official_company_page_seeds",
        lambda company_name, domain: [
            {"query": "domain_homepage_seed", "title": "home", "url": "https://zf.com", "snippet": ""},
            {"query": "domain_impressum_seed", "title": "impressum", "url": "https://zf.com/impressum", "snippet": ""},
        ],
    )

    result = research_module.company_source_pack("ZF Friedrichshafen", "zf.com", max_results=1)

    assert len(result["results"]) == 1
    assert result["results"][0]["url"] == "https://a.example"


def test_build_revision_message_includes_structured_field_issues():
    message = _build_revision_message(
        _review(
            False,
            issue="Revenue unsupported.",
            instruction="Set unsupported revenue to n/v.",
            field_issues=[
                {
                    "field_path": "revenue",
                    "issue_type": "stale_sources",
                    "summary": "Revenue lacks fresh support.",
                    "recommendation": "Set revenue to n/v unless fresh primary evidence is available.",
                }
            ],
        )
    )

    assert "Field issues:" in message
    assert "revenue" in message
    assert "Targeted fixes:" in message


def test_company_intelligence_review_feedback_does_not_encourage_nv_placeholder_people():
    message = _build_revision_message(
        _review(
            False,
            issue="Key people are missing.",
            instruction="Use an empty list if no verifiable key people are found.",
            field_issues=[
                {
                    "field_path": "key_people",
                    "issue_type": "missing_information",
                    "summary": "No verifiable leaders were found in the cited sources.",
                    "recommendation": "Keep key_people as an empty list unless specific names and roles are source-backed.",
                }
            ],
        )
    )

    assert "empty list" in message
    assert "{'name':'n/v'" not in message
    assert '"name":"n/v"' not in message


def test_pre_critic_validation_accepts_concatenated_json_objects_and_uses_last_payload():
    content = _company_reply() + "\n" + _company_reply(revenue="123")
    issues = _validate_pre_critic_output("company_intelligence", content)
    assert issues == []
    payload = _extract_json_payload(content)
    assert payload is not None
    assert payload["revenue"] == "123"


def test_pre_critic_allows_conservative_strategic_signals_output_without_source_pack_flag():
    context = ContextVariables(data={ENFORCE_STRATEGIC_SIGNALS_SOURCE_PACK_KEY: True})

    result = _pre_critic_check(
        output=_industry_reply(),
        context_variables=context,
        stage_key="strategic_signals",
        producer_name="StrategicSignals",
        critic_name="StrategicSignalsCritic",
        next_target_name="MarketNetwork",
        attempts_key="strategic_signals_attempts",
    )

    assert getattr(result.target, "agent_name", "") == "StrategicSignalsCritic"


def test_pre_critic_rejects_strategic_signals_with_company_only_sources():
    payload = json.loads(_industry_reply())
    payload["key_trends"] = ["Electrification push"]
    payload["sources"] = [
        {
            "publisher": "ZF Friedrichshafen AG",
            "url": "https://www.zf.com/",
            "title": "Homepage ZF Friedrichshafen AG - ZF",
            "accessed": "2026-03-20",
        },
        {
            "publisher": "Wikipedia",
            "url": "https://en.wikipedia.org/wiki/ZF_Friedrichshafen",
            "title": "ZF Friedrichshafen - Wikipedia",
            "accessed": "2026-03-20",
        },
    ]

    issues = _validate_pre_critic_output("strategic_signals", json.dumps(payload))

    assert any(issue.field_path == "sources" for issue in issues)
    assert any("external market" in issue.summary.lower() for issue in issues)


def test_model_selection_uses_stage_specific_defaults(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("STRUCTURED_LLM_MODEL", raising=False)

    assert get_model_selection(agent_name="concierge") == ("gpt-4.1-mini", "gpt-4.1-mini")
    assert get_model_selection(agent_name="strategic_signals") == ("gpt-5-mini", "gpt-5-mini")
    assert get_model_selection(agent_name="market_network") == ("gpt-4.1", "gpt-4.1")
    assert get_model_selection(agent_name="synthesis") == ("gpt-4.1", "gpt-4.1")
    assert get_model_selection(agent_name="synthesis_critic") == ("gpt-4.1-mini", "gpt-4.1-mini")


def test_model_selection_honors_agent_specific_env_override(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("STRUCTURED_LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("LLM_MODEL_STRATEGIC_SIGNALS", "gpt-4.1")

    preferred, structured = get_model_selection(agent_name="strategic_signals")

    assert preferred == "gpt-4.1"
    assert structured == "gpt-4.1"


def test_get_llm_config_uses_agent_specific_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("STRUCTURED_LLM_MODEL", raising=False)

    config = get_llm_config(agent_name="company_intelligence")

    assert config.config_list[0].model == "gpt-4.1"
    assert "max_tokens" in config.config_list[0]


def test_get_llm_config_uses_max_completion_tokens_for_gpt5_family(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MAX_TOKENS", "1400")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("STRUCTURED_LLM_MODEL", raising=False)

    config = get_llm_config(agent_name="strategic_signals")

    assert config.config_list[0].model == "gpt-5-mini"
    assert config.config_list[0]["max_completion_tokens"] == 1400
    assert getattr(config.config_list[0], "max_tokens", None) in (None, 0)


def test_inject_missing_critic_turn_appends_critic_review_for_valid_producer_output():
    prepared = PreparedGroupChat(
        context_variables=ContextVariables(data={}),
        groupchat=SimpleNamespace(messages=[{"name": "StrategicSignals", "role": "user", "content": _industry_reply()}]),
        manager=SimpleNamespace(),
        processed_messages=[],
        last_agent=None,
    )
    agents = {
        "strategic_signals_critic": SequenceAgent("StrategicSignalsCritic", [_review(True)]),
    }

    injected = _inject_missing_critic_turn(prepared, agents)

    assert injected == "StrategicSignalsCritic"
    assert prepared.groupchat.messages[-1]["name"] == "StrategicSignalsCritic"
    assert json.loads(prepared.groupchat.messages[-1]["content"])["approved"] is True


def test_collect_usage_summary_aggregates_agents():
    usage = _collect_usage_summary(
        {
            "company": FakeUsageAgent(
                actual={
                    "total_cost": 0.01,
                    "gpt-4o-mini": {
                        "cost": 0.01,
                        "prompt_tokens": 100,
                        "completion_tokens": 50,
                        "total_tokens": 150,
                    },
                },
                total={
                    "total_cost": 0.02,
                    "gpt-4o-mini": {
                        "cost": 0.02,
                        "prompt_tokens": 120,
                        "completion_tokens": 80,
                        "total_tokens": 200,
                    },
                },
            ),
            "market": FakeUsageAgent(
                actual={
                    "total_cost": 0.005,
                    "gpt-4o-mini": {
                        "cost": 0.005,
                        "prompt_tokens": 40,
                        "completion_tokens": 10,
                        "total_tokens": 50,
                    },
                },
                total={
                    "total_cost": 0.007,
                    "gpt-4o-mini": {
                        "cost": 0.007,
                        "prompt_tokens": 60,
                        "completion_tokens": 10,
                        "total_tokens": 70,
                    },
                },
            ),
        }
    )

    assert usage["actual"]["total_cost"] == 0.015
    assert usage["actual"]["prompt_tokens"] == 140
    assert usage["actual"]["completion_tokens"] == 60
    assert usage["actual"]["total_tokens"] == 200
    assert usage["total"]["total_cost"] == 0.027
    assert usage["total"]["models"]["gpt-4o-mini"]["total_tokens"] == 270


def test_runner_helpers_detect_tool_loops_and_incomplete_runs():
    raw_chat = []
    for idx in range(1, COMPANY_INTELLIGENCE_MAX_CONSECUTIVE_TOOL_TURNS + 1):
        raw_chat.append({"name": "CompanyIntelligence", "tool_calls": [{"id": str(idx)}]})
        if idx < COMPANY_INTELLIGENCE_MAX_CONSECUTIVE_TOOL_TURNS:
            raw_chat.append({"name": "_Group_Tool_Executor", "tool_responses": [{"tool_call_id": str(idx)}]})
    pipeline_data = {
        "company_profile": {},
        "industry_analysis": {},
        "market_network": {},
        "synthesis": {},
    }

    assert _count_tool_calls_from_chat_messages(raw_chat) == COMPANY_INTELLIGENCE_MAX_CONSECUTIVE_TOOL_TURNS
    assert _detect_stalled_tool_agent(raw_chat) == (
        "CompanyIntelligence",
        COMPANY_INTELLIGENCE_MAX_CONSECUTIVE_TOOL_TURNS,
    )
    assert _workflow_completed(raw_chat, pipeline_data) is False
    assert "company_profile" in _build_incomplete_run_message(raw_chat, pipeline_data)
    assert "_Group_Tool_Executor" not in _build_incomplete_run_message(raw_chat, pipeline_data)
    assert "CompanyIntelligence" in _build_incomplete_run_message(raw_chat, pipeline_data)


def test_company_intelligence_allowed_tool_budget_does_not_trigger_stall_guard():
    raw_chat = []
    for idx in range(1, COMPANY_INTELLIGENCE_MAX_STAGE_TOOL_CALLS + 1):
        raw_chat.append({"name": "CompanyIntelligence", "tool_calls": [{"id": str(idx)}]})
        if idx < COMPANY_INTELLIGENCE_MAX_STAGE_TOOL_CALLS:
            raw_chat.append({"name": "_Group_Tool_Executor", "tool_responses": [{"tool_call_id": str(idx)}]})

    assert _detect_stalled_tool_agent(raw_chat) is None


def test_extract_pipeline_data_and_pdf_generation():
    messages = []

    def emit(agent: str, content: str, msg_type: str = "agent_message") -> None:
        messages.append(
            {
                "type": msg_type,
                "agent": agent,
                "content": content,
                "timestamp": _ts(),
            }
        )

    emit("Admin", "Research the company 'Lenze SE' (domain: lenze.com) for a Liquisto sales meeting preparation.")
    emit("Concierge", _concierge_reply())
    emit("CompanyIntelligence", _company_reply())
    emit("StrategicSignals", _industry_reply())
    emit("MarketNetwork", _market_reply())
    emit("EvidenceQA", _qa_reply())
    emit("Synthesis", _synthesis_reply())
    emit("Admin", "TERMINATE")

    pipeline_data = _extract_pipeline_data(messages)
    assert pipeline_data["company_profile"]
    assert pipeline_data["industry_analysis"]
    assert pipeline_data["market_network"]
    assert pipeline_data["quality_review"]
    assert pipeline_data["synthesis"]
    assert pipeline_data["quality_review"]["gap_details"]
    assert any(
        detail.get("issue_type") == "stale_sources"
        for detail in pipeline_data["quality_review"]["gap_details"]
        if isinstance(detail, dict)
    )
    assert any(
        detail.get("issue_type") == "missing_peer_competitors"
        for detail in pipeline_data["quality_review"]["gap_details"]
        if isinstance(detail, dict)
    )

    pdf_de = generate_pdf(pipeline_data, lang="de")
    pdf_en = generate_pdf(pipeline_data, lang="en")
    assert len(pdf_de) > 1000
    assert len(pdf_en) > 1000


def test_extract_pipeline_data_removes_placeholder_key_people_and_records_gap():
    company_payload = json.dumps(
        {
            "company_name": "IMS Gear SE & Co. KGaA",
            "legal_form": "SE & Co. KGaA",
            "founded": "1863",
            "headquarters": "Donaueschingen, Germany",
            "website": "https://www.imsgear.com",
            "industry": "Machinery/Mechanical Engineering",
            "employees": "2775",
            "revenue": "n/v",
            "products_and_services": ["Gear components"],
            "key_people": [{"name": "n/v", "role": "n/v"}],
            "description": "IMS Gear manufactures gears.",
            "economic_situation": {
                "revenue_trend": "n/v",
                "profitability": "n/v",
                "recent_events": [],
                "inventory_signals": [],
                "financial_pressure": "n/v",
                "assessment": "n/v",
            },
            "sources": [
                {
                    "publisher": "IMS Gear",
                    "url": "https://www.imsgear.com",
                    "title": "IMS Gear",
                    "accessed": "2026-03-20",
                }
            ],
        }
    )
    messages = [
        {"type": "agent_message", "agent": "CompanyIntelligence", "content": company_payload, "timestamp": _ts()},
        {"type": "agent_message", "agent": "StrategicSignals", "content": _industry_reply(), "timestamp": _ts()},
        {"type": "agent_message", "agent": "MarketNetwork", "content": _market_reply(), "timestamp": _ts()},
    ]

    pipeline_data = _extract_pipeline_data(messages)

    assert pipeline_data["company_profile"]["key_people"] == []
    assert any(
        detail.get("issue_type") == "placeholder_key_people"
        for detail in pipeline_data["quality_review"]["gap_details"]
        if isinstance(detail, dict)
    )


def test_extract_pipeline_data_flags_incomplete_source_metadata():
    industry_payload = json.dumps(
        {
            "industry_name": "Machinery/Mechanical Engineering",
            "market_size": "n/v",
            "trend_direction": "unsicher",
            "growth_rate": "n/v",
            "key_trends": [],
            "overcapacity_signals": [],
            "excess_stock_indicators": "n/v",
            "demand_outlook": "n/v",
            "assessment": "No specific market evidence was found.",
            "sources": [
                {
                    "publisher": "Trade Journal",
                    "url": "https://example.com/report",
                    "title": "",
                    "accessed": "",
                }
            ],
        }
    )
    messages = [
        {"type": "agent_message", "agent": "CompanyIntelligence", "content": _company_reply(), "timestamp": _ts()},
        {"type": "agent_message", "agent": "StrategicSignals", "content": industry_payload, "timestamp": _ts()},
        {"type": "agent_message", "agent": "MarketNetwork", "content": _market_reply(), "timestamp": _ts()},
    ]

    pipeline_data = _extract_pipeline_data(messages)

    assert any(
        detail.get("issue_type") == "incomplete_source_metadata"
        for detail in pipeline_data["quality_review"]["gap_details"]
        if isinstance(detail, dict)
    )


def test_extract_pipeline_data_rejects_legacy_payload_shapes():
    legacy_company_payload = json.dumps(
        {
            "LegalInformation": {
                "LegalName": "IMS Gear SE & Co. KGaA",
                "LegalForm": "SE & Co. KGaA",
            },
            "IndustryAndMarket": {
                "Industry": "Machinery/Mechanical Engineering",
            },
        }
    )
    messages = [
        {
            "type": "agent_message",
            "agent": "CompanyIntelligence",
            "content": legacy_company_payload,
            "timestamp": _ts(),
        }
    ]

    pipeline_data = _extract_pipeline_data(messages)

    assert not pipeline_data["company_profile"]
    assert pipeline_data["validation_errors"]
    assert pipeline_data["validation_errors"][0]["agent"] == "CompanyIntelligence"
    assert pipeline_data["validation_errors"][0]["section"] == "company_profile"
    assert "company_name" in pipeline_data["validation_errors"][0]["details"]


def test_extract_pipeline_data_does_not_invent_qa_or_synthesis_for_early_incomplete_runs():
    messages = [
        {
            "type": "agent_message",
            "agent": "Concierge",
            "content": _concierge_reply(),
            "timestamp": _ts(),
        }
    ]

    pipeline_data = _extract_pipeline_data(messages)

    assert not pipeline_data["company_profile"]
    assert not pipeline_data["industry_analysis"]
    assert not pipeline_data["market_network"]
    assert not pipeline_data["quality_review"]
    assert not pipeline_data["synthesis"]


def test_assess_research_usability_flags_sparse_meeting_brief():
    pipeline_data = {
        "company_profile": {
            "company_name": "ZF Friedrichshafen AG",
            "legal_form": "n/v",
            "founded": "n/v",
            "headquarters": "n/v",
            "website": "https://www.zf.com",
            "economic_situation": {
                "revenue_trend": "n/v",
                "profitability": "n/v",
                "financial_pressure": "n/v",
                "assessment": "n/v",
            },
        },
        "industry_analysis": {
            "market_size": "n/v",
            "growth_rate": "n/v",
            "demand_outlook": "n/v",
            "excess_stock_indicators": "n/v",
            "sources": [
                {
                    "publisher": "ZF",
                    "url": "https://www.zf.com/mobile/en/homepage/homepage.html",
                    "title": "ZF Homepage",
                    "accessed": "2026-03-20",
                }
            ],
        },
        "market_network": {
            "peer_competitors": {"companies": []},
            "downstream_buyers": {"companies": []},
            "service_providers": {"companies": []},
            "cross_industry_buyers": {"companies": []},
        },
        "quality_review": {"evidence_health": "niedrig"},
    }

    readiness = _assess_research_usability(pipeline_data)

    assert readiness["research_usable"] is False
    assert any("Firmenprofil unvollstaendig" in reason for reason in readiness["reasons"])
    assert any("Wirtschaftslage nicht verwertbar" in reason for reason in readiness["reasons"])
    assert any("Branchenanalyse ohne belastbare externe Quellen" in reason for reason in readiness["reasons"])
    assert any("MarketNetwork ohne belastbare Buyer" in reason for reason in readiness["reasons"])
    assert any("Evidenzqualitaet ist nur niedrig" in reason for reason in readiness["reasons"])


def test_extract_pipeline_data_downgrades_company_and_wiki_only_industry_sources():
    company_payload = json.dumps(
        {
            "company_name": "ZF Friedrichshafen AG",
            "legal_form": "Aktiengesellschaft (AG)",
            "founded": "20 August 1915",
            "headquarters": "Friedrichshafen, Baden-Württemberg, Germany",
            "website": "https://www.zf.com/",
            "industry": "Automotive industry",
            "employees": "153000",
            "revenue": "EUR 38.8bn",
            "products_and_services": ["Transmission systems"],
            "key_people": [{"name": "Mathias Miedreich", "role": "CEO"}],
            "description": "ZF profile.",
            "economic_situation": {
                "revenue_trend": "stable",
                "profitability": "n/v",
                "recent_events": [],
                "inventory_signals": [],
                "financial_pressure": "n/v",
                "assessment": "n/v",
            },
            "sources": [
                {
                    "publisher": "ZF Friedrichshafen AG",
                    "url": "https://www.zf.com/",
                    "title": "Homepage ZF Friedrichshafen AG - ZF",
                    "accessed": "2026-03-20",
                }
            ],
        }
    )
    industry_payload = json.dumps(
        {
            "industry_name": "Automotive and Mobility Technology Industry",
            "market_size": "n/v",
            "trend_direction": "unsicher",
            "growth_rate": "n/v",
            "key_trends": ["Electrification"],
            "overcapacity_signals": ["No explicit overcapacity found."],
            "excess_stock_indicators": "No direct evidence found.",
            "demand_outlook": "n/v",
            "assessment": "Based on available sources, no excess stock signals are visible.",
            "sources": [
                {
                    "publisher": "ZF Friedrichshafen AG",
                    "url": "https://www.zf.com/",
                    "title": "Homepage ZF Friedrichshafen AG - ZF",
                    "accessed": "2026-03-20",
                },
                {
                    "publisher": "Wikipedia",
                    "url": "https://en.wikipedia.org/wiki/ZF_Friedrichshafen",
                    "title": "ZF Friedrichshafen - Wikipedia",
                    "accessed": "2026-03-20",
                },
            ],
        }
    )
    market_payload = _market_reply()
    qa_payload = json.dumps(
        {
            "validated_agents": ["CompanyIntelligence", "StrategicSignals", "MarketNetwork"],
            "evidence_health": "good",
            "open_gaps": [],
            "recommendations": [],
            "gap_details": [],
        }
    )
    messages = [
        {"type": "agent_message", "agent": "CompanyIntelligence", "content": company_payload, "timestamp": _ts()},
        {"type": "agent_message", "agent": "StrategicSignals", "content": industry_payload, "timestamp": _ts()},
        {"type": "agent_message", "agent": "MarketNetwork", "content": market_payload, "timestamp": _ts()},
        {"type": "agent_message", "agent": "EvidenceQA", "content": qa_payload, "timestamp": _ts()},
    ]

    pipeline_data = _extract_pipeline_data(messages)

    assert pipeline_data["quality_review"]["evidence_health"] == "niedrig"
    assert any(
        detail.get("issue_type") == "missing_external_market_sources"
        for detail in pipeline_data["quality_review"]["gap_details"]
        if isinstance(detail, dict)
    )
    assert any(
        "Branchenanalyse ohne belastbare externe Quellen" in reason
        for reason in pipeline_data["research_readiness"]["reasons"]
    )


def test_extract_pipeline_data_adds_research_readiness_for_usable_brief():
    company_payload = json.dumps(
        {
            "company_name": "IMS Gear SE & Co. KGaA",
            "legal_form": "SE & Co. KGaA",
            "founded": "1863",
            "headquarters": "Donaueschingen, Germany",
            "website": "https://www.imsgear.com",
            "industry": "Machinery/Mechanical Engineering",
            "employees": "2775",
            "revenue": "EUR 450m",
            "products_and_services": ["Gear components"],
            "key_people": [{"name": "Bernd Schilling", "role": "Managing Director"}],
            "description": "IMS Gear manufactures gears.",
            "economic_situation": {
                "revenue_trend": "stabil",
                "profitability": "solide",
                "recent_events": [],
                "inventory_signals": [],
                "financial_pressure": "niedrig",
                "assessment": "Keine akuten Belastungssignale aus den verfuegbaren Quellen.",
            },
            "sources": [
                {
                    "publisher": "IMS Gear",
                    "url": "https://www.imsgear.com",
                    "title": "IMS Gear",
                    "accessed": "2026-03-20",
                }
            ],
        }
    )
    industry_payload = json.dumps(
        {
            "industry_name": "Machinery/Mechanical Engineering",
            "market_size": "EUR 12bn",
            "trend_direction": "stabil",
            "growth_rate": "2-3%",
            "key_trends": ["Aftermarket resilience"],
            "overcapacity_signals": [],
            "excess_stock_indicators": "Keine klaren Signale",
            "demand_outlook": "stabil",
            "assessment": "Current industry data points to a stable demand picture without clear overcapacity signals.",
            "sources": [
                {
                    "publisher": "VDMA",
                    "url": "https://www.vdma.org/example-report",
                    "title": "Mechanical Engineering Outlook",
                    "accessed": "2026-03-20",
                }
            ],
        }
    )
    market_payload = json.dumps(
        {
            "target_company": "IMS Gear SE & Co. KGaA",
            "peer_competitors": {
                "companies": [
                    {
                        "name": "Sample Peer",
                        "website": "https://peer.example.com",
                        "city": "Berlin",
                        "country": "Germany",
                        "relevance": "Competes in geared drive systems",
                        "matching_products": ["Drive systems"],
                        "evidence_tier": "verified",
                        "source": {
                            "publisher": "Peer Example",
                            "url": "https://peer.example.com/products",
                            "title": "Products",
                            "accessed": "2026-03-20",
                        },
                    }
                ],
                "assessment": "Verified peer overlap found.",
                "sources": [
                    {
                        "publisher": "Peer Example",
                        "url": "https://peer.example.com/products",
                        "title": "Products",
                        "accessed": "2026-03-20",
                    }
                ],
            },
            "downstream_buyers": {"companies": [], "assessment": "No verified downstream buyers found.", "sources": []},
            "service_providers": {"companies": [], "assessment": "No verified service providers found.", "sources": []},
            "cross_industry_buyers": {"companies": [], "assessment": "No verified cross-industry buyers found.", "sources": []},
        }
    )
    qa_payload = json.dumps(
        {
            "validated_agents": ["CompanyIntelligence", "StrategicSignals", "MarketNetwork"],
            "evidence_health": "mittel",
            "open_gaps": [],
            "recommendations": [],
            "gap_details": [],
        }
    )
    messages = [
        {"type": "agent_message", "agent": "CompanyIntelligence", "content": company_payload, "timestamp": _ts()},
        {"type": "agent_message", "agent": "StrategicSignals", "content": industry_payload, "timestamp": _ts()},
        {"type": "agent_message", "agent": "MarketNetwork", "content": market_payload, "timestamp": _ts()},
        {"type": "agent_message", "agent": "EvidenceQA", "content": qa_payload, "timestamp": _ts()},
    ]

    pipeline_data = _extract_pipeline_data(messages)

    assert pipeline_data["research_readiness"]["research_usable"] is True
    assert pipeline_data["research_readiness"]["reasons"] == []


def test_request_group_chat_stop_injects_next_turn_termination():
    class DummyParticipant:
        def __init__(self):
            self.stopped = False

        def stop_reply_at_receive(self, *_args, **_kwargs):
            self.stopped = True

    manager = DummyParticipant()
    sender = DummyParticipant()
    participant = DummyParticipant()
    groupchat = SimpleNamespace(
        agents=[participant],
        messages=[{"name": "CompanyIntelligence", "content": "None"}],
        max_round=39,
        select_speaker=lambda *_args, **_kwargs: "unexpected",
    )
    prepared = PreparedGroupChat(
        context_variables=None,
        groupchat=groupchat,
        manager=manager,
        processed_messages=[],
        last_agent=None,
    )

    _request_group_chat_stop(prepared, sender)

    assert participant.stopped is True
    assert manager.stopped is True
    assert sender.stopped is True
    assert prepared.manager._is_termination_msg({"content": "anything"}) is True
    try:
        prepared.groupchat.select_speaker(None, None)
    except NoEligibleSpeakerError:
        pass
    else:
        raise AssertionError("select_speaker should raise NoEligibleSpeakerError after stop request")


def test_prepare_group_chat_accepts_documented_ag2_011_tuple_shape():
    context_variables = object()
    groupchat = object()
    manager = object()
    last_agent = object()
    processed_messages = [{"content": "Research imsgear.com"}]

    class FakePattern:
        def prepare_group_chat(self, *, max_rounds, messages):
            assert max_rounds == 12
            assert messages == "Research imsgear.com"
            return (
                "agents",
                "wrapped_agents",
                "user_agent",
                context_variables,
                "initial_agent",
                "group_after_work",
                "tool_executor",
                groupchat,
                manager,
                processed_messages,
                last_agent,
                "group_agent_names",
                "temp_user_list",
            )

    prepared = _prepare_group_chat(FakePattern(), max_rounds=12, messages="Research imsgear.com")

    assert prepared.context_variables is context_variables
    assert prepared.groupchat is groupchat
    assert prepared.manager is manager
    assert prepared.processed_messages == processed_messages
    assert prepared.last_agent is last_agent


def test_prepare_group_chat_fails_loudly_on_unexpected_ag2_shape():
    class FakePattern:
        def prepare_group_chat(self, *, max_rounds, messages):
            return ("too", "short")

    try:
        _prepare_group_chat(FakePattern(), max_rounds=12, messages="Research imsgear.com")
    except RuntimeError as exc:
        message = str(exc)
        assert "AG2 0.11.x" in message
        assert "13-item tuple" in message
        assert "got 2" in message
    else:
        raise AssertionError("Expected _prepare_group_chat to reject an unexpected tuple shape")


def test_try_parse_json():
    test_cases = [
        ("direct json", '{"key": "value"}', True),
        ("markdown fence", '```json\n{"key": "value"}\n```', True),
        ("text + json", 'Here is the result:\n{"key": "value"}\nDone.', True),
        ("no json", "This is just text", False),
        ("empty", "", False),
    ]
    for _label, text, should_parse in test_cases:
        result = _try_parse_json(text)
        assert (result is not None) == should_parse


def test_budget_helpers_clamp_too_small_env_values(monkeypatch):
    monkeypatch.setenv("PIPELINE_MAX_STAGE_ATTEMPTS", "1")
    monkeypatch.setenv("PIPELINE_MAX_TOOL_CALLS", "6")
    monkeypatch.setenv("PIPELINE_COMPANY_INTELLIGENCE_MAX_TOOL_CALLS", "1")

    assert _definitions_env_int_with_min("PIPELINE_MAX_STAGE_ATTEMPTS", 4, 2) == 2
    assert _runner_env_int_with_min("PIPELINE_MAX_TOOL_CALLS", 48, 12) == 12
    assert research_module._env_int_with_min("PIPELINE_MAX_TOOL_CALLS", 48, 12) == 12


def test_detect_duplicate_structured_producer_turn_flags_same_producer_twice():
    messages = [
        {"name": "StrategicSignals", "content": _industry_reply()},
        {"name": "StrategicSignals", "content": _industry_reply()},
    ]
    assert _detect_duplicate_structured_producer_turn(messages) == "StrategicSignals"


def test_workflow_completed_accepts_duplicate_producer_turns_if_final_critic_passes():
    chat_history = [
        {"name": "StrategicSignals", "content": _industry_reply()},
        {"name": "StrategicSignals", "content": _industry_reply()},
        {"name": "SynthesisCritic", "content": _review(True)},
    ]
    pipeline_data = {
        "company_profile": json.loads(_company_reply()),
        "industry_analysis": json.loads(_industry_reply()),
        "market_network": json.loads(_market_reply()),
        "synthesis": json.loads(_synthesis_reply()),
    }
    assert _workflow_completed(chat_history, pipeline_data) is True


def test_should_auto_resume_groupchat_when_last_actor_is_structured_producer():
    chat_history = [
        {"name": "_User", "content": "start"},
        {"name": "StrategicSignals", "content": _industry_reply()},
    ]

    assert _should_auto_resume_groupchat(chat_history) is True


def test_should_not_auto_resume_groupchat_after_critic():
    chat_history = [
        {"name": "_User", "content": "start"},
        {"name": "StrategicSignalsCritic", "content": _review(True)},
    ]

    assert _should_auto_resume_groupchat(chat_history) is False


def main():
    print("=" * 60)
    print("AG2-NATIVE PIPELINE TEST")
    print("=" * 60)

    test_groupchat_routes_full_workflow_in_order()
    print("  ✅ full AG2 workflow order is correct")
    test_groupchat_retries_same_producer_after_critic_rejection()
    print("  ✅ critic rejection loops back to the same producer")
    test_research_query_builders_are_agent_specific()
    print("  ✅ agent-specific research query packs are targeted")
    test_collect_usage_summary_aggregates_agents()
    print("  ✅ usage and cost summaries aggregate across agents")
    test_extract_pipeline_data_and_pdf_generation()
    print("  ✅ extraction and PDF generation still work")
    test_extract_pipeline_data_rejects_legacy_payload_shapes()
    print("  ✅ legacy payload shapes are rejected instead of normalized")
    test_try_parse_json()
    print("  ✅ JSON extraction handles expected variants")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    main()
