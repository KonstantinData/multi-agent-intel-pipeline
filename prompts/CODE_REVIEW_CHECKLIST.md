# Code Review Checklist (Merge Gate)

Use this checklist for all non-trivial code changes. Every unchecked item is a potential blocker.

## Correctness
- [ ] Functional behavior matches task requirements.
- [ ] Edge cases and error paths are handled explicitly.
- [ ] No hidden state coupling or unintended side effects.

## Maintainability
- [ ] Naming is clear and domain-consistent.
- [ ] Complexity is reasonable for each function/module.
- [ ] Duplication is minimized.
- [ ] Control flow is easy to follow without implicit assumptions.

## Testability
- [ ] New logic is covered by tests.
- [ ] Negative/error scenarios are tested.
- [ ] Tests are deterministic and isolated.

## Quality Gates
- [ ] `ruff check` passes.
- [ ] `mypy` passes.
- [ ] CI workflow gates pass.

## Security and Governance
- [ ] No secrets or unsafe patterns introduced.
- [ ] Workflow/permissions changes remain least-privilege.
- [ ] Required artifacts and schemas remain valid.

## Decision
- [ ] Merge Status: ALLOWED
- [ ] Release Status: ALLOWED
