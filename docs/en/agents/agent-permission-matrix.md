# Agent Permission Matrix

> Language: `en`
> Path: `agents/agent-permission-matrix.md`

## Purpose

This document records the runtime permissions for Liquisto Department Runtime
agents. It mirrors the implemented role boundaries in `src/orchestration/tool_policy.py`,
`src/orchestration/department_runtime.py`, and `src/orchestration/speaker_selector.py`.

The matrix is a governance view. The executable source remains authoritative.

## Permission Principles

- The `Supervisor` is the only control-plane role.
- Domain interpretation, evidence review, retry decisions, and judge decisions
  stay inside the assigned department.
- Department groups are bounded AG2 GroupChats. They may collaborate internally,
  but their external output is a validated `DepartmentPackage`, not raw chat.
- Tool grants are explicit per role and, where needed, per task.
- Long-term memory may store process patterns only. Run-specific facts stay in
  the run brain for the `run_id`.

## Runtime Roles

| Role | Control scope | Read access | Write access | Tools |
| --- | --- | --- | --- | --- |
| `Supervisor` | Intake, routing, run state, package admission, follow-up routing | Intake, run context, department packages, answer matrix | `RunContext.active_tasks`, package admission envelopes, resolution state, status messages | `website_snapshot`, `search` for intake normalization |
| `CompanyDepartment` | Company research department container | Department assignment, supervisor brief, department KB, run working set | `DepartmentPackage`, department run state, evidence packets, gap candidates, answer matrix updates | none directly |
| `MarketDepartment` | Market research department container | Same as above | Same as above | none directly |
| `BuyerDepartment` | Buyer and redeployment department container | Same as above | Same as above | none directly |
| `ContactDepartment` | Contact intelligence department container | Same as above plus approved buyer candidates where available | Same as above for contact intelligence | none directly |
| `SynthesisDepartment` | Cross-domain interpretation | Approved department report segments, quality review, memory snapshot | `synthesis` package | AG2-internal synthesis tools only as implemented |
| `ReportWriter` | Report assembly | Finalized `pipeline_data`, run context, final briefing artifacts | `run_context.report_package` | LLM report composition when API key is available |

## Department Group Roles

Each domain department contains these five AG2 `ConversableAgent` roles.

| Role pattern | Primary responsibility | Tool grant | May decide task outcome? | May write persistent run artifacts? |
| --- | --- | --- | --- | --- |
| `<Department>Lead` | Operationalize the contract, steer the group, enforce completion, finalize package | `finalize_package` | yes, by storing lead acceptance or routing judge decisions | yes, through package finalization and `DepartmentRunState` |
| `<Department>Researcher` | Gather evidence and produce task-level findings | `search`, `page_fetch`, `llm_structured` | no | indirectly through `TaskArtifact` |
| `<Department>Critic` | Review evidence quality and identify defects | none | no, produces review recommendation | indirectly through `TaskReviewArtifact` |
| `<Department>Judge` | Resolve borderline cases after retry or escalation | `judge_decision` | yes | indirectly through `TaskDecisionArtifact` |
| `<Department>CodingSpecialist` | Refine blocked queries, parsing, and recovery tactics | `query_refinement` | no | indirectly through strategy-change records |

## Task-Level Tool Grants

Implemented task overrides grant research tools only to researchers and query
refinement only to coding specialists.

| Role | Task keys | Allowed tools |
| --- | --- | --- |
| `Supervisor` | `intake_normalization` | `website_snapshot`, `search` |
| `CompanyResearcher` | `company_fundamentals`, `economic_commercial_situation`, `product_asset_scope` | `search`, `page_fetch`, `llm_structured` |
| `MarketResearcher` | `market_situation` | `search`, `page_fetch`, `llm_structured` |
| `BuyerResearcher` | `peer_companies`, `monetization_redeployment` | `search`, `page_fetch`, `llm_structured` |
| `ContactResearcher` | `contact_discovery`, `contact_qualification` | `search`, `page_fetch`, `llm_structured` |
| Department coding specialists | `query_refinement` | `query_refinement` |

## Explicit Non-Permissions

| Actor | Not permitted |
| --- | --- |
| `Supervisor` | No domain-level fact interpretation, evidence review, intra-department retry, intra-department judging, or hidden participation in department review loops |
| Department leads | No control over other departments, no write access to long-term memory as case facts, no `request_supervisor_revision` tool |
| Researchers | No package admission decisions, no final task decisions, no direct long-term memory writes |
| Critics | No external research tools and no final control-plane decision |
| Judges | No research tools and no control-plane authority beyond the escalated task decision |
| Coding specialists | No evidence acceptance, no package admission, no direct search/fetch grant unless explicitly implemented later |
| `ReportWriter` | No research authority and no mutation of department packages or evidence history |

## Memory Access

| Memory area | Contents | Writers | Readers |
| --- | --- | --- | --- |
| Run brain in `run_context.json` | Case-specific artifacts, packages, evidence, gaps, decisions, usage, follow-ups | Supervisor loop, department runtime, report runtime, exporter | Follow-up resolver, UI, export layer |
| `memory_snapshot.json` | Exported short-term memory snapshot | exporter | operators, tests, follow-up diagnostics |
| Long-term process memory | Scrubbed process patterns only | `consolidate_role_patterns()` after successful usable runs | active retrievable roles at run start |

## Guardrails

The department speaker selector is guardrail-only:

1. tool calls route to the executor,
2. executor output returns to the Lead,
3. repeated non-Lead text loops return to the Lead,
4. termination routes correctly.

It does not encode a hidden workflow. The Lead drives the department through
explicit messages and the task contract.
