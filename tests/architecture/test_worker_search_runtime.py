from __future__ import annotations

import pytest

from src.domain.intake import SupervisorBrief
from src.research.search import build_company_queries


def _worker_cls():
    pytest.importorskip("openai")
    from src.agents.worker import ResearchWorker
    return ResearchWorker


def _brief() -> SupervisorBrief:
    return SupervisorBrief(
        submitted_company_name="ZIEHL-ABEGG",
        submitted_web_domain="ziehl-abegg.com",
        verified_company_name="ZIEHL-ABEGG",
        verified_legal_name="ZIEHL-ABEGG SE",
        name_confidence="high",
        website_reachable=True,
        homepage_url="https://www.ziehl-abegg.com/",
        page_title="ZIEHL-ABEGG",
        meta_description="Ventilatoren und Antriebstechnik",
        raw_homepage_excerpt="Ventilatoren, Elektromotoren, Regeltechnik",
        normalized_domain="ziehl-abegg.com",
    )


def test_build_company_queries_contains_financial_basics():
    queries = build_company_queries("ZIEHL-ABEGG SE", "ziehl-abegg.com")
    lowered = " | ".join(queries).lower()
    assert "revenue" in lowered or "umsatz" in lowered
    assert "employees" in lowered or "mitarbeiter" in lowered
    assert "bundesanzeiger" in lowered
    assert "unternehmensregister" in lowered


def test_search_queries_use_extended_timeout_and_task_result_cap(monkeypatch):
    seen_calls: list[tuple[int, int]] = []

    def _fake_search(query: str, *, max_results: int = 5, timeout: int = 20):
        seen_calls.append((max_results, timeout))
        return [
            {"title": "Result", "url": "https://example.com/r1", "source_type": "secondary", "summary": "ok"}
        ]

    monkeypatch.setattr("src.agents.worker.perform_search", _fake_search)
    worker = _worker_cls()("CompanyResearcher")
    results, _ = worker._search_queries(
        ['"Ziehl-Abegg" annual report'],
        granted_tools=("search",),
        task_key="financial_deep_dive",
    )
    assert results
    assert seen_calls
    max_results, timeout = seen_calls[0]
    assert max_results == 12
    assert timeout >= 18


def test_company_fundamentals_extracts_revenue_and_employees_from_search_summary(monkeypatch):
    def _fake_search(query: str, *, max_results: int = 5, timeout: int = 20):
        return [
            {
                "title": "Ziehl-Abegg verzeichnet Rekordjahr 2023",
                "url": "https://www.ziehl-abegg.com/presse/rekordjahr",
                "source_type": "owned",
                "summary": "Geschäftsjahr 2023: Umsatz 955 Mio. EUR. Ziehl-Abegg beschäftigt 5.300 Mitarbeiter.",
            }
        ]

    monkeypatch.setattr("src.agents.worker.perform_search", _fake_search)
    worker = _worker_cls()("CompanyResearcher")
    result = worker.run(
        brief=_brief(),
        task_key="company_fundamentals",
        target_section="company_profile",
        objective="Basisdaten recherchieren",
        current_sections={},
        allowed_tools=("search",),
    )
    payload = result.get("payload", {})
    assert payload.get("revenue") not in {None, "", "n/v"}
    assert payload.get("employees") not in {None, "", "n/v"}

