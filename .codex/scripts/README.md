# Codex Scripts

Executable helpers that belong to the `.codex` app-level operating layer.

- `run_pre_pr_gates.py`: local pre-PR gate runner mirroring `compliance-security-ai` gate names, with `--resume` and `--resume-from-changes` support, live progress JSON output in `artifacts/pre_pr_gate_progress.json`, and an on-demand `--status` view.
- `load_config.py`: deterministic bootstrap loader that reads `.codex/config.toml` first, then loads `.codex/config/instruction_index.json` from the configured pointer.
