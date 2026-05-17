# Runtime Reference Layer

This directory contains Codex runtime references for guarded runtime-agent work.
It complements executable code and architecture contracts; it is not a second
architecture source of truth.

## Source Of Truth

1. Executable code
2. `src/orchestration/contracts.py`
3. `docs/drawio/target_runtime_architecture.md`
4. `README.md`
5. `AGENTS.md`
6. `.codex/runtime/*`

## Runtime Memory Target

- Provider: Cloudflare
- Worker service: `maip-memory-worker`
- Worker environments: `dev`, `staging`, `prod`
- D1 databases: `maip-memory-dev`, `maip-memory-staging`, `maip-memory-prod`
- D1 binding: `MEMORY_DB`

Remote Cloudflare actions require explicit approval and credentials:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- Worker secret `INGEST_API_TOKEN`

Without those, runtime work remains local configuration and documentation only.

## Autonomous Runtime Contract

The intended runtime-agent loop is:

`PLAN -> EDIT -> TEST -> EVALUATE -> RETRY -> FINISH_OR_ESCALATE`

The loop is controlled autonomy. It must keep the Supervisor as the only control
plane, preserve department autonomy, and respect typed runtime artifacts.

## Risk Classification

- `low`: docs, `.codex/runtime/*` references, non-executed JSON additions.
- `medium`: GitHub Actions, Cloudflare env/scripts, `.gitignore`, executable config keys.
- `high`: Supervisor logic, speaker selector behavior, artifact schemas, memory persistence, auth, secrets, deployments, production runtime behavior.

## Gates

Run gates in this order when applicable:

1. Static config validation
2. Architecture and contract tests
3. Runtime or integration tests for affected paths

Do not run deploys, remote D1 creation, migrations, or secret mutation without
explicit remote-operation approval.

## Retry And Escalation

- Max 3 retries per failed phase.
- Each retry must state a new hypothesis.
- Escalate after 3 failed retries in one phase.
- Escalate after 2 consecutive test failures with no meaningful diff.
- Escalate on secret-policy uncertainty or architecture-contract conflict.
- Escalate when required credentials are missing for a remote operation.
- Escalate if the runtime exceeds 45 minutes without passing required gates.

## Confidence Scoring

- Start at `0.5`.
- Add `0.2` if all selected tests pass.
- Add `0.1` if changed config files validate.
- Add `0.1` if changes are low or medium risk.
- Add `0.1` if no unresolved architecture conflicts remain.
- Subtract `0.2` for each failed required gate.
- Do not subtract for blocked validation if the blocker is external, documented, and outside allowed permissions.
- Subtract `0.2` if validation is skipped without a documented blocker.
- Subtract `0.2` if validation is blocked by a problem caused by the agent's own changes.
- Clamp final score to `0.0..1.0`.

Escalate if confidence is below `0.6`, or below `0.75` for high-risk changes.

## Memory Rules

Allowed event classes are defined in `runtime_memory_reference.json`.
Codex operating-layer learning events are defined in `learning_event_schema.json`
and recorded through `.codex/scripts/record_learning_event.py`.

Never store secrets, raw tokens, passwords, private keys, customer facts as
process memory, or run-specific conclusions as reusable long-term truth.

## Local Learning Event Recorder

Hooks and PR lifecycle tooling write append-only events locally before optional
remote sync:

```powershell
python .codex/scripts/record_learning_event.py record `
  --event-type compliance_check_completed `
  --area learning `
  --source manual_smoke `
  --correlation-id manual-smoke `
  --payload-json '{"status":"manual"}'
```

Requirements:

- Remote sync is optional and requires `MAIP_MEMORY_BASE_URL` and `MAIP_MEMORY_INGEST_API_TOKEN`.
- If remote sync is unavailable, events remain in `artifacts/codex-learning/outbox/*.jsonl`.
