"""Runtime store factory for local MVP and Phase-2 production profiles."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.memory.long_term_store import FileLongTermMemoryStore
from src.storage.contracts import RuntimeStorageConfig, RuntimeStores, StorageHealth


@dataclass(slots=True)
class LocalRunStateStore:
    """Development run-state store.

    Local JSON export remains handled by `export_run()` and `_write_checkpoint()`;
    this contract object makes the storage boundary explicit without changing
    the MVP persistence path.
    """

    runs_root: Path

    def healthcheck(self) -> StorageHealth:
        return StorageHealth(
            status="ok",
            component="run_state",
            details={"backend": "local_file_export", "runs_root": str(self.runs_root)},
        )

    def create_run(self, *, run_id: str, intake: dict[str, Any], phase: str) -> None:
        return None

    def write_checkpoint(
        self,
        *,
        run_id: str,
        phase: str,
        sequence: int,
        run_context_snapshot: dict[str, Any],
    ) -> None:
        return None


@dataclass(slots=True)
class UnconfiguredPostgresRunStateStore:
    """Fail-fast production placeholder until a DSN-backed store is wired."""

    reason: str
    error_code: str = "postgres_dsn_missing"

    def healthcheck(self) -> StorageHealth:
        return StorageHealth(
            status="failed",
            component="run_state",
            error_code=self.error_code,
            message=self.reason,
            details={"backend": "postgres"},
        )

    def create_run(self, *, run_id: str, intake: dict[str, Any], phase: str) -> None:
        raise RuntimeError(self.reason)

    def write_checkpoint(
        self,
        *,
        run_id: str,
        phase: str,
        sequence: int,
        run_context_snapshot: dict[str, Any],
    ) -> None:
        raise RuntimeError(self.reason)


@dataclass(slots=True)
class UnconfiguredPostgresLongTermMemoryStore:
    reason: str
    error_code: str = "postgres_dsn_missing"

    def healthcheck(self) -> StorageHealth:
        return StorageHealth(
            status="failed",
            component="long_term_memory",
            error_code=self.error_code,
            message=self.reason,
            details={"backend": "postgres_pgvector"},
        )

    def retrieve(
        self,
        *,
        domain: str,
        industry_hint: str = "",
        role: str = "",
        pattern_scope: str = "",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        raise RuntimeError(self.reason)

    def upsert_strategy(self, pattern: dict[str, Any]) -> None:
        raise RuntimeError(self.reason)


def create_runtime_stores(
    *,
    config: RuntimeStorageConfig | None = None,
    runs_root: Path,
    long_term_memory_path: Path,
) -> RuntimeStores:
    cfg = config or RuntimeStorageConfig.from_env()
    if cfg.profile == "production":
        if not cfg.postgres_dsn_present:
            reason = (
                "Production storage profile requires LIQUISTO_POSTGRES_DSN "
                "or DATABASE_URL with migrated pgvector schema."
            )
            return RuntimeStores(
                config=cfg,
                long_term_memory=UnconfiguredPostgresLongTermMemoryStore(reason),
                run_state=UnconfiguredPostgresRunStateStore(reason),
            )
        # Full DSN-backed Postgres implementation is intentionally kept behind
        # the schema freeze and deployment work in Point 3.15.
        reason = "Postgres runtime store is not enabled until schema migration is applied."
        return RuntimeStores(
            config=cfg,
            long_term_memory=UnconfiguredPostgresLongTermMemoryStore(
                reason,
                error_code="postgres_pgvector_store_disabled",
            ),
            run_state=UnconfiguredPostgresRunStateStore(
                reason,
                error_code="postgres_run_state_store_disabled",
            ),
        )

    return RuntimeStores(
        config=cfg,
        long_term_memory=FileLongTermMemoryStore(long_term_memory_path),
        run_state=LocalRunStateStore(runs_root),
    )


__all__ = [
    "LocalRunStateStore",
    "UnconfiguredPostgresLongTermMemoryStore",
    "UnconfiguredPostgresRunStateStore",
    "create_runtime_stores",
]
