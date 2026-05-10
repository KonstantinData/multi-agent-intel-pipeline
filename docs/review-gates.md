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
- Require the `pipeline-status` job from the `compliance-security-ai` workflow
  to pass.
- Require `codeql / analyze` and `dependency-review` to pass.
- Require branches to be up to date before merging.
- Require signed commits and block force-pushes/deletions.
- Keep the individual gate jobs visible for diagnosis: `lint`, `type-check`,
  `bandit-sast`, `dependency-lock-gate`, `dependency-vuln-gate`,
  `secret-scan`, `governance-gates`, `actions-hardening-gate`,
  `script-contract-tests`, `architecture-tests`,
  `runtime-contract-tests`, `ai-bom-gate`, `sbom-gate`, and
  `provenance-gate`.

Ruleset desired state:

- `.github/rulesets/main-protection.json` is the versioned desired state for
  the default branch.
- `scripts/validate_ruleset_config.py` checks required reviews, Code Owner
  review, strict status checks, signed commits, no force-pushes, no deletion,
  and required status checks.
- A GitHub repository admin must import or mirror this ruleset in repository
  settings; CI validates the policy artifact, not GitHub's hosted settings.

Workflow-hardening baseline:

- All external GitHub Actions references must be pinned to full-length commit
  SHAs.
- Workflows must define least-privilege permissions, timeouts, and concurrency.
- CodeQL must run unconditionally; opt-in switches such as `ENABLE_CODEQL` are
  blocked.
- `pull_request_target`, write-all permissions, empty permissions, and inline
  placeholder shell blocks are blocked by CI.
- Docker base images and Docker-based scanner images must be pinned by digest.
- Runtime installs and dependency audit must use `requirements.lock`;
  `requirements.txt` is only the direct dependency constraint input.
- SBOM artifacts are generated from the OCI image with Syft and validated as
  CycloneDX JSON.
- Release tags build and push `ghcr.io/<owner>/<repo>`, then create and verify
  SLSA provenance and SBOM attestations bound to the image digest.
- AI-BOM artifacts are generated and validated in CI; non-PR pushes also
  produce an attested compliance manifest.

Secret protection baseline:

- CI runs `detect-secrets` on the current tree and Gitleaks against repository
  history.
- GitHub Secret Scanning and Push Protection are mandatory repository settings.
- Secret findings require key rotation, history/log cleanup, and a clean rerun
  of both scanners.

Test-layer gates:

- Architecture and contract checks run with `pytest -q tests/architecture` and must not import AG2/autogen, OpenAI SDK, pypdf, reportlab, or PDF exporter runtime modules.
- Query and governance checks run with `pytest -q tests/test_query_consistency.py tests/test_query_migration.py tests/test_scripts_contracts.py`.
- Runtime/integration checks run separately with `pytest -q tests/runtime tests/integration`; optional runtime dependencies may skip only in the runtime job context.

Organizational note: local tests can verify CODEOWNERS and ruleset structure,
but GitHub team existence, branch-protection enforcement, Secret Scanning, and
Push Protection must be configured in the repository settings.
