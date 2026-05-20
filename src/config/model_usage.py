"""Provider usage helpers for token and reasoning telemetry."""

from __future__ import annotations

from typing import Any


def _field(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _int_field(source: Any, name: str) -> int:
    try:
        return int(_field(source, name, 0) or 0)
    except (TypeError, ValueError):
        return 0


def extract_thinking_tokens(usage: Any) -> int:
    """Return provider-exposed reasoning/thinking tokens when available."""

    if usage is None:
        return 0
    direct = max(
        _int_field(usage, "thinking_tokens"),
        _int_field(usage, "reasoning_tokens"),
    )
    if direct:
        return direct

    for details_name in (
        "completion_tokens_details",
        "output_tokens_details",
        "input_tokens_details",
    ):
        details = _field(usage, details_name, None)
        tokens = max(
            _int_field(details, "reasoning_tokens"),
            _int_field(details, "thinking_tokens"),
        )
        if tokens:
            return tokens
    return 0


def build_usage_record(
    usage: Any,
    *,
    provider: str = "",
    model: str = "",
    llm_calls: int = 1,
) -> dict[str, Any]:
    """Build the canonical RuntimeStep usage payload from provider usage."""

    payload: dict[str, Any] = {
        "llm_calls": int(llm_calls),
        "prompt_tokens": _int_field(usage, "prompt_tokens"),
        "completion_tokens": _int_field(usage, "completion_tokens"),
        "total_tokens": _int_field(usage, "total_tokens"),
    }
    if provider:
        payload["provider"] = provider
    if model:
        payload["model"] = model
    thinking_tokens = extract_thinking_tokens(usage)
    if thinking_tokens:
        payload["thinking_tokens"] = thinking_tokens
    return payload


def build_reasoning_realized_record(
    usage: Any,
    *,
    planned_effort: str | None = None,
    reasoning_summary_available: bool = False,
) -> dict[str, Any] | None:
    """Build RuntimeStep.execution.reasoning_realized when provider data exists."""

    thinking_tokens = extract_thinking_tokens(usage)
    if not thinking_tokens:
        return None
    return {
        "effort_used": planned_effort or "unknown",
        "thinking_tokens": thinking_tokens,
        "reasoning_summary_available": bool(reasoning_summary_available),
    }
