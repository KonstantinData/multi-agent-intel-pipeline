# Git Hooks

Repository-local Git hooks.

Available hooks:

1. `pre-commit`: runs `.codex/compliance/scripts/check_compliance_policies.py --changed-only` for all relevant changed files in the working tree, including ignored files under `.codex/compliance`.

Enable repository-local hooks once:

```bash
git config core.hooksPath .githooks
```
