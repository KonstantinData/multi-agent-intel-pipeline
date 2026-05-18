# Codex Scripts

Executable helpers that belong to the `.codex` app-level operating layer.

## Local Git Guards

- `guard_git_branch.py`: hard local branch guard used by `pre-commit` and `pre-push` through the `pre-commit` framework. It blocks commits on local `main`, pushes from local `main`, and direct pushes to remote `main`. Guard failures are recorded as `git_branch_guard_failed` learning events.
- `record_learning_event.py`: single append-only learning-event recorder. It writes to `artifacts/codex-learning/outbox/*.jsonl` first and can best-effort flush events to the MAIP memory worker via `MAIP_MEMORY_BASE_URL` and `MAIP_MEMORY_INGEST_API_TOKEN`.

## PR Lifecycle

- `pr_lifecycle.py`: local/Codex-side PR lifecycle orchestrator. It can create/find PRs, run local pre-PR gates, and by default start PR-check polling every 180 seconds immediately after `create` (`--no-watch-checks` disables this). It records PR failure/recovery events and can run an explicit operator-provided auto-fix command inside a bounded retry loop.
- `run_pre_pr_gates.py`: local pre-PR gate runner mirroring `compliance-security-ai` gate names, with `--resume` and `--resume-from-changes` support, live progress JSON output in `artifacts/pre_pr_gate_progress.json`, and an on-demand `--status` view.

## Config

- `load_config.py`: deterministic bootstrap loader that reads `.codex/config.toml` first, then loads `.codex/config/instruction_index.json` from the configured pointer.

## Operating Model

`.codex` owns rules, policies, and orchestration. Git hooks, GitHub Actions, and GitHub Rulesets are the explicit execution/enforcement entrypoints. Do not reintroduce a second `.githooks` hook system.
