# Test Architecture

The test suite is organized into three layers with clear dependency boundaries.

## Layers

### 1. Architecture / Contract Tests (`tests/architecture/`)

**No AG2/autogen dependency.** These tests validate:

- Runtime contracts (TaskArtifact, TaskReviewArtifact, TaskDecisionArtifact, DepartmentRunState)
- Allowed state transitions and terminal/non-terminal outcomes
- Memory boundaries (ShortTermMemoryStore, consolidation process-safety)
- Serialization round-trips
- Selector guardrail behavior (using MagicMock fakes, not real AG2 agents)
- Package assembly logic and finalization from stored decisions
- Follow-up evidence selection and department answer routing
- Task backlog contract fields and validation rules
- Critic evaluator and Judge gate logic
- Supervisor routing (weighted keyword scoring)
- Synthesis context building
- Section assembly via Pydantic models
- Run condition evaluation
- Config defaults

**Files:**
| File | Scope |
|------|-------|
| `test_contracts.py` | TaskArtifact, TaskReviewArtifact, TaskDecisionArtifact, DepartmentRunState |
| `test_memory.py` | ShortTermMemoryStore, consolidation, memory policies |
| `test_selector.py` | Speaker selector guardrails (MagicMock-based) |
| `test_orchestration.py` | Follow-up, task backlog, critic, judge, routing, synthesis, section assembly |
| `test_follow_up.py` | Follow-up answer routing, long-term store |

### 2. Integration / Runtime Tests (`tests/integration/`)

**Requires AG2/autogen.** Auto-skipped if AG2 is not installed. These tests validate:

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

## Running Tests

```bash
# Architecture/contract tests only (no AG2 needed)
pytest tests/architecture

# Same via markers
pytest tests -m "architecture or contract"

# Integration tests only (requires AG2)
pytest tests/integration

# Smoke tests only
pytest tests/smoke

# All tests
pytest tests

# Exclude integration tests (CI without AG2)
pytest tests -m "not integration"
```

## Markers

| Marker | Applied to | Meaning |
|--------|-----------|---------|
| `architecture` | `tests/architecture/` | Pure structure/contract tests |
| `contract` | `tests/architecture/` | Contract validation (alias) |
| `integration` | `tests/integration/` | Requires AG2/autogen runtime |
| `runtime` | `tests/integration/` | Requires runtime dependencies |
| `smoke` | `tests/smoke/` | Lightweight sanity checks |

## Key Design Decision: `speaker_selector.py`

The speaker selector module uses `TYPE_CHECKING` for the `autogen.ConversableAgent`
import. This means:

- At runtime (when AG2 is installed), the type annotation is available
- At test time (architecture tests), the module can be imported without AG2
- Selector tests use `MagicMock` objects that quack like `ConversableAgent`

## Legacy Test Files

The original root-level test files are deprecated:

| File | Status |
|------|--------|
| `test_contracts.py` | Skipped — migrated to `tests/architecture/` |
| `test_runtime_architecture.py` | Skipped — migrated to `tests/architecture/` + `tests/integration/` |
| `test_integration.py` | Skipped — migrated to `tests/integration/` |
| `test_optimizations.py` | Skipped — migrated to `tests/architecture/` + `tests/integration/` |
| `test_preflight.py` | Skipped — migrated to `tests/smoke/` |
| `test_pipeline.py` | Not yet migrated — run directly with `pytest test_pipeline.py` |
| `test_startup.py` | Not yet migrated — run directly with `python test_startup.py` |

The skipped files contain `pytest.skip(..., allow_module_level=True)` so they
are harmless if accidentally collected. They can be deleted once the team
confirms the new structure.
