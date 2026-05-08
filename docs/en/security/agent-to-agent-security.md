# Agent To Agent Security

> Language: `en`
> Path: `security/agent-to-agent-security.md`

## Purpose

This document defines security expectations for communication between runtime
agents. It reflects the bounded AG2 department architecture and the
guardrail-only selector model.

## Security Model

The runtime separates:

- control plane: `Supervisor`;
- research plane: Company, Market, Buyer, and Contact departments;
- synthesis plane: Synthesis Department;
- report node: `ReportWriter`.

The Supervisor coordinates assignments and package admission. It does not join
department retry/review loops. Departments collaborate internally and return a
validated `DepartmentPackage`.

## Agent-to-Agent Boundaries

| Boundary | Allowed communication | Security requirement |
| --- | --- | --- |
| Supervisor to department | Assignment contract, supervisor brief, task list | No hidden override of department review loop |
| Department Lead to Researcher | Task execution request | Must use assigned task key and department scope |
| Researcher to Lead | Research result / tool output | Must be recorded as `TaskArtifact` |
| Lead to Critic | Review request | Must reference a specific task attempt |
| Critic to Lead | Review result | Must be recorded as `TaskReviewArtifact` |
| Lead to Judge | Escalation request | Only for borderline or retry-exhausted cases |
| Judge to Lead | Decision | Must be recorded as `TaskDecisionArtifact` |
| Lead to Coding Specialist | Query or parsing recovery request | Must not grant broader research authority |
| Departments to Synthesis | Approved package segments | Only downstream-visible package content |
| ReportWriter | Final artifacts only | No research or package mutation authority |

## Prompt Injection Controls

Public sources can contain adversarial instructions. Agents must treat fetched
content and search snippets as evidence, not as instructions.

Controls:

- system and role prompts define authority above source content;
- source text should be summarized into evidence artifacts;
- tool grants are role-limited;
- package finalization uses stored artifacts and decisions;
- source claims require evidence quality review.

## Speaker Selector Guardrails

The department speaker selector may route turns for safety and liveness only:

1. tool calls route to executor,
2. executor output returns to Lead,
3. repeated non-Lead text loops return to Lead,
4. termination routes correctly.

It must not become a hidden state machine for task workflow. Workflow ownership
belongs to the Lead.

## Tool-Call Security

- Only researchers receive `search`, `page_fetch`, and `llm_structured`.
- Only coding specialists receive `query_refinement`.
- Critics and judges do not receive web research tools.
- Department container roles do not directly receive tools.
- `request_supervisor_revision` is not a registered department tool.

## Artifact Integrity

Task state must flow through typed artifacts:

- `TaskArtifact`
- `TaskReviewArtifact`
- `TaskDecisionArtifact`
- `DepartmentRunState`

Downstream components should read these artifacts and package admission
envelopes rather than infer state from chat text.

## Failure Handling

If an agent loop, malformed tool call, or unsupported task state occurs:

- return control to the Department Lead where possible;
- record the gap or blocker;
- downgrade or block the affected package rather than silently accepting it;
- persist the status in run artifacts.

## Review Checklist

Before adding a new agent-to-agent path:

- define the sender, receiver, and artifact written;
- define the role's allowed tools;
- verify the Supervisor boundary remains intact;
- add or update tests for selector behavior and contract artifacts;
- update this document and `docs/en/agents/agent-permission-matrix.md`.
