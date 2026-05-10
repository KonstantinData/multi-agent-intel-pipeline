# Start Script for Every New Task

This document is the mandatory entrypoint for every new task.

## 1) Extract input from user request

Required fields:
- Task
- Target State (Baseline | Release-ready | Audit-ready)
- Scope
- Blocking Threshold (P0 | P0+P1 | All)

If a required field is missing, apply safe defaults:
- Target State: Baseline
- Scope: Full repository
- Blocking Threshold: P0

## 2) Auto-select specialists

Roles are selected from:
- scope paths
- task keywords
- target-state requirements

Rules are defined in ROLE_ROUTING_RULES.md.

## 3) Generate task file

```powershell
pwsh -File scripts/init_multi_role_task.ps1 -Task "<task title/description>" -TargetState Baseline -Scope "Full repository" -BlockingThreshold P0
```

Generated output:
- prompts/current-task.md

## 4) Mandatory execution model

Each task is executed from prompts/current-task.md with:
- one shared specialist plan
- gate rules
- conflict priority
- code review evidence via CODE_REVIEW_CHECKLIST.md
- consolidated final report

## 5) Dynamic role expansion during execution

If new risks or scope areas are discovered, additional roles are added without requiring a new user task.

Mandatory rule:
- Document each added role in the running report as: Added during execution.
- Extend the specialist plan and continue execution.
