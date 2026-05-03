# Provider Deployer Role Classification

> Language: `en`
> Path: `ai-act/provider-deployer-role-classification.md`

## Purpose

This document classifies the likely AI Act roles for the Liquisto Department
Runtime. It is a working governance record and must be reviewed for each
commercial deployment pattern.

## Role Summary

| Party | Working role | Notes |
| --- | --- | --- |
| Repository maintainers / product owner | Provider of the Liquisto AI system when placing it on the market or putting it into service under own name | Applies if the runtime is packaged, hosted, or offered as a product/service. |
| Internal Liquisto operator using the app | Deployer | Uses the AI system under organizational authority for meeting preparation. |
| Customer organization receiving a briefing | Usually recipient/user of output, possibly deployer if it operates the system itself | Classification depends on whether the customer controls the system execution. |
| External model/API vendor | Upstream model or GPAI/service provider | The project does not train or place a GPAI model on the market. |
| Public web sources | Data/source providers, not AI Act providers for this system | Their content is consumed as evidence and must be cited/qualified. |

## Provider-Side Responsibilities for This Project

When the project is offered under the owner's name, provider-side controls
should include:

- documented intended use and prohibited use;
- model and tool routing documentation;
- data classification and audit minimization policies;
- evidence traceability through run artifacts;
- human oversight instructions;
- quality gates for meeting-readiness and department package acceptance;
- security and release governance gates;
- AI-BOM and SBOM generation;
- incident and defect handling for materially incorrect or unsafe outputs.

## Deployer-Side Responsibilities

Operators using the system should:

- use outputs as decision support, not as an automated decision;
- review evidence and unresolved gaps before acting;
- avoid entering special-category, HR, medical, credit, or other regulated data
  unless a separate impact review permits it;
- protect exported run artifacts and reports according to their data class;
- delete or restrict run artifacts when they are no longer needed;
- ensure business-contact outreach complies with applicable privacy and
  marketing rules.

## Boundary With External Model Providers

The runtime calls external OpenAI-compatible APIs for:

- AG2 chat-based agent execution;
- structured extraction and report composition;
- OpenAI `web_search_preview`-based search;
- translation in PDF export when an API key is available.

The project remains responsible for how those services are orchestrated,
logged, routed, and presented to users. The external provider remains
responsible for its own service, model, and contractual commitments.

## Cases Requiring Reclassification

Review this document before:

- exposing the runtime as a customer-operated SaaS;
- embedding it into customer workflows that make eligibility, employment,
  credit, procurement exclusion, or similarly consequential decisions;
- accepting customer-private datasets as routine input;
- replacing external model calls with an in-house trained or fine-tuned model;
- branding or distributing a model artifact rather than an application runtime.

## References

- Regulation (EU) 2024/1689 definitions of provider and deployer:
  https://eur-lex.europa.eu/eli/reg/2024/1689/oj
- European Commission AI Act overview:
  https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai
