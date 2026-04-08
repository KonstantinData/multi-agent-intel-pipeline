"""Phase 3 — Runtime parity tests: legacy _build_queries() vs resolve_queries().

For each of the 11 task keys the test asserts that the new resolver produces
the same query list as the legacy path using a fixed SupervisorBrief fixture.

Migration rule: the resolver must NOT proceed until these tests are green.
"""
from __future__ import annotations

import os
import pytest

# Suppress LLM calls in tests
os.environ.setdefault("PYTEST_CURRENT_TEST", "1")

from src.domain.intake import SupervisorBrief
from src.research.query_resolver import resolve_queries, clear_strategy_cache

# ---------------------------------------------------------------------------
# Fixed brief fixture — identical for every task to ensure deterministic output
# ---------------------------------------------------------------------------

_BRIEF = SupervisorBrief(
    submitted_company_name="Acme Automotive GmbH",
    submitted_web_domain="acme-automotive.de",
    verified_company_name="Acme Automotive GmbH",
    verified_legal_name="Acme Automotive Gesellschaft mit beschränkter Haftung",
    name_confidence="high",
    website_reachable=True,
    homepage_url="https://www.acme-automotive.de",
    page_title="Acme Automotive GmbH – Brake Systems & Components",
    meta_description="Acme Automotive manufactures brake systems, chassis components and spare parts.",
    raw_homepage_excerpt=(
        "Acme Automotive GmbH specialises in brake systems, chassis components, "
        "spare parts and aftermarket solutions for automotive OEMs and distributors."
    ),
    normalized_domain="acme-automotive.de",
    industry_hint="n/v",
)

# Fixture with NO industry/keywords to test fallback paths
_BRIEF_BARE = SupervisorBrief(
    submitted_company_name="BareCo GmbH",
    submitted_web_domain="bareco.de",
    verified_company_name="BareCo GmbH",
    verified_legal_name="BareCo GmbH",
    name_confidence="high",
    website_reachable=True,
    homepage_url="https://www.bareco.de",
    page_title="BareCo",
    meta_description="",
    raw_homepage_excerpt="",
    normalized_domain="bareco.de",
    industry_hint="n/v",
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear LRU strategy cache between tests."""
    clear_strategy_cache()
    yield
    clear_strategy_cache()


# ---------------------------------------------------------------------------
# Helper: call legacy _build_queries via worker directly
# ---------------------------------------------------------------------------

def _legacy_build(brief: SupervisorBrief, task_key: str, current_section: dict | None = None) -> list[str]:
    from src.agents.worker import ResearchWorker
    worker = ResearchWorker(name="test-worker")
    return worker._build_queries_legacy(brief=brief, task_key=task_key, current_section=current_section or {})


# ---------------------------------------------------------------------------
# Parity tests — all 11 task keys
# ---------------------------------------------------------------------------

COMPANY_TASKS = [
    "company_fundamentals",
    "economic_commercial_situation",
    "financial_deep_dive",
    "product_asset_scope",
    "transaction_event_intelligence",
]

MARKET_TASKS = ["market_situation"]

BUYER_TASKS = ["peer_companies", "monetization_redeployment"]

CONTACT_TASKS = ["target_company_contacts"]


@pytest.mark.parametrize("task_key", COMPANY_TASKS + MARKET_TASKS + BUYER_TASKS + CONTACT_TASKS)
def test_parity_fixed_brief(task_key: str) -> None:
    """Resolver output must exactly match legacy output for the fixed brief."""
    legacy = _legacy_build(_BRIEF, task_key)
    resolved = resolve_queries(task_key, _BRIEF)
    assert resolved == legacy, (
        f"Parity failure for task '{task_key}':\n"
        f"  legacy   ({len(legacy)}): {legacy}\n"
        f"  resolved ({len(resolved)}): {resolved}"
    )


@pytest.mark.parametrize("task_key", COMPANY_TASKS + MARKET_TASKS + BUYER_TASKS + CONTACT_TASKS)
def test_parity_bare_brief(task_key: str) -> None:
    """Resolver output must match legacy for a bare brief (no keywords/industry)."""
    legacy = _legacy_build(_BRIEF_BARE, task_key)
    resolved = resolve_queries(task_key, _BRIEF_BARE)
    assert resolved == legacy, (
        f"Bare-brief parity failure for task '{task_key}':\n"
        f"  legacy   ({len(legacy)}): {legacy}\n"
        f"  resolved ({len(resolved)}): {resolved}"
    )


def test_parity_contact_discovery_with_buyers() -> None:
    """Contact tasks with buyer candidates must produce the same buyer-expanded queries."""
    current_section = {
        "buyer_candidates": [
            {"company_name": "ZF Friedrichshafen AG"},
            "Continental AG",
            "Magna International",
        ]
    }
    for task_key in ("contact_discovery", "contact_qualification"):
        legacy = _legacy_build(_BRIEF, task_key, current_section=current_section)
        resolved = resolve_queries(task_key, _BRIEF, current_section=current_section)
        assert resolved == legacy, (
            f"Buyer-candidate parity failure for '{task_key}':\n"
            f"  legacy   ({len(legacy)}): {legacy}\n"
            f"  resolved ({len(resolved)}): {resolved}"
        )


def test_parity_contact_discovery_no_buyers() -> None:
    """Contact fallback (no valid candidates) must match legacy."""
    for task_key in ("contact_discovery", "contact_qualification"):
        legacy = _legacy_build(_BRIEF, task_key, current_section={})
        resolved = resolve_queries(task_key, _BRIEF, current_section={})
        assert resolved == legacy, (
            f"Fallback parity failure for '{task_key}':\n"
            f"  legacy   ({len(legacy)}): {legacy}\n"
            f"  resolved ({len(resolved)}): {resolved}"
        )


# ---------------------------------------------------------------------------
# query_overrides semantics (Option A — preserve or-idiom exactly)
# ---------------------------------------------------------------------------

def test_override_non_empty_skips_resolver() -> None:
    overrides = ["custom query A", "custom query B"]
    result = resolve_queries("company_fundamentals", _BRIEF, query_overrides=overrides)
    assert result == overrides


def test_override_empty_list_falls_through_to_resolver() -> None:
    """[] is falsy — must fall through to strategy resolution, not return []."""
    result_empty_override = resolve_queries("company_fundamentals", _BRIEF, query_overrides=[])
    result_none_override = resolve_queries("company_fundamentals", _BRIEF, query_overrides=None)
    assert result_empty_override == result_none_override
    assert len(result_empty_override) > 0


def test_override_none_uses_resolver() -> None:
    result = resolve_queries("company_fundamentals", _BRIEF, query_overrides=None)
    assert isinstance(result, list)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# Error contract
# ---------------------------------------------------------------------------

def test_unknown_task_key_raises_key_error() -> None:
    with pytest.raises(KeyError, match="Unknown task key"):
        resolve_queries("nonexistent_task", _BRIEF)


def test_resolver_returns_non_empty_for_all_tasks() -> None:
    all_tasks = list(COMPANY_TASKS + MARKET_TASKS + BUYER_TASKS + CONTACT_TASKS)
    for task_key in all_tasks:
        result = resolve_queries(task_key, _BRIEF)
        assert isinstance(result, list), f"Expected list for {task_key}"
        assert len(result) > 0, f"Expected non-empty list for {task_key}"
