"""Runtime configuration helpers."""
from __future__ import annotations

import os
import re
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import dotenv_values


DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_STRUCTURED_MODEL = "gpt-4.1-mini"
DEFAULT_SEARCH_MODEL = "gpt-4.1-mini"
DEFAULT_TRANSLATION_MODEL = "gpt-4.1-mini"
DEFAULT_EXTRACTION_MODEL = "gpt-4.1-nano"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 90.0
DEFAULT_OPENAI_MAX_RETRIES = 1
MAX_TASK_RETRIES = int(os.getenv("LIQUISTO_MAX_TASK_RETRIES", "3"))
SOFT_TOKEN_BUDGET = int(os.getenv("LIQUISTO_SOFT_TOKEN_BUDGET", "200000"))
HARD_TOKEN_CAP = int(os.getenv("LIQUISTO_HARD_TOKEN_CAP", "500000"))
ROOT = Path(__file__).resolve().parents[2]
TEMPERATURE_LOCKED_MODEL_PREFIXES = ("gpt-5",)
ROLE_MODEL_DEFAULTS = {
    "Supervisor": "gpt-4.1",
    "CompanyDepartment": "gpt-4.1",
    "MarketDepartment": "gpt-4.1",
    "BuyerDepartment": "gpt-4.1",
    "CompanyLead": "gpt-4.1",
    "MarketLead": "gpt-4.1",
    "BuyerLead": "gpt-4.1",
    "CompanyResearcher": "gpt-4.1-mini",
    "MarketResearcher": "gpt-4.1-mini",
    "BuyerResearcher": "gpt-4.1-mini",
    "CompanyCritic": "gpt-4.1",
    "MarketCritic": "gpt-4.1",
    "BuyerCritic": "gpt-4.1",
    "CompanyJudge": "gpt-4.1",
    "MarketJudge": "gpt-4.1",
    "BuyerJudge": "gpt-4.1",
    "CompanyCodingSpecialist": "gpt-4.1-mini",
    "MarketCodingSpecialist": "gpt-4.1-mini",
    "BuyerCodingSpecialist": "gpt-4.1-mini",
    "ContactDepartment": "gpt-4.1",
    "ContactLead": "gpt-4.1",
    "ContactResearcher": "gpt-4.1-mini",
    "ContactCritic": "gpt-4.1",
    "ContactJudge": "gpt-4.1",
    "ContactCodingSpecialist": "gpt-4.1-mini",
    "SynthesisLead": "gpt-4.1",
    "SynthesisAnalyst": "gpt-4.1",
    "SynthesisCritic": "gpt-4.1",
    "SynthesisJudge": "gpt-4.1",
    "ReportWriter": "gpt-4.1",
}
ROLE_STRUCTURED_MODEL_DEFAULTS = {
    "Supervisor": "gpt-4.1",
    "CompanyDepartment": "gpt-4.1-mini",
    "MarketDepartment": "gpt-4.1-mini",
    "BuyerDepartment": "gpt-4.1-mini",
    "CompanyLead": "gpt-4.1-mini",
    "MarketLead": "gpt-4.1-mini",
    "BuyerLead": "gpt-4.1-mini",
    "CompanyResearcher": "gpt-4.1-mini",
    "MarketResearcher": "gpt-4.1-mini",
    "BuyerResearcher": "gpt-4.1-mini",
    "CompanyCritic": "gpt-4.1-mini",
    "MarketCritic": "gpt-4.1-mini",
    "BuyerCritic": "gpt-4.1-mini",
    "CompanyJudge": "gpt-4.1-mini",
    "MarketJudge": "gpt-4.1-mini",
    "BuyerJudge": "gpt-4.1-mini",
    "CompanyCodingSpecialist": "gpt-4.1-mini",
    "MarketCodingSpecialist": "gpt-4.1-mini",
    "BuyerCodingSpecialist": "gpt-4.1-mini",
    "ContactDepartment": "gpt-4.1-mini",
    "ContactLead": "gpt-4.1-mini",
    "ContactResearcher": "gpt-4.1-mini",
    "ContactCritic": "gpt-4.1-mini",
    "ContactJudge": "gpt-4.1-mini",
    "ContactCodingSpecialist": "gpt-4.1-mini",
    "SynthesisLead": "gpt-4.1-mini",
    "SynthesisAnalyst": "gpt-4.1-mini",
    "SynthesisCritic": "gpt-4.1-mini",
    "SynthesisJudge": "gpt-4.1-mini",
    "ReportWriter": "gpt-4.1-mini",
}


@lru_cache(maxsize=1)
def _dotenv_lookup() -> dict[str, str]:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return {}
    return {
        str(key): str(value or "").strip()
        for key, value in dotenv_values(env_path).items()
        if isinstance(key, str)
    }


def _get_env_value(key: str) -> str:
    process_value = os.getenv(key, "").strip()
    if process_value:
        return process_value
    return _dotenv_lookup().get(key, "").strip()


def get_openai_api_key() -> str:
    """Resolve the OpenAI API key from environment or local .env."""
    return _get_env_value("OPENAI_API_KEY")


def get_model_selection() -> tuple[str, str]:
    """Return the chat and structured-output models for UI display."""
    preferred_model = _get_env_value("OPENAI_MODEL") or DEFAULT_MODEL
    structured_model = _get_env_value("OPENAI_STRUCTURED_MODEL") or DEFAULT_STRUCTURED_MODEL or preferred_model
    return preferred_model, structured_model


def _role_env_fragments(role: str) -> tuple[str, str]:
    """Return (preferred, legacy) env fragments for role model overrides.

    Preferred format is snake-case with separators, e.g. `CompanyResearcher`
    -> `COMPANY_RESEARCHER`.
    Legacy compact format remains supported for backwards compatibility:
    `COMPANYRESEARCHER`.
    """
    separated = re.sub(r"(?<!^)(?=[A-Z])", "_", role)
    preferred = "".join(character if character.isalnum() else "_" for character in separated).upper()
    legacy = "".join(character if character.isalnum() else "_" for character in role).upper()
    return preferred, legacy


def _first_env(*keys: str) -> str:
    for key in keys:
        value = _get_env_value(key)
        if value:
            return value
    return ""


def get_search_model() -> str:
    """Resolve the model used for web search synthesis."""
    return _first_env("OPENAI_MODEL_SEARCH", "OPENAI_MODEL_WEB_SEARCH") or DEFAULT_SEARCH_MODEL


def get_translation_model() -> str:
    """Resolve the model used for translation tasks in exporters."""
    return _first_env("OPENAI_MODEL_TRANSLATION") or DEFAULT_TRANSLATION_MODEL


def get_extraction_model() -> str:
    """Resolve the model used for lightweight extraction helpers."""
    return _first_env("OPENAI_MODEL_EXTRACTION") or DEFAULT_EXTRACTION_MODEL


def get_openai_timeout_seconds() -> float:
    """Resolve OpenAI request timeout (seconds)."""
    raw = _first_env("LIQUISTO_OPENAI_TIMEOUT_SECONDS")
    if not raw:
        return DEFAULT_OPENAI_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_OPENAI_TIMEOUT_SECONDS
    if not math.isfinite(value) or value <= 0:
        return DEFAULT_OPENAI_TIMEOUT_SECONDS
    return value


def get_openai_max_retries() -> int:
    """Resolve OpenAI max retries for transient request failures."""
    raw = _first_env("LIQUISTO_OPENAI_MAX_RETRIES")
    if not raw:
        return DEFAULT_OPENAI_MAX_RETRIES
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_OPENAI_MAX_RETRIES
    return max(value, 0)


def supports_custom_temperature(model_name: str) -> bool:
    """Return False for models that currently only support default temperature."""
    normalized = (model_name or "").strip().lower()
    if not normalized:
        return True
    return not normalized.startswith(TEMPERATURE_LOCKED_MODEL_PREFIXES)


def resolve_model_temperature(model_name: str, temperature: float | None) -> float | None:
    """Normalize a requested temperature for a specific model.

    Returns None when the parameter should be omitted from the API call.
    """
    if temperature is None:
        return None
    try:
        value = float(temperature)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    if not supports_custom_temperature(model_name):
        # GPT-5 family currently supports only the default temperature value.
        if abs(value - 1.0) <= 1e-9:
            return 1.0
        return None
    return value


def temperature_param(model_name: str, temperature: float | None) -> dict[str, float]:
    """Return OpenAI chat parameter dict for temperature (or empty)."""
    value = resolve_model_temperature(model_name, temperature)
    if value is None:
        return {}
    return {"temperature": value}


def get_role_model_selection(role: str) -> tuple[str, str]:
    """Resolve role-specific chat and structured models with env overrides."""
    preferred_model, structured_fallback = get_model_selection()
    env_fragment, legacy_fragment = _role_env_fragments(role)
    role_model = (
        _first_env(
            f"OPENAI_MODEL_{env_fragment}",
            f"OPENAI_MODEL_{legacy_fragment}",
        )
        or ROLE_MODEL_DEFAULTS.get(role, preferred_model)
        or preferred_model
    )
    role_structured = (
        _first_env(
            f"OPENAI_STRUCTURED_MODEL_{env_fragment}",
            f"OPENAI_STRUCTURED_MODEL_{legacy_fragment}",
        )
        or ROLE_STRUCTURED_MODEL_DEFAULTS.get(role, structured_fallback)
        or role_model
    )
    return role_model, role_structured


def summarize_runtime_models() -> str:
    """Return a compact UI summary of role-to-model assignments."""
    parts = [
        f"Supervisor {get_role_model_selection('Supervisor')[0]}",
        f"Departments {get_role_model_selection('CompanyResearcher')[1]}",
        f"Synthesis {get_role_model_selection('SynthesisLead')[0]}",
        f"Search {get_search_model()}",
        f"Translation {get_translation_model()}",
    ]
    return " · ".join(parts)


def get_llm_config(*, role: str | None = None, model: str | None = None, temperature: float = 0.1) -> dict[str, Any]:
    """Return a minimal OpenAI-compatible config payload."""
    if role:
        selected_model, structured_model = get_role_model_selection(role)
    else:
        selected_model, structured_model = get_model_selection()
    chosen_model = model or selected_model
    normalized_temperature = resolve_model_temperature(chosen_model, temperature)
    api_key = get_openai_api_key()
    return {
        "provider": "openai",
        "model": chosen_model,
        "structured_model": structured_model,
        "temperature": normalized_temperature,
        "api_key_present": bool(api_key),
    }
