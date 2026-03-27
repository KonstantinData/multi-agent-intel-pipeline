"""Runtime configuration helpers."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values


DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_STRUCTURED_MODEL = "gpt-4.1-mini"
MAX_TASK_RETRIES = int(os.getenv("LIQUISTO_MAX_TASK_RETRIES", "3"))
SOFT_TOKEN_BUDGET = int(os.getenv("LIQUISTO_SOFT_TOKEN_BUDGET", "200000"))
HARD_TOKEN_CAP = int(os.getenv("LIQUISTO_HARD_TOKEN_CAP", "500000"))
ROOT = Path(__file__).resolve().parents[2]
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
    "CrossDomainStrategicAnalyst": "gpt-4.1",
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
    "CrossDomainStrategicAnalyst": "gpt-4.1-mini",
}


def get_openai_api_key() -> str:
    """Resolve the OpenAI API key from environment or local .env."""
    process_key = os.getenv("OPENAI_API_KEY", "").strip()
    if process_key:
        return process_key
    env_path = ROOT / ".env"
    if env_path.exists():
        return str(dotenv_values(env_path).get("OPENAI_API_KEY", "") or "").strip()
    return ""


def get_model_selection() -> tuple[str, str]:
    """Return the chat and structured-output models for UI display."""
    preferred_model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    structured_model = os.getenv("OPENAI_STRUCTURED_MODEL", DEFAULT_STRUCTURED_MODEL).strip() or preferred_model
    return preferred_model, structured_model


def _role_env_fragment(role: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in role).upper()


def get_role_model_selection(role: str) -> tuple[str, str]:
    """Resolve role-specific chat and structured models with env overrides."""
    preferred_model, structured_fallback = get_model_selection()
    env_fragment = _role_env_fragment(role)
    role_model = (
        os.getenv(f"OPENAI_MODEL_{env_fragment}", "").strip()
        or ROLE_MODEL_DEFAULTS.get(role, preferred_model)
        or preferred_model
    )
    role_structured = (
        os.getenv(f"OPENAI_STRUCTURED_MODEL_{env_fragment}", "").strip()
        or ROLE_STRUCTURED_MODEL_DEFAULTS.get(role, structured_fallback)
        or role_model
    )
    return role_model, role_structured


def summarize_runtime_models() -> str:
    """Return a compact UI summary of role-to-model assignments."""
    parts = [
        f"Supervisor {get_role_model_selection('Supervisor')[0]}",
        f"Departments {get_role_model_selection('CompanyResearcher')[1]}",
        f"Cross-domain {get_role_model_selection('CrossDomainStrategicAnalyst')[0]}",
    ]
    return " · ".join(parts)


def get_llm_config(*, role: str | None = None, model: str | None = None, temperature: float = 0.1) -> dict[str, Any]:
    """Return a minimal OpenAI-compatible config payload."""
    if role:
        selected_model, structured_model = get_role_model_selection(role)
    else:
        selected_model, structured_model = get_model_selection()
    chosen_model = model or selected_model
    api_key = get_openai_api_key()
    return {
        "provider": "openai",
        "model": chosen_model,
        "structured_model": structured_model,
        "temperature": temperature,
        "api_key_present": bool(api_key),
    }
