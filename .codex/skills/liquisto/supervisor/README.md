# Supervisor Skill

## Intent

Implement changes that preserve Supervisor as control plane only.

## Guardrails

- Do not move domain fact interpretation into Supervisor.
- Do not add intra-department judge/retry logic to Supervisor.
- Keep department execution ownership in department runtime.

## Done Criteria

- Routing and orchestration changes remain boundary-safe.
- Related contracts/tests are updated consistently.

## Memory Hooks

- Store patterns that reduce control-plane leakage.
- Store anti-patterns when boundary regressions are found.
