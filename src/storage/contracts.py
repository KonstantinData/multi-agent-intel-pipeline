"""Storage contracts for the Phase-2 Hetzner/Postgres runtime backbone."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

STORAGE_SCHEMA_VERSION = "2026-05-12.1"


@dataclass(frozen=True, slots=True)
class StorageHealth:
    status: str
    component: str
    error_code: str = ""
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class StorageHealthcheckError(RuntimeError):
    """Raised when a required runtime store is unavailable."""

    def __init__(self, health: StorageHealth):
        self.health = health
        self.component = health.component
        self.error_code = health.error_code or health.status
        self.message = health.message
        super().__init__(
            f"storage healthcheck failed: {health.component}: "
            f"{self.error_code}: {health.message}"
        )


@dataclass(frozen=True, slots=True)
class RuntimeStorageConfig:
    """Non-secret storage runtime config.

    `postgres_dsn_present` records only presence, never the DSN value.
    """

    profile: str = "local_dev"
    run_state_backend: str = "local_file_export"
    memory_backend: str = "file"
    object_storage_backend: str = "local_artifacts"
    postgres_dsn_present: bool = False
    cloudflare_tunnel_required: bool = False
    schema_version: str = STORAGE_SCHEMA_VERSION

    @classmethod
    def from_env(cls) -> RuntimeStorageConfig:
        profile = os.getenv("LIQUISTO_STORAGE_PROFILE", "local_dev").strip().lower() or "local_dev"
        postgres_dsn = (
            os.getenv("LIQUISTO_POSTGRES_DSN")
            or os.getenv("DATABASE_URL")
            or ""
        )
        if profile == "production":
            return cls(
                profile=profile,
                run_state_backend="postgres",
                memory_backend="postgres_pgvector",
                object_storage_backend=os.getenv("LIQUISTO_OBJECT_STORAGE_BACKEND", "cloudflare_r2"),
                postgres_dsn_present=bool(postgres_dsn),
                cloudflare_tunnel_required=True,
            )
        return cls(profile=profile)

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile,
            "run_state_backend": self.run_state_backend,
            "memory_backend": self.memory_backend,
            "object_storage_backend": self.object_storage_backend,
            "postgres_dsn_present": self.postgres_dsn_present,
            "cloudflare_tunnel_required": self.cloudflare_tunnel_required,
        }


class LongTermMemoryStore(Protocol):
    def retrieve(
        self,
        *,
        domain: str,
        industry_hint: str = "",
        role: str = "",
        pattern_scope: str = "",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        ...

    def upsert_strategy(self, pattern: dict[str, Any]) -> None:
        ...

    def healthcheck(self) -> StorageHealth:
        ...


class RunStateStore(Protocol):
    def healthcheck(self) -> StorageHealth:
        ...

    def create_run(
        self,
        *,
        run_id: str,
        intake: dict[str, Any],
        phase: str,
    ) -> None:
        ...

    def write_checkpoint(
        self,
        *,
        run_id: str,
        phase: str,
        sequence: int,
        run_context_snapshot: dict[str, Any],
    ) -> None:
        ...


@dataclass(slots=True)
class RuntimeStores:
    config: RuntimeStorageConfig
    long_term_memory: LongTermMemoryStore
    run_state: RunStateStore

    def healthcheck_required(self) -> None:
        failures = [
            health
            for health in (
                self.long_term_memory.healthcheck(),
                self.run_state.healthcheck(),
            )
            if health.status != "ok"
        ]
        if failures:
            raise StorageHealthcheckError(failures[0])

    def snapshot(self) -> dict[str, Any]:
        return {
            **self.config.snapshot(),
            "long_term_memory_health": asdict(self.long_term_memory.healthcheck()),
            "run_state_health": asdict(self.run_state.healthcheck()),
        }
