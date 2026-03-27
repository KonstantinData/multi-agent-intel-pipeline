# Test Architecture

## Canonical Rule

> **`pytest tests/` is the single source of truth.**
> No test files may exist outside `tests/`. CI and local runs execute the same surface.

## Layers

### 1. Architecture / Contract Tests (`tests/architecture/`)

**No AG2/autogen dependency.** Validates:

- Runtime contracts (TaskArtifact, TaskReviewArtifact, TaskDecisionArtifact, DepartmentRunState)
- Allowed state transitions, terminal/non-terminal outcomes, dependency satisfaction
- Memory boundaries (ShortTermMemoryStore, consolidation, merge, isolation)
- Serialization round-trips
- Selector guardrail behavior (MagicMock fakes, not real AG2 agents)
- Package assembly and finalization from stored decisions
- Follow-up evidence selection and department answer routing
- Task backlog contract fields, validation rules, dependency graph
- Critic evaluator, Judge gate, contract violation signals
- Supervisor routing (weighted keyword scoring)
- Supervisor acceptance gates (F2 department, F3 synthesis)
- Synthesis context building
- Section assembly via Pydantic models
- Run condition evaluation (including F2 envelope format)
- Config defaults
- Role memory registry consistency (F6)
- Vocabulary consistency across layers (F7)

### 2. Integration / Runtime Tests (`tests/integration/`)

**Requires AG2/autogen.** Auto-skipped if AG2 is not installed. Validates:

- Real AG2 GroupChat tool closures with monkeypatched LLM
- Department end-to-end flows (Company, Contact)
- SynthesisDepartmentAgent with mocked packages
- Fallback package assembly on max_round
- CHG-03 compliance (no supervisor in department loop)
- Shared search cache across departments
- Assignment contract field propagation

### 3. Smoke Tests (`tests/smoke/`)

Lightweight sanity checks:

- Preflight API key loading
- Port status detection
- Module importability (verifies architecture-layer modules load without AG2)
- Dependency graph validity (F4)
- No top-level test files outside `tests/` (F8 guard)

## What is NOT part of the default test surface

| Check | Location | How to run |
|-------|----------|-----------|
| Heavy E2E pipeline test | `scripts/manual_validation/test_pipeline.py` | `pytest scripts/manual_validation/test_pipeline.py` (requires OpenAI key) |
| Streamlit startup test | `scripts/manual_validation/test_startup.py` | `python scripts/manual_validation/test_startup.py` (requires running Streamlit) |

These are **manual/credentialed validation** scripts, not part of `pytest tests/`.

## Running Tests

```bash
# All default tests (the canonical surface)
pytest tests/

# Architecture/contract tests only (no AG2 needed)
pytest tests/architecture

# Integration tests only (requires AG2)
pytest tests/integration

# Smoke tests only
pytest tests/smoke

# Exclude integration tests (CI without AG2)
pytest tests -m "not integration"
```

## CI Configuration

CI must execute `pytest tests/` explicitly. Do not rely on bare `pytest` without
`testpaths` — always specify the canonical test root.

## Markers

| Marker | Applied to | Meaning |
|--------|-----------|---------| 
| `architecture` | `tests/architecture/` | Pure structure/contract tests |
| `contract` | `tests/architecture/` | Contract validation (alias) |
| `integration` | `tests/integration/` | Requires AG2/autogen runtime |
| `runtime` | `tests/integration/` | Requires runtime dependencies |
| `smoke` | `tests/smoke/` | Lightweight sanity checks |
