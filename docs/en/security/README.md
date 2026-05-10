# Security Hub

> Language: `en`
> Path: `security/README.md`

This document is the single entry point for all security-relevant areas of the
Liquisto Department Runtime. It does not replace the linked documents — it maps
each security area to its authoritative source so that reviewers, contributors,
and operators can navigate the architecture without searching across directories.

Read this file first. Then follow only the links relevant to your task.

---

## How to use this document

| You need to... | Go to |
| --- | --- |
| Understand the overall risk landscape | [Threat Model](#1-threat-model) |
| Know what data may appear where | [Data Classification & Privacy](#2-data-classification--privacy) |
| Understand how agents are isolated from each other | [Agent Security & RBAC](#3-agent-security--rbac) |
| Look up how API keys and secrets are handled | [Secret & Credential Management](#4-secret--credential-management) |
| Understand what CI/CD checks run and why | [CI/CD Security Gates](#5-cicd-security-gates) |
| Know the branch protection and review rules | [Branch Protection & Governance](#6-branch-protection--governance) |
| Understand how audit logs are written and constrained | [Audit Logging](#7-audit-logging) |
| Know the EU AI Act classification for this system | [Regulatory Classification](#8-regulatory-classification) |
| Find all security-relevant source code | [Runtime Hardening in Code](#9-runtime-hardening-in-code) |
| Understand what is not yet fully mitigated | [Residual Risks](#10-residual-risks) |
| Know when a security review is mandatory | [Security Review Triggers](#11-security-review-triggers) |
| Report a vulnerability | [SECURITY.md](../../../SECURITY.md) |

---

## 1. Threat Model

**File:** [docs/en/security/threat-model.md](threat-model.md)

The threat model is the authoritative record of what assets exist in the system,
where the trust boundaries are, and which controls defend each threat. It is the
document to read before any architectural change and the reference used when
evaluating whether a new feature increases attack surface.

Key sections:

- **System assets** — the seven runtime assets (API keys, run artifacts,
  long-term memory, KB YAML, department artifacts, PDFs, CI/CD workflows) and
  why each one matters.
- **Trust boundaries** — the seven trust boundary crossings (UI intake,
  public web, external model APIs, department chats to artifacts, run brain to
  long-term memory, artifacts to reports, repo to CI/CD) with the risk each
  crossing introduces.
- **Main threats and controls** — a table mapping each concrete threat to its
  impact and the specific controls in place. Covers prompt injection, secret
  leakage, memory privacy, fabricated findings, contact over-collection,
  concurrent mutation, dependency vulnerabilities, malicious workflow changes,
  release artifact tampering, and report over-disclosure.
- **Existing security gates** — a complete list of the CI/CD controls
  currently enforced (SAST, dependency audit, secret scanning, CodeQL, AI-BOM,
  SBOM, provenance attestation, and more).
- **Runtime hardening** — six runtime hardening measures implemented in code
  (centralized timeouts, phase budget tracking, Pydantic validation, atomic
  writes, file locking, fail-closed search).

---

## 2. Data Classification & Privacy

Three policies govern how data is classified and where it may appear. They are
separate documents because they cover distinct scopes: what data is, where data
goes externally, and how much of it survives into logs.

### 2a. Data Classification Policy

**File:** [docs/en/privacy/data-classification-policy.md](../privacy/data-classification-policy.md)

Defines five classification levels (Public, Business Confidential, Personal
Business Contact Data, Secret, Process Metadata) and maps each runtime area —
intake, search results, department artifacts, contact intelligence, run reports,
long-term memory, CI artifacts — to its classification and allowed handling.

The most important rule: **Secrets must never appear in prompts, run artifacts,
exported PDFs, logs, AI-BOM/SBOM, or long-term memory.** Only process metadata
(scrubbed structural patterns) may enter long-term memory.

### 2b. Model Privacy Policy

**File:** [docs/en/privacy/model-privacy-policy.md](../privacy/model-privacy-policy.md)

Governs what data is sent to external model and search services (OpenAI,
`web_search_preview`, structured extraction, synthesis, report writing,
translation). Defines data minimization rules for prompts: include only the
current task objective, relevant supervisor brief fields, necessary source
snippets, required schemas, and relevant gaps. Explicitly prohibits sending API
keys, full raw pages, unrelated artifacts, unapproved customer-private data, or
hidden chain-of-thought requests to any model.

Also covers: query privacy rules (no secrets in public search queries),
memory privacy (long-term memory stores only scrubbed process patterns, not
run-specific facts), output handling (LLM output is decision support, not
ground truth), and incident triggers.

### 2c. Audit Log Minimization Policy

**File:** [docs/en/privacy/audit-log-minimization-policy.md](../privacy/audit-log-minimization-policy.md)

Defines precisely what the runtime may persist for auditability and what it must
not store. Allowed data includes: intake fields, normalized supervisor brief,
department packages, task/review/decision artifacts, evidence packet source URLs,
answer matrix and readiness state, usage counters, and follow-up history.
Disallowed data includes: API keys, auth headers, full raw HTML/PDF dumps,
unapproved customer-private documents, special-category personal data, personal
contact data beyond business-contact context, company-specific facts in
long-term memory, and hidden model reasoning.

Also defines checkpoint phases, operational log fields, and a review checklist
to run before adding any new field to run exports or logs.

---

## 3. Agent Security & RBAC

Two documents cover agent-level security. The permission matrix defines who can
do what. The agent-to-agent security document defines how that is enforced at
the communication boundary.

### 3a. Agent Permission Matrix

**File:** [docs/en/agents/agent-permission-matrix.md](../agents/agent-permission-matrix.md)

The runtime RBAC definition. Specifies the control scope, read access, write
access, and tool grants for every role: Supervisor, four domain department
containers (Company, Market, Buyer, Contact), Synthesis, and ReportWriter.
Within each department, the five AG2 agent roles (Lead, Researcher, Critic,
Judge, CodingSpecialist) are further scoped: only researchers receive search and
fetch tools, only coding specialists receive query refinement, critics and judges
receive no external research tools.

The matrix also lists explicit non-permissions — what each role is prohibited
from doing — and the memory access boundaries (run brain vs. long-term process
memory).

**Note:** The matrix is a governance view. The executable source remains
authoritative and is located in:

- [`src/orchestration/tool_policy.py`](../../../src/orchestration/tool_policy.py)
- [`src/orchestration/department_runtime.py`](../../../src/orchestration/department_runtime.py)
- [`src/orchestration/speaker_selector.py`](../../../src/orchestration/speaker_selector.py)

### 3b. Agent-to-Agent Security

**File:** [docs/en/security/agent-to-agent-security.md](agent-to-agent-security.md)

Defines the allowed communication paths between agents, what artifact each path
must produce, and what the security requirement at each boundary is. Covers:
Supervisor-to-department contracts, Researcher-to-Lead task artifacts, Lead-to-
Critic review artifacts, Lead-to-Judge escalation, Judge decisions, Coding
Specialist scope restrictions, and ReportWriter authority boundaries.

Also defines: prompt injection controls (role prompts take authority over source
content; fetched content is summarized into typed evidence artifacts, not treated
as instructions), speaker selector guardrails (routes turns for safety and
liveness only — does not encode hidden workflow logic), tool-call security rules,
artifact integrity requirements, failure handling behavior, and a review
checklist to complete before adding any new agent-to-agent communication path.

---

## 4. Secret & Credential Management

**File:** [docs/Secrets-Management.md](../../Secrets-Management.md)

The binding operational policy for all API keys and runtime secrets. Defines a
strict two-source priority chain for `OPENAI_API_KEY`:

1. **Process environment variable or deployment secret** — the preferred source
   for CI and deployment. Set via `$env:OPENAI_API_KEY`. Never written to
   repository files, build artifacts, or logs.
2. **OS keyring via `python-keyring`** — the recommended source for local
   development. Set via `python -m keyring set liquisto-department-runtime OPENAI_API_KEY`.

**A plaintext `.env` file is not a permitted source for API keys**, regardless
of any legacy environment variable overrides.

The policy covers: preflight output rules (only a scrubbed `configured` status
may appear — never the key value, source, or keyring account), logging rules
(only boolean/scrubbed status like `configured` or `api_key_present: true` is
allowed in logs), commit and CI protection (`.env` is `.gitignore`-listed;
`detect-secrets` and Gitleaks CI gates block accidental commits), and a
remediation checklist for when a secret has been accidentally logged or
committed.

**Canonical implementation:**

- [`src/config/settings.py`](../../../src/config/settings.py) — `resolve_openai_api_key()`, `get_llm_config()`
- [`preflight.py`](../../../preflight.py) — startup credential gate
- [`tests/smoke/test_preflight.py`](../../../tests/smoke/test_preflight.py) — smoke tests covering all resolution scenarios

---

## 5. CI/CD Security Gates

**File:** [.github/workflows/compliance-security-ai.yml](../../../.github/workflows/compliance-security-ai.yml)

The main security pipeline. Every push and pull request runs 21 sequential gates.
No gate is optional. All gates must pass before the `pipeline-status` aggregator
job succeeds, and `pipeline-status` is a required status check on the main branch.

| Gate | Tool | What it checks |
| --- | --- | --- |
| `lint` | Ruff | Code style and import hygiene on `src`, `scripts`, `tests` |
| `type-check` | MyPy (strict) | Type correctness across `src`, `scripts`, `tests` |
| `bandit-sast` | Bandit | Python security issues in `src` and `scripts` (excludes `tests`) |
| `dependency-lock-gate` | uv | `requirements.txt` to `requirements.lock` drift — fails if lock is stale |
| `dependency-vuln-gate` | pip-audit | Known CVEs in `requirements.lock`; exceptions require entries in `policies/license/dependency-risk-exceptions.json` with an expiry date |
| `secret-scan` | detect-secrets + Gitleaks | Hardcoded secrets in working tree (detect-secrets) and full git history (Gitleaks); validated by `scripts/validate_secret_scan.py` |
| `governance-gates` | custom scripts | Repository directory structure and main branch ruleset desired-state validation |
| `policy-as-code-gate` | Conftest + OPA/Rego | Actions-BOM generation and validation; Rego unit tests; workflow supply chain policy enforcement |
| `scorecard-policy-gate` | custom scripts | OpenSSF scorecard-adjacent controls validation |
| `actions-hardening-gate` | custom scripts | GitHub Actions hardening baseline (pinned actions, limited permissions) |
| `dependency-policy-gate` | custom scripts | Dependency license and registry policy against allowlist in `.github/dependency-review-config.yml` |
| `dependency-diff-gate` | custom scripts | Tracks dependency changes introduced by a PR |
| `vuln-scan-gate` | Trivy | Filesystem and Dockerfile misconfiguration scans |
| `script-contract-tests` | pytest | Contract validation tests for scripts |
| `architecture-tests` | pytest | Architecture and contract tests for `src` |
| `runtime-contract-tests` | pytest | Readiness, golden, query, and smoke tests |
| `integration-tests` | pytest | Full integration tests (manual trigger only via `workflow_dispatch`) |
| `ai-bom-gate` | custom scripts | AI-BOM generation and CycloneDX schema validation |
| `sbom-gate` | Syft + CycloneDX | SBOM generation and CycloneDX schema validation |
| `provenance-gate` | custom scripts | Compliance manifest attestation with SHA256 checksums (non-PR runs only) |
| `pipeline-status` | — | Aggregates all gate results; required status check |

**Additional security workflows:**

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| [codeql.yml](../../../.github/workflows/codeql.yml) | Push, PR, weekly Monday 03:23 | Mandatory CodeQL semantic analysis on Python |
| [dependency-review.yml](../../../.github/workflows/dependency-review.yml) | PR | GitHub Dependency Review — fails on moderate+ severity CVEs and unlicensed packages |
| [scorecard.yml](../../../.github/workflows/scorecard.yml) | Weekly Monday 04:30 | OpenSSF Scorecard; results uploaded to GitHub Security tab as SARIF |
| [release-attestation.yml](../../../.github/workflows/release-attestation.yml) | Release | Binds SLSA Build L2 provenance and CycloneDX SBOM to GHCR image digest |
| [deploy.yml](../../../.github/workflows/deploy.yml) | After Release Attestation succeeds | Deploys to Hetzner via SSH; only triggers on `conclusion == 'success'`; uses digest-pinned SSH action and CI secrets (`HETZNER_HOST`, `HETZNER_USER`, `HETZNER_SSH_KEY`) |

**Local pre-commit hooks** (`pip install pre-commit && pre-commit install`) run
Ruff and Bandit on every `git commit` with the same scope as CI, catching issues
before they reach the pipeline.

---

## 6. Branch Protection & Governance

**File:** [.github/rulesets/main-protection.json](../../../.github/rulesets/main-protection.json)

Defines the GitHub Ruleset applied to the `main` branch. Key rules:

- **Deletion and non-fast-forward protection** — the main branch cannot be
  deleted or force-pushed.
- **Required signatures** — all commits to main must be signed.
- **Pull request requirements:**
  - 2 approving reviews required.
  - Code owner review (CODEOWNERS) required.
  - Stale reviews are dismissed when new commits are pushed.
  - The last push must be approved by someone other than its author.
  - All review threads must be resolved before merge.
  - Allowed merge methods: merge commit and squash only (rebase is disabled).
- **Required status checks** (all must pass; no dismissal allowed):
  - `pipeline-status` (aggregates all 21 compliance-security-ai gates)
  - `codeql / analyze`
  - `dependency-review`
  - `compliance-security-ai / policy-as-code-gate`
  - `compliance-security-ai / scorecard-policy-gate`

**OPA/Rego supply chain policy** enforced by the `policy-as-code-gate`:

- Denies `pull_request_target` triggers.
- Denies `write-all` or empty permissions blocks.
- Denies unexpected write permissions (only `security-events`, `id-token`,
  `attestations`, and `artifact-metadata` are permitted in release jobs).
- Requires all external actions to be pinned to a full commit SHA.
- Requires all Docker scanner images to be digest-pinned.
- Denies any attempt to make the CodeQL gate optional.
- Denies governance documents with placeholder markers (`TODO`,
  `REVIEW_REQUIRED`, `TBD`).

Policy file: [`policies/rego/ci_supply_chain.rego`](../../../policies/rego/ci_supply_chain.rego)
Unit tests: [`policies/rego/ci_supply_chain_test.rego`](../../../policies/rego/ci_supply_chain_test.rego)

---

## 7. Audit Logging

**File:** [docs/en/audit/logging-schema.md](../audit/logging-schema.md)

Defines the run directory structure and the schema of every file written by the
runtime during a run. Each run produces artifacts under
`artifacts/runs/<run_id>/`:

| File | Contents |
| --- | --- |
| `run_meta.json` | Run identification, timing, usage totals |
| `run_context.json` | Normalized supervisor brief, department packages, answer matrix, readiness state |
| `pipeline_data.json` | Evidence packets, source URLs, final pipeline state |
| `chat_history.json` | AG2 conversation transcript |
| `memory_snapshot.json` | Exported short-term memory state |
| `checkpoints/` | Crash-recovery snapshots at defined phases |
| `follow_up_history.json` | Historical follow-up questions and answers |
| `reports/` | Final report package and exported PDFs |

The minimization rules that govern what may be written to these files are defined
in the [Audit Log Minimization Policy](#2c-audit-log-minimization-policy) above.

---

## 8. Regulatory Classification

**File:** [docs/en/ai-act/risk-classification.md](../ai-act/risk-classification.md)

Engineering-level EU AI Act classification for the Liquisto Department Runtime.
Not a legal opinion — a repository-level record to guide controls and release
gates.

**Current classification:** The system is not a prohibited AI practice, is not
classified as high-risk for its intended use (pre-meeting commercial briefings
with human review), and is not a GPAI model provider. Limited transparency risk
applies because LLM-mediated summaries are presented to users.

**Reclassification is mandatory** if the system is changed to automate decisions
in employment, credit, insurance, education, law enforcement, biometric, medical,
or public-service eligibility contexts; to infer sensitive personal attributes;
to perform employee monitoring; or to become a market-facing AI system or API.

**Required controls for the current classification** (cross-referenced to
repository mechanisms): human oversight via UI/dashboard, evidence traceability
via run artifacts, quality gates via critic/judge/meeting-readiness, data
minimization via audit log policy, transparency via report package, and security
governance via CI gates.

---

## 9. Runtime Hardening in Code

Security controls embedded in source code. These are the authoritative
implementations — the policy documents reference them, but the code governs.

| Control | File | What it does |
| --- | --- | --- |
| API key resolution | [`src/config/settings.py`](../../../src/config/settings.py) | `resolve_openai_api_key()` enforces the two-source priority chain (env > keyring). `get_llm_config()` returns only an `api_key_present` boolean, never the key value. |
| Startup validation | [`preflight.py`](../../../preflight.py) | Validates Python version, installed packages, project files, credential presence, and Streamlit CLI. Outputs only a scrubbed credential status. |
| Tool policy enforcement | [`src/orchestration/tool_policy.py`](../../../src/orchestration/tool_policy.py) | `resolve_allowed_tools(agent_name, task_key)` returns the exact set of tools permitted for a role and task. `tool_is_allowed()` is the predicate used by the runtime to gate tool calls. |
| Contract validation | [`src/orchestration/contract_validation.py`](../../../src/orchestration/contract_validation.py) | `validate_payload_against_task_schema()` validates department payload updates against registered Pydantic schemas. Returns a list of `ContractViolation` objects with field path, type, and severity. Empty payloads escalate to `high` severity. |
| Memory sanitization | [`src/memory/consolidation.py`](../../../src/memory/consolidation.py) | `consolidate_role_patterns()` scrubs company names, domains, emails, URLs, and legal entity suffixes from queries before writing to long-term memory. Replaces them with structural placeholders (`{company}`, `{domain}`, `{url}`, `{contact}`). Only patterns passing `_is_process_safe_query()` (≥ 12 chars, ≥ 1 non-placeholder word) are stored. |
| Runtime guardrails | [`src/orchestration/runtime_guardrails.py`](../../../src/orchestration/runtime_guardrails.py) | Phase-aware token budgets (first pass: 350 000, closure: 80 000, optional depth: 50 000). `validate_structured_artifact()` validates runtime artifacts against registered Pydantic models. `sort_answer_matrix()` enforces deterministic output ordering. |
| Secret scan validation | [`scripts/validate_secret_scan.py`](../../../scripts/validate_secret_scan.py) | Parses detect-secrets and Gitleaks JSON reports and fails the CI gate on any finding outside the documented exclusion paths. |
| Dependency audit with policy | [`scripts/run_pip_audit_with_policy.py`](../../../scripts/run_pip_audit_with_policy.py) | Runs pip-audit over `requirements.lock`. Checks CVE exception entries in `policies/license/dependency-risk-exceptions.json` for valid expiry dates. Fails if any exception is expired or any unapproved CVE is found. |

---

## 10. Residual Risks

These risks are documented in the threat model and have no full mitigation in the
current implementation. They are accepted as-is for the current scope.

| Risk | Why unmitigated |
| --- | --- |
| Public web data may be outdated or fabricated | The runtime cannot verify source freshness or ground truth of public pages |
| Local artifact directories are not encrypted | No application-level encryption is implemented for `artifacts/` |
| Retention deletion is not automated | Operators must delete run directories manually according to their retention policy |
| External model service behavior depends on vendor configuration | Account-level controls (rate limits, usage policies) are outside the codebase |
| Generated PDFs may be copied outside the controlled artifact directory | No DRM or export tracking is implemented |

---

## 11. Security Review Triggers

A security review is mandatory before merging any change that involves:

- Adding new tools to any agent or broadening existing tool grants.
- Adding ingestion of customer-private data (documents, finance, HR, contact
  datasets).
- Changing long-term memory write paths or the scrubbing logic in
  `src/memory/consolidation.py`.
- Exposing the runtime as a hosted or multi-tenant service.
- Adding write access to any external system (APIs, databases, messaging).
- Changing CI/CD workflow permissions, unpinning actions, or modifying the
  `policy-as-code-gate` Rego policies.
- Changing report export destinations or adding new export formats.
- Any change that would trigger a reclassification under the
  [EU AI Act risk classification](#8-regulatory-classification).

To run a security review on the current branch:

```text
/security-review
```
