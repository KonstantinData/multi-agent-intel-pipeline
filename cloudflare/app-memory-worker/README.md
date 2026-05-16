# App Memory Worker (Cloudflare)

This worker is the app-level memory service for Liquisto agents.
It is intentionally isolated from the runtime-level orchestration running on Hetzner.

## Scope boundary

- Cloudflare Worker: app-level memory API and persistence.
- Hetzner runtime: orchestration, department execution, and report generation.
- No runtime deployment should call `wrangler deploy` from repository root.

## Endpoints

- `GET /healthz`
- `POST /v1/memory/events` (Bearer auth required)
- `GET /v1/memory/events?run_id=<id>&limit=<1..200>` (Bearer auth required)

## 1) Install dependencies

```bash
npm install
```

## 2) Create D1 databases

Use one database per environment.

```bash
npx wrangler d1 create liquisto-app-memory-dev --location weur
npx wrangler d1 create liquisto-app-memory-staging --location weur
npx wrangler d1 create liquisto-app-memory-prod --location weur
```

Copy the generated `database_id` values into `wrangler.jsonc`:

- `env.dev.d1_databases[0].database_id`
- `env.staging.d1_databases[0].database_id`
- `env.production.d1_databases[0].database_id`

## 3) Configure secrets

Local development:

```bash
cp .dev.vars.example .dev.vars
```

Production and staging:

```bash
npx wrangler secret put INGEST_API_TOKEN --env staging
npx wrangler secret put INGEST_API_TOKEN --env production
```

## 4) Apply migrations

```bash
npm run d1:migrate:local
npm run d1:migrate:staging
npm run d1:migrate:prod
```

## 5) Validate and deploy

```bash
npm run check
npm run deploy:staging
npm run deploy:prod
```

## GitHub Actions deployment

Workflow: `.github/workflows/deploy-app-memory-worker.yml`

Required repository secrets:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `APP_MEMORY_DB_ID_DEV`
- `APP_MEMORY_DB_ID_STAGING`
- `APP_MEMORY_DB_ID_PRODUCTION`
- `APP_MEMORY_INGEST_API_TOKEN_DEV`
- `APP_MEMORY_INGEST_API_TOKEN_STAGING`
- `APP_MEMORY_INGEST_API_TOKEN_PRODUCTION`

Run the workflow manually and select `dev`, `staging`, or `production`.
The workflow applies migrations, updates `INGEST_API_TOKEN`, and deploys
`liquisto-app-memory-worker` for the selected environment.

## Operational defaults

- `upload_source_maps: true`
- `observability.enabled: true`
- log sampling: `1`
- trace sampling: `0.1`

Adjust sampling rates based on production traffic and cost profile.
