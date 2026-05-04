from __future__ import annotations

import pytest

from src.domain.intake import SupervisorBrief


class _FakeMessage:
    content = '{"payload_updates": {"company_name": "TestCo"}, "open_questions": []}'


class _FakeChoice:
    message = _FakeMessage()


class _FakeUsage:
    prompt_tokens = 3
    completion_tokens = 4
    total_tokens = 7


class _FakeResponse:
    choices = [_FakeChoice()]
    usage = _FakeUsage()


class _FakeCompletions:
    def __init__(self, owner, *, fail: bool = False):
        self.owner = owner
        self.fail = fail

    def create(self, **kwargs):
        self.owner.requests.append(kwargs)
        if self.fail:
            raise RuntimeError("llm failure")
        return _FakeResponse()


class _FakeChat:
    def __init__(self, owner, *, fail: bool = False):
        self.completions = _FakeCompletions(owner, fail=fail)


class _FakeOpenAIClient:
    def __init__(self, *, fail: bool = False):
        self.closed = False
        self.requests: list[dict] = []
        self.chat = _FakeChat(self, fail=fail)

    def close(self):
        self.closed = True


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


def test_search_queries_use_extended_timeout_and_task_result_cap(monkeypatch):
    seen_calls: list[tuple[int, int]] = []

    def _fake_search(query: str, *, max_results: int = 5, timeout: int = 20):
        seen_calls.append((max_results, timeout))
        return [
            {
                "title": "Result",
                "url": "https://example.com/r1",
                "source_type": "secondary",
                "summary": "ok",
            }
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
                "summary": (
                    "Geschäftsjahr 2023: Umsatz 955 Mio. EUR. "
                    "Ziehl-Abegg beschäftigt 5.300 Mitarbeiter."
                ),
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


def test_llm_synthesis_closes_openai_client_after_success():
    worker = _worker_cls()("CompanyResearcher")
    fake_client = _FakeOpenAIClient()
    worker._client = fake_client

    result = worker._llm_synthesis(
        {
            "brief": {"company_name": "TestCo"},
            "task_key": "company_fundamentals",
            "search_results": [],
            "page_evidence": [],
        }
    )

    assert result["payload_updates"]["company_name"] == "TestCo"
    assert fake_client.closed is True
    assert worker._client is None


def test_llm_synthesis_bounds_request_message_content():
    worker = _worker_cls()("CompanyResearcher")
    fake_client = _FakeOpenAIClient()
    worker._new_client = lambda: fake_client
    oversized_text = "x" * 100_000

    worker._llm_synthesis(
        {
            "brief": {"company_name": "TestCo"},
            "task_key": "company_fundamentals",
            "search_results": [{"summary": oversized_text}],
            "page_evidence": [{"visible_text_excerpt": oversized_text}],
            "current_section": {"oversized": oversized_text},
            "memory_context": {"oversized": oversized_text},
        }
    )

    messages = fake_client.requests[0]["messages"]
    assert len(messages[0]["content"]) <= 12_012
    assert len(messages[1]["content"]) <= 24_012
    assert fake_client.closed is True


def test_llm_synthesis_closes_openai_client_after_failure():
    worker = _worker_cls()("CompanyResearcher")
    fake_client = _FakeOpenAIClient(fail=True)
    worker._client = fake_client

    with pytest.raises(RuntimeError, match="llm failure"):
        worker._llm_synthesis(
            {
                "brief": {"company_name": "TestCo"},
                "task_key": "company_fundamentals",
                "search_results": [],
                "page_evidence": [],
            }
        )

    assert fake_client.closed is True
    assert worker._client is None
