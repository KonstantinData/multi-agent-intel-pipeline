"""PostgreSQL-backed run artifact helpers used in production profile."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from src.storage.contracts import RuntimeStorageConfig


def _is_production_profile() -> bool:
    return RuntimeStorageConfig.from_env().profile == "production"


def _postgres_dsn() -> str:
    return (
        os.getenv("LIQUISTO_POSTGRES_DSN", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )


def _connect_pg(dsn: str) -> Any:
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(dsn, row_factory=dict_row, autocommit=False)


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _content_hash(payload: Any) -> str:
    return hashlib.sha256(_json_text(payload).encode("utf-8")).hexdigest()


def should_use_postgres_run_artifacts() -> bool:
    return _is_production_profile()


def upsert_run_artifact_json(
    *,
    run_id: str,
    artifact_type: str,
    payload: Any,
    storage_backend: str = "postgres_jsonb",
) -> None:
    dsn = _postgres_dsn()
    if not dsn:
        raise RuntimeError(
            "Production run artifacts require LIQUISTO_POSTGRES_DSN or DATABASE_URL.",
        )
    content_hash = _content_hash(payload)
    with _connect_pg(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO run_artifacts (
                    run_id,
                    artifact_type,
                    storage_backend,
                    storage_key,
                    content_hash,
                    metadata_json
                ) VALUES (
                    %s, %s, %s, %s, %s, %s::jsonb
                )
                """,
                (
                    run_id,
                    artifact_type,
                    storage_backend,
                    artifact_type,
                    content_hash,
                    _json_text(payload),
                ),
            )
        conn.commit()


def load_latest_run_artifact_json(
    *,
    run_id: str,
    artifact_type: str,
) -> Any:
    dsn = _postgres_dsn()
    if not dsn:
        raise RuntimeError(
            "Production run artifacts require LIQUISTO_POSTGRES_DSN or DATABASE_URL.",
        )
    with _connect_pg(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT metadata_json
                FROM run_artifacts
                WHERE run_id = %s
                  AND artifact_type = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (run_id, artifact_type),
            )
            row = cur.fetchone() or {}
        conn.rollback()
    if not row:
        raise FileNotFoundError(
            f"Run artifact not found in postgres: run_id={run_id} artifact_type={artifact_type}",
        )
    return row.get("metadata_json")


def append_follow_up_history(*, run_id: str, follow_up_answer: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        existing = load_latest_run_artifact_json(
            run_id=run_id,
            artifact_type="follow_up_history",
        )
        history = list(existing) if isinstance(existing, list) else []
    except FileNotFoundError:
        history = []
    history.append(dict(follow_up_answer))
    upsert_run_artifact_json(
        run_id=run_id,
        artifact_type="follow_up_history",
        payload=history,
    )
    return history
