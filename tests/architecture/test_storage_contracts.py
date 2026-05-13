from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest

from src.memory.retrieval import retrieve_strategies
from src.storage.contracts import (
    RuntimeStorageConfig,
    StorageHealth,
    StorageHealthcheckError,
)
from src.storage.runtime_stores import create_runtime_stores


def test_local_storage_profile_uses_file_memory_and_redacted_snapshot(tmp_path: Path) -> None:
    memory_path = tmp_path / "long_term_memory.json"

    stores = create_runtime_stores(
        config=RuntimeStorageConfig(profile="local_dev"),
        runs_root=tmp_path / "runs",
        long_term_memory_path=memory_path,
    )

    stores.healthcheck_required()
    snapshot = stores.snapshot()
    assert snapshot["profile"] == "local_dev"
    assert snapshot["memory_backend"] == "file"
    assert snapshot["run_state_backend"] == "local_file_export"
    assert snapshot["postgres_dsn_present"] is False
    assert "postgres://" not in repr(snapshot)
    assert snapshot["long_term_memory_health"]["status"] == "ok"
    assert snapshot["run_state_health"]["status"] == "ok"


def test_production_storage_without_dsn_fails_fast(tmp_path: Path) -> None:
    cfg = RuntimeStorageConfig(
        profile="production",
        run_state_backend="postgres",
        memory_backend="postgres_pgvector",
        object_storage_backend="cloudflare_r2",
        postgres_dsn_present=False,
        cloudflare_tunnel_required=True,
    )
    stores = create_runtime_stores(
        config=cfg,
        runs_root=tmp_path / "runs",
        long_term_memory_path=tmp_path / "memory.json",
    )

    with pytest.raises(StorageHealthcheckError) as exc_info:
        stores.healthcheck_required()

    assert exc_info.value.component == "long_term_memory"
    assert exc_info.value.error_code == "postgres_dsn_missing"
    assert stores.snapshot()["cloudflare_tunnel_required"] is True


def test_production_env_config_redacts_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIQUISTO_STORAGE_PROFILE", "production")
    raw_database_url = "postgresql://example.internal/db"
    monkeypatch.setenv("DATABASE_URL", raw_database_url)

    cfg = RuntimeStorageConfig.from_env()

    assert cfg.postgres_dsn_present is True
    assert cfg.memory_backend == "postgres_pgvector"
    assert cfg.run_state_backend == "postgres"
    assert raw_database_url not in repr(cfg.snapshot())


def test_production_storage_with_dsn_still_requires_enabled_migrated_store(tmp_path: Path) -> None:
    cfg = RuntimeStorageConfig(
        profile="production",
        run_state_backend="postgres",
        memory_backend="postgres_pgvector",
        object_storage_backend="cloudflare_r2",
        postgres_dsn_present=True,
        cloudflare_tunnel_required=True,
    )
    stores = create_runtime_stores(
        config=cfg,
        runs_root=tmp_path / "runs",
        long_term_memory_path=tmp_path / "memory.json",
    )

    with pytest.raises(StorageHealthcheckError) as exc_info:
        stores.healthcheck_required()

    assert exc_info.value.error_code == "postgres_pgvector_store_disabled"
    assert "schema migration" in str(exc_info.value)


def test_retrieve_strategies_accepts_long_term_memory_protocol() -> None:
    class FakeMemoryStore:
        def retrieve(
            self,
            *,
            domain: str,
            industry_hint: str = "",
            role: str = "",
            pattern_scope: str = "",
            limit: int = 5,
        ):
            return [{"name": "query-pattern", "role": role, "score": 1.0}]

        def upsert_strategy(self, pattern):
            return None

        def healthcheck(self):
            return StorageHealth(status="ok", component="long_term_memory")

    results = retrieve_strategies(FakeMemoryStore(), domain="example.com", role="researcher", limit=1)

    assert len(results) == 1
    assert results[0]["name"] == "query-pattern"
    assert results[0]["role"] == "researcher"
    assert results[0]["rank"] == 1


def test_storage_health_is_dataclass_serializable() -> None:
    health = StorageHealth(status="ok", component="run_state", details={"backend": "postgres"})

    assert asdict(health) == {
        "status": "ok",
        "component": "run_state",
        "error_code": "",
        "message": "",
        "details": {"backend": "postgres"},
    }


def test_phase2_sql_declares_postgres_pgvector_runtime_schema() -> None:
    sql = Path("sql/20260512_phase2_storage.sql").read_text(encoding="utf-8").lower()

    for required in (
        "create extension if not exists vector",
        "create table if not exists runs",
        "create table if not exists run_checkpoints",
        "create table if not exists run_events",
        "create table if not exists run_artifacts",
        "create table if not exists run_locks",
        "create table if not exists memory_patterns",
        "embedding vector(1536)",
        "using hnsw",
        "create table if not exists memory_retrieval_events",
        "create table if not exists memory_backfill_jobs",
    ):
        assert required in sql
