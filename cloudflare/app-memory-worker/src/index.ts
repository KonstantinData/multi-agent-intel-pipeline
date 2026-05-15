interface Env {
  APP_ENV: string;
  INGEST_API_TOKEN: string;
  MEMORY_DB: D1Database;
}

type JsonRecord = Record<string, unknown>;

const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8"
};

const MAX_RUN_ID_LENGTH = 128;
const MAX_DEPARTMENT_LENGTH = 64;
const MAX_KIND_LENGTH = 64;

function toJsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: JSON_HEADERS
  });
}

function normalizeBearerToken(authHeader: string | null): string | null {
  if (!authHeader) {
    return null;
  }
  const [scheme, token] = authHeader.split(" ", 2);
  if (scheme !== "Bearer" || !token) {
    return null;
  }
  return token.trim();
}

function validateRequiredString(field: unknown, maxLength: number): field is string {
  return typeof field === "string" && field.length > 0 && field.length <= maxLength;
}

function asObject(value: unknown): JsonRecord | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as JsonRecord;
}

async function requireTokenAuth(request: Request, env: Env): Promise<Response | null> {
  const expectedToken = (env.INGEST_API_TOKEN || "").trim();
  if (!expectedToken) {
    return toJsonResponse(
      {
        error: "Server misconfiguration: missing INGEST_API_TOKEN secret."
      },
      500
    );
  }

  const providedToken = normalizeBearerToken(request.headers.get("authorization"));
  if (!providedToken || providedToken !== expectedToken) {
    return toJsonResponse(
      {
        error: "Unauthorized."
      },
      401
    );
  }

  return null;
}

async function handleIngest(request: Request, env: Env): Promise<Response> {
  let parsed: unknown;
  try {
    parsed = await request.json();
  } catch {
    return toJsonResponse({ error: "Request body must be valid JSON." }, 400);
  }

  const payload = asObject(parsed);
  if (!payload) {
    return toJsonResponse({ error: "Request body must be a JSON object." }, 400);
  }

  const runId = payload.run_id;
  const department = payload.department;
  const kind = payload.kind;
  const source = typeof payload.source === "string" && payload.source.length <= 64 ? payload.source : "app";
  const eventPayload = payload.payload ?? {};

  if (!validateRequiredString(runId, MAX_RUN_ID_LENGTH)) {
    return toJsonResponse({ error: "run_id must be a non-empty string <= 128 chars." }, 400);
  }
  if (!validateRequiredString(department, MAX_DEPARTMENT_LENGTH)) {
    return toJsonResponse({ error: "department must be a non-empty string <= 64 chars." }, 400);
  }
  if (!validateRequiredString(kind, MAX_KIND_LENGTH)) {
    return toJsonResponse({ error: "kind must be a non-empty string <= 64 chars." }, 400);
  }

  const eventId = crypto.randomUUID();
  const createdAt = new Date().toISOString();
  const payloadJson = JSON.stringify(eventPayload);

  await env.MEMORY_DB.prepare(
    `INSERT INTO memory_events (event_id, run_id, department, kind, source, payload_json, created_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)`
  )
    .bind(eventId, runId, department, kind, source, payloadJson, createdAt)
    .run();

  return toJsonResponse(
    {
      event_id: eventId,
      created_at: createdAt
    },
    201
  );
}

async function handleList(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const runId = url.searchParams.get("run_id");
  if (!runId || runId.length > MAX_RUN_ID_LENGTH) {
    return toJsonResponse({ error: "run_id query parameter is required (<= 128 chars)." }, 400);
  }

  const rawLimit = Number.parseInt(url.searchParams.get("limit") ?? "50", 10);
  const limit = Number.isFinite(rawLimit) ? Math.min(Math.max(rawLimit, 1), 200) : 50;

  const result = await env.MEMORY_DB.prepare(
    `SELECT event_id, run_id, department, kind, source, payload_json, created_at
     FROM memory_events
     WHERE run_id = ?1
     ORDER BY created_at DESC
     LIMIT ?2`
  )
    .bind(runId, limit)
    .all<{
      event_id: string;
      run_id: string;
      department: string;
      kind: string;
      source: string;
      payload_json: string;
      created_at: string;
    }>();

  const events = (result.results ?? []).map((row) => ({
    event_id: row.event_id,
    run_id: row.run_id,
    department: row.department,
    kind: row.kind,
    source: row.source,
    payload: safeParseJson(row.payload_json),
    created_at: row.created_at
  }));

  return toJsonResponse({ events });
}

function safeParseJson(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function handleHealth(env: Env): Response {
  return toJsonResponse({
    ok: true,
    service: "liquisto-app-memory-worker",
    env: env.APP_ENV,
    ts: new Date().toISOString()
  });
}

export default {
  async fetch(request, env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/healthz") {
      return handleHealth(env);
    }

    const authFailure = await requireTokenAuth(request, env);
    if (authFailure) {
      return authFailure;
    }

    if (request.method === "POST" && url.pathname === "/v1/memory/events") {
      return handleIngest(request, env);
    }

    if (request.method === "GET" && url.pathname === "/v1/memory/events") {
      return handleList(request, env);
    }

    return toJsonResponse(
      {
        error: "Not found."
      },
      404
    );
  }
} satisfies ExportedHandler<Env>;
