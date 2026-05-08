"""OpenAI token pricing helpers for runtime cost estimation."""
from __future__ import annotations

import os
from typing import Any

MODEL_PRICING_PER_1M: dict[str, dict[str, float]] = {
    "gpt-5": {"input": 1.25, "output": 10.00},
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
    "gpt-5-nano": {"input": 0.05, "output": 0.40},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
}


def _pricing_env_fragment(model_name: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in model_name).upper()


def get_model_pricing(model_name: str) -> dict[str, float] | None:
    """Resolve pricing for a model name with exact, prefix, and env overrides."""
    normalized = (model_name or "").strip()
    if not normalized:
        return None

    env_fragment = _pricing_env_fragment(normalized)
    env_input = os.getenv(f"OPENAI_PRICE_INPUT_PER_1M_{env_fragment}", "").strip()
    env_output = os.getenv(f"OPENAI_PRICE_OUTPUT_PER_1M_{env_fragment}", "").strip()
    if env_input and env_output:
        return {"input": float(env_input), "output": float(env_output)}

    if normalized in MODEL_PRICING_PER_1M:
        return MODEL_PRICING_PER_1M[normalized]

    for known_model, pricing in MODEL_PRICING_PER_1M.items():
        if normalized.startswith(f"{known_model}-") or normalized == known_model:
            return pricing
    return None


def estimate_cost_usd(*, model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost from prompt and completion tokens."""
    pricing = get_model_pricing(model_name)
    if pricing is None:
        return 0.0
    prompt_cost = (max(prompt_tokens, 0) / 1_000_000) * pricing["input"]
    completion_cost = (max(completion_tokens, 0) / 1_000_000) * pricing["output"]
    return round(prompt_cost + completion_cost, 10)


def _is_reasoning_model(model_name: str) -> bool:
    normalized = (model_name or "").strip().lower()
    return normalized.startswith("gpt-5") or normalized.startswith("o")


def estimate_web_search_preview_call_cost_usd(*, search_calls: int, model_name: str) -> float:
    """Estimate fixed web_search_preview call fees.

    Pricing defaults follow OpenAI API pricing:
    - reasoning models: $10 / 1K calls
    - non-reasoning models: $25 / 1K calls
    Values can be overridden via env vars:
    - OPENAI_PRICE_WEB_SEARCH_PREVIEW_REASONING_PER_1K_CALLS
    - OPENAI_PRICE_WEB_SEARCH_PREVIEW_NON_REASONING_PER_1K_CALLS
    """
    calls = int(search_calls or 0)
    if calls <= 0:
        return 0.0

    if _is_reasoning_model(model_name):
        per_1k = float(os.getenv("OPENAI_PRICE_WEB_SEARCH_PREVIEW_REASONING_PER_1K_CALLS", "10.0"))
    else:
        per_1k = float(os.getenv("OPENAI_PRICE_WEB_SEARCH_PREVIEW_NON_REASONING_PER_1K_CALLS", "25.0"))
    return round((calls / 1000.0) * per_1k, 10)


def summarize_worker_report_costs(worker_reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate token usage and estimated cost by model and worker."""
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    total_cost = 0.0
    models: dict[str, dict[str, float | int]] = {}
    agents: dict[str, Any] = {}

    for report in worker_reports:
        usage = report.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        combined_tokens = int(usage.get("total_tokens", 0) or 0)
        if prompt_tokens == 0 and completion_tokens == 0 and combined_tokens == 0:
            continue
        model_name = str(report.get("model_name", "unknown")).strip() or "unknown"
        worker_name = str(report.get("worker", "worker")).strip() or "worker"
        cost = estimate_cost_usd(
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        total_prompt_tokens += prompt_tokens
        total_completion_tokens += completion_tokens
        total_tokens += combined_tokens or (prompt_tokens + completion_tokens)
        total_cost += cost

        model_bucket = models.setdefault(
            model_name,
            {"cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )
        model_bucket["cost"] = round(float(model_bucket["cost"]) + cost, 10)
        model_bucket["prompt_tokens"] = int(model_bucket["prompt_tokens"]) + prompt_tokens
        model_bucket["completion_tokens"] = int(model_bucket["completion_tokens"]) + completion_tokens
        model_bucket["total_tokens"] = int(model_bucket["total_tokens"]) + (combined_tokens or (prompt_tokens + completion_tokens))

        agent_bucket = agents.setdefault(worker_name.lower(), {"actual": {"total_cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "models": {}}})
        agent_actual = agent_bucket["actual"]
        agent_actual["total_cost"] = round(float(agent_actual["total_cost"]) + cost, 10)
        agent_actual["prompt_tokens"] = int(agent_actual["prompt_tokens"]) + prompt_tokens
        agent_actual["completion_tokens"] = int(agent_actual["completion_tokens"]) + completion_tokens
        agent_actual["total_tokens"] = int(agent_actual["total_tokens"]) + (combined_tokens or (prompt_tokens + completion_tokens))
        agent_model_bucket = agent_actual["models"].setdefault(
            model_name,
            {"cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )
        agent_model_bucket["cost"] = round(float(agent_model_bucket["cost"]) + cost, 10)
        agent_model_bucket["prompt_tokens"] = int(agent_model_bucket["prompt_tokens"]) + prompt_tokens
        agent_model_bucket["completion_tokens"] = int(agent_model_bucket["completion_tokens"]) + completion_tokens
        agent_model_bucket["total_tokens"] = int(agent_model_bucket["total_tokens"]) + (combined_tokens or (prompt_tokens + completion_tokens))

    for agent_bucket in agents.values():
        agent_bucket["total"] = dict(agent_bucket["actual"])

    total = {
        "total_cost": round(total_cost, 10),
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "total_tokens": total_tokens,
        "models": models,
    }
    return {"total": total, "actual": dict(total), "agents": agents}
