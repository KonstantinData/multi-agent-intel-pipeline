"""Architecture tests for PostgreSQL-only auth storage."""
from __future__ import annotations

import pytest

from ui.auth import db as auth_db


def test_auth_dsn_prefers_dedicated_auth_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config.settings._keyring_lookup", lambda service, account: "")
    monkeypatch.setenv("LIQUISTO_AUTH_POSTGRES_DSN", "postgresql://auth-db")
    monkeypatch.setenv("LIQUISTO_POSTGRES_DSN", "postgresql://runtime-db")
    monkeypatch.setenv("DATABASE_URL", "postgresql://fallback-db")
    assert auth_db._postgres_dsn() == "postgresql://auth-db"


def test_auth_dsn_falls_back_to_runtime_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config.settings._keyring_lookup", lambda service, account: "")
    monkeypatch.delenv("LIQUISTO_AUTH_POSTGRES_DSN", raising=False)
    monkeypatch.setenv("LIQUISTO_POSTGRES_DSN", "postgresql://runtime-db")
    monkeypatch.setenv("DATABASE_URL", "postgresql://fallback-db")
    assert auth_db._postgres_dsn() == "postgresql://runtime-db"


def test_auth_dsn_uses_database_url_last(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config.settings._keyring_lookup", lambda service, account: "")
    monkeypatch.delenv("LIQUISTO_AUTH_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("LIQUISTO_POSTGRES_DSN", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fallback-db")
    assert auth_db._postgres_dsn() == "postgresql://fallback-db"


def test_auth_dsn_required_fails_without_any_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config.settings._keyring_lookup", lambda service, account: "")
    monkeypatch.delenv("LIQUISTO_AUTH_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("LIQUISTO_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        auth_db._require_postgres_dsn()
    assert "LIQUISTO_AUTH_POSTGRES_DSN" in str(exc_info.value)


def test_auth_dsn_reads_keyring_when_environment_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIQUISTO_AUTH_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("LIQUISTO_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        "src.config.settings._keyring_lookup",
        lambda service, account: "postgresql://auth-keyring-db" if account == "LIQUISTO_AUTH_POSTGRES_DSN" else "",
    )
    assert auth_db._postgres_dsn() == "postgresql://auth-keyring-db"
