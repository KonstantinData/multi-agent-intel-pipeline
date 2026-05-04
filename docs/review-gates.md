# Review Gates

High-impact paths require Code Owner review and at least two approvals before
merge:

- `src/orchestration/**`
- `src/agents/**`
- `src/memory/**`
- `knowledge/**`
- `docs/drawio/**`
- `docs/target_runtime_architecture.md`
- `tests/**`
- `.github/**`
- `requirements*`
- `pyproject.toml`

Branch protection should enable:

- Require a pull request before merging.
- Require review from Code Owners.
- Require at least two approving reviews for high-impact paths.
- Require the `compliance-security-ai` workflow to pass.
- Require branches to be up to date before merging.
- Require status checks: `lint`, `type-check`, `bandit-sast`, `secret-scan`, `dependency-vuln-gate`, `governance-gates`, `actions-hardening-gate`, `script-contract-tests`, `architecture-tests`, `runtime-contract-tests`, `ai-bom-gate`, `sbom-gate`.

Test-layer gates:

- Architecture and contract checks run with `pytest -q tests/architecture` and must not import AG2/autogen, OpenAI SDK, pypdf, reportlab, or PDF exporter runtime modules.
- Query and governance checks run with `pytest -q tests/test_query_consistency.py tests/test_query_migration.py tests/test_scripts_contracts.py`.
- Runtime/integration checks run separately with `pytest -q tests/runtime tests/integration`; optional runtime dependencies may skip only in the runtime job context.

Organizational note: local tests can verify CODEOWNERS structure, but GitHub
team existence and branch-protection enforcement must be configured in the
repository settings.
