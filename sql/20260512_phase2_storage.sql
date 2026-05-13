-- Phase 2 storage schema for Hetzner PostgreSQL + pgvector.
-- Schema version: 2026-05-12.1

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS runs (
    run_id text PRIMARY KEY,
    company_name text NOT NULL,
    web_domain text NOT NULL,
    normalized_domain text NOT NULL,
    status text NOT NULL,
    current_phase text NOT NULL,
    schema_version text NOT NULL DEFAULT '2026-05-12.1',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    error_code text NOT NULL DEFAULT '',
    error_message text NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_current_phase ON runs(current_phase);
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at);

CREATE TABLE IF NOT EXISTS run_checkpoints (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    phase text NOT NULL,
    sequence integer NOT NULL,
    schema_version text NOT NULL DEFAULT '2026-05-12.1',
    run_context_snapshot jsonb NOT NULL,
    content_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, phase, sequence)
);

CREATE INDEX IF NOT EXISTS idx_run_checkpoints_run_phase
    ON run_checkpoints(run_id, phase, sequence);

CREATE TABLE IF NOT EXISTS run_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    sequence integer NOT NULL,
    agent text NOT NULL,
    type text NOT NULL,
    phase text NOT NULL DEFAULT '',
    schema_version text NOT NULL DEFAULT '2026-05-12.1',
    content_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, sequence)
);

CREATE TABLE IF NOT EXISTS run_artifacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    artifact_type text NOT NULL,
    storage_backend text NOT NULL,
    storage_key text NOT NULL,
    content_hash text NOT NULL,
    schema_version text NOT NULL DEFAULT '2026-05-12.1',
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_run_artifacts_run_type
    ON run_artifacts(run_id, artifact_type);

CREATE TABLE IF NOT EXISTS run_locks (
    run_id text PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
    owner text NOT NULL,
    locked_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_patterns (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role text NOT NULL,
    pattern_scope text NOT NULL,
    industry_hint text NOT NULL DEFAULT '',
    content_text text NOT NULL,
    content_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(1536),
    embedding_model text NOT NULL DEFAULT '',
    score double precision NOT NULL DEFAULT 0,
    source_run_id text,
    schema_version text NOT NULL DEFAULT '2026-05-12.1',
    content_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memory_patterns_filters
    ON memory_patterns(role, pattern_scope, industry_hint, schema_version);
CREATE INDEX IF NOT EXISTS idx_memory_patterns_score
    ON memory_patterns(score DESC);
CREATE INDEX IF NOT EXISTS idx_memory_patterns_embedding_hnsw
    ON memory_patterns USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS memory_retrieval_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id text NOT NULL,
    role text NOT NULL DEFAULT '',
    industry_hint text NOT NULL DEFAULT '',
    limit_requested integer NOT NULL,
    retrieval_policy_version text NOT NULL,
    schema_version text NOT NULL DEFAULT '2026-05-12.1',
    result_count integer NOT NULL,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memory_retrieval_events_run
    ON memory_retrieval_events(run_id, role, created_at);

CREATE TABLE IF NOT EXISTS memory_backfill_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_key text NOT NULL UNIQUE,
    status text NOT NULL,
    dry_run boolean NOT NULL DEFAULT true,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    read_count integer NOT NULL DEFAULT 0,
    inserted_count integer NOT NULL DEFAULT 0,
    rejected_count integer NOT NULL DEFAULT 0,
    error_count integer NOT NULL DEFAULT 0,
    schema_version text NOT NULL DEFAULT '2026-05-12.1',
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);

