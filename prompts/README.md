# Prompt Packs for Repository Specialists

This directory contains one prompt pack per specialist role defined in the repository architecture roadmap.

Source of roles:
- docs/en/architecture/EU-Compliant-Roadmap-for-MAS.md (Section 3.1 Responsibilities)

## Prompt architecture (Codex GPT-5.3 aligned)

Each pack follows a strict structure that maps to Codex best-practice prompting:
- Goal: explicit task objective
- Context: explicit repository scope and evidence sources
- Constraints: hard rules, non-goals, and enforcement boundaries
- Done when: acceptance criteria and gate decision conditions

Each role folder includes:
- RoleProfile.md
- SystemPrompt.md
- Template.md

## Start workflow

Use these files for every new task:
- START_SCRIPT.md
- MULTI_ROLE_TASK_TEMPLATE.md
- ROLE_ROUTING_RULES.md
- CODE_REVIEW_CHECKLIST.md

Automation script:
- scripts/init_multi_role_task.ps1 generates prompts/current-task.md with auto-selected specialist roles and conflict order.

## Roles

| Role | Folder | Gate |
| --- | --- | --- |
| Product Owner | product-owner | Requirements Gate |
| AI Compliance Owner | ai-compliance-owner | AI Risk Gate |
| Security Architect | security-architect | Security Gate |
| Data Protection Officer | data-protection-officer | Privacy Gate |
| Model Privacy Owner | model-privacy-owner | Model Privacy Gate |
| Agent Security Owner | agent-security-owner | Agent Security Gate |
| License Owner | license-owner | License Gate |
| Human Reviewer | human-reviewer | Human Approval Gate |
| Code Reviewer | code-reviewer | Code Review Gate |
| Release Manager | release-manager | Release Gate |
| Audit Owner | audit-owner | Audit Gate |
| Maintainer | maintainer | Quality Gate |
