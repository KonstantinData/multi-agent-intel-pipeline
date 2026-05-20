"""Architecture tests for AG2 usage normalization."""

from __future__ import annotations

import pytest

from src.orchestration.ag2_usage import build_ag2_usage_delta, snapshot_ag2_usage


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
