# Security Skill

## Intent

Apply secure defaults for prompts, secrets, and policy-sensitive runtime changes.

## Guardrails

- Never persist secrets in memory or telemetry artifacts.
- Preserve secret guard behavior and related protections.
- Prefer least-privilege tool usage.

## Done Criteria

- Security-sensitive changes include targeted checks/tests.
- No policy violations in changed files.

## Memory Hooks

- Persist robust hardening patterns and their validation signals.
- Persist anti-patterns that exposed prompt/secret risk.
