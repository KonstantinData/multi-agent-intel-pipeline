# Tool Allowlist Policy

## Defaults

- Prefer non-destructive file operations.
- Prefer targeted reads/writes over broad mutations.
- Use destructive operations only when explicitly requested and validated.

## Git safeguards

- Do not rewrite history unless explicitly requested.
- Never force-reset unrequested changes.
- Prefer branch-based workflow for publish actions.

## Testing safeguards

- Match test scope to risk level.
- Require architecture checks for contract/control-plane changes.
