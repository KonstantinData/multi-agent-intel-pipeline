from __future__ import annotations

from src.config.settings import (
    DEFAULT_EXTRACTION_MODEL,
    DEFAULT_SEARCH_MODEL,
    DEFAULT_TRANSLATION_MODEL,
    get_extraction_model,
    get_role_model_selection,
    get_search_model,
    get_translation_model,
    resolve_model_temperature,
    temperature_param,
)


def _disable_dotenv_lookup(monkeypatch):
    monkeypatch.setattr("src.config.settings._dotenv_lookup", lambda: {})


def test_role_model_env_override_prefers_snake_case(monkeypatch):
    _disable_dotenv_lookup(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL_COMPANY_RESEARCHER", "model-snake")
    monkeypatch.setenv("OPENAI_MODEL_COMPANYRESEARCHER", "model-legacy")
    chat_model, _ = get_role_model_selection("CompanyResearcher")
    assert chat_model == "model-snake"


def test_role_model_env_override_supports_legacy_compact_key(monkeypatch):
    _disable_dotenv_lookup(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL_COMPANYRESEARCHER", "model-legacy")
    monkeypatch.delenv("OPENAI_MODEL_COMPANY_RESEARCHER", raising=False)
    chat_model, _ = get_role_model_selection("CompanyResearcher")
    assert chat_model == "model-legacy"


def test_role_structured_model_env_override_prefers_snake_case(monkeypatch):
    _disable_dotenv_lookup(monkeypatch)
    monkeypatch.setenv("OPENAI_STRUCTURED_MODEL_COMPANY_RESEARCHER", "structured-snake")
    monkeypatch.setenv("OPENAI_STRUCTURED_MODEL_COMPANYRESEARCHER", "structured-legacy")
    _, structured_model = get_role_model_selection("CompanyResearcher")
    assert structured_model == "structured-snake"


def test_search_translation_extraction_models_have_separate_overrides(monkeypatch):
    _disable_dotenv_lookup(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL_SEARCH", "search-model")
    monkeypatch.setenv("OPENAI_MODEL_TRANSLATION", "translation-model")
    monkeypatch.setenv("OPENAI_MODEL_EXTRACTION", "extraction-model")
    assert get_search_model() == "search-model"
    assert get_translation_model() == "translation-model"
    assert get_extraction_model() == "extraction-model"


def test_search_translation_extraction_models_have_stable_defaults(monkeypatch):
    _disable_dotenv_lookup(monkeypatch)
    monkeypatch.delenv("OPENAI_MODEL_SEARCH", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_TRANSLATION", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_EXTRACTION", raising=False)
    assert get_search_model() == DEFAULT_SEARCH_MODEL
    assert get_translation_model() == DEFAULT_TRANSLATION_MODEL
    assert get_extraction_model() == DEFAULT_EXTRACTION_MODEL


def test_gpt5_temperature_is_omitted_for_non_default_values():
    assert resolve_model_temperature("gpt-5", 0.1) is None
    assert temperature_param("gpt-5-mini", 0.0) == {}


def test_non_gpt5_temperature_is_kept():
    assert resolve_model_temperature("gpt-4.1", 0.1) == 0.1
    assert temperature_param("gpt-4.1-mini", 0.2) == {"temperature": 0.2}
