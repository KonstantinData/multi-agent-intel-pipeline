# Follow-up Skill

## Intent

Preserve run-based follow-up behavior using persisted artifacts first.

## Guardrails

- Follow evidence priority: run artifacts, then pipeline data, then package fallback.
- Trigger additional research only for unresolved evidence gaps.

## Done Criteria

- Follow-up answers are grounded in stored run state.
- New behavior does not degrade run rehydration or routing.

## Memory Hooks

- Persist patterns that reduced redundant re-research.
- Persist anti-patterns where fallback order was violated.
