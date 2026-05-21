interface MaipMemoryEnv extends Env {
  ACCOUNT_ID?: string;
  APP_ENV: Env["APP_ENV"];
  INGEST_API_TOKEN?: string;
  MEMORY_DB: D1Database;
  MEMORY_OBJECTS?: R2Bucket;
  PATTERN_INDEX?: VectorizeIndex;
  POLICY_VERSION: Env["POLICY_VERSION"];
  SCHEMA_VERSION: Env["SCHEMA_VERSION"];
}

type JsonRecord = Record<string, unknown>;

const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };
const DEFAULT_SCHEMA_VERSION = "2026-05-17.1";
const DEFAULT_POLICY_VERSION = "maip-memory-policy-2026-05-17.1";
const MAX_JSON_BYTES = 64 * 1024;
const MAX_LIMIT = 200;

const ALLOWED_AREAS = new Set(["operations", "learning", "governance", "ci", "docs", "tests"]);
const ALLOWED_EVENT_TYPES = new Set([
  "worker_smoke_test",
  "d1_migration_applied",
  "r2_object_written",
  "vectorize_rebuild_started",
  "vectorize_rebuild_completed",
  "deployment_attempted",
  "deployment_succeeded",
  "deployment_failed",
  "healthcheck_observed",
  "ci_gate_result",
  "schema_change_proposed",
  "schema_change_applied",
  "incident_note",
  "maintenance_note",
  "learning_candidate_created",
  "learning_candidate_rejected",
  "learning_pattern_accepted",
  "query_strategy_candidate",
  "critic_heuristic_candidate",
  "source_strategy_candidate",
  "evidence_pattern_candidate",
  "task_recipe_candidate",
  "critic_acceptance_heuristic_candidate",
  "judge_principle_candidate",
  "failure_mode_pattern",
  "test_gap_pattern",
  "report_quality_pattern",
  "department_completion_pattern",
  "scrub_check_passed",
  "scrub_check_failed",
  "policy_rejection",
  "unsafe_payload_rejected",
  "pattern_deprecated",
  "manual_review_required",
  "manual_review_accepted",
  "manual_review_rejected",
  "git_branch_guard_failed",
  "compliance_check_completed",
  "pre_pr_gate_completed",
  "pr_check_failed",
  "pr_fix_attempt_started",
  "pr_fix_attempt_completed",
  "pr_recheck_completed",
  "pr_recovered",
  "learning_pattern_candidate_created"
]);
const ALLOWED_CANDIDATE_TYPES = new Set([
  "query_strategy_candidate",
  "critic_heuristic_candidate",
  "source_strategy_candidate",
  "evidence_pattern_candidate",
  "task_recipe_candidate",
  "critic_acceptance_heuristic_candidate",
  "judge_principle_candidate",
  "failure_mode_pattern",
  "test_gap_pattern",
  "report_quality_pattern",
  "department_completion_pattern"
]);
const ALLOWED_PATTERN_TYPES = new Set([
  "query_strategy",
  "critic_heuristic",
  "source_strategy",
  "evidence_pattern",
  "task_recipe",
  "critic_acceptance_heuristic",
  "judge_principle",
  "failure_mode",
  "test_gap",
  "report_quality",
  "department_completion"
]);
const ALLOWED_REVIEW_DECISIONS = new Set([
  "accepted",
  "rejected",
  "needs_revision",
  "unsafe_payload",
  "duplicate",
  "out_of_scope"
]);
const FORBIDDEN_CONTENT_PATTERNS = [
  /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i,
  /https?:\/\/[^\s"'<>]+/i,
  /\b[a-z0-9-]+(\.[a-z0-9-]+)+\b/i,
  /\b(api[_-]?key|secret|token|password|bearer)\b\s*[:=]/i
];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });
}

function nowIso(): string {
  return new Date().toISOString();
}

function schemaVersion(env: MaipMemoryEnv): string {
  return env.SCHEMA_VERSION || DEFAULT_SCHEMA_VERSION;
}

function policyVersion(env: MaipMemoryEnv): string {
  return env.POLICY_VERSION || DEFAULT_POLICY_VERSION;
}

function asObject(value: unknown): JsonRecord | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : null;
}

function requiredString(value: unknown, max = 256): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= max;
}

function optionalString(value: unknown, fallback = "", max = 256): string {
  return typeof value === "string" && value.length <= max ? value : fallback;
}

function clampLimit(value: string | null, fallback = 50): number {
  const parsed = Number.parseInt(value || String(fallback), 10);
  return Number.isFinite(parsed) ? Math.min(Math.max(parsed, 1), MAX_LIMIT) : fallback;
}

function stringify(value: unknown): string {
  return JSON.stringify(value ?? {});
}

function parseJson(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function payloadTooLarge(value: unknown): boolean {
  return new TextEncoder().encode(stringify(value)).byteLength > MAX_JSON_BYTES;
}

function forbiddenMatches(value: unknown): string[] {
  const text = stringify(value);
  return FORBIDDEN_CONTENT_PATTERNS.filter((pattern) => pattern.test(text)).map((pattern) => pattern.source);
}

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function objectKey(...parts: string[]): string {
  return parts.map((part) => part.replace(/[^a-zA-Z0-9._/-]/g, "_")).join("/");
}

function normalizeBearerToken(authHeader: string | null): string | null {
  if (!authHeader) {
    return null;
  }
  const [scheme, token] = authHeader.split(" ", 2);
  return scheme === "Bearer" && token ? token.trim() : null;
}

function timingSafeEqual(left: string, right: string): boolean {
  const encoder = new TextEncoder();
  const leftBytes = encoder.encode(left);
  const rightBytes = encoder.encode(right);
  if (leftBytes.byteLength !== rightBytes.byteLength) {
    return false;
  }
  return (
    crypto.subtle as SubtleCrypto & {
      timingSafeEqual(a: ArrayBuffer | ArrayBufferView, b: ArrayBuffer | ArrayBufferView): boolean;
    }
  ).timingSafeEqual(leftBytes, rightBytes);
}

async function requireAuth(request: Request, env: MaipMemoryEnv): Promise<Response | null> {
  const expected = (env.INGEST_API_TOKEN || "").trim();
  if (!expected) {
    return json({ error: "Server misconfiguration: missing INGEST_API_TOKEN secret." }, 500);
  }
  const provided = normalizeBearerToken(request.headers.get("authorization"));
  if (!provided || !timingSafeEqual(provided, expected)) {
    return json({ error: "Unauthorized." }, 401);
  }
  return null;
}

async function readBody(request: Request): Promise<JsonRecord | Response> {
  let parsed: unknown;
  try {
    parsed = await request.json();
  } catch {
    return json({ error: "Request body must be valid JSON." }, 400);
  }
  const body = asObject(parsed);
  return body || json({ error: "Request body must be a JSON object." }, 400);
}

async function writeEvent(
  env: MaipMemoryEnv,
  input: { area: string; eventType: string; source: string; correlationId: string; payload: unknown }
): Promise<{ event_id: string; created_at: string }> {
  const eventId = crypto.randomUUID();
  const createdAt = nowIso();
  await env.MEMORY_DB.prepare(
    `INSERT INTO memory_events (
       event_id, area, event_type, source, correlation_id, schema_version, payload_json, created_at
     )
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)`
  )
    .bind(
      eventId,
      input.area,
      input.eventType,
      input.source,
      input.correlationId,
      schemaVersion(env),
      stringify(input.payload),
      createdAt
    )
    .run();
  return { event_id: eventId, created_at: createdAt };
}

async function storeObject(
  env: MaipMemoryEnv,
  input: { objectType: string; key: string; body: unknown; createdBy: string }
): Promise<{ objectId: string; objectKey: string; contentHash: string }> {
  if (!env.MEMORY_OBJECTS) {
    throw new Error("missing_MEMORY_OBJECTS_binding");
  }
  const objectBody = JSON.stringify(input.body, null, 2);
  const contentHash = await sha256Hex(objectBody);
  const objectId = crypto.randomUUID();
  const createdAt = nowIso();
  await env.MEMORY_OBJECTS.put(input.key, objectBody, {
    httpMetadata: { contentType: "application/json; charset=utf-8" },
    customMetadata: {
      object_id: objectId,
      object_type: input.objectType,
      content_hash: contentHash,
      schema_version: schemaVersion(env)
    }
  });
  await env.MEMORY_DB.prepare(
    `INSERT INTO memory_objects (
       object_id, object_key, object_type, content_hash, content_type, schema_version, created_at, created_by
     )
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)`
  )
    .bind(objectId, input.key, input.objectType, contentHash, "application/json", schemaVersion(env), createdAt, input.createdBy)
    .run();
  return { objectId, objectKey: input.key, contentHash };
}

async function readObject(env: MaipMemoryEnv, key: string): Promise<unknown | null> {
  if (!env.MEMORY_OBJECTS) {
    return null;
  }
  const object = await env.MEMORY_OBJECTS.get(key);
  return object ? parseJson(await object.text()) : null;
}

async function createEvent(request: Request, env: MaipMemoryEnv): Promise<Response> {
  const body = await readBody(request);
  if (body instanceof Response) {
    return body;
  }
  const area = body.area;
  const eventType = body.event_type;
  const correlationId = body.correlation_id;
  const source = optionalString(body.source, "app");
  const payload = body.payload ?? {};
  if (!requiredString(area, 64) || !ALLOWED_AREAS.has(area)) {
    return json({ error: "area is required and must be allowed." }, 400);
  }
  if (!requiredString(eventType, 64) || !ALLOWED_EVENT_TYPES.has(eventType)) {
    return json({ error: "event_type is required and must be allowed." }, 400);
  }
  if (!requiredString(correlationId, 128)) {
    return json({ error: "correlation_id must be a non-empty string <= 128 chars." }, 400);
  }
  if (payloadTooLarge(payload)) {
    return json({ error: "payload exceeds 64 KiB limit." }, 413);
  }
  return json(await writeEvent(env, { area, eventType, source, correlationId, payload }), 201);
}

async function listEvents(request: Request, env: MaipMemoryEnv): Promise<Response> {
  const url = new URL(request.url);
  const filters = [
    ["area", url.searchParams.get("area")],
    ["event_type", url.searchParams.get("event_type")],
    ["correlation_id", url.searchParams.get("correlation_id")]
  ] as const;
  const clauses: string[] = [];
  const params: string[] = [];
  for (const [field, value] of filters) {
    if (value) {
      clauses.push(`${field} = ?${params.length + 1}`);
      params.push(value);
    }
  }
  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  const result = await env.MEMORY_DB.prepare(
    `SELECT event_id, area, event_type, source, correlation_id, schema_version, payload_json, created_at
     FROM memory_events
     ${where}
     ORDER BY created_at DESC
     LIMIT ?${params.length + 1}`
  )
    .bind(...params, clampLimit(url.searchParams.get("limit")))
    .all<{
      event_id: string;
      area: string;
      event_type: string;
      source: string;
      correlation_id: string;
      schema_version: string;
      payload_json: string;
      created_at: string;
    }>();
  return json({
    events: (result.results || []).map((row) => ({
      event_id: row.event_id,
      area: row.area,
      event_type: row.event_type,
      source: row.source,
      correlation_id: row.correlation_id,
      schema_version: row.schema_version,
      payload: parseJson(row.payload_json),
      created_at: row.created_at
    }))
  });
}

async function createCandidate(request: Request, env: MaipMemoryEnv): Promise<Response> {
  const body = await readBody(request);
  if (body instanceof Response) {
    return body;
  }
  const candidateType = body.candidate_type;
  const role = body.role;
  const scope = body.scope;
  const content = body.body ?? {};
  const createdBy = optionalString(body.created_by, "maip-memory-worker");
  if (!requiredString(candidateType, 64) || !ALLOWED_CANDIDATE_TYPES.has(candidateType)) {
    return json({ error: "candidate_type is required and must be allowed." }, 400);
  }
  if (!requiredString(role, 64) || !requiredString(scope, 128)) {
    return json({ error: "role and scope are required." }, 400);
  }
  if (payloadTooLarge(content)) {
    return json({ error: "candidate body exceeds 64 KiB limit." }, 413);
  }
  const forbidden = forbiddenMatches(content);
  if (forbidden.length) {
    return json({ error: "Candidate body failed forbidden-content scan.", rejection_code: "unsafe_payload_rejected", matched_patterns: forbidden }, 422);
  }
  const candidateId = crypto.randomUUID();
  const createdAt = nowIso();
  const object = await storeObject(env, {
    objectType: "learning_candidate",
    key: objectKey("maip-memory", "learning", "candidates", `${candidateId}.json`),
    createdBy,
    body: {
      schema_version: schemaVersion(env),
      policy_version: policyVersion(env),
      candidate_id: candidateId,
      candidate_type: candidateType,
      role,
      scope,
      body: content
    }
  });
  await env.MEMORY_DB.prepare(
    `INSERT INTO learning_candidates (
       candidate_id, candidate_type, role, scope, status, scrub_status, policy_version,
       source_reference_hash, object_id, content_hash, schema_version, created_at, updated_at
     )
     VALUES (?1, ?2, ?3, ?4, 'proposed', 'passed', ?5, ?6, ?7, ?8, ?9, ?10, ?11)`
  )
    .bind(
      candidateId,
      candidateType,
      role,
      scope,
      optionalString(body.policy_version, policyVersion(env)),
      optionalString(body.source_reference_hash),
      object.objectId,
      object.contentHash,
      schemaVersion(env),
      createdAt,
      createdAt
    )
    .run();
  await writeEvent(env, {
    area: "learning",
    eventType: "learning_candidate_created",
    source: createdBy,
    correlationId: candidateId,
    payload: { candidate_id: candidateId, candidate_type: candidateType, role, scope, object_key: object.objectKey }
  });
  return json({ candidate_id: candidateId, object_key: object.objectKey, content_hash: object.contentHash, status: "proposed", created_at: createdAt }, 201);
}

async function getCandidate(request: Request, env: MaipMemoryEnv, candidateId: string): Promise<Response> {
  const includeBody = new URL(request.url).searchParams.get("include_body") === "true";
  const row = await env.MEMORY_DB.prepare(
    `SELECT c.*, o.object_key
     FROM learning_candidates c
     JOIN memory_objects o ON c.object_id = o.object_id
     WHERE c.candidate_id = ?1`
  )
    .bind(candidateId)
    .first<{ object_key: string } & JsonRecord>();
  if (!row) {
    return json({ error: "Candidate not found." }, 404);
  }
  return json({ candidate: row, body: includeBody ? await readObject(env, row.object_key) : undefined });
}

async function createReview(request: Request, env: MaipMemoryEnv, candidateId: string): Promise<Response> {
  const body = await readBody(request);
  if (body instanceof Response) {
    return body;
  }
  const decision = body.decision;
  if (!requiredString(decision, 64) || !ALLOWED_REVIEW_DECISIONS.has(decision)) {
    return json({ error: "decision is required and must be allowed." }, 400);
  }
  const candidate = await env.MEMORY_DB.prepare(`SELECT candidate_id FROM learning_candidates WHERE candidate_id = ?1`)
    .bind(candidateId)
    .first<{ candidate_id: string }>();
  if (!candidate) {
    return json({ error: "Candidate not found." }, 404);
  }
  const reviewId = crypto.randomUUID();
  const createdAt = nowIso();
  const reviewer = optionalString(body.reviewer, "manual");
  await env.MEMORY_DB.prepare(
    `INSERT INTO pattern_reviews (review_id, candidate_id, decision, reviewer, policy_version, notes_json, created_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)`
  )
    .bind(reviewId, candidateId, decision, reviewer, optionalString(body.policy_version, policyVersion(env)), stringify(body.notes ?? {}), createdAt)
    .run();
  await writeEvent(env, {
    area: "governance",
    eventType: decision === "accepted" ? "manual_review_accepted" : "manual_review_rejected",
    source: reviewer,
    correlationId: candidateId,
    payload: { candidate_id: candidateId, review_id: reviewId, decision }
  });
  return json({ review_id: reviewId, decision, created_at: createdAt }, 201);
}

async function acceptPattern(request: Request, env: MaipMemoryEnv, candidateId: string): Promise<Response> {
  const body = await readBody(request);
  if (body instanceof Response) {
    return body;
  }
  const patternType = body.pattern_type;
  if (!requiredString(patternType, 64) || !ALLOWED_PATTERN_TYPES.has(patternType)) {
    return json({ error: "pattern_type is required and must be allowed." }, 400);
  }
  const candidate = await env.MEMORY_DB.prepare(
    `SELECT c.candidate_id, c.role, c.scope, c.scrub_status, o.object_key
     FROM learning_candidates c
     JOIN memory_objects o ON c.object_id = o.object_id
     WHERE c.candidate_id = ?1`
  )
    .bind(candidateId)
    .first<{ candidate_id: string; role: string; scope: string; scrub_status: string; object_key: string }>();
  if (!candidate) {
    return json({ error: "Candidate not found." }, 404);
  }
  if (candidate.scrub_status !== "passed") {
    return json({ error: "Candidate scrub_status must be passed." }, 422);
  }
  const acceptedReview = await env.MEMORY_DB.prepare(
    `SELECT review_id FROM pattern_reviews WHERE candidate_id = ?1 AND decision = 'accepted' ORDER BY created_at DESC LIMIT 1`
  )
    .bind(candidateId)
    .first<{ review_id: string }>();
  if (!acceptedReview) {
    return json({ error: "Candidate requires accepted review before acceptance." }, 422);
  }
  const patternId = crypto.randomUUID();
  const version = 1;
  const vectorId = `pattern:${patternId}:v${version}`;
  const role = optionalString(body.role, candidate.role);
  const scope = optionalString(body.scope, candidate.scope);
  const createdAt = nowIso();
  const object = await storeObject(env, {
    objectType: "accepted_pattern",
    key: objectKey("maip-memory", "learning", "patterns", `${patternId}.json`),
    createdBy: optionalString(body.created_by, "maip-memory-worker"),
    body: {
      schema_version: schemaVersion(env),
      policy_version: optionalString(body.policy_version, policyVersion(env)),
      pattern_id: patternId,
      candidate_id: candidateId,
      pattern_type: patternType,
      role,
      scope,
      source_candidate: await readObject(env, candidate.object_key)
    }
  });
  let vectorMutation: unknown = null;
  let vectorError = "";
  if (Array.isArray(body.vector) && env.PATTERN_INDEX) {
    try {
      vectorMutation = await env.PATTERN_INDEX.upsert([
        {
          id: vectorId,
          values: body.vector as number[],
          metadata: {
            pattern_id: patternId,
            role,
            scope,
            pattern_type: patternType,
            status: "active",
            schema_version: schemaVersion(env),
            policy_version: optionalString(body.policy_version, policyVersion(env)),
            content_hash: object.contentHash
          }
        }
      ]);
    } catch (error) {
      vectorError = error instanceof Error ? error.message : "vectorize_upsert_failed";
    }
  }
  await env.MEMORY_DB.prepare(
    `INSERT INTO accepted_patterns (
       pattern_id, candidate_id, pattern_type, role, scope, status, version, object_id, vector_id,
       content_hash, policy_version, schema_version, created_at, updated_at
     )
     VALUES (?1, ?2, ?3, ?4, ?5, 'active', ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)`
  )
    .bind(patternId, candidateId, patternType, role, scope, version, object.objectId, vectorId, object.contentHash, policyVersion(env), schemaVersion(env), createdAt, createdAt)
    .run();
  await env.MEMORY_DB.prepare(`UPDATE learning_candidates SET status = 'accepted', updated_at = ?1 WHERE candidate_id = ?2`)
    .bind(createdAt, candidateId)
    .run();
  await writeEvent(env, {
    area: "learning",
    eventType: "learning_pattern_accepted",
    source: optionalString(body.created_by, "maip-memory-worker"),
    correlationId: patternId,
    payload: { pattern_id: patternId, candidate_id: candidateId, vector_id: vectorId, vector_upserted: Boolean(vectorMutation), vector_error: vectorError }
  });
  return json({ pattern_id: patternId, object_key: object.objectKey, vector_id: vectorId, vector_mutation: vectorMutation, vector_error: vectorError, created_at: createdAt }, 201);
}

async function listPatternRows(
  env: MaipMemoryEnv,
  input: { role?: string; scope?: string; patternType?: string; patternIds?: string[]; limit: number }
) {
  const clauses = ["p.status = 'active'"];
  const params: string[] = [];
  if (input.role) {
    clauses.push(`p.role = ?${params.length + 1}`);
    params.push(input.role);
  }
  if (input.scope) {
    clauses.push(`p.scope = ?${params.length + 1}`);
    params.push(input.scope);
  }
  if (input.patternType) {
    clauses.push(`p.pattern_type = ?${params.length + 1}`);
    params.push(input.patternType);
  }
  if (input.patternIds?.length) {
    const placeholders = input.patternIds.map((id) => {
      params.push(id);
      return `?${params.length}`;
    });
    clauses.push(`p.pattern_id IN (${placeholders.join(", ")})`);
  }
  return env.MEMORY_DB.prepare(
    `SELECT p.pattern_id, p.candidate_id, p.pattern_type, p.role, p.scope, p.status, p.version,
            p.vector_id, p.content_hash, p.policy_version, p.schema_version, p.created_at, p.updated_at, o.object_key
     FROM accepted_patterns p
     JOIN memory_objects o ON p.object_id = o.object_id
     WHERE ${clauses.join(" AND ")}
     ORDER BY p.updated_at DESC
     LIMIT ?${params.length + 1}`
  )
    .bind(...params, input.limit)
    .all<{ pattern_id: string; object_key: string } & JsonRecord>();
}

async function listPatterns(request: Request, env: MaipMemoryEnv): Promise<Response> {
  const url = new URL(request.url);
  const result = await listPatternRows(env, {
    role: url.searchParams.get("role") || undefined,
    scope: url.searchParams.get("scope") || undefined,
    patternType: url.searchParams.get("pattern_type") || undefined,
    limit: clampLimit(url.searchParams.get("limit"), 20)
  });
  const includeBody = url.searchParams.get("include_body") === "true";
  const patterns = [];
  for (const row of result.results || []) {
    patterns.push({ ...row, body: includeBody ? await readObject(env, row.object_key) : undefined });
  }
  return json({ patterns });
}

async function retrievalQuery(request: Request, env: MaipMemoryEnv): Promise<Response> {
  const body = await readBody(request);
  if (body instanceof Response) {
    return body;
  }
  const role = optionalString(body.role);
  const scope = optionalString(body.scope);
  const patternType = optionalString(body.pattern_type);
  const topK = typeof body.top_k === "number" ? Math.min(Math.max(body.top_k, 1), 20) : 5;
  const correlationId = optionalString(body.correlation_id, crypto.randomUUID());
  let vectorError = "";
  let ids: string[] = [];
  if (Array.isArray(body.vector) && env.PATTERN_INDEX) {
    try {
      const matches = await env.PATTERN_INDEX.query(body.vector as number[], {
        topK,
        returnMetadata: "indexed",
        filter: {
          status: "active",
          ...(role ? { role } : {}),
          ...(scope ? { scope } : {}),
          ...(patternType ? { pattern_type: patternType } : {})
        }
      });
      ids = matches.matches
        .map((match) => (typeof match.metadata === "object" ? match.metadata?.pattern_id : undefined))
        .filter((value): value is string => typeof value === "string");
    } catch (error) {
      vectorError = error instanceof Error ? error.message : "vectorize_query_failed";
    }
  }
  const result = await listPatternRows(env, {
    role: role || undefined,
    scope: scope || undefined,
    patternType: patternType || undefined,
    patternIds: ids.length ? ids : undefined,
    limit: topK
  });
  const retrievalId = crypto.randomUUID();
  const createdAt = nowIso();
  await env.MEMORY_DB.prepare(
    `INSERT INTO retrieval_events (
       retrieval_id, correlation_id, role, scope, query_hash, policy_version, result_count, metadata_json, created_at
     )
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)`
  )
    .bind(
      retrievalId,
      correlationId,
      role,
      scope,
      optionalString(body.query_hash, "not_provided"),
      optionalString(body.policy_version, policyVersion(env)),
      result.results?.length || 0,
      stringify({ vector_error: vectorError, vector_match_ids: ids.length }),
      createdAt
    )
    .run();
  return json({ retrieval_id: retrievalId, patterns: result.results || [], vector_query_used: Boolean(ids.length), vector_error: vectorError });
}

async function createOpsEvent(request: Request, env: MaipMemoryEnv): Promise<Response> {
  const body = await readBody(request);
  if (body instanceof Response) {
    return body;
  }
  const component = body.component;
  const eventType = body.event_type;
  const status = body.status;
  if (!requiredString(component, 128) || !requiredString(eventType, 64) || !requiredString(status, 64)) {
    return json({ error: "component, event_type, and status are required." }, 400);
  }
  if (!ALLOWED_EVENT_TYPES.has(eventType)) {
    return json({ error: "event_type must be allowed." }, 400);
  }
  const opsEventId = crypto.randomUUID();
  const createdAt = nowIso();
  await env.MEMORY_DB.prepare(
    `INSERT INTO ops_events (
       ops_event_id, component, environment, event_type, status, schema_version, metadata_json, created_at
     )
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)`
  )
    .bind(opsEventId, component, optionalString(body.environment, env.APP_ENV), eventType, status, schemaVersion(env), stringify(body.metadata ?? {}), createdAt)
    .run();
  await writeEvent(env, {
    area: "operations",
    eventType,
    source: optionalString(body.source, "ops_api"),
    correlationId: opsEventId,
    payload: { component, status, metadata: body.metadata ?? {} }
  });
  return json({ ops_event_id: opsEventId, created_at: createdAt }, 201);
}

async function listOpsEvents(request: Request, env: MaipMemoryEnv): Promise<Response> {
  const url = new URL(request.url);
  const result = await env.MEMORY_DB.prepare(
    `SELECT ops_event_id, component, environment, event_type, status, schema_version, metadata_json, created_at
     FROM ops_events
     ORDER BY created_at DESC
     LIMIT ?1`
  )
    .bind(clampLimit(url.searchParams.get("limit")))
    .all<{ metadata_json: string } & JsonRecord>();
  return json({
    events: (result.results || []).map((row) => ({ ...row, metadata: parseJson(row.metadata_json), metadata_json: undefined }))
  });
}

function health(env: MaipMemoryEnv): Response {
  return json({
    ok: true,
    service: "maip-memory-worker",
    env: env.APP_ENV,
    schema_version: schemaVersion(env),
    bindings: {
      memory_db: Boolean(env.MEMORY_DB),
      memory_objects: Boolean(env.MEMORY_OBJECTS),
      pattern_index: Boolean(env.PATTERN_INDEX)
    },
    ts: nowIso()
  });
}

async function route(request: Request, env: MaipMemoryEnv): Promise<Response> {
  const path = new URL(request.url).pathname;
  if (request.method === "POST" && path === "/v1/events") return createEvent(request, env);
  if (request.method === "GET" && path === "/v1/events") return listEvents(request, env);
  if (request.method === "POST" && path === "/v1/learning/candidates") return createCandidate(request, env);
  const candidate = path.match(/^\/v1\/learning\/candidates\/([^/]+)$/);
  if (candidate && request.method === "GET") return getCandidate(request, env, candidate[1]);
  const review = path.match(/^\/v1\/learning\/candidates\/([^/]+)\/reviews$/);
  if (review && request.method === "POST") return createReview(request, env, review[1]);
  const accept = path.match(/^\/v1\/patterns\/([^/]+)\/accept$/);
  if (accept && request.method === "POST") return acceptPattern(request, env, accept[1]);
  if (request.method === "GET" && path === "/v1/patterns") return listPatterns(request, env);
  if (request.method === "POST" && path === "/v1/retrieval/query") return retrievalQuery(request, env);
  if (request.method === "POST" && path === "/v1/ops/events") return createOpsEvent(request, env);
  if (request.method === "GET" && path === "/v1/ops/events") return listOpsEvents(request, env);
  return json({ error: "Not found." }, 404);
}

export default {
  async fetch(request, env): Promise<Response> {
    const appEnv = env as MaipMemoryEnv;
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/healthz") {
      return health(appEnv);
    }
    const authFailure = await requireAuth(request, appEnv);
    if (authFailure) {
      return authFailure;
    }
    try {
      return await route(request, appEnv);
    } catch (error) {
      return json({ error: "Internal server error.", error_code: error instanceof Error ? error.message : "unknown_error" }, 500);
    }
  }
} satisfies ExportedHandler<Env>;
