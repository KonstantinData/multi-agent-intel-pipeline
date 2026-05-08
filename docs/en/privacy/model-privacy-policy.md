# Model Privacy Policy

> Language: `en`
> Path: `privacy/model-privacy-policy.md`

## Purpose

This policy defines privacy expectations for data sent to external or local LLM
and search services by the Liquisto Department Runtime.

## Model Call Surfaces

| Surface | Implementation | Data sent |
| --- | --- | --- |
| AG2 department chat | `DepartmentLeadAgent` and department `ConversableAgent` roles | Supervisor brief, task contract, department context, selected artifacts |
| Web search synthesis | `src/research/search.py` using OpenAI Responses API with `web_search_preview` | Search query text |
| Structured extraction | `src/agents/worker.py`, `src/research/extract.py` | Source snippets, task context, extraction schema |
| Synthesis | `SynthesisDepartmentAgent` | Approved department report segments and quality context |
| Report writing | `ReportWriterAgent` | Finalized `pipeline_data`, final status, briefing artifacts |
| Translation | `src/exporters/pdf_report.py` | Narrative report fields requiring translation |

## Data Minimization for Model Calls

Model prompts should include only:

- the current task objective;
- relevant supervisor brief fields;
- necessary source snippets or evidence packets;
- schemas required for structured output;
- unresolved gaps relevant to the current step.

Model prompts should not include:

- API keys, environment variables, credentials, cookies, or auth headers;
- full raw web pages when extracted snippets are sufficient;
- unrelated department artifacts;
- private customer data unless explicitly approved for model processing;
- hidden chain-of-thought requests.

## External API Preconditions

Before enabling external model/API calls in a deployment, confirm:

- `OPENAI_API_KEY` or equivalent credentials are stored only as secrets;
- the vendor account and contract permit the relevant data categories;
- customer-private data processing is covered where customer data is entered;
- operators understand that public web search queries can reveal research
  intent to the search/model service.

## Query Privacy

Queries may contain target company names, domains, product hints, and public
contact-search terms. Query construction is centralized in
`src/research/query_resolver.py` and `knowledge/query_strategies/*.yaml`.

Rules:

- do not include secrets or private customer inventory identifiers in public
  search queries unless explicitly approved;
- prefer source-scoped and task-scoped queries over broad personal searches;
- for contact tasks, search only for business-role relevance.

## Memory Privacy

Run-specific model inputs and outputs may be represented in run artifacts, but
they must not be reused as long-term truth. Long-term memory may store only
scrubbed structural process patterns produced by `src/memory/consolidation.py`.

Examples allowed in long-term memory:

- `site:{domain} {company} products`
- evidence-source type effectiveness;
- retry trigger patterns;
- critique heuristics.

Examples not allowed:

- a target company's actual revenue;
- a target domain;
- a contact name;
- a run-specific conclusion;
- a customer-provided inventory list.

## Output Handling

LLM outputs must be treated as generated decision support. The runtime should:

- attach evidence where available;
- preserve gaps and uncertainty;
- route weak or conflicting task outputs through critic/judge handling;
- block or downgrade final readiness when meeting-critical gaps remain.

## Incident Triggers

Open a privacy/security review if:

- a secret appears in a prompt, artifact, log, or report;
- private customer data is sent to a model without approval;
- long-term memory contains company, domain, URL, email, or contact identifiers;
- a generated report includes personal data unrelated to business-contact
  meeting preparation;
- a model response fabricates sensitive or unsupported personal information.
