# Security Policy Enforcement Checklist

Purpose: make secret-handling and prompt-safety rules enforceable in every
chat/session by relying on repository controls, not assistant memory.

## 1. Secret Source Policy

- Runtime secrets are injected from deployment/CI secrets only.
- `.env` files are not a valid secret source for `OPENAI_API_KEY`.
- OS keyring is allowed for local development fallback.

Code references:
- `src/config/settings.py` (`resolve_openai_api_key`)
- `tests/smoke/test_preflight.py` (`.env` API-key fallback blocked)

## 2. Repository Guard: No `.env*` Tracked

- `.env` and `.envrc` are git-ignored.
- CI fails if any `.env*` file is tracked.

Code references:
- `.gitignore`
- `scripts/check_no_dotenv_files.py`
- `.github/workflows/compliance-security-ai.yml`

## 3. CI Secret Gates

- `detect-secrets` scans the working tree.
- Gitleaks scans repository history.
- CI fails on any non-excluded finding.

Code references:
- `.github/workflows/compliance-security-ai.yml`
- `scripts/validate_secret_scan.py`
- `.gitleaks.toml`

## 4. Prompt Secret Guardrails

- LLM requests are checked before API calls.
- Suspected secrets in prompt payloads block the request.
- Error messages must not contain the secret value itself.

Code references:
- `src/security/secret_guard.py`
- `src/agents/worker.py`
- `src/agents/report_writer.py`
- `src/research/extract.py`
- `src/exporters/pdf_report.py`
- `src/research/search.py`

## 5. Logging and Artifact Hygiene

- Do not log API keys, tokens, auth headers, or environment values.
- Run artifacts and reports must not contain secrets.
- Runtime snapshots expose only non-secret metadata.

Code references:
- `docs/Secrets-Management.md`
- `docs/en/privacy/audit-log-minimization-policy.md`
- `src/storage/contracts.py` (`RuntimeStorageConfig.snapshot`)

## 6. Operational Checklist Before Merge

- Run architecture tests and script contract tests.
- Verify no `.env*` tracked files exist.
- Verify secret scans are green in CI.
- Verify prompt guard tests are green.
