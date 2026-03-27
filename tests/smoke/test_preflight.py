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
    (tmp_path / ".env").write_text("# OPENAI_API_KEY=test\nOPENAI_API_KEY=\n", encoding="utf-8")
    with pytest.raises(ValueError):
        preflight._load_openai_api_key()


def test_load_openai_api_key_accepts_non_empty_env_file(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
    key, source = preflight._load_openai_api_key()
    assert key == "test-key"
    assert source == ".env"


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


def test_report_writer_is_not_a_runtime_agent():
    """F9: ReportWriterAgent must not exist as a runtime agent class."""
    import importlib
    try:
        mod = importlib.import_module("src.agents.report_writer")
        assert not hasattr(mod, "ReportWriterAgent"), (
            "ReportWriterAgent still exists as a class — should have been removed in F9"
        )
    except (ImportError, ModuleNotFoundError):
        pass  # Module removed entirely — correct


def test_pipeline_runner_does_not_require_report_writer_agent():
    """F9: pipeline_runner must not access agents['report_writer']."""
    import inspect
    from src import pipeline_runner
    source = inspect.getsource(pipeline_runner.run_pipeline)
    assert 'agents["report_writer"]' not in source
    assert "agents['report_writer']" not in source


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
