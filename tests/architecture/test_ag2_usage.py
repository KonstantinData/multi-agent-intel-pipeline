"""Architecture tests for AG2 usage normalization."""

from __future__ import annotations

import pytest

from src.orchestration.ag2_usage import (
    _merge_summary_reasoning_delta,
    _with_reasoning_token_fields,
    build_ag2_usage_delta,
    snapshot_ag2_usage,
)


class _FakeAgent:
    def __init__(self, usage):
        self.usage = usage

    def get_actual_usage(self):
        return self.usage


def test_snapshot_ag2_usage_returns_detached_dict():
    source = _FakeAgent({"gpt-5-mini": {"total_tokens": 10}})

    snapshot = snapshot_ag2_usage(source)
    source.usage["gpt-5-mini"]["total_tokens"] = 99

    assert snapshot == {"gpt-5-mini": {"total_tokens": 10}}


def test_ag2_usage_delta_normalizes_nested_model_summary():
    before = {
        "total_cost": 0.01,
        "gpt-5-mini-2025-08-07": {
            "cost": 0.01,
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }
    after = {
        "total_cost": 0.03,
        "gpt-5-mini-2025-08-07": {
            "cost": 0.03,
            "prompt_tokens": 30,
            "completion_tokens": 12,
            "total_tokens": 42,
            "reasoning_tokens": 4,
        },
    }

    usage = build_ag2_usage_delta(
        before=before,
        after=after,
        model="gpt-5-mini",
    )

    assert usage == {
        "provider": "openai",
        "model": "gpt-5-mini",
        "llm_calls": 1,
        "prompt_tokens": 20,
        "completion_tokens": 7,
        "total_tokens": 27,
        "thinking_tokens": 4,
        "estimated_cost_usd": pytest.approx(0.02),
    }


def test_ag2_usage_delta_returns_none_without_new_usage():
    before = {
        "gpt-4.1": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }
    }

    assert build_ag2_usage_delta(before=before, after=before, model="gpt-4.1") is None


def test_ag2_usage_delta_supports_direct_usage_payload():
    after = {
        "model": "gpt-4.1-mini",
        "prompt_tokens": 8,
        "completion_tokens": 2,
        "total_tokens": 10,
    }

    assert build_ag2_usage_delta(before={}, after=after, model="gpt-4.1-mini") == {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "llm_calls": 1,
        "prompt_tokens": 8,
        "completion_tokens": 2,
        "total_tokens": 10,
    }


def test_ag2_usage_delta_extracts_nested_reasoning_details():
    after = {
        "gpt-5-mini": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "completion_tokens_details": {"reasoning_tokens": 7},
        }
    }

    usage = build_ag2_usage_delta(before={}, after=after, model="gpt-5-mini")

    assert usage is not None
    assert usage["thinking_tokens"] == 7


def test_ag2_openai_usage_enrichment_preserves_provider_reasoning_tokens():
    payload = {"model": "gpt-5-mini", "prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}
    provider_usage = {"completion_tokens_details": {"reasoning_tokens": 5}}

    enriched = _with_reasoning_token_fields(payload, provider_usage)

    assert enriched["thinking_tokens"] == 5
    assert enriched["reasoning_tokens"] == 5
    assert "thinking_tokens" not in payload


def test_ag2_usage_summary_merge_avoids_double_counting_reasoning_tokens():
    summary = {
        "total_cost": 0.0,
        "gpt-5-mini": {
            "cost": 0.0,
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "thinking_tokens": 6,
            "reasoning_tokens": 6,
        },
    }
    response_usage = {"model": "gpt-5-mini", "reasoning_tokens": 6}

    _merge_summary_reasoning_delta(summary, response_usage, before_tokens=0)

    assert summary["gpt-5-mini"]["thinking_tokens"] == 6
    assert summary["gpt-5-mini"]["reasoning_tokens"] == 6


def test_ag2_usage_summary_merge_adds_missing_reasoning_tokens():
    summary = {
        "total_cost": 0.0,
        "gpt-5-mini": {
            "cost": 0.0,
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        },
    }
    response_usage = {"model": "gpt-5-mini", "reasoning_tokens": 6}

    _merge_summary_reasoning_delta(summary, response_usage, before_tokens=0)

    assert summary["gpt-5-mini"]["thinking_tokens"] == 6
    assert summary["gpt-5-mini"]["reasoning_tokens"] == 6
