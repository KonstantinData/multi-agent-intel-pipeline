"""Normalize AG2 usage summaries for RuntimeStep telemetry."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.config.model_usage import extract_thinking_tokens

_TOKEN_KEYS = {
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "thinking_tokens",
    "reasoning_tokens",
}
_CALL_KEYS = ("llm_calls", "num_calls", "calls", "call_count")


def snapshot_ag2_usage(source: Any) -> dict[str, Any]:
    """Return a detached AG2 actual-usage snapshot from an agent-like object."""

    if source is None or not hasattr(source, "get_actual_usage"):
        return {}
    try:
        usage = source.get_actual_usage()
    except Exception:
        return {}
    return deepcopy(usage) if isinstance(usage, dict) else {}


def build_ag2_usage_delta(
    *,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    provider: str = "openai",
    model: str = "",
) -> dict[str, Any] | None:
    """Build a canonical RuntimeStep usage record from two AG2 snapshots."""

    after_flat = _select_usage(after or {}, preferred_model=model)
    before_flat = _select_usage(before or {}, preferred_model=after_flat.get("model") or model)
    if not after_flat:
        return None

    prompt_tokens = _positive_delta(after_flat, before_flat, "prompt_tokens")
    completion_tokens = _positive_delta(after_flat, before_flat, "completion_tokens")
    total_tokens = _positive_delta(after_flat, before_flat, "total_tokens")
    thinking_tokens = max(
        _positive_delta(after_flat, before_flat, "thinking_tokens"),
        _positive_delta(after_flat, before_flat, "reasoning_tokens"),
    )
    if not thinking_tokens:
        thinking_tokens = max(
            extract_thinking_tokens(after_flat) - extract_thinking_tokens(before_flat),
            0,
        )
    cost = _positive_delta(after_flat, before_flat, "estimated_cost_usd")
    if not cost:
        cost = _positive_delta(after_flat, before_flat, "cost")

    if not any((prompt_tokens, completion_tokens, total_tokens, thinking_tokens, cost)):
        return None

    payload: dict[str, Any] = {
        "provider": provider,
        "model": str(model or after_flat.get("model", "")).strip(),
        "llm_calls": max(_call_delta(after_flat, before_flat), 1),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }
    if thinking_tokens:
        payload["thinking_tokens"] = thinking_tokens
    if cost:
        payload["estimated_cost_usd"] = cost
    return {key: value for key, value in payload.items() if value not in {"", None}}


def _select_usage(usage: dict[str, Any], *, preferred_model: str = "") -> dict[str, Any]:
    candidates = _usage_candidates(usage)
    if not candidates:
        return {}
    preferred = preferred_model.strip()
    if preferred:
        for candidate in candidates:
            model_name = str(candidate.get("model", ""))
            if model_name == preferred or model_name.startswith(preferred) or preferred.startswith(model_name):
                return candidate
    return max(candidates, key=lambda item: int(item.get("total_tokens", 0) or 0))


def _usage_candidates(usage: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if any(key in usage for key in _TOKEN_KEYS):
        candidates.append(_normalize_usage_entry(usage, model=str(usage.get("model", ""))))
    top_level_cost = _float_value(usage.get("total_cost"))
    for key, value in usage.items():
        if not isinstance(value, dict):
            continue
        if not any(token_key in value for token_key in _TOKEN_KEYS):
            continue
        candidate = _normalize_usage_entry(value, model=str(value.get("model") or key))
        if top_level_cost and not candidate.get("estimated_cost_usd"):
            candidate["estimated_cost_usd"] = top_level_cost
        candidates.append(candidate)
    return candidates


def _normalize_usage_entry(entry: dict[str, Any], *, model: str) -> dict[str, Any]:
    payload = dict(entry)
    payload["model"] = model
    payload["prompt_tokens"] = _int_value(entry.get("prompt_tokens"))
    payload["completion_tokens"] = _int_value(entry.get("completion_tokens"))
    payload["total_tokens"] = _int_value(entry.get("total_tokens"))
    thinking_tokens = max(
        _int_value(entry.get("thinking_tokens")),
        _int_value(entry.get("reasoning_tokens")),
        extract_thinking_tokens(entry),
    )
    if thinking_tokens:
        payload["thinking_tokens"] = thinking_tokens
    cost = _float_value(entry.get("estimated_cost_usd"))
    if not cost:
        cost = _float_value(entry.get("cost"))
    if cost:
        payload["estimated_cost_usd"] = cost
    return payload


def _positive_delta(after: dict[str, Any], before: dict[str, Any], key: str) -> int | float:
    after_value = after.get(key, 0)
    before_value = before.get(key, 0)
    if isinstance(after_value, float) or isinstance(before_value, float):
        return max(_float_value(after_value) - _float_value(before_value), 0.0)
    return max(_int_value(after_value) - _int_value(before_value), 0)


def _call_delta(after: dict[str, Any], before: dict[str, Any]) -> int:
    for key in _CALL_KEYS:
        delta = _int_value(after.get(key)) - _int_value(before.get(key))
        if delta > 0:
            return delta
    return 0


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_value(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
