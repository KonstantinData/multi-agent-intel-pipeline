# Data Classification Policy

> Language: `en`
> Path: `privacy/data-classification-policy.md`

## Purpose

This policy classifies data handled by the Liquisto Department Runtime and
defines handling rules for storage, model calls, exports, and memory.

## Classification Levels

| Level | Meaning | Examples in this repository |
| --- | --- | --- |
| Public | Already public or intentionally published | Company websites, public news, public registry pages, public source URLs |
| Business confidential | Operational or customer context that is not public | Customer-provided meeting context, internal inventory hints, private target lists |
| Personal business contact data | Work-related personal data | Names, titles, companies, professional profiles, business email patterns |
| Secret | Credentials or security-sensitive data | `OPENAI_API_KEY`, tokens, auth headers, cookies, CI secrets |
| Process metadata | Non-case-specific operational patterns | Scrubbed query patterns, critique heuristics, retry patterns |

## Data by Runtime Area

| Runtime area | Typical data | Classification | Handling |
| --- | --- | --- | --- |
| Intake | `company_name`, `web_domain` | Public or business confidential depending on use case | Store in run artifacts; do not store in long-term memory |
| Website snapshot | title, meta description, visible text snippets | Public unless source is non-public | Store summarized/extracted form only |
| Search results | title, URL, source type, summary | Public | Store source URLs and concise summaries |
| Department artifacts | facts, sources, open questions, decisions | Mixed | Store in run brain; cite sources; retain gaps |
| Contact intelligence | business names, titles, roles, source URLs | Personal business contact data | Store only when relevant to meeting prep; avoid enrichment beyond business context |
| Customer confirmations | internal missing data requests | Business confidential | Store as blockers/actions, not as speculative facts |
| Run reports | final briefing and PDFs | Mixed | Protect according to highest included class |
| Long-term memory | process patterns only | Process metadata | Scrub company/domain/contact identifiers before write |
| CI artifacts | SBOM, AI-BOM, test reports | Public/internal metadata | Must not contain secrets or run case facts |

## Personal Data Rules

Business-contact data may be processed only for the contact-intelligence purpose
of the run. The runtime should prefer:

- role and function relevance over personal profiling;
- source-backed contact records;
- minimal fields needed for outreach preparation;
- clear unresolved status when contact evidence is weak.

The runtime must not infer sensitive personal attributes or use personal data
for employment, credit, insurance, eligibility, or similar consequential
decisions.

## Customer-Provided Data

Customer-provided non-public information is business confidential by default.
Before such data is entered into the runtime, the operator must confirm:

- the data is needed for meeting preparation;
- external model/API processing is permitted for that data;
- retention in run artifacts is acceptable;
- the generated report may include or reference it.

## Secrets

Secrets are never valid runtime evidence. They must stay in environment
variables, CI secrets, or local `.env` files and must not be copied into:

- prompts;
- run artifacts;
- exported PDFs;
- logs;
- AI-BOM/SBOM;
- long-term memory.

## Storage Rules

| Store | Allowed data |
| --- | --- |
| `run_artifacts` / `run_checkpoints` (PostgreSQL) | Case-specific data required for audit, report export, and follow-up |
| `memory_patterns` (PostgreSQL) | Scrubbed process patterns only |
| `bom/*` | Inventory and release metadata only |
| CI reports | Test and gate results only |

## Deletion and Retention

This repository does not currently implement automatic retention deletion.
Operators should treat run directories as retained case files and delete or
archive them according to the deployment's retention policy.

Before adding retention automation, preserve:

- ability to answer follow-ups while the run is retained;
- audit integrity of exported reports;
- append safety for `follow_up_history` updates.
