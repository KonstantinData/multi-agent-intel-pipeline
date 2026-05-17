# MAIP Memory Worker

New Cloudflare app-memory service for the multi-agent-intel-pipeline project.

This worker replaces the old app-memory setup for new deployments. It uses only
new MAIP resource names:

- D1: `maip-memory-dev`, `maip-memory-staging`, `maip-memory-prod`
- R2: `maip-memory-dev-objects`, `maip-memory-staging-objects`,
  `maip-memory-prod-objects`
- Vectorize: `maip-memory-dev-patterns`, `maip-memory-staging-patterns`,
  `maip-memory-prod-patterns`
- Workers: `maip-memory-worker-dev`, `maip-memory-worker-staging`,
  `maip-memory-worker-prod`

## Scope

Cloudflare stores app-memory and runtime-improvement memory only:

- operations events
- scrubbed learning candidates
- review decisions
- accepted patterns
- retrieval telemetry

Hetzner remains the runtime artifact store. Raw runtime artifacts, evidence,
reports, company facts, domains, URLs, people, and customer-specific conclusions
must not be stored in this worker.

## Storage roles

- D1: metadata, lifecycle, audit, reviews, accepted-pattern registry
- R2: scrubbed candidate and accepted-pattern JSON objects
- Vectorize: rebuildable semantic projection over accepted patterns

D1 is the source of truth. Vectorize can be rebuilt from D1 and R2.

## Local development

Do not commit local secrets. Use temporary CLI injection:

```powershell
npm install
npm run d1:migrate:local
npm run dev -- --var INGEST_API_TOKEN:local-memory-smoke-token
```

## Endpoints

- `GET /healthz`
- `POST /v1/events`
- `GET /v1/events?area=&event_type=&correlation_id=&limit=`
- `POST /v1/learning/candidates`
- `GET /v1/learning/candidates/<candidate_id>?include_body=true`
- `POST /v1/learning/candidates/<candidate_id>/reviews`
- `POST /v1/patterns/<candidate_id>/accept`
- `GET /v1/patterns?role=&scope=&pattern_type=&include_body=&limit=`
- `POST /v1/retrieval/query`
- `POST /v1/ops/events`
- `GET /v1/ops/events?limit=`

All endpoints except `/healthz` require:

```text
Authorization: Bearer <INGEST_API_TOKEN>
```

## GitHub deployment

Workflow: `.github/workflows/deploy-maip-memory-worker.yml`

Required GitHub secrets:

- `MAIS_MASTER_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `MAIP_MEMORY_INGEST_API_TOKEN`

Optional:

- `CLOUDFLARE_ZONE_ID` for future custom-domain routing.

The workflow creates missing D1 databases, R2 buckets, and Vectorize indexes,
then applies D1 migrations, sets the worker secret, and deploys the selected
environment.
