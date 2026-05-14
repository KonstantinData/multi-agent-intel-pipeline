from __future__ import annotations

import pytest

from src.security.secret_guard import (
    PromptSecretLeakError,
    assert_no_secrets_in_payload,
    assert_no_secrets_in_text,
)


def test_secret_guard_accepts_safe_prompt_payload() -> None:
    payload = [
        {"role": "system", "content": "Summarize structured runtime context."},
        {"role": "user", "content": "{\"company_name\": \"Example GmbH\"}"},
    ]
    assert_no_secrets_in_payload(payload, context="unit_test_safe_payload")


def test_secret_guard_blocks_openai_key_and_redacts_error_content() -> None:
    leaked = "sk-1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ"  # pragma: allowlist secret
    payload = [{"role": "user", "content": f"api_key={leaked}"}]
    with pytest.raises(PromptSecretLeakError) as exc_info:
        assert_no_secrets_in_payload(payload, context="unit_test_leak_payload")
    message = str(exc_info.value)
    assert "unit_test_leak_payload" in message
    assert "openai_api_key" in message or "credential_assignment" in message
    assert leaked not in message


def test_secret_guard_blocks_private_key_block() -> None:
    with pytest.raises(PromptSecretLeakError):
        assert_no_secrets_in_text(
            "-----BEGIN PRIVATE KEY-----\nMIIB...\n-----END PRIVATE KEY-----",  # pragma: allowlist secret
            context="unit_test_private_key",
        )


def test_secret_guard_does_not_flag_normal_token_budget_text() -> None:
    assert_no_secrets_in_text(
        "token_budget=350000 and phase_budget=80000 are runtime limits.",
        context="unit_test_budget_text",
    )
