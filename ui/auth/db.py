"""SQLite user store and audit log for Liquisto auth."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator

# Docker: set LIQUISTO_DATA_DIR=/app/data  |  Dev: defaults to <project_root>/data/
_DATA_DIR = Path(
    os.environ.get("LIQUISTO_DATA_DIR", Path(__file__).resolve().parents[2] / "data")
)
_DB_PATH = _DATA_DIR / "users.db"

_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15


@contextmanager
def _db() -> Generator[sqlite3.Connection, None, None]:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
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
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                email                   TEXT    UNIQUE NOT NULL COLLATE NOCASE,
                password_hash           TEXT    NOT NULL,
                first_name              TEXT    NOT NULL DEFAULT '',
                last_name               TEXT    NOT NULL DEFAULT '',
                company                 TEXT    NOT NULL DEFAULT '',
                role                    TEXT    NOT NULL DEFAULT '',
                mobile                  TEXT    NOT NULL DEFAULT '',
                language                TEXT    NOT NULL DEFAULT 'de',
                is_admin                INTEGER NOT NULL DEFAULT 0,
                is_active               INTEGER NOT NULL DEFAULT 1,
                created_at              TEXT    NOT NULL,
                last_login              TEXT,
                failed_login_attempts   INTEGER NOT NULL DEFAULT 0,
                locked_until            TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp     TEXT NOT NULL,
                actor_email   TEXT NOT NULL,
                action        TEXT NOT NULL,
                target_email  TEXT,
                detail        TEXT
            );
        """)


# ── User queries ──────────────────────────────────────────────────────────────

def get_user_by_email(email: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def list_users() -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]


def user_count() -> int:
    with _db() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        return row["n"] if row else 0


# ── User mutations ────────────────────────────────────────────────────────────

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
            """INSERT INTO users
               (email, password_hash, first_name, last_name, company, role,
                mobile, language, is_admin, is_active, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (
                email.strip().lower(), password_hash,
                first_name.strip(), last_name.strip(),
                company.strip(), role.strip(), mobile.strip(),
                language, int(is_admin), now,
            ),
        )
        _write_audit(conn, actor_email, "create_user", email,
                     f"{first_name} {last_name} admin={is_admin}")
    return get_user_by_email(email)  # type: ignore[return-value]


def update_user(actor_email: str, user_id: int, **fields: object) -> None:
    allowed = {
        "first_name", "last_name", "company", "role", "mobile",
        "language", "is_admin", "is_active", "password_hash",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return

    with _db() as conn:
        conn.execute(
            """UPDATE users SET
               first_name = CASE WHEN ? THEN ? ELSE first_name END,
               last_name = CASE WHEN ? THEN ? ELSE last_name END,
               company = CASE WHEN ? THEN ? ELSE company END,
               role = CASE WHEN ? THEN ? ELSE role END,
               mobile = CASE WHEN ? THEN ? ELSE mobile END,
               language = CASE WHEN ? THEN ? ELSE language END,
               is_admin = CASE WHEN ? THEN ? ELSE is_admin END,
               is_active = CASE WHEN ? THEN ? ELSE is_active END,
               password_hash = CASE WHEN ? THEN ? ELSE password_hash END
               WHERE id = ?""",
            (
                "first_name" in updates, updates.get("first_name"),
                "last_name" in updates, updates.get("last_name"),
                "company" in updates, updates.get("company"),
                "role" in updates, updates.get("role"),
                "mobile" in updates, updates.get("mobile"),
                "language" in updates, updates.get("language"),
                "is_admin" in updates, updates.get("is_admin"),
                "is_active" in updates, updates.get("is_active"),
                "password_hash" in updates, updates.get("password_hash"),
                user_id,
            ),
        )
        _write_audit(conn, actor_email, "update_user", str(user_id),
                     str(sorted(updates.keys())))


# ── Login tracking ────────────────────────────────────────────────────────────

def record_login_success(user_id: int, email: str) -> None:
    with _db() as conn:
        conn.execute(
            """UPDATE users
               SET last_login = ?, failed_login_attempts = 0, locked_until = NULL
               WHERE id = ?""",
            (_utcnow(), user_id),
        )
        _write_audit(conn, email, "login", email, "success")


def record_login_failure(user_id: int, email: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE users SET failed_login_attempts = failed_login_attempts + 1 WHERE id = ?",
            (user_id,),
        )
        row = conn.execute(
            "SELECT failed_login_attempts FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row and row["failed_login_attempts"] >= _MAX_FAILED_ATTEMPTS:
            locked = (
                datetime.now(timezone.utc) + timedelta(minutes=_LOCKOUT_MINUTES)
            ).isoformat()
            conn.execute("UPDATE users SET locked_until = ? WHERE id = ?", (locked, user_id))
        _write_audit(conn, email, "login_failed", email, "invalid credentials")


# ── Audit log ─────────────────────────────────────────────────────────────────

def log_audit(actor_email: str, action: str, target_email: str = "", detail: str = "") -> None:
    with _db() as conn:
        _write_audit(conn, actor_email, action, target_email, detail)


def get_audit_log(limit: int = 200) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_audit(
    conn: sqlite3.Connection,
    actor: str,
    action: str,
    target: str,
    detail: str = "",
) -> None:
    conn.execute(
        """INSERT INTO audit_log (timestamp, actor_email, action, target_email, detail)
           VALUES (?, ?, ?, ?, ?)""",
        (_utcnow(), actor, action, target, detail),
    )
