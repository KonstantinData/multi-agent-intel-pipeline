"""Smoke tests for preflight and basic importability.

NO AG2/autogen dependency.
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import preflight


class _OkHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        return


def test_load_openai_api_key_rejects_empty_or_commented_value(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LIQUISTO_ALLOW_DOTENV_SECRETS", "1")
    monkeypatch.setattr("src.config.settings._keyring_lookup", lambda service, account: "")
    monkeypatch.setattr("src.config.settings._dotenv_lookup", lambda: {"OPENAI_API_KEY": ""})
    with pytest.raises(ValueError):
        preflight._load_openai_api_key()


def test_load_openai_api_key_accepts_env_file_only_when_explicitly_allowed(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LIQUISTO_ALLOW_DOTENV_SECRETS", "1")
    monkeypatch.setattr("src.config.settings._keyring_lookup", lambda service, account: "")
    monkeypatch.setattr("src.config.settings._dotenv_lookup", lambda: {"OPENAI_API_KEY": "test-key"})
    key, source = preflight._load_openai_api_key()
    assert key == "test-key"
    assert source == ".env explicit fallback"


def test_load_openai_api_key_ignores_env_file_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LIQUISTO_ALLOW_DOTENV_SECRETS", raising=False)
    monkeypatch.setattr("src.config.settings._keyring_lookup", lambda service, account: "")
    monkeypatch.setattr("src.config.settings._dotenv_lookup", lambda: {"OPENAI_API_KEY": "file-key"})
    with pytest.raises(ValueError):
        preflight._load_openai_api_key()


def test_load_openai_api_key_prefers_process_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "process-key")
    monkeypatch.setattr("src.config.settings._dotenv_lookup", lambda: {"OPENAI_API_KEY": "file-key"})
    key, source = preflight._load_openai_api_key()
    assert key == "process-key"
    assert source == "environment"


def test_load_openai_api_key_reads_os_keyring_before_env_file(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LIQUISTO_ALLOW_DOTENV_SECRETS", "1")
    monkeypatch.setattr("src.config.settings._keyring_lookup", lambda service, account: "keyring-key")
    monkeypatch.setattr("src.config.settings._dotenv_lookup", lambda: {"OPENAI_API_KEY": "file-key"})
    key, source = preflight._load_openai_api_key()
    assert key == "keyring-key"
    assert source == "keyring:liquisto-department-runtime/OPENAI_API_KEY"


def test_port_status_accepts_reachable_local_http_service():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status = preflight._port_status(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert "reachable local http service" in status.lower()


def test_pure_modules_importable():
    """Verify that architecture-layer modules can be imported without AG2."""
    import src.orchestration.contracts
    import src.orchestration.follow_up
    import src.orchestration.task_router
    import src.orchestration.tool_policy
    import src.orchestration.synthesis
    import src.orchestration.run_context
    import src.memory.short_term_store
    import src.memory.consolidation
    import src.memory.policies
    import src.models.registry
    import src.models.schemas
    import src.app.use_cases
    import src.domain.intake
    import src.agents.critic
    import src.agents.judge
    import src.agents.supervisor
    import src.agents.specs
    import src.agents.registry
    import src.orchestration.speaker_selector


def test_dependency_graph_is_valid():
    """F4/Patch 0: All depends_on references must exist as task_keys."""
    from src.app.use_cases import STANDARD_TASK_BACKLOG
    all_keys = {t["task_key"] for t in STANDARD_TASK_BACKLOG}
    for task in STANDARD_TASK_BACKLOG:
        for dep in task["depends_on"]:
            assert dep in all_keys, (
                f"Task '{task['task_key']}' depends on unknown task_key '{dep}'. "
                f"Known keys: {sorted(all_keys)}"
            )


def test_dependency_graph_has_no_cycles():
    """F4/Patch 0: The dependency graph must be a DAG (no cycles)."""
    from src.app.use_cases import STANDARD_TASK_BACKLOG
    deps = {t["task_key"]: list(t["depends_on"]) for t in STANDARD_TASK_BACKLOG}

    visited: set[str] = set()
    in_stack: set[str] = set()

    def _visit(key: str) -> None:
        if key in in_stack:
            raise AssertionError(f"Cycle detected involving '{key}'")
        if key in visited:
            return
        in_stack.add(key)
        for dep in deps.get(key, []):
            _visit(dep)
        in_stack.discard(key)
        visited.add(key)

    for k in deps:
        _visit(k)


def test_no_toplevel_test_files():
    """F8: No test files may exist outside tests/."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    # Check project root for test_*.py and *_test.py
    root_tests = list(root.glob("test_*.py")) + list(root.glob("*_test.py"))
    assert not root_tests, (
        f"Top-level test files found outside tests/: {[f.name for f in root_tests]}. "
        "Move to tests/ or scripts/manual_validation/."
    )
    # Check src/ and ui/ for stray test files
    for subdir in ("src", "ui"):
        d = root / subdir
        if d.exists():
            stray = list(d.rglob("test_*.py")) + list(d.rglob("*_test.py"))
            assert not stray, (
                f"Test files found in {subdir}/: {[str(f.relative_to(root)) for f in stray]}. "
                "Move to tests/."
            )


def test_report_writer_exists_as_runtime_agent():
    """ReportWriterAgent must exist as a runtime agent class."""
    import importlib
    mod = importlib.import_module("src.agents.report_writer")
    assert hasattr(mod, "ReportWriterAgent"), "ReportWriterAgent class is missing."


def test_pipeline_runner_requires_report_writer_agent():
    """pipeline_runner should access agents['report_writer'] for report assembly."""
    import inspect
    from src import pipeline_runner
    source = inspect.getsource(pipeline_runner.run_pipeline)
    assert 'agents["report_writer"]' in source or "agents['report_writer']" in source


def test_supervisor_loop_returns_named_tuple():
    """F10: run_supervisor_loop must return a SupervisorLoopResult NamedTuple."""
    from src.orchestration.supervisor_loop import SupervisorLoopResult
    assert hasattr(SupervisorLoopResult, '_fields')
    assert 'sections' in SupervisorLoopResult._fields
    assert 'department_packages' in SupervisorLoopResult._fields
    assert 'messages' in SupervisorLoopResult._fields
    assert 'completed_backlog' in SupervisorLoopResult._fields
    assert 'department_timings' in SupervisorLoopResult._fields


def test_acceptance_methods_return_typed_dicts():
    """F10: Supervisor acceptance methods must use TypedDict return types."""
    from src.agents.supervisor import DepartmentAcceptanceResult, SynthesisAcceptanceResult
    # TypedDicts have __annotations__
    assert 'decision' in DepartmentAcceptanceResult.__annotations__
    assert 'accepted_tasks' in DepartmentAcceptanceResult.__annotations__
    assert 'decision' in SynthesisAcceptanceResult.__annotations__
    assert 'generation_mode' in SynthesisAcceptanceResult.__annotations__


# ---------------------------------------------------------------------------
# P2-3: DAG / Phase invariants — config-driven
# ---------------------------------------------------------------------------

# Canonical phase configuration — single source of truth for test assertions.
# If the runtime phasing changes, update this mapping and the tests will catch drift.
_PHASE_CONFIG = {
    "parallel": {"CompanyDepartment", "MarketDepartment"},
    "sequential": ["BuyerDepartment", "ContactDepartment"],
}

_DEPARTMENT_TASK_OWNERSHIP = {
    "CompanyDepartment": {
        "company_fundamentals",
        "economic_commercial_situation",
        "financial_deep_dive",
        "product_asset_scope",
        "transaction_event_intelligence",
    },
    "MarketDepartment": {"market_situation"},
    "BuyerDepartment": {"peer_companies", "monetization_redeployment"},
    "ContactDepartment": {"contact_discovery", "target_company_contacts", "contact_qualification"},
    "SynthesisDepartment": {"liquisto_opportunity_assessment", "negotiation_relevance"},
}


def test_phase_invariants_match_backlog():
    """P2-3: All research tasks must belong to exactly one department."""
    from src.app.use_cases import STANDARD_TASK_BACKLOG
    all_owned = set()
    for dept, keys in _DEPARTMENT_TASK_OWNERSHIP.items():
        overlap = all_owned & keys
        assert not overlap, f"Tasks {overlap} assigned to multiple departments"
        all_owned |= keys
    backlog_keys = {t["task_key"] for t in STANDARD_TASK_BACKLOG}
    unowned = backlog_keys - all_owned
    assert not unowned, f"Tasks {unowned} not assigned to any department in phase config"


def test_parallel_departments_have_no_cross_dependencies():
    """P2-3: Parallel departments must not depend on each other's tasks."""
    from src.app.use_cases import STANDARD_TASK_BACKLOG
    parallel_tasks = set()
    for dept in _PHASE_CONFIG["parallel"]:
        parallel_tasks |= _DEPARTMENT_TASK_OWNERSHIP.get(dept, set())
    for task in STANDARD_TASK_BACKLOG:
        if task["task_key"] in parallel_tasks:
            for dep in task["depends_on"]:
                # dep must be either in the same department or have no department (root)
                dep_dept = None
                for d, keys in _DEPARTMENT_TASK_OWNERSHIP.items():
                    if dep in keys:
                        dep_dept = d
                        break
                if dep_dept and dep_dept in _PHASE_CONFIG["parallel"]:
                    task_dept = None
                    for d, keys in _DEPARTMENT_TASK_OWNERSHIP.items():
                        if task["task_key"] in keys:
                            task_dept = d
                            break
                    assert dep_dept == task_dept, (
                        f"Parallel cross-dependency: {task['task_key']} ({task_dept}) "
                        f"depends on {dep} ({dep_dept})"
                    )


def test_sequential_departments_respect_order():
    """P2-3: Sequential departments must only depend on earlier phases."""
    from src.app.use_cases import STANDARD_TASK_BACKLOG
    sequential = _PHASE_CONFIG["sequential"]
    for i, dept in enumerate(sequential):
        dept_tasks = _DEPARTMENT_TASK_OWNERSHIP.get(dept, set())
        for task in STANDARD_TASK_BACKLOG:
            if task["task_key"] not in dept_tasks:
                continue
            for dep in task["depends_on"]:
                # dep must not be in a later sequential department
                for j in range(i + 1, len(sequential)):
                    later_dept = sequential[j]
                    later_tasks = _DEPARTMENT_TASK_OWNERSHIP.get(later_dept, set())
                    assert dep not in later_tasks, (
                        f"Backward dependency: {task['task_key']} ({dept}) "
                        f"depends on {dep} ({later_dept}) which runs later"
                    )


# ---------------------------------------------------------------------------
# P2-1: Guard — no CrossDomainStrategicAnalyst references remain
# ---------------------------------------------------------------------------

def test_no_cross_domain_strategic_analyst_references():
    """P2-1: CrossDomainStrategicAnalyst must not appear in any active registry."""
    from src.config.settings import ROLE_MODEL_DEFAULTS, ROLE_STRUCTURED_MODEL_DEFAULTS
    from src.orchestration.tool_policy import BASE_TOOL_POLICY, TASK_TOOL_OVERRIDES
    from src.memory.consolidation import MEMORY_ROLE_STATUS

    assert "CrossDomainStrategicAnalyst" not in ROLE_MODEL_DEFAULTS
    assert "CrossDomainStrategicAnalyst" not in ROLE_STRUCTURED_MODEL_DEFAULTS
    assert "CrossDomainStrategicAnalyst" not in BASE_TOOL_POLICY
    for key in TASK_TOOL_OVERRIDES:
        assert "CrossDomainStrategicAnalyst" not in key[0]
    assert "CrossDomainStrategicAnalyst" not in MEMORY_ROLE_STATUS


# ---------------------------------------------------------------------------
# P1-2: Every AGENT_SPECS role must resolve to a model default
# ---------------------------------------------------------------------------

def test_all_agent_specs_have_model_defaults():
    """P1-2: Every role in AGENT_SPECS must be resolvable in model defaults."""
    from src.agents.specs import AGENT_SPECS
    from src.config.settings import get_role_model_selection
    for role_name in AGENT_SPECS:
        chat, structured = get_role_model_selection(role_name)
        assert chat, f"{role_name} has no chat model"
        assert structured, f"{role_name} has no structured model"


# ---------------------------------------------------------------------------
# P1-3: Guard — input_artifacts must not exist in task backlog
# ---------------------------------------------------------------------------

def test_no_input_artifacts_in_backlog():
    """P1-3: input_artifacts field must not exist in STANDARD_TASK_BACKLOG."""
    from src.app.use_cases import STANDARD_TASK_BACKLOG
    for task in STANDARD_TASK_BACKLOG:
        assert "input_artifacts" not in task, (
            f"Task '{task['task_key']}' still has input_artifacts — "
            "field was removed in P1-3"
        )


# ---------------------------------------------------------------------------
# P0-5: Envelope module must be importable without AG2
# ---------------------------------------------------------------------------

def test_envelope_module_importable():
    """P0-5: envelope.py must be importable as a pure module."""
    import src.orchestration.envelope
