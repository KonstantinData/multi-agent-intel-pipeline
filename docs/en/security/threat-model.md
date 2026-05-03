# Threat Model

> Language: `en`
> Path: `security/threat-model.md`

## Purpose

This document records the security threat model for the Liquisto Department
Runtime. It covers the local app/runtime, external model and web-search calls,
run artifacts, memory, CI/CD governance, and generated reports.

## System Assets

| Asset | Why it matters |
| --- | --- |
| `OPENAI_API_KEY` and other credentials | Enables external model/API access |
| Run artifacts under `artifacts/runs/<run_id>/` | Contain case-specific company, contact, evidence, and report data |
| Long-term memory under `artifacts/memory/` | Must contain process patterns only |
| Knowledge base YAML files | Influence source selection, query strategy, and acceptance gates |
| Department artifacts | Authoritative evidence/review/decision history |
| Generated PDFs | Operator-facing briefing output |
| CI/CD workflows and scripts | Enforce governance, security, and release inventory gates |

## Trust Boundaries

| Boundary | Risk |
| --- | --- |
| User/UI intake to Supervisor | Malformed or intentionally misleading company/domain input |
| Runtime to public web | Untrusted content, stale data, prompt injection in pages |
| Runtime to external model APIs | Data disclosure and generated-output reliability |
| Department chats to artifacts | Chat text could be misread as authoritative state |
| Run brain to long-term memory | Case facts could leak into reusable memory |
| Local artifacts to reports | Sensitive or low-confidence data could be overexposed |
| Repository to CI/CD | Dependency, secret, or workflow supply-chain risk |

## Main Threats and Controls

| Threat | Impact | Controls |
| --- | --- | --- |
| Prompt injection from public sources | Agents follow source instructions instead of task contract | Role prompts, tool grants, critic review, artifact-based finalization |
| Secret leakage into logs or prompts | Credential exposure | `.env` isolation, secret scanning, audit minimization policy |
| Case facts written to long-term memory | Privacy and confidentiality breach | `consolidate_role_patterns()` scrubbing, process-memory-only policy |
| Unsupported or fabricated findings | Bad meeting preparation | Evidence packets, source URLs, critic/judge review, meeting-readiness gate |
| Contact over-collection | Privacy risk | Contact department scope, business-contact relevance, data classification policy |
| Concurrent department mutation | Corrupt run state | working-set snapshots and deterministic merge in `ShortTermMemoryStore` |
| Dependency vulnerability | Runtime compromise | `pip-audit`, Dependabot, dependency review, CodeQL, Bandit |
| Malicious workflow/action change | CI compromise | pinned actions, hardening checks, limited permissions |
| Report export over-disclosure | Sensitive data in PDFs | finalization sync, success-path unresolved sanitization, report package boundary |

## Existing Security Gates

The `compliance-security-ai` workflow includes:

- Ruff linting for scripts and tests;
- MyPy type check;
- Bandit SAST for `src` and `scripts`;
- `pip-audit` dependency gate;
- `detect-secrets` scan for `src` and `scripts`;
- governance structure validation;
- GitHub Actions hardening check;
- script contract tests;
- architecture tests;
- runtime contract tests;
- AI-BOM generation and validation;
- SBOM generation and validation.

Additional workflows cover dependency review, CodeQL, and release attestation.

## Runtime Hardening

- OpenAI timeout and retry settings are centralized.
- Phase budgets and stop reasons are tracked by `PhaseBudgetTracker`.
- Runtime artifacts are validated with Pydantic models where registered.
- JSON exports use atomic writes.
- Follow-up history uses a file lock.
- Search helpers fail closed to empty results on errors.

## Residual Risks

- Public data may be outdated or wrong even when cited.
- Local artifact directories are not encrypted by the application.
- Retention deletion is not automated.
- External model service behavior depends on account/vendor configuration.
- Generated PDFs may be copied outside the controlled artifact directory.

## Security Review Triggers

Run a security review before:

- adding new tools or broadening tool grants;
- adding customer-private data ingestion;
- changing long-term memory writes;
- exposing the runtime as a hosted multi-tenant service;
- adding write access to external systems;
- changing CI/CD workflow permissions or unpinning actions;
- changing report export destinations.
