# Git Hooks

Repository-local Git hooks.

- `pre-push`: runs `.codex/scripts/run_pre_pr_gates.py --fail-fast` and blocks push on failure.

Enable once per clone:

```bash
git config core.hooksPath .githooks
```
