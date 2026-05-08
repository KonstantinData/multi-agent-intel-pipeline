from __future__ import annotations

from src.research.search import build_company_queries


def test_build_company_queries_contains_financial_basics():
    queries = build_company_queries("ZIEHL-ABEGG SE", "ziehl-abegg.com")
    lowered = " | ".join(queries).lower()
    assert "revenue" in lowered or "umsatz" in lowered
    assert "employees" in lowered or "mitarbeiter" in lowered
    assert "bundesanzeiger" in lowered
    assert "unternehmensregister" in lowered

