# Secret Policy

- Never persist credentials, tokens, keys, or secret-like payloads.
- Never copy secrets into telemetry, eval traces, or memory entries.
- Redact uncertain values as `[REDACTED]`.
- Treat prompt payloads as sensitive by default.

Validation rule:
- if value matches secret pattern, block persistence and record only incident metadata.
