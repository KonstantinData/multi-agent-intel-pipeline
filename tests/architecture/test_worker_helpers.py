"""Pure architecture tests for worker data-transformation helpers.

Tests the functions extracted into src/agents/_helpers.py.
NO AG2/autogen or OpenAI dependency.
"""
from __future__ import annotations

from src.agents._helpers import (
    assess_contact_coverage,
    build_memory_context,
    coerce_contact_records,
    coerce_to_string,
    extract_financial_deep_dive,
    extract_transaction_events,
    normalize_payload_updates,
    parse_contact_from_title,
    prioritize_contact_records,
    salvage_valid_fields,
    sanitize_for_section,
)

# ---------------------------------------------------------------------------
# coerce_to_string
# ---------------------------------------------------------------------------

class TestCoerceToString:
    def test_dict_to_csv(self):
        assert coerce_to_string({"city": "Friedrichshafen", "country": "Germany"}) == "Friedrichshafen, Germany"

    def test_plain_string_passthrough(self):
        assert coerce_to_string("Berlin, Germany") == "Berlin, Germany"

    def test_none_becomes_nv(self):
        assert coerce_to_string(None) == "n/v"

    def test_int_becomes_str(self):
        assert coerce_to_string(153000) == "153000"

    def test_list_becomes_csv(self):
        assert coerce_to_string(["Berlin", "Germany"]) == "Berlin, Germany"

    def test_empty_string_becomes_nv(self):
        assert coerce_to_string("") == "n/v"

    def test_empty_dict_becomes_nv(self):
        assert coerce_to_string({}) == "n/v"


# ---------------------------------------------------------------------------
# sanitize_for_section (coerces headquarters, founded, etc.)
# ---------------------------------------------------------------------------

class TestSanitizeForSection:
    def test_coerces_headquarters_dict_to_string(self):
        payload = {
            "company_name": "ZF AG",
            "headquarters": {"city": "Friedrichshafen", "country": "Germany"},
            "founded": 1915,
            "employees": 153000,
            "financial_deep_dive": {
                "latest_fiscal_year": 2025,
                "key_financials": [{"value": "EUR 38.8bn"}],
            },
        }
        result = sanitize_for_section("company_profile", payload)
        assert isinstance(result["headquarters"], str)
        assert "Friedrichshafen" in result["headquarters"]
        assert isinstance(result["founded"], str)
        assert result["founded"] == "1915"
        assert isinstance(result["employees"], str)
        assert result["financial_deep_dive"]["latest_fiscal_year"] == "2025"
        assert "EUR 38.8bn" in result["financial_deep_dive"]["key_financials"][0]

    def test_coerces_target_company_contacts(self):
        payload = {
            "target_company_contacts": [
                {"name": "Jane Doe", "company": "ZF Group", "title": "CFO"}
            ],
            "target_company_summary": {"summary": "Finance entry point"},
        }
        result = sanitize_for_section("contact_intelligence", payload)
        assert result["target_company_contacts"][0]["firma"] == "ZF Group"
        assert result["target_company_contacts"][0]["rolle_titel"] == "CFO"
        assert result["target_company_summary"] == "Finance entry point"


# ---------------------------------------------------------------------------
# salvage_valid_fields
# ---------------------------------------------------------------------------

class TestSalvageValidFields:
    def test_rescues_valid_fields_from_mixed_payload(self):
        updates = {
            "company_name": "ZF AG",
            "founded": "1915",
            "headquarters": {"city": "Friedrichshafen", "country": "Germany"},
            "employees": "153000",
            "revenue": "38 billion EUR",
        }
        salvaged = salvage_valid_fields("company_profile", updates)
        assert "company_name" in salvaged
        assert "founded" in salvaged
        assert "employees" in salvaged
        assert "headquarters" in salvaged
        assert isinstance(salvaged["headquarters"], str)

    def test_returns_empty_for_unknown_section(self):
        assert salvage_valid_fields("unknown_section", {"x": 1}) == {}


# ---------------------------------------------------------------------------
# build_memory_context
# ---------------------------------------------------------------------------

class TestBuildMemoryContext:
    def test_injects_company_profile_for_peers(self):
        ctx = build_memory_context(
            task_key="peer_companies",
            target_section="market_network",
            current_sections={
                "company_profile": {
                    "products_and_services": ["driveline", "chassis"],
                    "industry": "Automotive",
                    "description": "Global technology company",
                }
            },
            role_memory=None,
        )
        assert ctx["known_products"] == ["driveline", "chassis"]
        assert ctx["known_industry"] == "Automotive"

    def test_injects_contacts_for_qualification(self):
        ctx = build_memory_context(
            task_key="contact_qualification",
            target_section="contact_intelligence",
            current_sections={
                "contact_intelligence": {
                    "contacts": [
                        {"name": "John Doe", "rolle_titel": "CEO", "firma": "n/v"},
                    ]
                }
            },
            role_memory=None,
        )
        assert len(ctx["discovered_contacts"]) == 1
        assert ctx["discovered_contacts"][0]["name"] == "John Doe"
        assert "firma" not in ctx["discovered_contacts"][0]

    def test_empty_when_no_relevant_sections(self):
        ctx = build_memory_context(
            task_key="company_fundamentals",
            target_section="company_profile",
            current_sections={},
            role_memory=None,
        )
        assert ctx == {}

    def test_injects_role_memory_queries(self):
        ctx = build_memory_context(
            task_key="peer_companies",
            target_section="market_network",
            current_sections={},
            role_memory=[
                {"successful_queries": ["query1", "query2", "query3"]},
            ],
        )
        assert "prior_successful_queries" in ctx
        assert "query1" in ctx["prior_successful_queries"]

    def test_market_situation_includes_company_profile(self):
        ctx = build_memory_context(
            task_key="market_situation",
            target_section="industry_analysis",
            current_sections={
                "company_profile": {
                    "industry": "Automotive",
                    "products_and_services": ["driveline", "chassis", "safety systems"],
                    "description": "Global technology company for mobility",
                }
            },
            role_memory=None,
        )
        assert ctx.get("company_industry") == "Automotive"
        assert "driveline" in ctx.get("company_products", [])

    def test_financial_deep_dive_includes_existing_economic_context(self):
        ctx = build_memory_context(
            task_key="financial_deep_dive",
            target_section="company_profile",
            current_sections={
                "company_profile": {
                    "products_and_services": ["gearboxes"],
                    "economic_situation": {"financial_pressure": "high"},
                }
            },
            role_memory=None,
        )
        assert ctx["known_economic_signals"]["financial_pressure"] == "high"
        assert ctx["known_products"] == ["gearboxes"]


# ---------------------------------------------------------------------------
# Contact field aliasing (EN → DE schema)
# ---------------------------------------------------------------------------

class TestContactCoercion:
    def test_maps_english_keys_to_schema(self):
        items = [{
            "name": "Dr. Arne Flemming",
            "company": "Robert Bosch GmbH",
            "title": "SVP Corporate Supply Chain",
            "function": "Supply Chain",
            "seniority": "C-level",
            "location": "Stuttgart",
            "source_url": "https://example.com/flemming",
            "relevance": "Key procurement decision-maker",
        }]
        result = coerce_contact_records(items)
        assert len(result) == 1
        c = result[0]
        assert c["name"] == "Dr. Arne Flemming"
        assert c["firma"] == "Robert Bosch GmbH"
        assert c["rolle_titel"] == "SVP Corporate Supply Chain"
        assert c["funktion"] == "Supply Chain"
        assert c["senioritaet"] == "C-level"
        assert c["standort"] == "Stuttgart"
        assert c["quelle"] == "https://example.com/flemming"
        assert c["relevance_reason"] == "Key procurement decision-maker"

    def test_handles_german_keys_unchanged(self):
        items = [{
            "name": "Dirk Große-Loheide",
            "firma": "Volkswagen AG",
            "rolle_titel": "Head of Procurement",
            "funktion": "Procurement",
            "senioritaet": "Board",
            "standort": "Wolfsburg",
            "quelle": "https://vw.com",
        }]
        result = coerce_contact_records(items)
        assert result[0]["firma"] == "Volkswagen AG"
        assert result[0]["rolle_titel"] == "Head of Procurement"

    def test_handles_empty_and_nv(self):
        items = [{"name": "Jane Doe", "company": "", "title": "n/v"}]
        result = coerce_contact_records(items)
        assert result[0]["firma"] == "n/v"
        assert result[0]["rolle_titel"] == "n/v"

    def test_market_network_sanitize_preserves_top_level_sources(self):
        result = sanitize_for_section(
            "market_network",
            {
                "target_company": "ACME",
                "sources": [{"title": "Press release", "url": "https://example.com/pr"}],
            },
        )
        assert result["sources"][0]["url"] == "https://example.com/pr"

    def test_parse_contact_from_title_rejects_job_postings(self):
        parsed = parse_contact_from_title(
            "Director, Procurement - OEMs | Wheels, LLC",
            "https://www.linkedin.com/jobs/view/director-procurement-oems-at-wheels-llc-4255617394",
        )
        assert parsed is None


class TestFinancialExtraction:
    def test_extract_financial_deep_dive_from_evidence_text(self):
        result = extract_financial_deep_dive(
            [
                "Revenue increased to EUR 1.4 billion in 2024 while EBIT reached EUR 95 million.",
                "Inventories rose to EUR 240 million and net working capital remained elevated.",
                "Net debt fell to EUR 110 million after a one-off restructuring charge.",
                "Inventory write-downs of EUR 12 million were recognized in 2024.",
            ]
        )
        assert result["latest_fiscal_year"] == "2024"
        assert any("revenue:" in item.lower() for item in result["key_financials"])
        assert any("inventor" in item.lower() for item in result["inventory_positions"])
        assert any("write-down" in item.lower() or "write down" in item.lower() for item in result["inventory_risks"])
        assert any("working capital" in item.lower() or "net debt" in item.lower() for item in result["balance_sheet_signals"])

    def test_extract_financial_deep_dive_captures_proxy_pressure_signals(self):
        result = extract_financial_deep_dive(
            [
                "The company announced a EUR 45 million investment in the North Carolina plant in 2025.",
                "A restructuring program includes a headcount reduction of 800 employees and short-time work at one German site.",
                "Management cited margin pressure and working-capital discipline during the transition.",
            ]
        )
        assert result["assessment"] != "n/v"
        assert any("proxy operating" in item.lower() for item in result["key_financials"])
        assert any(
            "investment" in item.lower() or "headcount" in item.lower() or "margin pressure" in item.lower()
            for item in result["balance_sheet_signals"]
        )

    def test_extract_transaction_events_captures_strategy_and_footprint_signals(self):
        result = extract_transaction_events(
            [
                "The company announced a North Carolina site expansion as part of its local-for-local strategy.",
                "A press release highlighted Poland capacity expansion tied to data center demand.",
            ]
        )
        assert result["assessment"] != "n/v"
        assert any("north carolina" in item.lower() or "poland" in item.lower() for item in result["strategic_events"])


class TestContactPrioritization:
    def test_prioritize_contacts_fills_metadata_and_coverage(self):
        prioritized = prioritize_contact_records(
            [
                {"name": "Jane Doe", "firma": "Buyer AG", "rolle_titel": "Chief Procurement Officer", "quelle": "https://example.com/jane"},
                {"name": "John Smith", "firma": "Buyer AG", "rolle_titel": "Plant Operations Director", "quelle": "https://example.com/john"},
            ],
            preferred_company_names=["Buyer AG"],
        )
        assert prioritized[0]["senioritaet"] in {"Executive", "VP", "Director"}
        assert prioritized[0]["suggested_outreach_angle"] != "n/v"
        coverage = assess_contact_coverage(
            contacts=prioritized,
            prioritized_contacts=prioritized,
            target_contacts=[],
        )
        assert coverage in {"medium", "high"}

    def test_prioritize_contacts_filters_weak_or_mismatched_buyer_candidates(self):
        prioritized = prioritize_contact_records(
            [
                {
                    "name": "Mark Taylor",
                    "firma": "Chicago Transit Authority",
                    "rolle_titel": "Bus Procurement Coordinator",
                    "quelle": "https://example.com/weak",
                },
                {
                    "name": "Jane Miller",
                    "firma": "Buyer AG",
                    "rolle_titel": "Head of Procurement",
                    "quelle": "https://example.com/strong",
                },
            ],
            preferred_company_names=["Buyer AG"],
        )
        assert len(prioritized) == 1
        assert prioritized[0]["name"] == "Jane Miller"

    def test_target_contact_prioritization_prefers_operational_owner_over_ceo(self):
        prioritized = prioritize_contact_records(
            [
                {
                    "name": "Alice Meyer",
                    "firma": "Target AG",
                    "rolle_titel": "CEO",
                    "quelle": "https://example.com/ceo",
                },
                {
                    "name": "Bob Schneider",
                    "firma": "Target AG",
                    "rolle_titel": "Director Supply Chain Europe",
                    "quelle": "https://example.com/scm",
                },
            ],
            preferred_company_names=["Target AG"],
            target_company_mode=True,
        )
        assert prioritized[0]["name"] == "Bob Schneider"

    def test_buyer_contact_prioritization_requires_asset_fit_and_verification(self):
        prioritized = prioritize_contact_records(
            [
                {
                    "name": "Mark Taylor",
                    "firma": "Buyer AG",
                    "rolle_titel": "Head of Procurement",
                    "quelle": "https://example.com/weak",
                    "verification_status": "role_inferred",
                    "relevance_reason": "General procurement role.",
                },
                {
                    "name": "Jane Miller",
                    "firma": "Buyer AG",
                    "rolle_titel": "Head of Aftermarket Procurement",
                    "quelle": "https://example.com/strong",
                    "verification_status": "partially_verified",
                    "relevance_reason": "Owns spare-parts and aftermarket channel sourcing relevant for excess inventory resale.",
                },
            ],
            preferred_company_names=["Buyer AG"],
        )
        assert len(prioritized) == 1
        assert prioritized[0]["name"] == "Jane Miller"

    def test_buyer_contact_prioritization_filters_non_person_names(self):
        prioritized = prioritize_contact_records(
            [
                {
                    "name": "Director, Procurement - OEMs",
                    "firma": "Buyer AG",
                    "rolle_titel": "Director, Procurement - OEMs",
                    "quelle": "https://example.com/job-posting",
                    "verification_status": "partially_verified",
                    "relevance_reason": "Aftermarket sourcing relevance.",
                },
                {
                    "name": "Jane Miller",
                    "firma": "Buyer AG",
                    "rolle_titel": "Head of Aftermarket Procurement",
                    "quelle": "https://example.com/jane",
                    "verification_status": "partially_verified",
                    "relevance_reason": "Owns spare-parts sourcing.",
                },
            ],
            preferred_company_names=["Buyer AG"],
        )
        assert [item["name"] for item in prioritized] == ["Jane Miller"]

    def test_contact_coverage_does_not_promote_raw_buyer_count_without_prioritized_contacts(self):
        coverage = assess_contact_coverage(
            contacts=[
                {"name": "Weak One", "firma": "Buyer 1", "rolle_titel": "Coordinator", "quelle": "https://example.com/1"},
                {"name": "Weak Two", "firma": "Buyer 2", "rolle_titel": "Analyst", "quelle": "https://example.com/2"},
                {"name": "Weak Three", "firma": "Buyer 3", "rolle_titel": "Specialist", "quelle": "https://example.com/3"},
            ],
            prioritized_contacts=[],
            target_contacts=[],
        )
        assert coverage == "low"


# ---------------------------------------------------------------------------
# normalize_payload_updates
# ---------------------------------------------------------------------------

class TestNormalizePayloadUpdates:
    def test_unwraps_nested_section_key(self):
        result = normalize_payload_updates(
            "company_profile",
            {"company_profile": {"company_name": "ACME", "industry": "Automation"}},
        )
        assert result == {"company_name": "ACME", "industry": "Automation"}

    def test_passthrough_flat_updates(self):
        result = normalize_payload_updates(
            "company_profile",
            {"company_name": "ACME"},
        )
        assert result == {"company_name": "ACME"}

    def test_non_dict_returns_empty(self):
        assert normalize_payload_updates("x", "not a dict") == {}
