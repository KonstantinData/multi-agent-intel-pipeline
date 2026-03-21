"""Runtime configuration."""
from __future__ import annotations

import os
import re
from typing import Any

from autogen import LLMConfig
from dotenv import load_dotenv

load_dotenv()

DEFAULT_LLM_MODEL = "gpt-4.1-mini"
DEFAULT_STRUCTURED_LLM_MODEL = "gpt-4.1-mini"
DEFAULT_AGENT_MODELS = {
    "concierge": "gpt-4.1-mini",
    "company_intelligence": "gpt-4.1",
    "strategic_signals": "gpt-5-mini",
    "market_network": "gpt-4.1",
    "evidence_qa": "gpt-4.1-mini",
    "synthesis": "gpt-4.1",
    "repair_planner": "gpt-4.1-mini",
    "concierge_critic": "gpt-4.1-mini",
    "company_intelligence_critic": "gpt-4.1-mini",
    "strategic_signals_critic": "gpt-4.1-mini",
    "market_network_critic": "gpt-4.1-mini",
    "evidence_qa_critic": "gpt-4.1-mini",
    "synthesis_critic": "gpt-4.1-mini",
}
SUPPORTED_AG2_SERIES = "0.11.x"
SUPPORTED_PYTHON_RANGE = ">=3.10,<3.14"

STRUCTURED_OUTPUT_MODELS = (
    "gpt-5.4",
    "gpt-5-mini",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
)


def _supports_structured_outputs(model: str) -> bool:
    return any(model == prefix or model.startswith(f"{prefix}-") for prefix in STRUCTURED_OUTPUT_MODELS)


def _uses_max_completion_tokens(model: str) -> bool:
    normalized = str(model or "").strip().lower()
    return normalized == "gpt-5" or normalized.startswith("gpt-5-")


def _agent_env_key(agent_name: str) -> str:
    normalized = str(agent_name or "").strip().lower()
    normalized = normalized.replace(" ", "_")
    return re.sub(r"[^a-z0-9_]", "_", normalized).upper()


def get_model_selection(agent_name: str | None = None) -> tuple[str, str]:
    preferred_model = os.environ.get("LLM_MODEL", DEFAULT_LLM_MODEL)
    structured_model = os.environ.get("STRUCTURED_LLM_MODEL", DEFAULT_STRUCTURED_LLM_MODEL)
    if agent_name:
        env_key = _agent_env_key(agent_name)
        preferred_model = os.environ.get(
            f"LLM_MODEL_{env_key}",
            DEFAULT_AGENT_MODELS.get(agent_name, preferred_model),
        )
        structured_model = os.environ.get(
            f"STRUCTURED_LLM_MODEL_{env_key}",
            preferred_model if _supports_structured_outputs(preferred_model) else structured_model,
        )
    return preferred_model, structured_model


def get_llm_config(response_format: Any | None = None, agent_name: str | None = None) -> LLMConfig:
    preferred_model, structured_model = get_model_selection(agent_name=agent_name)
    max_tokens = os.environ.get("LLM_MAX_TOKENS", "1400")

    model = preferred_model
    if response_format is not None and not _supports_structured_outputs(preferred_model):
        model = structured_model

    llm_kwargs: dict[str, Any] = {
        "model": model,
        "api_key": os.environ["OPENAI_API_KEY"],
    }
    if max_tokens:
        token_key = "max_completion_tokens" if _uses_max_completion_tokens(model) else "max_tokens"
        llm_kwargs[token_key] = int(max_tokens)

    return LLMConfig(llm_kwargs, response_format=response_format)
