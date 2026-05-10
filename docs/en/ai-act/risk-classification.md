# Risk Classification

> Language: `en`
> Path: `ai-act/risk-classification.md`

## Purpose

This document records the working EU AI Act risk classification for the
Liquisto Department Runtime. It is not a legal opinion. It is a repository-level
engineering classification to guide controls, documentation, and release gates.

Canonical system behavior is defined in:

- `README.md`
- `docs/target_runtime_architecture.md`
- `docs/drawio/target_runtime_architecture.md`
- `src/orchestration/contracts.py`

## Intended Use

The system builds pre-meeting commercial briefings from `company_name` and
`web_domain`. It researches public company, market, buyer, and business-contact
signals, then produces meeting preparation artifacts.

The intended output supports human preparation for a business meeting. It does
not make an automated legal, credit, employment, insurance, education, law
enforcement, migration, biometric, medical, or public-service eligibility
decision.

## Current Classification

| Dimension | Classification | Rationale |
| --- | --- | --- |
| Prohibited AI practice | Not intended | No social scoring, subliminal manipulation, biometric categorization, emotion recognition in workplace/education, or prohibited law-enforcement use is part of the intended runtime. |
| High-risk AI system | Not currently classified as high-risk for intended use | The runtime produces a business briefing for human review and does not make or materially automate decisions in Annex III domains. |
| Limited/transparency risk | Possible | Generated content and LLM-mediated summaries are presented to users and should be treated as AI-generated decision support. |
| General-purpose AI model provider | No | The project uses external foundation/model services. It does not develop or place a GPAI model on the market. |
| Deployer obligations | Applicable when used operationally | Operators using the system under their authority must maintain human oversight, appropriate instructions, data governance, and use-case controls. |

## Risk-Relevant System Properties

- Human-in-the-loop: final meeting use is human-reviewed.
- Evidence-based output: departments produce `EvidencePacket`, `GapCandidate`,
  `AnswerMatrixUpdate`, and validated `DepartmentPackage` artifacts.
- Grounded follow-up: follow-up answers prefer stored run-brain artifacts before
  fallback package summaries.
- Bounded autonomy: departments can retry, critique, and escalate internally,
  but the Supervisor remains the single control plane.
- Memory separation: run-specific facts stay in the run brain; long-term memory
  stores only scrubbed process patterns.

## Reclassification Triggers

The classification must be reviewed before release if the system is changed to:

- rank, score, or reject natural persons for employment, credit, education,
  essential services, insurance, law enforcement, migration, or democratic
  process contexts;
- automate a customer-facing decision without meaningful human review;
- infer sensitive personal attributes;
- process biometric, medical, or special-category data;
- perform employee monitoring or emotion recognition;
- become a provider of a model or AI system placed on the market under a new
  product name or customer-facing API;
- accept non-public customer inventory, finance, HR, or contact datasets at
  scale without updated privacy and security review.

## Required Controls for Current Classification

| Control | Repository mechanism |
| --- | --- |
| Human oversight | UI/operator review, meeting-readiness status, dashboard pause/resume for user selections |
| Evidence traceability | `pipeline_data.json`, `run_context.json`, `memory_snapshot.json`, `DepartmentRunState` artifacts |
| Quality gates | Department policy KB gates, critic review, judge decisions, `MeetingReadinessGate` |
| Data minimization | Audit log minimization policy, run-brain/long-term memory separation |
| Transparency | Report package and exported briefing identify evidence, gaps, blockers, and readiness status |
| Security governance | CI gates for SAST, dependency audit, secret scan, CodeQL, AI-BOM, SBOM, release attestation |

## Current Residual Risks

- Public web sources can be stale, incomplete, or misleading.
- Business-contact data can still be personal data even when publicly available.
- LLM summaries can omit nuance; evidence packets and source URLs must remain
  inspectable.
- Follow-up answers can appear authoritative if operators ignore
  `requires_additional_research` and unresolved gaps.

## References

- Regulation (EU) 2024/1689: https://eur-lex.europa.eu/eli/reg/2024/1689/oj
- European Commission AI Act overview: https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai
