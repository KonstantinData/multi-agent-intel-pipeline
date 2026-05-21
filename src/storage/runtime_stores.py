"""Runtime store factory for local and production storage profiles."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config.settings import get_postgres_dsn
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
class FailedRunStateStore:
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
class FailedLongTermMemoryStore:
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

    def upsert_strategy(self, pattern: dict[str, Any]) -> bool:
        raise RuntimeError(self.reason)


def _resolve_postgres_dsn() -> str:
    return get_postgres_dsn().strip()


def _connect_pg(dsn: str) -> Any:
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(dsn, row_factory=dict_row, autocommit=False)


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _text_content_from_pattern(pattern: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "name",
        "role",
        "pattern_scope",
        "pattern_type",
        "best_practice_type",
        "task_key",
        "industry_hint",
        "rationale",
        "structural_queries",
        "source_strategy",
        "evidence_pattern",
        "task_recipe",
        "critic_acceptance_heuristic",
        "common_defect_classes",
        "retry_trigger_patterns",
    ):
        value = pattern.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value is not None:
            parts.append(str(value))
    return " | ".join(part for part in parts if part)


def _pattern_content_hash(pattern: dict[str, Any]) -> str:
    explicit = str(pattern.get("content_hash") or "").strip()
    if explicit:
        return explicit
    return hashlib.sha256(_json_text(pattern).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class PostgresRunStateStore:
    dsn: str

    def healthcheck(self) -> StorageHealth:
        try:
            with _connect_pg(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 AS ok")
                    cur.fetchone()
                    cur.execute(
                        """
                        SELECT to_regclass('public.runs') AS runs_table,
                               to_regclass('public.run_checkpoints') AS checkpoints_table
                        """,
                    )
                    row = cur.fetchone() or {}
                conn.rollback()
            if not row.get("runs_table") or not row.get("checkpoints_table"):
                return StorageHealth(
                    status="failed",
                    component="run_state",
                    error_code="postgres_schema_missing",
                    message="Required tables runs/run_checkpoints are missing.",
                    details={"backend": "postgres"},
                )
            return StorageHealth(
                status="ok",
                component="run_state",
                details={"backend": "postgres"},
            )
        except Exception:
            return StorageHealth(
                status="failed",
                component="run_state",
                error_code="postgres_connection_failed",
                message="Could not connect to PostgreSQL run_state backend.",
                details={"backend": "postgres"},
            )

    def create_run(self, *, run_id: str, intake: dict[str, Any], phase: str) -> None:
        company_name = str(intake.get("company_name", "") or "")
        web_domain = str(intake.get("web_domain", "") or "")
        normalized_domain = str(intake.get("normalized_domain", web_domain) or web_domain)
        with _connect_pg(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO runs (
                        run_id, company_name, web_domain, normalized_domain,
                        status, current_phase
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id) DO UPDATE
                    SET current_phase = EXCLUDED.current_phase,
                        status = EXCLUDED.status,
                        updated_at = now()
                    """,
                    (run_id, company_name, web_domain, normalized_domain, "running", phase),
                )
            conn.commit()

    def write_checkpoint(
        self,
        *,
        run_id: str,
        phase: str,
        sequence: int,
        run_context_snapshot: dict[str, Any],
    ) -> None:
        content_hash = hashlib.sha256(
            _json_text(run_context_snapshot).encode("utf-8"),
        ).hexdigest()
        with _connect_pg(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO run_checkpoints (
                        run_id, phase, sequence, run_context_snapshot, content_hash
                    ) VALUES (%s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (run_id, phase, sequence) DO UPDATE
                    SET run_context_snapshot = EXCLUDED.run_context_snapshot,
                        content_hash = EXCLUDED.content_hash
                    """,
                    (run_id, phase, sequence, _json_text(run_context_snapshot), content_hash),
                )
                cur.execute(
                    """
                    UPDATE runs
                    SET current_phase = %s, updated_at = now()
                    WHERE run_id = %s
                    """,
                    (phase, run_id),
                )
            conn.commit()


@dataclass(slots=True)
class PostgresLongTermMemoryStore:
    dsn: str

    def healthcheck(self) -> StorageHealth:
        try:
            with _connect_pg(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT EXISTS(
                            SELECT 1 FROM pg_extension WHERE extname = 'vector'
                        ) AS vector_installed,
                               to_regclass('public.memory_patterns') AS memory_patterns_table
                        """,
                    )
                    row = cur.fetchone() or {}
                conn.rollback()
            if not row.get("memory_patterns_table"):
                return StorageHealth(
                    status="failed",
                    component="long_term_memory",
                    error_code="postgres_schema_missing",
                    message="Required table memory_patterns is missing.",
                    details={"backend": "postgres_pgvector"},
                )
            if not row.get("vector_installed"):
                return StorageHealth(
                    status="failed",
                    component="long_term_memory",
                    error_code="pgvector_missing",
                    message="pgvector extension is not installed.",
                    details={"backend": "postgres_pgvector"},
                )
            return StorageHealth(
                status="ok",
                component="long_term_memory",
                details={"backend": "postgres_pgvector"},
            )
        except Exception:
            return StorageHealth(
                status="failed",
                component="long_term_memory",
                error_code="postgres_connection_failed",
                message="Could not connect to PostgreSQL long_term_memory backend.",
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
        resolved_limit = max(int(limit or 5), 1)
        with _connect_pg(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id::text AS pattern_id,
                        role,
                        pattern_scope,
                        industry_hint,
                        content_text,
                        content_json,
                        score,
                        schema_version,
                        content_hash
                    FROM memory_patterns
                    WHERE (%s = '' OR role = %s)
                      AND (%s = '' OR pattern_scope = %s)
                      AND (%s = '' OR industry_hint = %s OR industry_hint = '')
                    ORDER BY score DESC, updated_at DESC
                    LIMIT %s
                    """,
                    (
                        role,
                        role,
                        pattern_scope,
                        pattern_scope,
                        industry_hint,
                        industry_hint,
                        resolved_limit,
                    ),
                )
                rows = cur.fetchall() or []
            conn.rollback()
        results: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            content_json = payload.get("content_json")
            if isinstance(content_json, dict):
                payload.update(content_json)
            payload.setdefault("name", str(payload.get("pattern_id", "pattern")))
            payload.setdefault("score", float(payload.get("score", 0.0) or 0.0))
            results.append(payload)
        return results

    def upsert_strategy(self, pattern: dict[str, Any]) -> bool:
        role = str(pattern.get("role") or "").strip()
        scope = str(pattern.get("pattern_scope") or "").strip()
        if not role or not scope:
            return False
        industry_hint = str(pattern.get("industry_hint") or "").strip()
        score = float(pattern.get("score", 0.0) or 0.0)
        source_run_id = str(pattern.get("source_run_id") or "").strip() or None
        schema_version = str(pattern.get("schema_version") or "2026-05-21.1")
        content_hash = _pattern_content_hash(pattern)
        content_text = _text_content_from_pattern(pattern)
        with _connect_pg(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO memory_patterns (
                        role, pattern_scope, industry_hint, content_text, content_json,
                        embedding, embedding_model, score, source_run_id,
                        schema_version, content_hash
                    ) VALUES (
                        %s, %s, %s, %s, %s::jsonb,
                        NULL, '', %s, %s,
                        %s, %s
                    )
                    ON CONFLICT (content_hash) DO UPDATE
                    SET role = EXCLUDED.role,
                        pattern_scope = EXCLUDED.pattern_scope,
                        industry_hint = EXCLUDED.industry_hint,
                        content_text = EXCLUDED.content_text,
                        content_json = EXCLUDED.content_json,
                        score = EXCLUDED.score,
                        source_run_id = EXCLUDED.source_run_id,
                        schema_version = EXCLUDED.schema_version,
                        updated_at = now()
                    """,
                    (
                        role,
                        scope,
                        industry_hint,
                        content_text,
                        _json_text(pattern),
                        score,
                        source_run_id,
                        schema_version,
                        content_hash,
                    ),
                )
            conn.commit()
        return True


def create_runtime_stores(
    *,
    config: RuntimeStorageConfig | None = None,
    runs_root: Path,
    long_term_memory_path: Path,
) -> RuntimeStores:
    cfg = config or RuntimeStorageConfig.from_env()
    if cfg.profile == "production":
        dsn = _resolve_postgres_dsn()
        if not dsn or not cfg.postgres_dsn_present:
            reason = (
                "Production storage profile requires LIQUISTO_POSTGRES_DSN "
                "or DATABASE_URL with migrated pgvector schema."
            )
            return RuntimeStores(
                config=cfg,
                long_term_memory=FailedLongTermMemoryStore(reason),
                run_state=FailedRunStateStore(reason),
            )
        return RuntimeStores(
            config=cfg,
            long_term_memory=PostgresLongTermMemoryStore(dsn=dsn),
            run_state=PostgresRunStateStore(dsn=dsn),
        )

    return RuntimeStores(
        config=cfg,
        long_term_memory=FileLongTermMemoryStore(long_term_memory_path),
        run_state=LocalRunStateStore(runs_root),
    )


__all__ = [
    "LocalRunStateStore",
    "FailedLongTermMemoryStore",
    "FailedRunStateStore",
    "PostgresLongTermMemoryStore",
    "PostgresRunStateStore",
    "create_runtime_stores",
]
