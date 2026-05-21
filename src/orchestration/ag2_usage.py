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
_AG2_REASONING_PATCH_ATTR = "_liquisto_reasoning_usage_patch"


def install_ag2_reasoning_usage_patch() -> bool:
    """Preserve provider reasoning-token fields in AG2 usage summaries.

    AG2 0.12.x records only the canonical token fields in
    ``OpenAIWrapper.actual_usage_summary``. OpenAI responses can include
    reasoning-token metadata, but AG2 drops it before our RuntimeStep extractor
    sees the summary. This patch is intentionally narrow and idempotent: it only
    enriches usage dictionaries, and it does not alter prompts, responses, or
    control flow.
    """

    try:
        from autogen.oai.client import OpenAIClient, OpenAIWrapper
    except Exception:
        return False

    if not getattr(OpenAIClient.get_usage, _AG2_REASONING_PATCH_ATTR, False):
        original_get_usage = OpenAIClient.get_usage

        def get_usage_with_reasoning(response: Any) -> dict[str, Any]:
            payload = original_get_usage(response)
            if not isinstance(payload, dict):
                return payload
            return _with_reasoning_token_fields(payload, getattr(response, "usage", None))

        setattr(get_usage_with_reasoning, _AG2_REASONING_PATCH_ATTR, True)
        OpenAIClient.get_usage = staticmethod(get_usage_with_reasoning)

    if not getattr(OpenAIWrapper._update_usage, _AG2_REASONING_PATCH_ATTR, False):
        original_update_usage = OpenAIWrapper._update_usage

        def update_usage_with_reasoning(
            self: Any,
            actual_usage: dict[str, Any] | None,
            total_usage: dict[str, Any] | None,
        ) -> None:
            before_actual_tokens = _summary_thinking_tokens(
                getattr(self, "actual_usage_summary", None),
                actual_usage,
            )
            before_total_tokens = _summary_thinking_tokens(
                getattr(self, "total_usage_summary", None),
                total_usage,
            )
            original_update_usage(self, actual_usage, total_usage)
            _merge_summary_reasoning_delta(
                getattr(self, "actual_usage_summary", None),
                actual_usage,
                before_tokens=before_actual_tokens,
            )
            _merge_summary_reasoning_delta(
                getattr(self, "total_usage_summary", None),
                total_usage,
                before_tokens=before_total_tokens,
            )

        setattr(update_usage_with_reasoning, _AG2_REASONING_PATCH_ATTR, True)
        OpenAIWrapper._update_usage = update_usage_with_reasoning

    return True


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


def _with_reasoning_token_fields(payload: dict[str, Any], provider_usage: Any) -> dict[str, Any]:
    enriched = dict(payload)
    thinking_tokens = extract_thinking_tokens(provider_usage)
    if thinking_tokens:
        enriched["thinking_tokens"] = max(_int_value(enriched.get("thinking_tokens")), thinking_tokens)
        enriched["reasoning_tokens"] = max(_int_value(enriched.get("reasoning_tokens")), thinking_tokens)
    return enriched


def _summary_thinking_tokens(
    usage_summary: dict[str, Any] | None,
    response_usage: dict[str, Any] | None,
) -> int:
    if not isinstance(usage_summary, dict) or not isinstance(response_usage, dict):
        return 0
    model = str(response_usage.get("model", "")).strip()
    entry = usage_summary.get(model)
    return extract_thinking_tokens(entry) if isinstance(entry, dict) else 0


def _merge_summary_reasoning_delta(
    usage_summary: dict[str, Any] | None,
    response_usage: dict[str, Any] | None,
    *,
    before_tokens: int,
) -> None:
    if not isinstance(usage_summary, dict) or not isinstance(response_usage, dict):
        return
    thinking_tokens = extract_thinking_tokens(response_usage)
    if not thinking_tokens:
        return
    model = str(response_usage.get("model", "")).strip()
    entry = usage_summary.get(model)
    if not isinstance(entry, dict):
        return

    already_recorded = max(extract_thinking_tokens(entry) - int(before_tokens or 0), 0)
    missing_tokens = max(thinking_tokens - already_recorded, 0)
    if not missing_tokens:
        return
    entry["thinking_tokens"] = _int_value(entry.get("thinking_tokens")) + missing_tokens
    entry["reasoning_tokens"] = _int_value(entry.get("reasoning_tokens")) + missing_tokens


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
