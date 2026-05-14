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

## Canonical Security Pipeline Fit

Match validation to the changed surface:
- source changes: `ruff check src scripts tests`, `mypy`, `bandit -q -r src scripts -x tests`
- dependency changes: `uv pip compile requirements.txt --python-version 3.12 --output-file requirements.lock`, then `python scripts/run_pip_audit_with_policy.py`
- secret-sensitive changes: `detect-secrets scan . --all-files` plus `python scripts/validate_secret_scan.py`
- workflow/governance changes: `python scripts/validate_ruleset_config.py`, `python scripts/check_github_actions_hardening.py`, and policy-as-code checks
- release/security metadata changes: regenerate and validate AI-BOM/SBOM with the repository scripts

The authoritative aggregate gate is `.github/workflows/compliance-security-ai.yml`.

## Memory Hooks

- Persist robust hardening patterns and their validation signals.
- Persist anti-patterns that exposed prompt/secret risk.
