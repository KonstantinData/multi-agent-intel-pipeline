from __future__ import annotations

from src.config.pricing import (
    estimate_cost_usd,
    estimate_web_search_preview_call_cost_usd,
)


def test_estimate_cost_supports_gpt5_and_gpt5_mini_defaults():
    gpt5_cost = estimate_cost_usd(
        model_name="gpt-5",
        prompt_tokens=2_328,
        completion_tokens=9_382,
    )
    gpt5_mini_cost = estimate_cost_usd(
        model_name="gpt-5-mini",
        prompt_tokens=17_771,
        completion_tokens=22_799,
    )
    assert gpt5_cost == 0.09673
    assert gpt5_mini_cost == 0.05004075


def test_web_search_preview_call_cost_defaults_to_reasoning_rate_for_gpt5():
    cost = estimate_web_search_preview_call_cost_usd(
        search_calls=59,
        model_name="gpt-5-mini",
    )
    assert cost == 0.59


def test_web_search_preview_call_cost_defaults_to_non_reasoning_rate():
    cost = estimate_web_search_preview_call_cost_usd(
        search_calls=4,
        model_name="gpt-4.1-mini",
    )
    assert cost == 0.1
