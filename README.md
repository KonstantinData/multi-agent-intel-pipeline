# Liquisto Department Runtime

Multi-agent intelligence pipeline that builds Liquisto pre-meeting briefings.
The system takes `company_name` and `web_domain` as input and produces a
structured research briefing with company analysis, market context, buyer
landscape, contact intelligence, strategic synthesis, and an operator-facing
report.

Built on [AG2 (AutoGen)](https://github.com/ag2ai/ag2) group chats with
bounded department collaboration, coordinated by a single Supervisor.

## Quickstart

```bash
# 1. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Unix

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set OpenAI API key
echo OPENAI_API_KEY=sk-... > .env

# 4. Validate environment
python preflight.py

# 5. Start the UI
streamlit run ui/app.py
```

## Architecture

Architecture spec: [docs/target_runtime_architecture.md](docs/target_runtime_architecture.md) ·
Diagram: [docs/updated_runtime_architecture.drawio](docs/updated_runtime_architecture.drawio)

### Control Plane

- **Supervisor** — intake normalization, domain routing, run coordination, follow-up routing.
  No domain-level fact interpretation or evidence review.

### Research Plane

Four domain departments, each implemented as a bounded AG2 GroupChat:

| Department | Scope |
|------------|-------|
| Company Department | Company fundamentals, economic/commercial situation, product and asset scope. The CompanyLead owns the goods classification (made vs distributed vs held-in-stock) as a domain judgment |
| Market Department | Market situation, repurposing/circularity, analytics and operational improvement signals |
| Buyer Department | Peer companies, monetization and redeployment paths |
| Contact Department | Contact discovery and qualification at prioritized buyer firms |

Each department group contains:

| Role | Model | Tool |
|------|-------|------|
| Lead / Analyst | gpt-4.1 | `finalize_package` |
| Researcher | gpt-4.1-mini | `run_research` |
| Critic | gpt-4.1 | `review_research` |
| Judge (optional) | gpt-4.1 | `judge_decision` |
| Coding Specialist (optional) | gpt-4.1-mini | `suggest_refined_queries` |

The Lead decides retry, coding support, and Judge escalation autonomously
inside the department contract. The Supervisor does not participate in
intra-department decisions.

Turn routing uses a guardrail-only speaker selector that enforces tool-call
routing, loop prevention, and termination recognition. The Lead drives the
internal workflow through explicit agent addressing — the selector does not
maintain workflow state.

### Synthesis Plane

- **Synthesis Department** — AG2 GroupChat that reads all approved department report segments, identifies cross-domain patterns, and builds the Liquisto opportunity assessment. Contains SynthesisLead, SynthesisAnalyst, SynthesisCritic, and SynthesisJudge.
- **Report rendering** — turns the approved analysis into a professional operator-facing report for PDF export (German + English). This is a rule-based rendering step, not an agent.

## Runtime Modes

### Initial briefing

1. Supervisor normalizes intake → `SupervisorBrief`
2. Task router builds assignments from the standard Liquisto scope
3. Departments run in two phases:
   - **Parallel**: Company + Market (via ThreadPoolExecutor)
   - **Sequential**: Buyer → Contact (Contact depends on Buyer output)
4. Each department returns a validated `DepartmentPackage`
5. Synthesis Department builds the cross-domain interpretation via AG2 GroupChat
6. Report rendering produces the operator-facing report package
7. Artifacts exported to `artifacts/runs/<run_id>/`

### Follow-up

1. User enters `run_id` and a question in the UI
2. System loads the historical run context (full run brain including department artifact history)
3. Supervisor routes the question to the correct department or synthesis layer
4. Answer is generated from stored run memory and persisted as a follow-up artifact

## Key Files

| File | Purpose |
|------|---------|
| [src/pipeline_runner.py](src/pipeline_runner.py) | Public runtime entrypoint for UI and CLI |
| [src/orchestration/supervisor_loop.py](src/orchestration/supervisor_loop.py) | Supervisor-controlled department routing loop |
| [src/orchestration/department_runtime.py](src/orchestration/department_runtime.py) | Bounded department group runtime |
| [src/orchestration/synthesis_runtime.py](src/orchestration/synthesis_runtime.py) | Synthesis department AG2 runtime |
| [src/orchestration/task_router.py](src/orchestration/task_router.py) | Supervisor mandate → department assignments |
| [src/orchestration/follow_up.py](src/orchestration/follow_up.py) | Run loading, routing, persisted follow-up answers |
| [src/orchestration/contracts.py](src/orchestration/contracts.py) | Typed runtime contracts: TaskArtifact, TaskReviewArtifact, TaskDecisionArtifact, DepartmentRunState |
| [src/orchestration/speaker_selector.py](src/orchestration/speaker_selector.py) | Guardrail-only speaker selectors for department and synthesis GroupChats |
| [src/orchestration/tool_policy.py](src/orchestration/tool_policy.py) | Per-role tool allow-lists |
| [src/agents/specs.py](src/agents/specs.py) | Agent and pipeline step metadata (AGENT_SPECS) |
| [src/agents/runtime_factory.py](src/agents/runtime_factory.py) | Runtime agent instantiation |
| [src/agents/lead.py](src/agents/lead.py) | DepartmentLeadAgent — owns the AG2 group lifecycle |
| [src/agents/supervisor.py](src/agents/supervisor.py) | SupervisorAgent — intake, routing, package acceptance |
| [src/agents/worker.py](src/agents/worker.py) | ResearchWorker — web search, page fetch, LLM synthesis |
| [src/agents/critic.py](src/agents/critic.py) | CriticAgent — deterministic rule-based review |
| [src/agents/judge.py](src/agents/judge.py) | JudgeAgent — deterministic three-outcome quality gate |
| [src/agents/coding_assistant.py](src/agents/coding_assistant.py) | CodingAssistantAgent — query refinement for stuck tasks |
| [src/agents/synthesis_department.py](src/agents/synthesis_department.py) | SynthesisDepartmentAgent — AG2 GroupChat for cross-domain synthesis |
| [src/orchestration/synthesis.py](src/orchestration/synthesis.py) | Cross-domain synthesis context, quality review, report package assembly |
| [src/app/use_cases.py](src/app/use_cases.py) | Liquisto standard scope, task backlog, and validation rules |
| [src/config/settings.py](src/config/settings.py) | Model selection, role defaults, API key resolution |
| [src/models/schemas.py](src/models/schemas.py) | Pydantic schemas for pipeline data |
| [src/models/registry.py](src/models/registry.py) | Task sub-schemas, SCHEMA_REGISTRY, section assembly |
| [src/exporters/pdf_report.py](src/exporters/pdf_report.py) | PDF report generation (DE + EN) |
| [src/exporters/json_export.py](src/exporters/json_export.py) | Run artifact JSON export |
| [ui/app.py](ui/app.py) | Streamlit UI |

## Memory

### Short-term (per run)

Stored under `artifacts/runs/<run_id>/`. Contains:
supervisor brief, task statuses, department packages, department run states
(full artifact history: task artifacts, review artifacts, decision artifacts,
strategy changes, judge escalations, coding support events), conversation
traces, validated pipeline data, report package, follow-up history.

### Long-term (cross-run)

Stored at `artifacts/memory/long_term_memory.json`. Contains reusable process
patterns only — structural query patterns (scrubbed of company identifiers),
critique heuristics, judge decision principles, coding method tactics, and
retry trigger patterns. Never stores company-specific facts, evidence, or
contact names.

## Output Artifacts

Each run writes to `artifacts/runs/<run_id>/`:

| File | Content |
|------|---------|
| `run_meta.json` | Run metadata (company, domain, status, timing, cost) |
| `chat_history.json` | Full message trace |
| `pipeline_data.json` | Structured research output |
| `run_context.json` | Supervisor brief, task statuses, department packages, department run states |
| `memory_snapshot.json` | Short-term memory snapshot |
| `follow_up_history.json` | Follow-up Q&A (when applicable) |

## UI

The Streamlit UI supports:
- Starting a fresh run with company name and web domain
- Live progress tracking across all pipeline steps
- Loading an existing run by `run_id`
- Viewing the briefing tab with Liquisto recommendation, meeting preparation, and contacts
- Viewing detailed research per section (company, market, buyer, contact)
- Asking follow-up questions routed to the correct department
- Downloading German and English PDF briefings

## Configuration

- **API key**: set `OPENAI_API_KEY` in `.env` or as environment variable
- **Model overrides**: `OPENAI_MODEL_<ROLE>` and `OPENAI_STRUCTURED_MODEL_<ROLE>` env vars
- **Defaults**: defined in `src/config/settings.py` → `ROLE_MODEL_DEFAULTS`
- **Max retries**: `LIQUISTO_MAX_TASK_RETRIES` env var (default: 3)
- **Token budgets**: `LIQUISTO_SOFT_TOKEN_BUDGET` and `LIQUISTO_HARD_TOKEN_CAP` env vars
- **Streamlit**: `.streamlit/config.toml`

## Validation

```bash
python preflight.py   # environment, packages, project files, API key, import chain, port
pytest                # unit tests
```
