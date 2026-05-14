# Liquisto Tasks

This folder contains repository-scoped task definitions for Liquisto.

- `security_gate_regression.toml`: pre-PR security gate regression task.
- `contract_architecture_test_gate.toml`: mandatory architecture and contract test gate for orchestration and knowledge changes.
- `dependency_lock_sbom_license_gate.toml`: mandatory lock, dependency policy, and BOM consistency gate for dependency changes.
- `runtime_bugfix_repro_test_gate.toml`: reproducible-minimal-test-first bugfix workflow for `src/**` changes.
- `release_deploy_readiness_gate.toml`: pre-deploy gate for attestation/SBOM validity, digest consistency, compose env completeness, and security-gate continuity.
- `follow_up_grounding_gate.toml`: enforce follow-up evidence priority and run-brain grounding for follow-up and memory changes.
- `secret_guard_regression_gate.toml`: enforce secret-guard, redaction, and secret-scan regression checks for security-sensitive runtime paths.
