# Testing Skill

## Intent

Keep architecture tests fast and dependency-light while preserving runtime integration coverage where required.

## Guardrails

- Avoid importing runtime-heavy modules in architecture tests unless necessary.
- Prefer extracting dependency-light helpers and contracts.

## Done Criteria

- Relevant tests added/updated at the correct layer.
- Risky changes include runtime/integration validation where needed.

## Memory Hooks

- Persist patterns that reduced flaky tests and runtime-coupled architecture tests.
- Persist anti-patterns that slowed feedback loops unnecessarily.
