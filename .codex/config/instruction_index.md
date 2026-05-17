# Instruction Index

Canonical index of instruction sources for `.codex` app-level rule loading.

## Precedence

1. .codex policies
2. .codex config (profiles + routing)
3. .codex task gates
4. .codex skills
5. .codex runtime references
6. .codex memory/eval/telemetry (observational, non-normative)

## Required Startup Confirmation

Pflicht-Startmeldung: Ich habe die .codex-App-Ebene vollständig gelesen und verstanden (Instruction-Index, Policies, Config/Routing, Tasks, Skills, Runtime References). Ich beginne jetzt mit der Ausführung gemäß diesen Regeln und dokumentiere jede Abweichung sofort mit Begründung.

## Groups

### Codex Core Layer

Operating-layer objective, precedence, and trust model.

- [.codex/README.md](.codex/README.md)
- [.codex/config.toml](.codex/config.toml)

### Codex Policies

Hard constraints for secrets, tools, memory, and budgets.

- [.codex/policies/README.md](.codex/policies/README.md)
- [.codex/policies/liquisto/README.md](.codex/policies/liquisto/README.md)
- [.codex/policies/liquisto/data_governance.md](.codex/policies/liquisto/data_governance.md)
- [.codex/policies/liquisto/heuristic_promotion_policy.md](.codex/policies/liquisto/heuristic_promotion_policy.md)
- [.codex/policies/liquisto/memory_retention.md](.codex/policies/liquisto/memory_retention.md)
- [.codex/policies/liquisto/memory_topology.md](.codex/policies/liquisto/memory_topology.md)
- [.codex/policies/liquisto/prompt_budget_policy.md](.codex/policies/liquisto/prompt_budget_policy.md)
- [.codex/policies/liquisto/secret_policy.md](.codex/policies/liquisto/secret_policy.md)
- [.codex/policies/liquisto/tool_allowlist.md](.codex/policies/liquisto/tool_allowlist.md)

### Codex Profiles and Routing

Risk/effort profiles and model/tool routing defaults.

- [.codex/config/README.md](.codex/config/README.md)
- [.codex/config/profiles/liquisto_deep.toml](.codex/config/profiles/liquisto_deep.toml)
- [.codex/config/profiles/liquisto_fast.toml](.codex/config/profiles/liquisto_fast.toml)
- [.codex/config/profiles/liquisto_standard.toml](.codex/config/profiles/liquisto_standard.toml)
- [.codex/config/routing/model_routing.toml](.codex/config/routing/model_routing.toml)
- [.codex/config/routing/tool_routing.toml](.codex/config/routing/tool_routing.toml)

### Codex Task Gates

Executable rule tasks with trigger paths and acceptance criteria.

- [.codex/tasks/README.md](.codex/tasks/README.md)
- [.codex/tasks/liquisto/README.md](.codex/tasks/liquisto/README.md)
- [.codex/tasks/liquisto/contract_architecture_test_gate.toml](.codex/tasks/liquisto/contract_architecture_test_gate.toml)
- [.codex/tasks/liquisto/dependency_lock_sbom_license_gate.toml](.codex/tasks/liquisto/dependency_lock_sbom_license_gate.toml)
- [.codex/tasks/liquisto/follow_up_grounding_gate.toml](.codex/tasks/liquisto/follow_up_grounding_gate.toml)
- [.codex/tasks/liquisto/release_deploy_readiness_gate.toml](.codex/tasks/liquisto/release_deploy_readiness_gate.toml)
- [.codex/tasks/liquisto/runtime_bugfix_repro_test_gate.toml](.codex/tasks/liquisto/runtime_bugfix_repro_test_gate.toml)
- [.codex/tasks/liquisto/secret_guard_regression_gate.toml](.codex/tasks/liquisto/secret_guard_regression_gate.toml)
- [.codex/tasks/liquisto/security_gate_regression.toml](.codex/tasks/liquisto/security_gate_regression.toml)

### Codex Skills

Deterministic execution playbooks for recurring task classes.

- [.codex/skills/README.md](.codex/skills/README.md)
- [.codex/skills/liquisto/README.md](.codex/skills/liquisto/README.md)
- [.codex/skills/liquisto/departments/README.md](.codex/skills/liquisto/departments/README.md)
- [.codex/skills/liquisto/followup/README.md](.codex/skills/liquisto/followup/README.md)
- [.codex/skills/liquisto/security/README.md](.codex/skills/liquisto/security/README.md)
- [.codex/skills/liquisto/supervisor/README.md](.codex/skills/liquisto/supervisor/README.md)
- [.codex/skills/liquisto/synthesis/README.md](.codex/skills/liquisto/synthesis/README.md)
- [.codex/skills/liquisto/testing/README.md](.codex/skills/liquisto/testing/README.md)
- [.codex/skills/shared/README.md](.codex/skills/shared/README.md)
- [.codex/skills/shared/incident/README.md](.codex/skills/shared/incident/README.md)
- [.codex/skills/shared/refactor/README.md](.codex/skills/shared/refactor/README.md)
- [.codex/skills/shared/review/README.md](.codex/skills/shared/review/README.md)

### Codex Runtime References

Runtime-specific references and external memory backend bindings.

- [.codex/runtime/README.md](.codex/runtime/README.md)
- [.codex/runtime/autonomous_runtime_prompt.md](.codex/runtime/autonomous_runtime_prompt.md)
- [.codex/runtime/runtime_memory_reference.json](.codex/runtime/runtime_memory_reference.json)
