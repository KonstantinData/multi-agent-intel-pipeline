# Liquisto Department Runtime

Multi-agent intelligence pipeline that builds Liquisto pre-meeting briefings.
The system takes `company_name` and `web_domain` as input and produces a
**meeting-ready** briefing with company analysis, market context, buyer
landscape, contact intelligence, strategic synthesis, and concrete meeting
actions.

Built on [AG2 (AutoGen)](https://github.com/ag2ai/ag2) group chats with
bounded department collaboration, coordinated by a single Supervisor.

## Quickstart

```bash
# 1. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Unix

# 2. Install dependencies
pip install -r requirements.lock

# 3. Store OpenAI API key in the OS keyring
#    Details: docs/Secrets-Management.md
python -m keyring set liquisto-department-runtime OPENAI_API_KEY

# 4. Validate environment
python preflight.py

# 5. Start the UI
python -m streamlit run ui/app.py
# or (recommended on Windows without activation):
.\.venv\Scripts\python.exe launcher.py
```

### Local Pre-PR Gate Run

Before opening a PR, run the local compliance gate pipeline:

```bash
python .codex/scripts/run_pre_pr_gates.py --fail-fast
```

This mirrors the named gates in `.github/workflows/compliance-security-ai.yml` and writes a report to:

`artifacts/pre_pr_gate_report.json`

Optional runtime-memory recap before PR handling (non-blocking):

```bash
python .codex/scripts/run_pre_pr_gates.py --fail-fast --memory-run-id <run_id>
```

This prints a compact `[MEMORY-RECAP]` summary from the Cloudflare app-memory
worker. Missing token or unavailable endpoint only prints a skip/error message
and does not interrupt the gate run.

## Architecture

Architecture spec: [docs/drawio/target_runtime_architecture.md](docs/drawio/target_runtime_architecture.md) ·
Diagram: [docs/drawio/runtime_architecture.drawio](docs/drawio/runtime_architecture.drawio)

### Control Plane

- **Supervisor** — intake normalization, domain routing, run coordination, follow-up routing.
  No domain-level fact interpretation or evidence review.

### Research Plane

Four domain departments, each implemented as a bounded AG2 GroupChat.
Departments are **question-coverage contributors**: their primary outputs are
evidence packets, gap candidates, and answer-matrix updates for mapped meeting
questions.

| Department | Scope |
|------------|-------|
| Company Department | Company fundamentals, economic/commercial situation, product and asset scope. The CompanyLead owns the goods classification (made vs distributed vs held-in-stock) as a domain judgment |
| Market Department | Market situation, demand pressure, overcapacity, and excess-stock signals |
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

Department execution stays conversation-driven. Quality enforcement is
department-specific and checked at package finalization via Knowledge Base:

- `knowledge/sources/<department>.yaml` (source registry, priorities, evidence type, provenance notes — not runtime queries)
- `knowledge/policies/<department>.yaml` (required fields, evidence minimums, gate rules)
- `knowledge/query_strategies/<department>.yaml` (runtime query templates per task — the single query-strategy authority)

### Synthesis Plane

- **Synthesis Department** — AG2 GroupChat that reads all approved department report segments, identifies cross-domain patterns, and builds the Liquisto opportunity assessment.
- **Report Writer Runtime** — dedicated runtime node (`report_writer`) that assembles `report_package` after finalization from validated pipeline sections, final run status, meeting actions, and final briefing artifacts.
- **Report rendering/export** — UI/export layer generates operator-facing PDF output (German + English) from the finalized run artifacts.

### Meeting-Readiness Layer

The runtime plans around **meeting questions**, not only departments.

- **Question Registry** — 11 meeting questions with deterministic task-to-question mapping
- **Answer Matrix** — tracks coverage status per question, updated by each task outcome
- **Resolution Controller** — classifies the run into one of 5 resolution buckets after the first department round
- **Meeting-Readiness Gate** — blocks finalization when meeting-critical questions remain unresolved
- **Final Briefing Composer** — produces concrete `meeting_actions` as the primary action output

## Runtime Modes

### Initial briefing

1. Supervisor normalizes intake → `SupervisorBrief`
2. Question registry + answer matrix built before department execution
3. Departments run in two phases:
   - **Parallel**: Company + Market (via ThreadPoolExecutor)
   - **Sequential**: Buyer → Contact (Contact depends on Buyer output)
4. Each department returns evidence packets, gap candidates, and answer-matrix updates
5. Resolution Controller classifies the run state (AUTO_CLOSE / USER_DECISION / CUSTOMER_CONFIRMATION / NOT_MEETING_CRITICAL / BLOCKING_FAILURE)
6. Bounded closure loop for publicly researchable meeting-critical gaps
7. Synthesis Department builds the cross-domain interpretation
8. Meeting-Readiness Gate evaluates finalization eligibility
9. Final Briefing Composer produces meeting actions and final briefing artifacts
10. Report Writer assembles the final `report_package`
11. Artifacts exported to PostgreSQL (`run_artifacts`, `run_checkpoints`) with phase-aware checkpoints

### Dashboard pause/resume

1. Run pauses with `needs_user_selection` when optional depth decisions are required
2. UI shows resolution dashboard with answered questions, optional depth checkboxes, customer confirmation items
3. `resume_pipeline()` applies user selections and re-evaluates the finalization gate

### Follow-up

1. User enters `run_id` and a question in the UI
2. System loads the historical run context (run-brain task artifacts as primary grounding, then `pipeline_data`, then department packages)
3. Supervisor routes the question to the correct department
4. Answer is generated from stored run memory and persisted as a follow-up artifact

## Key Files

| File | Purpose |
|------|---------|
| [src/pipeline_runner.py](src/pipeline_runner.py) | Public runtime entrypoint: `run_pipeline()` and `resume_pipeline()` |
| [src/orchestration/supervisor_loop.py](src/orchestration/supervisor_loop.py) | Supervisor-controlled department routing loop |
| [src/orchestration/department_runtime.py](src/orchestration/department_runtime.py) | Bounded department group runtime |
| [src/orchestration/synthesis_runtime.py](src/orchestration/synthesis_runtime.py) | Synthesis department AG2 runtime |
| [src/orchestration/report_runtime.py](src/orchestration/report_runtime.py) | Report writer runtime wrapper used as real pipeline agent |
| [src/orchestration/task_router.py](src/orchestration/task_router.py) | Supervisor mandate → department assignments |
| [src/orchestration/meeting_questions.py](src/orchestration/meeting_questions.py) | Question registry, answer matrix, task-to-question mapping |
| [src/orchestration/resolution_controller.py](src/orchestration/resolution_controller.py) | 5-bucket resolution classification |
| [src/orchestration/meeting_readiness.py](src/orchestration/meeting_readiness.py) | MeetingReadinessGate + FinalBriefingComposer |
| [src/orchestration/runtime_guardrails.py](src/orchestration/runtime_guardrails.py) | Phase budgets, structured-output validation, deterministic ordering |
| [src/orchestration/follow_up.py](src/orchestration/follow_up.py) | Run loading, routing, run-brain-grounded follow-up |
| [src/orchestration/contracts.py](src/orchestration/contracts.py) | Typed runtime contracts: TaskArtifact, TaskReviewArtifact, TaskDecisionArtifact, DepartmentRunState |
| [src/orchestration/speaker_selector.py](src/orchestration/speaker_selector.py) | Guardrail-only speaker selectors |
| [src/orchestration/department_knowledge.py](src/orchestration/department_knowledge.py) | Department KB loading + policy-gate evaluation (acceptance-time) |
| [src/models/meeting_ready.py](src/models/meeting_ready.py) | Typed models: EvidencePacket, GapCandidate, AnswerMatrixUpdate, MeetingAction, MeetingReadinessAssessment, FinalBriefing |
| [src/agents/lead.py](src/agents/lead.py) | DepartmentLeadAgent — evidence-first AG2 group lifecycle |
| [src/agents/worker.py](src/agents/worker.py) | ResearchWorker — evidence packets as primary output |
| [src/research/query_resolver.py](src/research/query_resolver.py) | Central runtime query resolver — single authority for query construction per task |
| [src/agents/supervisor.py](src/agents/supervisor.py) | SupervisorAgent — intake, routing, package acceptance |
| [src/agents/report_writer.py](src/agents/report_writer.py) | ReportWriterAgent — report package assembly from pipeline artifacts |
| [src/agents/critic.py](src/agents/critic.py) | CriticAgent — deterministic rule-based review |
| [src/agents/judge.py](src/agents/judge.py) | JudgeAgent — deterministic three-outcome quality gate |
| [src/app/use_cases.py](src/app/use_cases.py) | Liquisto standard scope, task backlog, resolution plan helpers |
| [src/config/settings.py](src/config/settings.py) | Model selection, role defaults, API key resolution |
| [src/exporters/pdf_report.py](src/exporters/pdf_report.py) | PDF report generation (DE + EN) |
| [src/exporters/json_export.py](src/exporters/json_export.py) | Run artifact JSON export |
| [ui/app.py](ui/app.py) | Streamlit UI with resolution dashboard |

## Output Artifacts

In production profile, each run writes to PostgreSQL:

| Artifact type / table | Content |
|------|---------|
| `run_meta` in `run_artifacts` | Run metadata (company, domain, status, timing, cost, meeting_readiness) |
| `chat_history` in `run_artifacts` | Full message trace |
| `pipeline_data` in `run_artifacts` | Structured research output |
| `run_context` in `run_artifacts` | Supervisor brief, answer matrix, question registry, resolution state, department packages, department run states |
| `memory_snapshot` in `run_artifacts` | Short-term memory: evidence packets, gap candidates, meeting actions, resolution plans |
| `checkpoints` in `run_checkpoints` | Phase-aware checkpoints (after_first_pass, after_closure, after_synthesis, after_finalization) |
| `follow_up_history` in `run_artifacts` | Follow-up Q&A (when applicable) |

Non-production profile may export JSON files for local testing only.

## Success-Path Semantics

A successful run (`meeting_ready`) contains:
- `meeting_actions` — concrete, evidence-referenced preparation items
- `customer_confirmation_items` — items requiring customer-side validation
- `optional_depth_not_selected` — user-skipped depth areas

A successful run does **not** contain:
- generic `open_questions` block
- unresolved publicly researchable meeting-critical questions

## Security

Security architecture, threat model, agent permissions, CI/CD gates, and data classification are documented in the [Security Hub](docs/en/security/README.md).

## Configuration

- **Secrets management**: API-key lookup, OS-keyring setup, no-`.env` API-key rule, and logging requirements are documented in [docs/Secrets-Management.md](docs/Secrets-Management.md).
- **Role model overrides**: `OPENAI_MODEL_<ROLE>` and `OPENAI_STRUCTURED_MODEL_<ROLE>` (read from process env first, then optional untracked local `.env` fallback)
- **Role env key format**: preferred snake-case (for example `OPENAI_MODEL_COMPANY_RESEARCHER`), legacy compact keys (for example `OPENAI_MODEL_COMPANYRESEARCHER`) are still supported
- **Dedicated model settings**: `OPENAI_MODEL_SEARCH`, `OPENAI_MODEL_TRANSLATION`, `OPENAI_MODEL_EXTRACTION` (process env first, then optional untracked local `.env` fallback)
- **OpenAI request controls**: `LIQUISTO_OPENAI_TIMEOUT_SECONDS`, `LIQUISTO_OPENAI_MAX_RETRIES`
- **Runtime cost calculation**: `estimated_cost_usd` in `run_meta.json` is computed from
  tracked LLM token usage plus `web_search_preview` call fees
- **Defaults**: defined in `src/config/settings.py` → `ROLE_MODEL_DEFAULTS`
- **Pricing defaults**: defined in `src/config/pricing.py` (`gpt-5*` and `gpt-4.1*`)
- **Per-model pricing overrides**:
  `OPENAI_PRICE_INPUT_PER_1M_<MODEL>` and `OPENAI_PRICE_OUTPUT_PER_1M_<MODEL>`
  (example: `OPENAI_PRICE_INPUT_PER_1M_GPT_5_MINI`)
- **Web search call pricing overrides**:
  `OPENAI_PRICE_WEB_SEARCH_PREVIEW_REASONING_PER_1K_CALLS` and
  `OPENAI_PRICE_WEB_SEARCH_PREVIEW_NON_REASONING_PER_1K_CALLS`
- **Strict profile loading**: `LIQUISTO_STRICT_PROFILE_LOADING=1` disables silent fallback for department source profiles and policies (raises on missing/malformed file)
- **Query resolver verify mode**: `LIQUISTO_QUERY_RESOLVER_VERIFY=1` runs both the resolver and legacy path in parallel and logs divergence (migration monitoring)
- **Max retries**: `LIQUISTO_MAX_TASK_RETRIES` env var (default: 3)
- **Token budgets**: `LIQUISTO_SOFT_TOKEN_BUDGET` and `LIQUISTO_HARD_TOKEN_CAP` env vars
- **Phase budgets**: `LIQUISTO_FIRST_PASS_TOKEN_BUDGET`, `LIQUISTO_CLOSURE_TOKEN_BUDGET`, `LIQUISTO_OPTIONAL_DEPTH_TOKEN_BUDGET`
- **Streamlit**: `.streamlit/config.toml`

## Validation

```bash
python preflight.py   # environment, packages, project files, API key, import chain, port
pytest                # unit tests (400+ tests covering behavior, negative paths, golden traces, query parity, query consistency)
```

Dependency policy:

- `requirements.txt` defines the direct dependency constraints.
- `requirements.lock` is the reproducible, transitive install/audit/SBOM input
  used by CI.
- Regenerate the lockfile after dependency changes with:

```bash
uv pip compile requirements.txt --python-version 3.12 --universal --output-file requirements.lock
```

### Local pre-commit checks

```bash
pip install pre-commit
python scripts/setup_local_pre_commit.py
pre-commit run --all-files
```

If local hooks do not trigger, `core.hooksPath` is usually pointing to a stale
path. The setup script resets local `core.hooksPath` to Git default behavior
(`.git/hooks`) and reinstalls `pre-commit`.

During execution, each gate prints live status as:

- `=== [gate_index/total] gate-name ===`
- `[gate-name step/steps] $ <command>`
- `[SUCCESS|FAILURE] gate-name (seconds)`

Manual single-file check:

```bash
ruff check src/pipeline_runner.py --fix
mypy src/pipeline_runner.py
bandit src/pipeline_runner.py
```

## Release Artifact

The release artifact is an OCI image published to GitHub Container Registry:

```bash
docker build --platform linux/amd64 -t liquisto-department-runtime:local .
```

Release/tag workflows publish `ghcr.io/<owner>/<repo>` and bind both SLSA Build
L2 provenance and the CycloneDX SBOM to the image digest with GitHub artifact
attestations. Consumers should pull by digest and verify attestations with
`gh attestation verify` before deployment.
