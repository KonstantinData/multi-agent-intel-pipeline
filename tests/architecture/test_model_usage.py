"""Architecture tests for provider usage and reasoning telemetry helpers."""

from __future__ import annotations

import types

from src.config import (
    build_reasoning_realized_record,
    build_usage_record,
    extract_thinking_tokens,
)


def test_extract_thinking_tokens_from_completion_details_object():
    usage = types.SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        completion_tokens_details=types.SimpleNamespace(reasoning_tokens=3),
    )

    assert extract_thinking_tokens(usage) == 3


def test_extract_thinking_tokens_from_dict_payload():
    usage = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "output_tokens_details": {"reasoning_tokens": 4},
    }

    assert extract_thinking_tokens(usage) == 4


def test_build_usage_record_keeps_token_counts_canonical():
    usage = types.SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        completion_tokens_details=types.SimpleNamespace(reasoning_tokens=3),
    )

    assert build_usage_record(
        usage,
        provider="openai",
        model="gpt-5-mini",
        llm_calls=1,
    ) == {
        "provider": "openai",
        "model": "gpt-5-mini",
        "llm_calls": 1,
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "thinking_tokens": 3,
    }


def test_reasoning_realized_is_only_built_when_tokens_exist():
    no_reasoning_usage = types.SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    reasoning_usage = types.SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        completion_tokens_details=types.SimpleNamespace(reasoning_tokens=3),
    )

    assert build_reasoning_realized_record(no_reasoning_usage, planned_effort="high") is None
    assert build_reasoning_realized_record(reasoning_usage, planned_effort="high") == {
        "effort_used": "high",
        "thinking_tokens": 3,
        "reasoning_summary_available": False,
    }
