-- PostgreSQL auth schema for multi-user Liquisto runtime.
-- Applied automatically by ui/auth/db.py init_db(), but kept here for
-- explicit migration/audit operations.

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
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower
    ON users (LOWER(email));

CREATE TABLE IF NOT EXISTS audit_log (
    id           BIGSERIAL PRIMARY KEY,
    timestamp    TIMESTAMPTZ NOT NULL,
    actor_email  TEXT NOT NULL,
    action       TEXT NOT NULL,
    target_email TEXT,
    detail       TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp_desc
    ON audit_log (timestamp DESC);
