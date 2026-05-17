PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS memory_events (
  event_id TEXT PRIMARY KEY,
  area TEXT NOT NULL,
  event_type TEXT NOT NULL,
  source TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_objects (
  object_id TEXT PRIMARY KEY,
  object_key TEXT NOT NULL UNIQUE,
  object_type TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  content_type TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_candidates (
  candidate_id TEXT PRIMARY KEY,
  candidate_type TEXT NOT NULL,
  role TEXT NOT NULL,
  scope TEXT NOT NULL,
  status TEXT NOT NULL,
  scrub_status TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  source_reference_hash TEXT NOT NULL,
  object_id TEXT NOT NULL REFERENCES memory_objects(object_id),
  content_hash TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pattern_reviews (
  review_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES learning_candidates(candidate_id) ON DELETE CASCADE,
  decision TEXT NOT NULL,
  reviewer TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  notes_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accepted_patterns (
  pattern_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES learning_candidates(candidate_id),
  pattern_type TEXT NOT NULL,
  role TEXT NOT NULL,
  scope TEXT NOT NULL,
  status TEXT NOT NULL,
  version INTEGER NOT NULL,
  object_id TEXT NOT NULL REFERENCES memory_objects(object_id),
  vector_id TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (candidate_id, version),
  UNIQUE (vector_id)
);

CREATE TABLE IF NOT EXISTS retrieval_events (
  retrieval_id TEXT PRIMARY KEY,
  correlation_id TEXT NOT NULL,
  role TEXT NOT NULL,
  scope TEXT NOT NULL,
  query_hash TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  result_count INTEGER NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_events (
  ops_event_id TEXT PRIMARY KEY,
  component TEXT NOT NULL,
  environment TEXT NOT NULL,
  event_type TEXT NOT NULL,
  status TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_events_area_created
ON memory_events(area, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_events_correlation_created
ON memory_events(correlation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_learning_candidates_status
ON learning_candidates(status, candidate_type, role, scope);

CREATE INDEX IF NOT EXISTS idx_pattern_reviews_candidate
ON pattern_reviews(candidate_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_accepted_patterns_retrieval
ON accepted_patterns(status, role, scope, pattern_type);

CREATE INDEX IF NOT EXISTS idx_retrieval_events_correlation
ON retrieval_events(correlation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ops_events_component_created
ON ops_events(component, environment, created_at DESC);
