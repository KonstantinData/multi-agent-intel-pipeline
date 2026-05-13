"""PostgreSQL user store and audit log for Liquisto auth."""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Generator

_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15


def _postgres_dsn() -> str:
    return (
        os.getenv("LIQUISTO_AUTH_POSTGRES_DSN", "").strip()
        or os.getenv("LIQUISTO_POSTGRES_DSN", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )


def _require_postgres_dsn() -> str:
    dsn = _postgres_dsn()
    if dsn:
        return dsn
    raise RuntimeError(
        "PostgreSQL auth backend requires LIQUISTO_AUTH_POSTGRES_DSN, "
        "LIQUISTO_POSTGRES_DSN, or DATABASE_URL.",
    )


def _connect_postgres() -> Any:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "PostgreSQL auth backend requires package `psycopg`.",
        ) from exc
    return psycopg.connect(_require_postgres_dsn(), row_factory=dict_row, autocommit=False)


@contextmanager
def _db() -> Generator[Any, None, None]:
    conn = _connect_postgres()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id                    BIGSERIAL PRIMARY KEY,
                email                 TEXT NOT NULL,
                password_hash         TEXT NOT NULL,
                first_name            TEXT NOT NULL DEFAULT '',
                last_name             TEXT NOT NULL DEFAULT '',
                company               TEXT NOT NULL DEFAULT '',
                role                  TEXT NOT NULL DEFAULT '',
                mobile                TEXT NOT NULL DEFAULT '',
                language              TEXT NOT NULL DEFAULT 'de',
                is_admin              BOOLEAN NOT NULL DEFAULT FALSE,
                is_active             BOOLEAN NOT NULL DEFAULT TRUE,
                created_at            TIMESTAMPTZ NOT NULL,
                last_login            TIMESTAMPTZ,
                failed_login_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until          TIMESTAMPTZ
            )
            """,
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower
            ON users (LOWER(email))
            """,
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id           BIGSERIAL PRIMARY KEY,
                timestamp    TIMESTAMPTZ NOT NULL,
                actor_email  TEXT NOT NULL,
                action       TEXT NOT NULL,
                target_email TEXT,
                detail       TEXT
            )
            """,
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp_desc
            ON audit_log (timestamp DESC)
            """,
        )


def get_user_by_email(email: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE LOWER(email) = LOWER(%s)",
            (email.strip().lower(),),
        ).fetchone()
        return _normalize_row(row)


def get_user_by_id(user_id: int) -> dict | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
        return _normalize_row(row)


def list_users() -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY LOWER(last_name), LOWER(first_name)",
        ).fetchall()
        return [_normalize_row(row) for row in rows if row]


def user_count() -> int:
    with _db() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        if not row:
            return 0
        return int(row.get("n", 0) or 0)


def create_user(
    *,
    actor_email: str,
    email: str,
    password_hash: str,
    first_name: str,
    last_name: str,
    company: str = "",
    role: str = "",
    mobile: str = "",
    language: str = "de",
    is_admin: bool = False,
) -> dict:
    now = _utcnow()
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO users
            (email, password_hash, first_name, last_name, company, role,
             mobile, language, is_admin, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
            """,
            (
                email.strip().lower(),
                password_hash,
                first_name.strip(),
                last_name.strip(),
                company.strip(),
                role.strip(),
                mobile.strip(),
                language,
                bool(is_admin),
                now,
            ),
        )
        _write_audit(
            conn,
            actor_email,
            "create_user",
            email,
            f"{first_name} {last_name} admin={bool(is_admin)}",
        )
    return get_user_by_email(email)  # type: ignore[return-value]


def update_user(actor_email: str, user_id: int, **fields: object) -> None:
    allowed = {
        "first_name", "last_name", "company", "role", "mobile",
        "language", "is_admin", "is_active", "password_hash",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return

    assignments = ", ".join(f"{column} = %s" for column in updates.keys())
    values = list(updates.values())
    values.append(user_id)

    with _db() as conn:
        conn.execute(f"UPDATE users SET {assignments} WHERE id = %s", tuple(values))
        _write_audit(
            conn,
            actor_email,
            "update_user",
            str(user_id),
            str(sorted(updates.keys())),
        )


def record_login_success(user_id: int, email: str) -> None:
    with _db() as conn:
        conn.execute(
            """
            UPDATE users
            SET last_login = %s, failed_login_attempts = 0, locked_until = NULL
            WHERE id = %s
            """,
            (_utcnow(), user_id),
        )
        _write_audit(conn, email, "login", email, "success")


def record_login_failure(user_id: int, email: str) -> None:
    with _db() as conn:
        conn.execute(
            """
            UPDATE users
            SET failed_login_attempts = failed_login_attempts + 1
            WHERE id = %s
            """,
            (user_id,),
        )
        row = conn.execute(
            "SELECT failed_login_attempts FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
        attempts = int((row or {}).get("failed_login_attempts", 0) or 0)
        if attempts >= _MAX_FAILED_ATTEMPTS:
            locked = datetime.now(timezone.utc) + timedelta(minutes=_LOCKOUT_MINUTES)
            conn.execute(
                "UPDATE users SET locked_until = %s WHERE id = %s",
                (locked.isoformat(), user_id),
            )
        _write_audit(conn, email, "login_failed", email, "invalid credentials")


def log_audit(actor_email: str, action: str, target_email: str = "", detail: str = "") -> None:
    with _db() as conn:
        _write_audit(conn, actor_email, action, target_email, detail)


def get_audit_log(limit: int = 200) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT %s",
            (int(limit),),
        ).fetchall()
        return [_normalize_row(row) for row in rows if row]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_row(row: Any) -> dict | None:
    if not row:
        return None
    payload = dict(row)
    for key, value in list(payload.items()):
        if isinstance(value, datetime):
            payload[key] = value.astimezone(timezone.utc).isoformat()
    return payload


def _write_audit(
    conn: Any,
    actor: str,
    action: str,
    target: str,
    detail: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (timestamp, actor_email, action, target_email, detail)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (_utcnow(), actor, action, target, detail),
    )
