# Review Gates

High-impact paths require Code Owner review and at least two approvals before
merge:

- `src/orchestration/**`
- `src/agents/**`
- `src/memory/**`
- `knowledge/**`
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

Organizational note: local tests can verify CODEOWNERS structure, but GitHub
team existence and branch-protection enforcement must be configured in the
repository settings.

