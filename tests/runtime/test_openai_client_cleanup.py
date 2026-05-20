"""OpenAI client lifecycle regressions for runtime exit stability."""
from __future__ import annotations

import json
import sys
import types
from typing import Any


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Message(content)


class _ChatResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.choices = [_Choice(json.dumps(payload))]
        self.usage = types.SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)


class _FakeChatCompletions:
    def __init__(self, response_payload: dict[str, Any]) -> None:
        self._response_payload = response_payload

    def create(self, **_: Any) -> _ChatResponse:
        return _ChatResponse(self._response_payload)


class _FakeResponses:
    def create(self, **_: Any) -> Any:
        citation = types.SimpleNamespace(
            type="url_citation",
            url="https://example.com/source?utm_source=test",
            title="Example Source",
        )
        output_text = types.SimpleNamespace(
            type="output_text",
            text="search summary",
            annotations=[citation],
        )
        message = types.SimpleNamespace(type="message", content=[output_text])
        return types.SimpleNamespace(output=[message])


class _FakeOpenAI:
    instances: list[_FakeOpenAI] = []
    response_payload: dict[str, Any] = {}

    def __init__(self, **_: Any) -> None:
        self.closed = False
        self.chat = types.SimpleNamespace(
            completions=_FakeChatCompletions(self.response_payload)
        )
        self.responses = _FakeResponses()
        self.instances.append(self)

    def close(self) -> None:
        self.closed = True


def _install_fake_openai(monkeypatch, payload: dict[str, Any]) -> None:
    _FakeOpenAI.instances = []
    _FakeOpenAI.response_payload = payload
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeOpenAI))


def test_search_client_is_closed(monkeypatch) -> None:
    from src.research import search

    _install_fake_openai(monkeypatch, {})
    monkeypatch.setattr(search, "get_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(search, "get_openai_max_retries", lambda: 0)
    monkeypatch.setattr(search, "get_search_model", lambda: "test-model")

    results = search.perform_search("industrial sensors", max_results=1)

    assert results[0]["url"] == "https://example.com/source"
    assert _FakeOpenAI.instances[-1].closed is True


def test_keyword_extraction_client_is_closed(monkeypatch) -> None:
    from src.research import extract

    _install_fake_openai(monkeypatch, {"keywords": ["sensor", "automation"]})
    monkeypatch.setattr(extract, "get_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(extract, "get_openai_timeout_seconds", lambda: 1)
    monkeypatch.setattr(extract, "get_openai_max_retries", lambda: 0)
    monkeypatch.setattr(extract, "get_extraction_model", lambda: "test-model")

    keywords = extract._llm_extract_keywords("industrial sensor automation", company_name="ACME")

    assert keywords == ["sensor", "automation"]
    assert _FakeOpenAI.instances[-1].closed is True


def test_report_writer_client_is_closed(monkeypatch) -> None:
    from src.agents.report_writer import ReportWriterAgent

    _install_fake_openai(
        monkeypatch,
        {
            "language": "en",
            "run_id": "run-1",
            "run_status": "blocked_not_meeting_ready",
            "company_name": "ACME",
            "report_title": "Report",
            "executive_summary": "Summary",
            "primary_opportunity_path": "Path",
            "primary_opportunity_reasoning": "Reason",
            "confidence": "medium",
            "top_risks": [],
            "next_steps": [],
            "blocker_summary": "",
            "data_request_summary": "",
            "outreach_playbook_summary": "",
            "validation_notes": [],
            "sections": [],
        },
    )

    agent = ReportWriterAgent()
    payload = agent._compose_with_llm(language="en", blueprint={}, context={})

    assert _FakeOpenAI.instances[-1].closed is True
    assert payload["_usage"] == {
        "provider": "openai",
        "model": agent.structured_model or agent.chat_model,
        "llm_calls": 1,
        "prompt_tokens": 1,
        "completion_tokens": 1,
        "total_tokens": 2,
    }


def test_pdf_translation_clients_are_closed(monkeypatch) -> None:
    import src.config.settings as settings
    from src.exporters import pdf_report

    _install_fake_openai(monkeypatch, {"syn_exec": "Zusammenfassung", "t0": "Zusammenfassung"})
    monkeypatch.setattr(settings, "get_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(settings, "get_translation_model", lambda: "test-model")

    translated = pdf_report._translate_content(
        {"synthesis": {"executive_summary": "hello and the supply chain"}},
        "de",
    )
    residual = pdf_report._translate_residual_strings(
        {"text": "hello and the supply chain"},
        "de",
    )

    assert translated["synthesis"]["executive_summary"] == "Zusammenfassung"
    assert residual["text"] == "Zusammenfassung"
    assert [client.closed for client in _FakeOpenAI.instances] == [True, True]
