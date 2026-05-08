# Model Routing Policy

> Language: `en`
> Path: `models/model-routing-policy.md`

## Purpose

This document records how models are selected and routed in the Liquisto
Department Runtime. The implementation lives in `src/config/settings.py`,
`src/agents/lead.py`, `src/agents/worker.py`, `src/agents/synthesis_department.py`,
`src/agents/report_writer.py`, and `src/research/search.py`.

## Routing Principles

- Use stronger models for control, critique, synthesis, and final report
  composition.
- Use smaller models for high-volume research and structured extraction.
- Keep model selection configurable by environment variables.
- Keep search, translation, and extraction model settings separate from agent
  chat settings.
- If no API key is available, external model calls fail closed or return empty
  results depending on the helper.

## Default Role Models

| Role family | Default chat model | Default structured model |
| --- | --- | --- |
| `Supervisor` | `gpt-4.1` | `gpt-4.1` |
| Department container roles | `gpt-4.1` | `gpt-4.1-mini` |
| Department leads | `gpt-4.1` | `gpt-4.1-mini` |
| Department researchers | `gpt-4.1-mini` | `gpt-4.1-mini` |
| Department critics | `gpt-4.1` | `gpt-4.1-mini` |
| Department judges | `gpt-4.1` | `gpt-4.1-mini` |
| Department coding specialists | `gpt-4.1-mini` | `gpt-4.1-mini` |
| Synthesis roles | `gpt-4.1` | `gpt-4.1-mini` |
| `ReportWriter` | `gpt-4.1` | `gpt-4.1-mini` |

Fallback defaults:

| Setting | Default |
| --- | --- |
| `DEFAULT_MODEL` | `gpt-4.1-mini` |
| `DEFAULT_STRUCTURED_MODEL` | `gpt-4.1-mini` |
| `DEFAULT_SEARCH_MODEL` | `gpt-4.1-mini` |
| `DEFAULT_TRANSLATION_MODEL` | `gpt-4.1-mini` |
| `DEFAULT_EXTRACTION_MODEL` | `gpt-4.1-nano` |

## Environment Overrides

Global overrides:

| Variable | Meaning |
| --- | --- |
| `OPENAI_MODEL` | Global chat fallback |
| `OPENAI_STRUCTURED_MODEL` | Global structured-output fallback |
| `OPENAI_MODEL_SEARCH` or `OPENAI_MODEL_WEB_SEARCH` | Web-search synthesis model |
| `OPENAI_MODEL_TRANSLATION` | Translation model for report export |
| `OPENAI_MODEL_EXTRACTION` | Lightweight extraction model |

Role-specific overrides use preferred snake-case fragments:

```text
OPENAI_MODEL_COMPANY_RESEARCHER
OPENAI_STRUCTURED_MODEL_COMPANY_RESEARCHER
```

Legacy compact fragments are still supported:

```text
OPENAI_MODEL_COMPANYRESEARCHER
OPENAI_STRUCTURED_MODEL_COMPANYRESEARCHER
```

## Request Controls

| Variable | Default | Meaning |
| --- | --- | --- |
| `LIQUISTO_OPENAI_TIMEOUT_SECONDS` | `90` | OpenAI request timeout |
| `LIQUISTO_OPENAI_MAX_RETRIES` | `1` | Retry count for transient OpenAI request failures |
| `LIQUISTO_MAX_TASK_RETRIES` | `3` | Department task retry limit before judge/escalation path |
| `LIQUISTO_SOFT_TOKEN_BUDGET` | `200000` | Overall soft token budget |
| `LIQUISTO_HARD_TOKEN_CAP` | `500000` | Overall hard token cap |
| `LIQUISTO_FIRST_PASS_TOKEN_BUDGET` | `350000` | First-pass phase budget |
| `LIQUISTO_CLOSURE_TOKEN_BUDGET` | `80000` | Closure phase budget |
| `LIQUISTO_OPTIONAL_DEPTH_TOKEN_BUDGET` | `50000` | Optional-depth phase budget |

## Tool-Specific Model Use

| Capability | Implementation | Model source |
| --- | --- | --- |
| Department AG2 chat | `DepartmentLeadAgent` / AG2 group chat | `get_role_model_selection(role)` |
| Research web search | `src/research/search.py` via OpenAI Responses API and `web_search_preview` | `get_search_model()` |
| Structured worker extraction | `ResearchWorker` | role structured model |
| Synthesis AG2 chat | `SynthesisDepartmentAgent` | synthesis role model |
| Report composition | `ReportWriterAgent` | report writer model |
| PDF translation | `src/exporters/pdf_report.py` | `get_translation_model()` |
| Lightweight extraction helpers | `src/research/extract.py` | `get_extraction_model()` |

## Cost Tracking

Runtime usage totals are aggregated in `ShortTermMemoryStore.usage_totals`.
`src/config/pricing.py` estimates token and `web_search_preview` call costs.
Pricing can be overridden through:

- `OPENAI_PRICE_INPUT_PER_1M_<MODEL>`
- `OPENAI_PRICE_OUTPUT_PER_1M_<MODEL>`
- `OPENAI_PRICE_WEB_SEARCH_PREVIEW_REASONING_PER_1K_CALLS`
- `OPENAI_PRICE_WEB_SEARCH_PREVIEW_NON_REASONING_PER_1K_CALLS`

## Temperature Policy

`src/config/settings.py` omits custom temperature for model families that only
support default temperature. The current locked prefix is `gpt-5`.

## Change Control

Changing default models or routing rules requires:

- updating this document;
- updating `src/config/settings.py`;
- checking role-specific tests where applicable;
- regenerating or reviewing AI-BOM output when the model inventory changes;
- confirming cost assumptions in `src/config/pricing.py`.
