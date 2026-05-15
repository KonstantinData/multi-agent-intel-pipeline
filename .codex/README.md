# .codex Level-5 Operating Layer

This `.codex` directory is the assistant operating system for this repository.
It is process-oriented and does not replace code or architecture as source of truth.

## Objectives

- Improve execution quality and consistency across tasks.
- Learn from outcomes while storing only process patterns.
- Reduce token usage with targeted retrieval and prompt budgets.
- Enforce policy boundaries for security, data handling, and tools.

## Level-5 Components

- `config/`: runtime profiles and routing strategy.
- `tasks/`: executable task definitions with triggers, commands, and acceptance checks.
- `skills/`: explicit playbooks for recurring task classes.
- `memory/`: procedural memory and anti-pattern history.
- `eval/`: replay, scorecards, and regression baselines.
- `policies/`: guardrails for data, secrets, tools, and budgets.
- `scripts/`: executable app-level helpers (for example local gate runners).
- `automations/`: scheduled consolidation and maintenance jobs.
- `telemetry/`: metrics for quality, failures, and token efficiency.

## Operational Rule

When conflicts appear between this layer and repository architecture docs/code, prioritize:
1. Executable code
2. Repository architecture docs
3. Repository AGENTS instructions
4. This `.codex` layer

## Trusted Project Loading

Project-scoped `.codex` guidance is effective only in trusted Codex sessions.
If the repository is opened in untrusted mode, treat this layer as documentation-only
until the active session confirms which project rules, hooks, agents, or config layers
are actually loaded.

Security and runtime decisions must not rely on `.codex` enforcement unless the
session verifies that the project is trusted and the relevant `.codex` mechanism is active.
