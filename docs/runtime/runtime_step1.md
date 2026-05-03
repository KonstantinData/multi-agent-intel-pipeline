# Runtime Step 1: Intake + Supervisor Brief

This file explains the step shown in `docs/drawio/runtime_step1.drawio` in a precise, code-level way.

## Goal of Step 1

Starting from minimal input (`company_name`, `web_domain`), Step 1 creates a reliable runtime entry state:

1. formal intake object
2. normalized domain context for the run
3. `SupervisorBrief` as the domain-agnostic starting context
4. `supervisor_message` with status `ready_for_department_routing`

Step 1 ends **before** department orchestration (`run_supervisor_loop(...)`).

## Involved Scripts

- `src/pipeline_runner.py` → `run_pipeline(...)`
- `src/domain/intake.py` → `IntakeRequest`, `SupervisorBrief`
- `src/research/normalize.py` → `normalize_domain(...)`, `homepage_url(...)`
- `src/agents/supervisor.py` → `SupervisorAgent.build_intake_brief(...)`
- `src/research/tools.py` → `build_company_research(...)`
- `src/research/fetch.py` → `fetch_website_snapshot(...)`
- `src/research/extract.py` → `infer_company_identity(...)`, `infer_industry(...)`, `summarize_visible_text(...)`

## Exact Flow

1. **Input enters the runner**
   - `run_pipeline(company_name, web_domain, ...)` is called.
   - `run_id` and `run_dir` are created.

2. **Intake contract is created**
   - `IntakeRequest(company_name, web_domain)` is instantiated.
   - `language` defaults to `"de"` (`IntakeRequest.language`).

3. **RunContext is initialized**
   - `run_context.intake = {"company_name", "web_domain", "language"}`.
   - Long-term memory store is initialized.
   - Strategy retrieval uses normalized domain:
     - `retrieve_strategies(..., domain=normalize_domain(web_domain), limit=5)`
     - plus role-specific strategy retrieval for runtime roles.

4. **Supervisor builds the intake brief**
   - `agents["supervisor"].build_intake_brief(intake)` is called.
   - Core subcall: `build_company_research(intake.web_domain, intake.company_name)`.

5. **Research helpers produce input signals**
   - `normalize_domain(...)` standardizes the host/domain (scheme + `www.` cleanup, lowercase).
   - `homepage_url(...)` builds `https://<domain>`.
   - `fetch_website_snapshot(...)` fetches website/PDF snapshot and extracts:
     - `reachable`, `title`, `meta_description`, `visible_text`, `content_type`, `is_pdf`.
   - `infer_company_identity(...)` derives:
     - `verified_company_name`, `verified_legal_name`, `name_confidence`.
   - `summarize_visible_text(...)` creates a compact homepage excerpt.

6. **SupervisorBrief is assembled**
   - `SupervisorBrief` includes, among others:
     - submitted + verified company/domain
     - `normalized_domain`
     - `website_reachable`
     - `page_title`, `meta_description`, `raw_homepage_excerpt`
     - `industry_hint` from `infer_industry(title, description, summary)`
     - `observations` and `sources` (initial owned source from target site)

7. **Runtime message payload is produced**
   - `supervisor_message = {`
     - `"section": "supervisor_brief"`,
     - `"payload": asdict(brief)`,
     - `"status": "ready_for_department_routing"`
     - `}`

8. **Step-1 state is persisted into the run context**
   - `run_context.supervisor_brief = supervisor_message["payload"]`
   - `question_registry` and `answer_matrix` are initialized
   - Supervisor message is emitted into the message stream

## Output of Step 1

- **Object 1:** `brief: SupervisorBrief` (typed internal start context)
- **Object 2:** `supervisor_message` (serializable runtime payload)
- **Object 3:** `run_context` ready for routing in Step 2

## What Step 1 Explicitly Does Not Do

- no department execution
- no task review/judge decisions
- no synthesis
- no report assembly

These begin in the next step with `run_supervisor_loop(...)`.
