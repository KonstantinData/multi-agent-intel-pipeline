"""Evidence-driven research worker with optional LLM synthesis."""
from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from src.config.settings import get_llm_config, get_openai_api_key
from src.domain.intake import SupervisorBrief
from src.models.schemas import CompanyProfile, ContactIntelligenceSection, IndustryAnalysis, MarketNetwork
from src.orchestration.tool_policy import tool_is_allowed
from src.research.extract import extract_product_keywords, infer_industry, summarize_visible_text
from src.research.fetch import fetch_website_snapshot
from src.research.search import build_buyer_queries, build_company_queries, build_market_queries, perform_search


SECTION_MODELS = {
    "company_profile": CompanyProfile,
    "industry_analysis": IndustryAnalysis,
    "market_network": MarketNetwork,
    "contact_intelligence": ContactIntelligenceSection,
}


class ResearchWorker:
    """Runs one supervisor assignment against a compact evidence pack."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._client: OpenAI | None = None
        self._search_cache: dict[str, list[dict[str, str]]] = {}
        self._page_cache: dict[str, dict[str, str | bool]] = {}

    def run(
        self,
        *,
        brief: SupervisorBrief,
        task_key: str,
        target_section: str,
        objective: str,
        current_sections: dict[str, Any],
        query_overrides: list[str] | None = None,
        allowed_tools: list[str] | tuple[str, ...] | None = None,
        model_name: str | None = None,
        revision_request: dict[str, Any] | None = None,
        role_memory: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        granted_tools = tuple(allowed_tools or ())
        hints = self._derive_research_hints(brief)
        queries = query_overrides or self._build_queries(
            brief=brief,
            task_key=task_key,
            current_section=current_sections.get(target_section, {}),
        )
        search_results, search_calls = self._search_queries(queries, granted_tools=granted_tools, task_key=task_key)
        page_evidence, page_fetches = self._fetch_supporting_pages(search_results, granted_tools=granted_tools)
        existing_payload = dict(current_sections.get(target_section, {}))

        # Schicht 3: inject cross-task memory context so the LLM can
        # reference facts already collected by earlier tasks (e.g. peer
        # names from company_fundamentals available to peer_companies).
        memory_context = self._build_memory_context(
            task_key=task_key,
            target_section=target_section,
            current_sections=current_sections,
            role_memory=role_memory,
        )

        # P1 fix: strip default-only current_section so the LLM doesn't
        # reproduce "n/v" / [] defaults it sees in the evidence pack.
        stripped_payload = self._strip_default_only_payload(target_section, existing_payload)

        evidence_pack = {
            "brief": {
                "company_name": brief.company_name,
                "submitted_company_name": brief.submitted_company_name,
                "submitted_web_domain": brief.submitted_web_domain,
                "verified_company_name": brief.verified_company_name,
                "verified_legal_name": brief.verified_legal_name,
                "name_confidence": brief.name_confidence,
                "web_domain": brief.web_domain,
                "homepage_url": brief.homepage_url,
                "industry_hint": hints["industry_hint"],
                "product_keywords": hints["product_keywords"],
                "visible_text_excerpt": brief.raw_homepage_excerpt,
                "observations": brief.observations,
            },
            "objective": objective,
            "task_key": task_key,
            "target_section": target_section,
            "current_section": stripped_payload,
            "memory_context": memory_context,
            "queries": queries,
            "search_results": search_results,
            "page_evidence": page_evidence,
            "allowed_tools": list(granted_tools),
            "model_name": model_name or self.name,
            "revision_request": revision_request or {},
            "role_memory": role_memory or [],
        }

        llm_usage = {
            "llm_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        fallback_note: str | None = None
        used_llm = False
        if self._llm_enabled(granted_tools=granted_tools):
            try:
                used_llm = True
                synthesis = self._llm_synthesis(evidence_pack, model_name=model_name)
                llm_usage = synthesis.pop("usage", llm_usage)
            except Exception as exc:
                synthesis = self._fallback_synthesis(evidence_pack)
                fallback_note = f"LLM synthesis failed for {task_key}: {exc}"
        else:
            synthesis = self._fallback_synthesis(evidence_pack)
        if fallback_note:
            synthesis.setdefault("open_questions", []).append(fallback_note)
        # P5 fix: if products_and_services is empty after LLM synthesis but
        # product_keywords are available, inject them as fallback.
        raw_updates = self._normalize_payload_updates(target_section, synthesis.get("payload_updates", {}))

        # P2 bridge: if monetization_redeployment LLM synthesis left downstream_buyers /
        # monetization_paths / redeployment_paths empty but buyer_hypotheses were collected,
        # promote them into the MarketNetwork schema fields.
        if target_section == "market_network" and task_key == "monetization_redeployment":
            bh = synthesis.get("buyer_hypotheses", [])
            if bh:
                tier = raw_updates.setdefault("downstream_buyers", {})
                if isinstance(tier, dict) and not tier.get("companies"):
                    tier["companies"] = [
                        {"name": str(h)[:80], "city": "n/v", "country": "n/v", "relevance": "buyer hypothesis"}
                        for h in bh[:4]
                    ]
                    tier.setdefault("assessment", "Indicative — validate before outreach.")
                if not raw_updates.get("monetization_paths"):
                    raw_updates["monetization_paths"] = [str(h) for h in bh[:4]]
                if not raw_updates.get("redeployment_paths"):
                    facts = synthesis.get("facts", [])
                    if facts:
                        raw_updates["redeployment_paths"] = [str(f) for f in facts[:3]]

        # P3 bridge: if repurposing_circularity LLM synthesis left repurposing_signals empty,
        # generate indicative signals from product keywords as a last resort.
        if target_section == "industry_analysis" and task_key == "repurposing_circularity":
            if not raw_updates.get("repurposing_signals"):
                kw = hints.get("product_keywords", [])
                facts = synthesis.get("facts", [])
                if kw:
                    raw_updates["repurposing_signals"] = [
                        f"Adjacent reuse or remanufacturing may be plausible for {kw[0]} — requires validation."
                        if kw else "No validated repurposing path found yet."
                    ] + [str(f) for f in facts[:2] if f]

        # P0-2 bridge: if market_situation LLM synthesis left key_trends/demand_outlook
        # empty, fall back to the market_signals and facts the LLM DID collect.
        if target_section == "industry_analysis" and task_key == "market_situation":
            if not raw_updates.get("key_trends"):
                market_sigs = synthesis.get("market_signals", [])
                if market_sigs:
                    raw_updates["key_trends"] = market_sigs[:5]
            if not raw_updates.get("demand_outlook") or raw_updates.get("demand_outlook") == "n/v":
                facts = synthesis.get("facts", [])
                if facts:
                    raw_updates["demand_outlook"] = " ".join(str(f) for f in facts[:2])
            if not raw_updates.get("assessment") or raw_updates.get("assessment") == "n/v":
                kt = raw_updates.get("key_trends", [])
                if kt:
                    raw_updates["assessment"] = "Based on collected evidence: " + "; ".join(str(t) for t in kt[:3])

        # P0-3 bridge: if contact_discovery LLM synthesis left contacts empty,
        # extract real person names from search result titles as a fallback.
        if target_section == "contact_intelligence" and not raw_updates.get("contacts"):
            # Bug-5: pass buyer_candidates so irrelevant firms are filtered out
            _buyer_cands = (current_sections.get(target_section) or {}).get("buyer_candidates")
            bridged: list[dict[str, str]] = []
            for result in search_results[:6]:
                parsed = self._parse_contact_from_title(
                    str(result.get("title", "")), str(result.get("url", "")),
                    buyer_candidates=_buyer_cands,
                )
                if parsed:
                    bridged.append(parsed)
            if bridged:
                raw_updates["contacts"] = bridged
                raw_updates["contacts_found"] = len(bridged)
                raw_updates["firms_searched"] = len(
                    {c["firma"] for c in bridged if c.get("firma") not in {"n/v", ""}}
                )
                raw_updates.setdefault("coverage_quality", "low")

        if target_section == "company_profile" and task_key == "company_fundamentals":
            ps = raw_updates.get("products_and_services", [])
            if not ps or ps == []:
                kw = hints.get("product_keywords", [])
                if kw:
                    raw_updates["products_and_services"] = kw[:6]

        try:
            payload = self._merge_payload(
                section=target_section,
                current_payload=existing_payload,
                payload_updates=raw_updates,
                brief=brief,
                search_results=search_results,
            )
        except Exception as exc:
            if not used_llm:
                raise
            # Schicht 2: salvage valid fields from the LLM output instead of
            # discarding everything and falling back to the bare-minimum
            # fallback synthesis.  This preserves fields like founded,
            # employees, revenue even when one sibling field (e.g.
            # headquarters as dict) causes a Pydantic validation error.
            fallback_note = f"LLM payload normalization failed for {task_key}: {exc}"
            salvaged = self._salvage_valid_fields(
                target_section,
                self._normalize_payload_updates(target_section, synthesis.get("payload_updates", {})),
            )
            fallback = self._fallback_synthesis(evidence_pack)
            fallback.setdefault("open_questions", []).append(fallback_note)
            merged_updates = self._deep_merge(
                self._normalize_payload_updates(target_section, fallback.get("payload_updates", {})),
                salvaged,
            )
            # Keep the richer fact/signal lists from the original LLM synthesis.
            # Use _dedup_list instead of dict.fromkeys — items may be dicts (unhashable).
            for list_key in ("facts", "market_signals", "buyer_hypotheses", "next_actions"):
                orig = synthesis.get(list_key, [])
                fb = fallback.get(list_key, [])
                fallback[list_key] = self._dedup_list(orig + fb)
            fallback["open_questions"] = self._dedup_list(
                synthesis.get("open_questions", []) + fallback.get("open_questions", [])
            )
            synthesis = fallback
            payload = self._merge_payload(
                section=target_section,
                current_payload=existing_payload,
                payload_updates=merged_updates,
                brief=brief,
                search_results=search_results,
            )

        # Schicht 4: surface validation issues so the Critic can see them
        field_issues: list[str] = []
        if fallback_note:
            field_issues.append(fallback_note)

        return {
            "task_key": task_key,
            "section": target_section,
            "worker": self.name,
            "objective": objective,
            "model_name": model_name or self.name,
            "allowed_tools": list(granted_tools),
            "revision_request": revision_request or {},
            "payload": payload,
            "facts": synthesis.get("facts", []),
            "market_signals": synthesis.get("market_signals", []),
            "buyer_hypotheses": synthesis.get("buyer_hypotheses", []),
            "open_questions": synthesis.get("open_questions", []),
            "next_actions": synthesis.get("next_actions", []),
            "field_issues": field_issues,
            "sources": payload.get("sources", []),
            "queries_used": queries,
            "usage": {
                **llm_usage,
                "search_calls": search_calls,
                "page_fetches": page_fetches,
            },
        }

    def _build_memory_context(
        self,
        *,
        task_key: str,
        target_section: str,
        current_sections: dict[str, Any],
        role_memory: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Build cross-task memory context for the LLM.

        Schicht 3: surfaces facts already collected by earlier tasks so the
        LLM can reference them (e.g. peer names from company_fundamentals
        available to peer_companies, contact roles from discovery available
        to qualification).
        """
        ctx: dict[str, Any] = {}

        # For peer_companies / monetization: inject company_profile facts
        if task_key in {"peer_companies", "monetization_redeployment"}:
            company = current_sections.get("company_profile", {})
            if company:
                ctx["known_products"] = company.get("products_and_services", [])
                ctx["known_industry"] = company.get("industry", "n/v")
                ctx["known_description"] = (company.get("description") or "")[:300]

        # For contact_qualification: inject contact_discovery results
        if task_key == "contact_qualification":
            contacts_section = current_sections.get("contact_intelligence", {})
            if contacts_section:
                ctx["discovered_contacts"] = [
                    {k: v for k, v in c.items() if v != "n/v"}
                    for c in contacts_section.get("contacts", [])[:10]
                ]

        # For market_situation: inject any already-collected market facts
        if task_key == "market_situation":
            industry = current_sections.get("industry_analysis", {})
            if industry:
                ctx["existing_trends"] = industry.get("key_trends", [])
                ctx["existing_assessment"] = industry.get("assessment", "")
                ctx["existing_growth_rate"] = industry.get("growth_rate", "")
            # Also inject company context so the LLM can anchor market
            # analysis to the specific company's products and industry.
            company = current_sections.get("company_profile", {})
            if company:
                ctx["company_industry"] = company.get("industry", "n/v")
                ctx["company_products"] = company.get("products_and_services", [])[:5]
                ctx["company_description"] = (company.get("description") or "")[:300]

        # Inject successful queries from role memory
        if role_memory:
            successful_queries = []
            for mem in role_memory[:3]:
                successful_queries.extend(mem.get("successful_queries", [])[:5])
            if successful_queries:
                ctx["prior_successful_queries"] = self._dedup_list(successful_queries)[:10]

        return ctx

    def _derive_research_hints(self, brief: SupervisorBrief) -> dict[str, Any]:
        industry_hint = infer_industry(
            brief.page_title,
            brief.meta_description,
            brief.raw_homepage_excerpt,
        )
        product_keywords = extract_product_keywords(
            brief.raw_homepage_excerpt, company_name=brief.company_name,
        )
        return {
            "industry_hint": industry_hint or "n/v",
            "product_keywords": product_keywords,
        }

    def _build_queries(self, *, brief: SupervisorBrief, task_key: str, current_section: dict[str, Any] | None = None) -> list[str]:
        hints = self._derive_research_hints(brief)
        company_name = brief.company_name
        industry_hint = hints["industry_hint"]
        product_keywords = hints["product_keywords"]
        if task_key == "economic_commercial_situation":
            # Own distinct queries — intentionally do NOT reuse build_company_queries()
            # to avoid shared-cache hits that return company-identity results instead of
            # economic-signal results.
            return [
                f"\"{company_name}\" revenue growth financial results",
                f"\"{company_name}\" restructuring layoffs insolvency",
                f"\"{company_name}\" inventory write-down excess stock",
                f"\"{company_name}\" M&A acquisition cost cutting",
            ]

        if task_key in {"company_fundamentals", "product_asset_scope"}:
            queries = build_company_queries(company_name, brief.normalized_domain)
            if task_key == "product_asset_scope":
                queries.extend(
                    [
                        f"site:{brief.normalized_domain} {company_name} spare parts components",
                        f"\"{company_name}\" product portfolio materials",
                    ]
                )
            return queries

        if task_key in {"market_situation", "repurposing_circularity", "analytics_operational_improvement"}:
            if task_key == "market_situation":
                # Dedicated queries for market_situation — must NOT share the
                # generic build_market_queries() cache so the LLM receives
                # evidence specifically about demand, supply, and capacity.
                return [
                    f"\"{company_name}\" market demand supply trend",
                    f"{industry_hint} market outlook growth decline overcapacity",
                    f"\"{company_name}\" market share competitive position",
                    f"{industry_hint} demand forecast supply pressure {company_name}",
                ]
            queries = build_market_queries(company_name, industry_hint, product_keywords)
            if task_key == "repurposing_circularity":
                queries.extend(
                    [
                        f"{company_name} recycling reuse materials",
                        f"{' '.join(product_keywords[:3])} circular economy repurposing",
                    ]
                )
            if task_key == "analytics_operational_improvement":
                queries.extend(
                    [
                        f"\"{company_name}\" supply chain planning data",
                        f"{industry_hint} inventory visibility analytics",
                    ]
                )
            return queries

        if task_key in {"contact_discovery", "contact_qualification"}:
            raw_candidates = (current_section or {}).get("buyer_candidates") or []
            # Resolve each candidate to a plain firm name string; skip any that
            # look like schema field-path artefacts (no spaces, contains dots)
            buyer_candidates: list[str] = []
            for candidate in raw_candidates:
                firm = ""
                if isinstance(candidate, str):
                    firm = candidate.strip()
                elif isinstance(candidate, dict):
                    firm = (candidate.get("company_name") or candidate.get("name") or "").strip()
                # Guard: reject placeholder/field-path strings
                if firm and firm not in {"n/v", "n/a", "target_company"} and "." not in firm:
                    buyer_candidates.append(firm)
            queries = []
            # Search up to 5 buyer firms (was 3) — the raised search limits
            # in _QUERY_LIMITS allow more queries to actually execute.
            for firm in buyer_candidates[:5]:
                queries.extend([
                    f'"{firm}" procurement head supply chain director',
                    f'"{firm}" COO VP operations asset management',
                ])
            if not queries:
                # No valid buyer candidates — fall back to target company + industry
                queries = [
                    f'"{company_name}" procurement head supply chain director',
                    f'"{company_name}" COO VP operations asset management',
                    f'"{company_name}" {industry_hint} key accounts customer contacts',
                    f'{industry_hint} procurement director head of purchasing decision maker',
                ]
            return queries[:10]

        if task_key == "peer_companies":
            # Put targeted competitor queries FIRST so they survive the [:4] search cap.
            # P2 fix: add generic Tier-1/sector queries so obvious peers are not missed.
            peer_queries = [
                f"\"{company_name}\" competitors manufacturers",
                f"top {industry_hint} Tier 1 suppliers global ranking",
                f"{industry_hint} manufacturers europe competitors",
                f"{industry_hint} component manufacturers global competitors ranking",
            ]
            base_queries = build_buyer_queries(company_name, product_keywords, industry_hint)
            return self._dedup_list([*peer_queries, *base_queries])
        queries = build_buyer_queries(company_name, product_keywords, industry_hint)
        if task_key == "monetization_redeployment":
            queries.extend(
                [
                    f"{' '.join(product_keywords[:3])} distributors brokers marketplace",
                    f"{company_name} customers aftermarket service",
                ]
            )
        return queries

    # Task-specific search limits: contact and peer tasks need broader coverage
    _QUERY_LIMITS: dict[str, tuple[int, int]] = {
        # task_key_prefix → (max_queries, max_results)
        "contact_discovery": (8, 12),
        "contact_qualification": (8, 12),
        "peer_companies": (6, 8),
        "monetization_redeployment": (6, 8),
    }
    _DEFAULT_QUERY_LIMIT = (4, 5)

    def _search_queries(
        self,
        queries: list[str],
        *,
        granted_tools: tuple[str, ...],
        task_key: str = "",
    ) -> tuple[list[dict[str, str]], int]:
        if not tool_is_allowed(granted_tools, "search"):
            return [], 0
        max_queries, max_results = self._QUERY_LIMITS.get(
            task_key, self._DEFAULT_QUERY_LIMIT
        )
        results: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        search_calls = 0
        for query in queries[:max_queries]:
            if not query.strip():
                continue
            if query not in self._search_cache:
                search_calls += 1
                self._search_cache[query] = perform_search(query, max_results=3, timeout=3)
            for item in self._search_cache.get(query, []):
                url = str(item.get("url", "")).strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                record = {
                    "title": str(item.get("title", "n/v")),
                    "url": url,
                    "source_type": str(item.get("source_type", "secondary")),
                    "summary": str(item.get("summary", "")),
                }
                results.append(record)
                if len(results) >= max_results:
                    return results, search_calls
        return results, search_calls

    def _fetch_supporting_pages(
        self,
        results: list[dict[str, str]],
        *,
        granted_tools: tuple[str, ...],
    ) -> tuple[list[dict[str, str]], int]:
        if not tool_is_allowed(granted_tools, "page_fetch"):
            return [], 0
        if os.getenv("PYTEST_CURRENT_TEST"):
            return (
                [
                    {
                        "title": str(item.get("title", "n/v")),
                        "url": str(item.get("url", "")),
                        "reachable": "skipped",
                        "page_title": str(item.get("title", "n/v")),
                        "meta_description": "",
                        "visible_text_excerpt": "",
                    }
                    for item in results[:2]
                ],
                0,
            )
        page_evidence: list[dict[str, str]] = []
        fetches = 0
        for item in results[:2]:
            url = str(item.get("url", "")).strip()
            if not url.startswith("http"):
                continue
            if url not in self._page_cache:
                fetches += 1
                self._page_cache[url] = fetch_website_snapshot(url, timeout=3)
            snapshot = self._page_cache[url]
            page_evidence.append(
                {
                    "title": str(item.get("title", "n/v")),
                    "url": url,
                    "reachable": "yes" if snapshot.get("reachable") else "no",
                    "page_title": str(snapshot.get("title", "")),
                    "meta_description": str(snapshot.get("meta_description", "")),
                    "visible_text_excerpt": summarize_visible_text(str(snapshot.get("visible_text", "")), limit=500),
                }
            )
        return page_evidence, fetches

    def _llm_enabled(self, *, granted_tools: tuple[str, ...]) -> bool:
        if not tool_is_allowed(granted_tools, "llm_structured"):
            return False
        cfg = get_llm_config(role=self.name)
        if not cfg.get("api_key_present"):
            return False
        if os.getenv("PYTEST_CURRENT_TEST"):
            return False
        return os.getenv("LIQUISTO_DISABLE_LLM", "").strip().lower() not in {"1", "true", "yes"}

    def _client_instance(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=get_openai_api_key())
        return self._client

    def _llm_synthesis(self, evidence_pack: dict[str, Any], *, model_name: str | None = None) -> dict[str, Any]:
        config = get_llm_config(role=self.name, model=model_name)
        task_key = str(evidence_pack.get("task_key", ""))
        revision_request = evidence_pack.get("revision_request") or {}

        system_parts = [
            "You are a Liquisto research worker. Use only the supplied evidence. "
            "Never invent companies, URLs, or claims. If evidence is weak, keep outputs conservative. "
            "Return JSON with keys: payload_updates, facts, market_signals, buyer_hypotheses, "
            "open_questions, next_actions. payload_updates must only contain fields for the target section.",
        ]

        # Task-specific prompt extensions
        if task_key == "company_fundamentals":
            system_parts.append(
                "For company_fundamentals: extract CONCRETE structured fields directly from the evidence. "
                "You MUST populate: founded (year as string, e.g. '1915'), headquarters (city, country), "
                "employees (number as string, e.g. '150000'), revenue (e.g. '38 billion EUR'), "
                "goods_classification ('manufacturer', 'distributor', 'held_in_stock', 'mixed', or 'unclear'). "
                "If a field is mentioned anywhere in the evidence (titles, summaries, page excerpts), extract it. "
                "Only use 'n/v' if the field is genuinely absent from ALL evidence."
            )

        if task_key == "economic_commercial_situation":
            system_parts.append(
                "For economic_commercial_situation: you MUST populate the 'economic_situation' nested object "
                "inside payload_updates with ALL of these fields: "
                "revenue_trend (string: 'growing', 'declining', 'stable', or specific % change like '-11%'), "
                "profitability (string: EBIT margin or profit figure if found, otherwise 'n/v'), "
                "recent_events (list of concrete events: restructuring announcements, layoffs, M&A, credit rating changes), "
                "inventory_signals (list of concrete inventory or stock signals found in the evidence), "
                "financial_pressure (string: 'high', 'moderate', 'low', or 'n/v'), "
                "assessment (one paragraph summarizing the economic situation and commercial pressure). "
                "Extract ALL financial figures, restructuring news, layoff numbers, and pressure signals "
                "directly from search result titles, summaries, and page excerpts. "
                "Only use 'n/v' or [] if the field is genuinely absent from ALL evidence."
            )

        if task_key in {"contact_discovery", "contact_qualification"}:
            system_parts.append(
                "For contact tasks: extract REAL person names, job titles, and companies directly from "
                "the search result titles, summaries, and page excerpts. "
                "Each contact entry must have: name (real person, not a placeholder), title, company, source_url. "
                "Do NOT use placeholders like 'n/v', 'unknown', or 'target_company'. "
                "If a person's name appears in a title like 'John Smith, Head of Procurement at Acme Corp', "
                "extract all three fields. Return an empty list only if NO real names appear anywhere in the evidence."
            )

        if task_key == "market_situation":
            system_parts.append(
                "For market_situation: you MUST populate these fields from the evidence: "
                "assessment (overall market assessment paragraph), "
                "key_trends (list of at least 3 concrete trend statements), "
                "demand_outlook (paragraph on demand direction and why), "
                "trend_direction ('growth', 'decline', 'stable', 'moderate growth', or 'mixed'), "
                "growth_rate (specific figure if found, otherwise 'n/v'), "
                "market_size (specific figure if found, otherwise 'n/v'), "
                "overcapacity_signals (list of concrete signals from evidence), "
                "excess_stock_indicators (paragraph if evidence exists, otherwise 'n/v'). "
                "Extract concrete data points from the search results and page excerpts. "
                "Only use 'n/v' if the field is genuinely absent from ALL evidence."
            )

        if task_key == "repurposing_circularity":
            system_parts.append(
                "For repurposing_circularity: you MUST populate repurposing_signals "
                "(list of at least 2 concrete circularity or reuse statements from the evidence). "
                "Look specifically in: CDP climate questionnaires, sustainability reports, "
                "annual reports, press releases about recycling or remanufacturing. "
                "If no explicit circularity program is documented, infer plausible signals from "
                "the company's product types and restructuring news "
                "(e.g. deconsolidated product lines may become redeployable assets). "
                "Also update assessment and key_trends if the evidence contains relevant market context. "
                "Only return an empty list if the evidence contains absolutely no environmental, "
                "sustainability, or product-lifecycle signals."
            )

        if task_key == "analytics_operational_improvement":
            system_parts.append(
                "For analytics_operational_improvement: you MUST populate analytics_signals "
                "(list of at least 2 concrete operational improvement or analytics statements from the evidence). "
                "Also update assessment if the evidence contains relevant operational context. "
                "Extract concrete data points. Only use 'n/v' if genuinely absent from ALL evidence."
            )

        if task_key == "monetization_redeployment":
            system_parts.append(
                "For monetization_redeployment: you MUST populate these fields inside payload_updates: "
                "downstream_buyers.companies (list of real buyer or distributor firms found in the evidence, "
                "each with name/city/country/relevance), "
                "downstream_buyers.assessment (paragraph on buyer landscape), "
                "monetization_paths (list of concrete paths: aftermarket, licensing, refurbishment, etc.), "
                "redeployment_paths (list of concrete redeployment or adjacent-use paths). "
                "Use buyer_hypotheses you generate as the basis — turn them into concrete schema fields. "
                "Extract firm names from search result titles and summaries. "
                "Only use empty lists if no relevant companies or paths appear anywhere in the evidence."
            )

        if task_key == "peer_companies":
            system_parts.append(
                "For peer_companies: extract CONCRETE company names, cities, and countries "
                "directly from the search result titles and summaries. Do NOT use generic descriptions. "
                "Each entry in peer_competitors.companies must have a real company name found in the evidence. "
                "If no real company names are found, return an empty list — do not fabricate names. "
                "You MUST also populate peer_competitors.assessment with a paragraph that explains "
                "the competitive landscape: how many direct peers exist, what product overlap looks like, "
                "which geographies they compete in, and how the target company is positioned relative to them. "
                "Do NOT leave peer_competitors.assessment as 'n/v' — this is a required field. "
                "Also populate peer_competitors.sources with the URLs you used as evidence."
            )

        if task_key == "product_asset_scope":
            system_parts.append(
                "For product_asset_scope: you MUST populate the 'product_asset_scope' list "
                "with concrete product families, material groups, or asset types found in the evidence. "
                "Each entry should be a plain string describing a specific product category "
                "(e.g. 'automatic transmissions — manufactured', 'chassis components — manufactured', "
                "'aftermarket spare parts — distributed'). "
                "Include the commercialization type: made/manufactured, distributed, or held-in-stock. "
                "Also set 'goods_classification' to 'manufacturer', 'distributor', 'held_in_stock', "
                "'mixed', or 'unclear'. "
                "Extract from product catalog pages, press releases, annual report excerpts, and Wikipedia summaries. "
                "Only return an empty list if no specific product families appear anywhere in the evidence."
            )

        # Revision-request injection: make the LLM address specific gaps.
        # P1 fix: also inject the already-collected payload so the LLM has the
        # concrete evidence context and does not re-produce the same empty output.
        if revision_request.get("rejected_points") or revision_request.get("feedback_to_worker"):
            rejected = revision_request.get("rejected_points", [])
            feedback = revision_request.get("feedback_to_worker", [])
            revision_instructions = revision_request.get("revision_instructions", [])
            revision_note_parts = ["You are re-running a task that was previously rejected. You MUST specifically address these gaps:"]
            if rejected:
                revision_note_parts.append("Rejected points: " + "; ".join(str(p) for p in rejected))
            if feedback:
                revision_note_parts.append("Feedback: " + "; ".join(str(f) for f in feedback))
            if revision_instructions:
                revision_note_parts.append("Instructions: " + "; ".join(str(i) for i in revision_instructions))
            # Inject existing payload data so the LLM knows what is already filled
            # and can focus effort on the genuinely missing fields.
            current_section = evidence_pack.get("current_section", {})
            if current_section:
                revision_note_parts.append(
                    "Current payload (already collected — fill the MISSING fields, keep the existing ones): "
                    + json.dumps(current_section, ensure_ascii=False)[:800]
                )
            system_parts.append(" ".join(revision_note_parts))

        # Schicht 3: inject memory context so the LLM can reference
        # cross-task facts already collected by earlier tasks.
        memory_context = evidence_pack.get("memory_context", {})
        if memory_context:
            ctx_lines = ["Previously collected facts from other tasks (use as additional context, do not fabricate):"]
            for ctx_key, ctx_val in memory_context.items():
                if ctx_val and ctx_val != "n/v":
                    ctx_lines.append(f"  {ctx_key}: {json.dumps(ctx_val, ensure_ascii=False)[:500]}")
            if len(ctx_lines) > 1:
                system_parts.append(" ".join(ctx_lines))

        effective_model = model_name or str(config["structured_model"])
        response = self._client_instance().chat.completions.create(
            model=effective_model,
            temperature=float(config["temperature"]),
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": " ".join(system_parts),
                },
                {
                    "role": "user",
                    "content": json.dumps(evidence_pack, ensure_ascii=False),
                },
            ],
        )
        raw_content = response.choices[0].message.content or "{}"
        try:
            payload = json.loads(raw_content)
        except json.JSONDecodeError:
            payload = {"payload_updates": {}, "open_questions": ["Structured output could not be parsed reliably."]}
        usage = getattr(response, "usage", None)
        payload["usage"] = {
            "llm_calls": 1,
            "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        }
        return payload

    def _fallback_synthesis(self, evidence_pack: dict[str, Any]) -> dict[str, Any]:
        brief = evidence_pack["brief"]
        task_key = str(evidence_pack["task_key"])
        results = evidence_pack.get("search_results", [])
        pages = evidence_pack.get("page_evidence", [])
        titles = [str(item.get("title", "n/v")) for item in results[:4]]
        excerpts = [str(item.get("visible_text_excerpt", "")).strip() for item in pages if item.get("visible_text_excerpt")]

        payload_updates: dict[str, Any] = {}
        facts = [text for text in [brief.get("visible_text_excerpt", ""), *titles[:2]] if text and text != "n/v"][:4]
        market_signals: list[str] = []
        buyer_hypotheses: list[str] = []
        open_questions: list[str] = []
        next_actions: list[str] = []

        if evidence_pack["target_section"] == "company_profile":
            payload_updates = {
                "company_name": brief["company_name"],
                "website": brief["homepage_url"],
                "industry": brief["industry_hint"] or "n/v",
                "description": brief["visible_text_excerpt"] or "n/v",
                "products_and_services": brief["product_keywords"][:6],
            }
            if task_key == "economic_commercial_situation":
                payload_updates["economic_situation"] = {
                    "recent_events": titles[:3],
                    "inventory_signals": [
                        "Public web evidence on inventory pressure remains limited."
                        if not any("inventory" in title.lower() for title in titles)
                        else title
                        for title in titles[:1]
                    ],
                    "assessment": "Public signals indicate that commercial pressure should be validated further.",
                    "financial_pressure": "n/v",
                }
                next_actions.append("Validate commercial pressure and stock dynamics directly in the meeting.")
            if task_key == "product_asset_scope":
                payload_updates["product_asset_scope"] = [
                    f"{keyword} appears likely to matter for buyer, resale, redeployment, repurposing, or aftermarket analysis."
                    for keyword in brief["product_keywords"][:4]
                ] or ["No specific product family or asset scope was validated yet."]
                next_actions.append("Validate which SKUs, spare parts, materials, or assets are commercially movable.")

        elif evidence_pack["target_section"] == "industry_analysis":
            market_signals = titles[:3]
            payload_updates = {
                "industry_name": brief["industry_hint"] or "n/v",
                "trend_direction": "gemischt" if titles else "n/v",
                "key_trends": titles[:4],
                "demand_outlook": "Public demand signals are mixed and require validation." if titles else "n/v",
                "assessment": "Market evidence is indicative and should be strengthened with deeper external sources.",
            }
            if task_key == "repurposing_circularity":
                payload_updates["repurposing_signals"] = [
                    f"Adjacent reuse of {keyword} may be plausible but remains unvalidated."
                    for keyword in brief["product_keywords"][:3]
                ] or ["No validated repurposing path found yet."]
                next_actions.append("Test adjacent reuse and circular-economy partners for unused materials.")
            if task_key == "analytics_operational_improvement":
                payload_updates["analytics_signals"] = [
                    "Operational visibility and planning signals should be validated during discovery."
                ]
                next_actions.append("Probe forecasting, inventory visibility, and reporting bottlenecks in the meeting.")

        elif evidence_pack["target_section"] == "market_network":
            buyer_hypotheses = titles[:3]
            companies = [
                {
                    "name": title.split(" - ")[0][:80] or "n/v",
                    "city": "n/v",
                    "country": "n/v",
                    "relevance": "Indicative public-web match.",
                }
                for title in titles[:3]
            ]
            payload_updates = {
                "target_company": brief["company_name"],
            }
            if task_key == "peer_companies":
                payload_updates["peer_competitors"] = {
                    "companies": companies,
                    "assessment": "Peer landscape is indicative and should be validated further.",
                }
                next_actions.append("Validate which peer companies actually overlap on product families.")
            if task_key == "monetization_redeployment":
                payload_updates["downstream_buyers"] = {
                    "companies": companies,
                    "assessment": "Downstream buyer path remains indicative.",
                }
                payload_updates["service_providers"] = {
                    "companies": [],
                    "assessment": "Service and aftermarket path remains open.",
                }
                payload_updates["cross_industry_buyers"] = {
                    "companies": [],
                    "assessment": "Cross-industry path remains unvalidated.",
                }
                payload_updates["monetization_paths"] = [
                    f"Distributor or aftermarket path may exist for {keyword}."
                    for keyword in brief["product_keywords"][:3]
                ] or ["No credible monetization path validated yet."]
                payload_updates["redeployment_paths"] = [
                    f"Redeployment to adjacent users may be plausible for {keyword}."
                    for keyword in brief["product_keywords"][:2]
                ] or ["No validated redeployment path found yet."]
                next_actions.append("Check CRM coverage and likely buyer appetite before the meeting.")

        elif evidence_pack["target_section"] == "contact_intelligence":
            # P4 fix: extract real person names from search result titles
            # Pattern: "Name – Title | Company" or "Name - Title | Company"
            contacts = []
            for result in results[:6]:
                title = str(result.get("title", "n/v"))
                url = str(result.get("url", ""))
                parsed = self._parse_contact_from_title(title, url)
                if parsed:
                    contacts.append(parsed)
            payload_updates = {
                "contacts": contacts,
                "prioritized_contacts": [],
                "firms_searched": len({c["firma"] for c in contacts if c["firma"] != "n/v"}),
                "contacts_found": len(contacts),
                "coverage_quality": "low" if contacts else "n/v",
                "narrative_summary": "Contact intelligence coverage is limited. Further targeted research required.",
                "open_questions": ["Which decision-makers at buyer firms are most relevant for Liquisto?"],
                "sources": [],
            }
            open_questions.append("No verified contacts found — validate decision-makers directly before outreach.")

        if not results:
            open_questions.append(f"No external search evidence found for {task_key}.")
        if not excerpts:
            open_questions.append(f"Supporting page excerpts remain limited for {task_key}.")

        return {
            "payload_updates": payload_updates,
            "facts": facts,
            "market_signals": market_signals,
            "buyer_hypotheses": buyer_hypotheses,
            "open_questions": open_questions,
            "next_actions": next_actions,
        }

    def _merge_payload(
        self,
        *,
        section: str,
        current_payload: dict[str, Any],
        payload_updates: dict[str, Any],
        brief: SupervisorBrief,
        search_results: list[dict[str, str]],
    ) -> dict[str, Any]:
        hints = self._derive_research_hints(brief)
        merged = self._deep_merge(current_payload, payload_updates)
        merged["sources"] = self._merge_sources(
            current_payload.get("sources", []),
            brief.sources,
            search_results,
            merged.get("sources", []),
        )
        if section == "company_profile":
            merged.setdefault("company_name", brief.company_name)
            merged.setdefault("website", brief.homepage_url)
            merged.setdefault("industry", hints["industry_hint"] or "n/v")
        if section == "industry_analysis":
            merged.setdefault("industry_name", hints["industry_hint"] or "n/v")
        if section == "market_network":
            merged.setdefault("target_company", brief.company_name)
        if section == "contact_intelligence":
            merged.setdefault("contacts", [])
            merged.setdefault("prioritized_contacts", [])
            merged.setdefault("firms_searched", 0)
            merged.setdefault("contacts_found", 0)
            merged.setdefault("coverage_quality", "n/v")
            merged.setdefault("narrative_summary", "n/v")
            merged.setdefault("open_questions", [])
        merged = self._sanitize_for_section(section, merged)
        model = SECTION_MODELS[section].model_validate(merged)
        return model.model_dump(mode="json")

    def _normalize_payload_updates(self, section: str, payload_updates: Any) -> dict[str, Any]:
        if not isinstance(payload_updates, dict):
            return {}
        nested = payload_updates.get(section)
        if isinstance(nested, dict):
            return nested
        return payload_updates

    def _strip_default_only_payload(self, section: str, payload: dict[str, Any]) -> dict[str, Any]:
        """P1 fix: remove fields that only contain schema defaults so the LLM
        doesn't reproduce them.  Returns a copy with only non-default fields."""
        if not payload:
            return {}
        _DEFAULTS = {"n/v", "", None}
        stripped: dict[str, Any] = {}
        for k, v in payload.items():
            if isinstance(v, str) and (v.strip() in _DEFAULTS or v.strip() == "n/v"):
                continue
            if isinstance(v, list) and len(v) == 0:
                continue
            if isinstance(v, dict):
                inner = self._strip_default_only_payload(section, v)
                if inner:
                    stripped[k] = inner
                continue
            stripped[k] = v
        return stripped

    def _sanitize_for_section(self, section: str, payload: dict[str, Any]) -> dict[str, Any]:
        cleaned = self._deep_merge({}, payload)
        if section == "company_profile":
            # Schicht 1: coerce scalar string fields BEFORE Pydantic sees them.
            # Prevents a single type mismatch (e.g. headquarters as dict)
            # from blowing up the entire payload validation.
            for str_field in ("headquarters", "founded", "employees", "revenue",
                              "legal_form", "goods_classification", "company_name",
                              "website", "industry", "description"):
                if str_field in cleaned:
                    cleaned[str_field] = self._coerce_to_string(cleaned[str_field])
            for key in ("products_and_services", "product_asset_scope"):
                cleaned[key] = self._coerce_string_list(cleaned.get(key, []))
            cleaned["key_people"] = self._coerce_people(cleaned.get("key_people", []))
            cleaned["sources"] = self._coerce_sources(cleaned.get("sources", []))
            economic = cleaned.get("economic_situation", {})
            if isinstance(economic, dict):
                for econ_str in ("revenue_trend", "profitability", "financial_pressure", "assessment"):
                    if econ_str in economic:
                        economic[econ_str] = self._coerce_to_string(economic[econ_str])
                economic["recent_events"] = self._coerce_string_list(economic.get("recent_events", []))
                economic["inventory_signals"] = self._coerce_string_list(economic.get("inventory_signals", []))
                cleaned["economic_situation"] = economic
        elif section == "industry_analysis":
            for key in ("key_trends", "overcapacity_signals", "repurposing_signals", "analytics_signals"):
                cleaned[key] = self._coerce_string_list(cleaned.get(key, []))
            cleaned["sources"] = self._coerce_sources(cleaned.get("sources", []))
        elif section == "market_network":
            for tier_key in ("peer_competitors", "downstream_buyers", "service_providers", "cross_industry_buyers"):
                tier = cleaned.get(tier_key, {})
                # P3 fix: LLM returns list[dict] instead of MarketTier dict —
                # wrap it into the expected {companies, assessment, sources} shape.
                if isinstance(tier, list):
                    tier = {"companies": tier, "assessment": "n/v", "sources": []}
                if isinstance(tier, dict):
                    tier["companies"] = self._coerce_company_records(tier.get("companies", []))
                    tier["sources"] = self._coerce_sources(tier.get("sources", []))
                    cleaned[tier_key] = tier
            cleaned["monetization_paths"] = self._coerce_string_list(cleaned.get("monetization_paths", []))
            cleaned["redeployment_paths"] = self._coerce_string_list(cleaned.get("redeployment_paths", []))
        elif section == "contact_intelligence":
            cleaned["contacts"] = self._coerce_contact_records(cleaned.get("contacts", []))
            cleaned["prioritized_contacts"] = self._coerce_contact_records(cleaned.get("prioritized_contacts", []))
            cleaned["open_questions"] = self._coerce_string_list(cleaned.get("open_questions", []))
            cleaned["sources"] = self._coerce_sources(cleaned.get("sources", []))
        return cleaned

    def _coerce_to_string(self, value: Any) -> str:
        """Coerce any scalar-ish value to a plain string for Pydantic.

        Handles the common LLM patterns:
        - dict  → join values  (e.g. {"city": "X", "country": "Y"} → "X, Y")
        - int   → str
        - list  → join elements
        - None  → "n/v"
        """
        if value is None:
            return "n/v"
        if isinstance(value, str):
            return value.strip() or "n/v"
        if isinstance(value, dict):
            parts = [str(v).strip() for v in value.values() if v and str(v).strip()]
            return ", ".join(parts) if parts else "n/v"
        if isinstance(value, list):
            parts = [str(v).strip() for v in value if v and str(v).strip()]
            return ", ".join(parts) if parts else "n/v"
        return str(value).strip() or "n/v"

    def _salvage_valid_fields(
        self, section: str, payload_updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract individually valid fields from a payload that failed bulk validation.

        Tries to coerce each top-level field independently.  Fields that still
        fail after coercion are silently dropped — the fallback synthesis will
        provide safe defaults for them.
        """
        model_cls = SECTION_MODELS.get(section)
        if not model_cls or not isinstance(payload_updates, dict):
            return {}

        salvaged: dict[str, Any] = {}
        for key, value in payload_updates.items():
            if value is None or value == "n/v":
                continue
            # Try coercion for known string fields
            field_info = model_cls.model_fields.get(key)
            if field_info is not None:
                annotation = field_info.annotation
                # Simple heuristic: if the annotation is str, coerce
                if annotation is str or (hasattr(annotation, "__origin__") is False and annotation is str):
                    value = self._coerce_to_string(value)
            try:
                # Validate just this one field against the model
                model_cls.model_validate({key: value})
                salvaged[key] = value
            except Exception:
                # Try once more with coercion
                coerced = self._coerce_to_string(value) if isinstance(value, (dict, list, int, float)) else value
                try:
                    model_cls.model_validate({key: coerced})
                    salvaged[key] = coerced
                except Exception:
                    pass  # genuinely unsalvageable — fallback will handle it
        return salvaged

    def _coerce_string_list(self, items: Any) -> list[str]:
        if not isinstance(items, list):
            return []
        values: list[str] = []
        for item in items:
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                text = " | ".join(str(value).strip() for value in item.values() if str(value).strip())
            else:
                text = str(item).strip()
            if text:
                values.append(text)
        return values

    def _coerce_people(self, items: Any) -> list[dict[str, str]]:
        if not isinstance(items, list):
            return []
        people: list[dict[str, str]] = []
        for item in items:
            if isinstance(item, dict):
                people.append(
                    {
                        "name": str(item.get("name", "n/v")).strip() or "n/v",
                        "role": str(item.get("role", "n/v")).strip() or "n/v",
                    }
                )
            elif isinstance(item, str) and item.strip():
                people.append({"name": item.strip(), "role": "n/v"})
        return people

    def _coerce_company_records(self, items: Any) -> list[dict[str, str]]:
        """P2 fix: resolve multiple field-name variants for 'name'."""
        if not isinstance(items, list):
            return []
        companies: list[dict[str, str]] = []
        for item in items:
            if isinstance(item, dict):
                name = self._pick_field(item, ("name", "company_name", "company", "firm", "organisation", "organization"))
                companies.append(
                    {
                        "name": name,
                        "city": self._pick_field(item, ("city", "location", "headquarters")),
                        "country": self._pick_field(item, ("country",)),
                        "relevance": self._pick_field(item, ("relevance", "relevance_reason", "reason")),
                    }
                )
            elif isinstance(item, str) and item.strip():
                companies.append({"name": item.strip(), "city": "n/v", "country": "n/v", "relevance": "n/v"})
        return companies

    @staticmethod
    def _pick_field(item: dict[str, Any], keys: tuple[str, ...], default: str = "n/v") -> str:
        """Return the first non-empty, non-placeholder value from candidate keys."""
        for k in keys:
            v = item.get(k)
            if v and str(v).strip() and str(v).strip() != "n/v":
                return str(v).strip()
        return default

    def _coerce_contact_records(self, items: Any) -> list[dict[str, str]]:
        if not isinstance(items, list):
            return []
        contacts: list[dict[str, str]] = []
        for item in items:
            if isinstance(item, dict):
                contacts.append(self._normalize_contact_fields(item))
            elif isinstance(item, str) and item.strip():
                contacts.append({
                    "name": item.strip(), "firma": "n/v", "rolle_titel": "n/v",
                    "funktion": "n/v", "senioritaet": "n/v", "standort": "n/v",
                    "quelle": "n/v", "confidence": "inferred",
                    "relevance_reason": "n/v", "suggested_outreach_angle": "n/v",
                })
        return contacts

    def _normalize_contact_fields(self, item: dict[str, Any]) -> dict[str, str]:
        """Map common LLM field-name variants to the ContactPerson schema."""
        def _pick(keys: tuple[str, ...], default: str = "n/v") -> str:
            for k in keys:
                v = item.get(k)
                if v and str(v).strip() and str(v).strip() != "n/v":
                    return str(v).strip()
            return default

        return {
            "name": _pick(("name", "full_name", "person_name", "contact_name")),
            "firma": _pick(("firma", "company", "company_name", "organization", "firm")),
            "rolle_titel": _pick(("rolle_titel", "title", "job_title", "role", "position")),
            "funktion": _pick(("funktion", "function", "department", "area")),
            "senioritaet": _pick(("senioritaet", "seniority", "level", "seniority_level")),
            "standort": _pick(("standort", "location", "city", "office")),
            "quelle": _pick(("quelle", "source_url", "source", "url", "link")),
            "confidence": _pick(("confidence",), "inferred"),
            "relevance_reason": _pick(("relevance_reason", "relevance", "reason")),
            "suggested_outreach_angle": _pick(("suggested_outreach_angle", "outreach_angle", "outreach")),
        }

    def _coerce_sources(self, items: Any) -> list[dict[str, str]]:
        if not isinstance(items, list):
            return []
        sources: list[dict[str, str]] = []
        for item in items:
            if isinstance(item, dict):
                url = str(item.get("url", "")).strip()
                title = str(item.get("title", "")).strip() or url or "n/v"
                if not url:
                    continue
                sources.append(
                    {
                        "title": title,
                        "url": url,
                        "source_type": str(item.get("source_type", "secondary")).strip() or "secondary",
                        "summary": str(item.get("summary", "")).strip(),
                    }
                )
            elif isinstance(item, str) and item.strip():
                sources.append(
                    {
                        "title": item.strip(),
                        "url": item.strip(),
                        "source_type": "secondary",
                        "summary": "",
                    }
                )
        return sources

    def _merge_sources(self, *source_lists: list[dict[str, Any]]) -> list[dict[str, str]]:
        merged: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for source_list in source_lists:
            for item in source_list:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url", "")).strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                merged.append(
                    {
                        "title": str(item.get("title", "n/v")),
                        "url": url,
                        "source_type": str(item.get("source_type", "secondary")),
                        "summary": str(item.get("summary", ""))[:400],
                    }
                )
        return merged[:10]

    @staticmethod
    def _parse_contact_from_title(
        title: str,
        url: str,
        buyer_candidates: list[str] | None = None,
    ) -> dict[str, str] | None:
        """P4 fix: extract a contact from a search result title like
        'Tom Juedes – Managing Director | Peakstone Group'.
        Returns None if no real person name is detected.

        Bug-5 fix: when *buyer_candidates* is provided the extracted company
        must fuzzy-match at least one candidate — otherwise the contact is
        discarded as irrelevant.
        """
        # Patterns: "Name – Role | Company", "Name - Role | Company",
        # "Name – Role, Company", "Name, Role at Company"
        for sep in (" \u2013 ", " - ", " | "):
            if sep in title:
                parts = title.split(sep, 1)
                candidate_name = parts[0].strip()
                rest = parts[1].strip() if len(parts) > 1 else ""
                # A real person name has at least 2 words, no common non-name patterns
                words = candidate_name.split()
                if (
                    len(words) >= 2
                    and not any(kw in candidate_name.lower() for kw in (
                        "update", "outlook", "report", "description", "job",
                        "homepage", "press", "news", "credit", "opinion",
                        "automotive", "industry", "market", "forecast",
                    ))
                    and len(candidate_name) < 50
                ):
                    # Try to split rest into role and company
                    rolle = rest
                    firma = "n/v"
                    for role_sep in (" | ", " at ", ", "):
                        if role_sep in rest:
                            role_parts = rest.split(role_sep, 1)
                            rolle = role_parts[0].strip()
                            firma = role_parts[1].strip()
                            break

                    # Bug-5: filter out contacts whose firm does not match
                    # any known buyer candidate.
                    if buyer_candidates and firma and firma != "n/v":
                        firma_lower = firma.lower()
                        if not any(
                            bc.lower() in firma_lower or firma_lower in bc.lower()
                            for bc in buyer_candidates
                        ):
                            return None  # irrelevant firm

                    return {
                        "name": candidate_name,
                        "firma": firma if firma else "n/v",
                        "rolle_titel": rolle if rolle else "n/v",
                        "funktion": "n/v",
                        "senioritaet": "n/v",
                        "standort": "n/v",
                        "quelle": url,
                        "confidence": "inferred",
                        "relevance_reason": "Extracted from public search result.",
                        "suggested_outreach_angle": "n/v",
                    }
        return None

    def _dedup_list(self, items: list) -> list:
        """Deduplicate a list whose items may be dicts (unhashable).

        Uses JSON serialization as a stable key so that both string and dict
        items can be deduplicated without triggering 'unhashable type: dict'.
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

    def _deep_merge(self, base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged
