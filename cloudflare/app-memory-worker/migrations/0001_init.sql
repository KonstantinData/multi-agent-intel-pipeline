PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS memory_events (
  event_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  department TEXT NOT NULL,
  kind TEXT NOT NULL,
  source TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  summary_json TEXT NOT NULL,
  version INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (run_id, version)
);

CREATE INDEX IF NOT EXISTS idx_memory_events_run_created
ON memory_events(run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_events_kind_created
ON memory_events(kind, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_snapshots_run_created
ON memory_snapshots(run_id, created_at DESC);
