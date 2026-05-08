# Role Routing Rules

These rules define which specialists are required for a task.

## 1) Derive roles from scope

- docs/en/security, policies, .github/workflows, scripts, bom -> security-architect
- docs/en/ai-act, docs/en/ai-governance -> ai-compliance-owner
- docs/en/privacy -> data-protection-officer
- docs/en/models -> model-privacy-owner
- docs/en/agents, policies/rego -> agent-security-owner
- docs/en/licenses, bom -> license-owner
- docs/en/audit -> audit-owner
- release artifacts or release workflows -> release-manager
- critical agent decisions or human oversight requirements -> human-reviewer
- code quality/maintainability/readability/refactoring risks -> code-reviewer
- product/use-case/requirements definitions -> product-owner
- code/tests/scripts/CI implementation work -> maintainer

## 2) Derive roles from task keywords

Keyword examples:
- Security: security, threat, devsecops, owasp, rego, policy
- Compliance: ai act, compliance, risk class, governance
- Privacy: gdpr, dpia, pii, data subject, tom
- Model Privacy: model routing, eu hosted, provider, inference route
- Agent Security: agent communication, zero trust, tool rights, signed messages
- License: license, oss, dataset license, prompt license
- Release: release, signing, attestation, artifact
- Audit: audit trail, evidence retention, archiving
- Human Review: critical decision, human approval, escalation
- Code Review: code review, readability, maintainability, refactor risk, complexity
- Product: use case, requirements, product goal
- Maintainer: implementation, bugfix, tests, refactor

## 3) Target-state required roles

- Baseline: at least code-reviewer, maintainer
- Release-ready: at least security-architect, ai-compliance-owner, release-manager, code-reviewer, maintainer
- Audit-ready: at least audit-owner, ai-compliance-owner, security-architect, code-reviewer, maintainer

## 4) Dynamic expansion during execution

If new evidence appears, add roles immediately:
- new security findings or new policies/.github/workflows impact -> add security-architect
- new privacy/PII impact -> add data-protection-officer
- new model route/provider decision -> add model-privacy-owner
- new agent-to-agent/tool-permission concerns -> add agent-security-owner
- new license/BOM impact -> add license-owner
- new audit/retention requirement -> add audit-owner
- new release/signature concern -> add release-manager
- critical autonomous decision -> add human-reviewer
- maintainability or readability regressions -> add code-reviewer

## 5) Conflict priority for gate decisions

Default order:
1. security-architect
2. ai-compliance-owner
3. release-manager
4. data-protection-officer
5. model-privacy-owner
6. agent-security-owner
7. license-owner
8. audit-owner
9. human-reviewer
10. code-reviewer
11. product-owner
12. maintainer
