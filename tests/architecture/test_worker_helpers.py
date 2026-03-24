"""Pure architecture tests for worker data-transformation helpers.

Tests the functions extracted into src/agents/_helpers.py.
NO AG2/autogen or OpenAI dependency.
"""
from __future__ import annotations

from src.agents._helpers import (
    coerce_to_string,
    coerce_contact_records,
    sanitize_for_section,
    salvage_valid_fields,
    build_memory_context,
    normalize_payload_updates,
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
        }
        result = sanitize_for_section("company_profile", payload)
        assert isinstance(result["headquarters"], str)
        assert "Friedrichshafen" in result["headquarters"]
        assert isinstance(result["founded"], str)
        assert result["founded"] == "1915"
        assert isinstance(result["employees"], str)


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
