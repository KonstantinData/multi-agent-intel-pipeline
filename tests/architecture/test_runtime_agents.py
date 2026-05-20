"""Architecture tests for the runtime-agent composition contract.

These tests exercise the AG2-light primitives in
`src/orchestration/runtime_agents.py` plus the contract surface of
`src/agents/runtime_factory.py`. Real AG2 instantiation is covered by
`tests/integration/`.
"""
from __future__ import annotations

import threading

import pytest

from src.orchestration.runtime_agents import (
    DEPARTMENT_REQUIRED_METHODS,
    DOMAIN_DEPARTMENT_NAMES,
    FACTORY_VERSION,
    REPORT_WRITER_REQUIRED_METHODS,
    RUNTIME_AGENT_FACTORY_FAILED,
    RUNTIME_COMPOSITION_INVALID,
    SUPERVISOR_REQUIRED_METHODS,
    SYNTHESIS_REQUIRED_METHODS,
    RuntimeAgentFactoryError,
    RuntimeAgents,
    RuntimeAgentSpec,
    RuntimeFactoryConfig,
    SearchCache,
    SearchCacheNamespace,
    runtime_agents_healthcheck,
    validate_runtime_agents,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

class _Role:
    """Minimal duck-typed role exposing every method the validator looks for."""

    def build_intake_brief(self, *a, **kw): return None
    def opening_message(self, *a, **kw): return ""
    def accept_department_package(self, *a, **kw): return {}
    def accept_synthesis(self, *a, **kw): return {}
    def run(self, *a, **kw): return None


def _make_bundle(
    *,
    supervisor=None,
    departments: dict | None = None,
    synthesis=None,
    report_writer=None,
    config: RuntimeFactoryConfig | None = None,
) -> RuntimeAgents:
    cache = SearchCache()
    spec_supervisor = RuntimeAgentSpec(
        role_name="supervisor",
        runtime_type="StubSupervisor",
        required_methods=SUPERVISOR_REQUIRED_METHODS,
    )
    spec_synthesis = RuntimeAgentSpec(
        role_name="synthesis",
        runtime_type="StubSynthesis",
        required_methods=SYNTHESIS_REQUIRED_METHODS,
    )
    spec_report_writer = RuntimeAgentSpec(
        role_name="report_writer",
        runtime_type="StubReportWriter",
        required_methods=REPORT_WRITER_REQUIRED_METHODS,
    )
    deps = (
        departments
        if departments is not None
        else {name: _Role() for name in DOMAIN_DEPARTMENT_NAMES}
    )
    specs = {
        "supervisor": spec_supervisor,
        "synthesis": spec_synthesis,
        "report_writer": spec_report_writer,
    }
    for name in deps:
        specs[name] = RuntimeAgentSpec(
            role_name=name,
            runtime_type="StubDepartment",
            required_methods=DEPARTMENT_REQUIRED_METHODS,
            department_name=name,
        )
    return RuntimeAgents(
        supervisor=supervisor if supervisor is not None else _Role(),
        departments=deps,
        synthesis=synthesis if synthesis is not None else _Role(),
        report_writer=report_writer if report_writer is not None else _Role(),
        search_cache=cache,
        config=config or RuntimeFactoryConfig(),
        specs=specs,
    )


# ── 2.1 Typed contract / backward-compatibility ───────────────────────────────

def test_domain_department_names_is_canonical_tuple() -> None:
    """2.1: the canonical department list is exactly Company, Market, Buyer, Contact."""
    assert DOMAIN_DEPARTMENT_NAMES == (
        "CompanyDepartment",
        "MarketDepartment",
        "BuyerDepartment",
        "ContactDepartment",
    )


def test_runtime_agents_supports_dict_style_access() -> None:
    """2.1: legacy `agents["supervisor"]` access still works for in-flight callers."""
    bundle = _make_bundle()
    assert bundle["supervisor"] is bundle.supervisor
    assert bundle["synthesis"] is bundle.synthesis
    assert bundle["report_writer"] is bundle.report_writer
    assert bundle["departments"] is bundle.departments
    assert bundle.get("departments") is bundle.departments
    assert bundle.get("does_not_exist", {"fallback": True}) == {"fallback": True}
    assert "supervisor" in bundle
    with pytest.raises(KeyError):
        bundle["does_not_exist"]


def test_runtime_agents_as_dict_matches_legacy_shape() -> None:
    bundle = _make_bundle()
    legacy = bundle.as_dict()
    assert set(legacy.keys()) == {"supervisor", "departments", "synthesis", "report_writer"}
    assert set(legacy["departments"].keys()) == set(DOMAIN_DEPARTMENT_NAMES)


# ── 2.2 Capability metadata ───────────────────────────────────────────────────

def test_runtime_agents_specs_describe_required_methods() -> None:
    bundle = _make_bundle()
    assert bundle.specs["supervisor"].required_methods == SUPERVISOR_REQUIRED_METHODS
    assert bundle.specs["synthesis"].required_methods == SYNTHESIS_REQUIRED_METHODS
    assert bundle.specs["report_writer"].required_methods == REPORT_WRITER_REQUIRED_METHODS
    for dept in DOMAIN_DEPARTMENT_NAMES:
        assert bundle.specs[dept].department_name == dept
        assert bundle.specs[dept].required_methods == DEPARTMENT_REQUIRED_METHODS


def test_runtime_agent_spec_carries_capability_metadata() -> None:
    spec = RuntimeAgentSpec(
        role_name="CompanyDepartment",
        runtime_type="DepartmentRuntime",
        required_methods=DEPARTMENT_REQUIRED_METHODS,
        department_name="CompanyDepartment",
        tool_policy="department_runtime",
        model_profile="CompanyDepartment",
        observability_role="research_plane",
    )

    assert spec.tool_policy == "department_runtime"
    assert spec.model_profile == "CompanyDepartment"
    assert spec.observability_role == "research_plane"


# ── 2.3 Validation ────────────────────────────────────────────────────────────

def test_validate_runtime_agents_accepts_complete_bundle() -> None:
    result = validate_runtime_agents(_make_bundle())
    assert result.is_valid
    assert result.errors == ()


def test_validate_runtime_agents_rejects_missing_department() -> None:
    deps = {name: _Role() for name in DOMAIN_DEPARTMENT_NAMES if name != "ContactDepartment"}
    result = validate_runtime_agents(_make_bundle(departments=deps))
    assert not result.is_valid
    assert any("ContactDepartment" in err and "missing" in err for err in result.errors)


def test_validate_runtime_agents_rejects_unexpected_department() -> None:
    deps = {name: _Role() for name in DOMAIN_DEPARTMENT_NAMES}
    deps["CompanyDepartmnt"] = _Role()  # typo
    result = validate_runtime_agents(_make_bundle(departments=deps))
    assert not result.is_valid
    assert any("CompanyDepartmnt" in err and "unexpected" in err for err in result.errors)


def test_validate_runtime_agents_rejects_supervisor_missing_method() -> None:
    class _PartialSupervisor:
        def opening_message(self, *a, **kw): return ""
        # build_intake_brief intentionally absent
        def accept_department_package(self, *a, **kw): return {}
        def accept_synthesis(self, *a, **kw): return {}

    result = validate_runtime_agents(_make_bundle(supervisor=_PartialSupervisor()))
    assert not result.is_valid
    assert any("supervisor" in err and "build_intake_brief" in err for err in result.errors)


def test_validate_runtime_agents_rejects_department_missing_run() -> None:
    class _NoRun:
        pass

    deps = {name: _Role() for name in DOMAIN_DEPARTMENT_NAMES}
    deps["CompanyDepartment"] = _NoRun()
    result = validate_runtime_agents(_make_bundle(departments=deps))
    assert not result.is_valid
    assert any("CompanyDepartment" in err and "run" in err for err in result.errors)


def test_validate_runtime_agents_rejects_none_roles() -> None:
    base = _make_bundle()
    broken = RuntimeAgents(
        supervisor=None,
        departments=base.departments,
        synthesis=None,
        report_writer=None,
        search_cache=base.search_cache,
        config=base.config,
        specs=base.specs,
    )
    result = validate_runtime_agents(broken)
    assert not result.is_valid
    assert any("supervisor" in err and "missing" in err for err in result.errors)
    assert any("synthesis" in err and "missing" in err for err in result.errors)
    assert any("report_writer" in err and "missing" in err for err in result.errors)


# ── 2.5 SearchCache thread-safety + isolation ─────────────────────────────────

def test_search_cache_namespaces_are_isolated_per_instance() -> None:
    """Two factory calls produce two unrelated caches."""
    a = SearchCache()
    b = SearchCache()
    a.get_namespace("__search__")["k"] = "v"
    assert b.namespaces() == ()
    assert "k" not in b.get_namespace("__search__")


def test_search_cache_get_namespace_is_thread_safe() -> None:
    cache = SearchCache()
    barrier = threading.Barrier(8)
    references: list[dict] = []

    def _worker():
        barrier.wait()
        references.append(cache.get_namespace("__search__"))

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(references) == 8
    # All workers must observe the same dict (no torn allocation).
    first = references[0]
    assert all(ref is first for ref in references)


def test_search_cache_namespace_operations_are_locked() -> None:
    namespace = SearchCacheNamespace()
    barrier = threading.Barrier(8)

    def _worker(idx: int) -> None:
        barrier.wait()
        namespace[f"k{idx}"] = idx

    threads = [threading.Thread(target=_worker, args=(idx,)) for idx in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(namespace) == 8
    assert namespace.get("k3") == 3
    assert namespace.snapshot()["k7"] == 7


def test_search_cache_metrics_reflect_namespaces_and_entries() -> None:
    cache = SearchCache()
    cache.get_namespace("__search__")["q1"] = ["r1"]
    cache.get_namespace("__pages__")["u1"] = "html1"
    assert set(cache.namespaces()) == {"__search__", "__pages__"}
    assert cache.entry_count() == 2


# ── 2.7 RuntimeAgentFactoryError ──────────────────────────────────────────────

def test_runtime_agent_factory_error_carries_code_and_errors() -> None:
    exc = RuntimeAgentFactoryError(
        code=RUNTIME_COMPOSITION_INVALID,
        reason="composition invalid",
        errors=("missing department 'ContactDepartment'",),
    )
    assert exc.code == RUNTIME_COMPOSITION_INVALID
    assert exc.reason == "composition invalid"
    assert exc.errors == ("missing department 'ContactDepartment'",)


# ── 2.8 Snapshot ──────────────────────────────────────────────────────────────

def test_runtime_agents_snapshot_is_non_sensitive_and_stable() -> None:
    bundle = _make_bundle()
    snap = bundle.snapshot()
    assert snap["factory_version"] == FACTORY_VERSION
    assert snap["shared_cache"] is True
    assert snap["cache_strategy"] == "per_run_shared_threadsafe"
    assert snap["tool_policy_mode"] == "role_resolved"
    assert snap["runtime_profile"] == "production"
    assert snap["departments"] == sorted(DOMAIN_DEPARTMENT_NAMES)
    # snapshot must not leak any role objects or prompts
    snap_text = repr(snap)
    assert "object at 0x" not in snap_text  # no raw object reprs
    assert "supervisor" in snap["specs"]
    assert snap["specs"]["supervisor"]["runtime_type"] == "StubSupervisor"
    assert snap["specs"]["supervisor"]["tool_policy"] == "runtime_default"
    assert snap["specs"]["supervisor"]["observability_role"] == "runtime_agent"


def test_runtime_agents_snapshot_reflects_cache_namespaces() -> None:
    bundle = _make_bundle()
    bundle.search_cache.get_namespace("__search__")["q"] = ["r"]
    snap = bundle.snapshot()
    assert "__search__" in snap["search_cache_namespaces"]
    assert snap["search_cache_entries"] >= 1


# ── 2.6 Healthcheck ───────────────────────────────────────────────────────────

def test_runtime_agents_healthcheck_ok_for_complete_bundle() -> None:
    result = runtime_agents_healthcheck(_make_bundle())
    assert result["status"] == "ok"
    assert result["errors"] == ()
    assert result["snapshot"]["factory_version"] == FACTORY_VERSION


def test_runtime_agents_healthcheck_failed_for_missing_department() -> None:
    deps = {name: _Role() for name in DOMAIN_DEPARTMENT_NAMES if name != "ContactDepartment"}
    result = runtime_agents_healthcheck(_make_bundle(departments=deps))
    assert result["status"] == "failed"
    assert any("ContactDepartment" in err for err in result["errors"])


def test_runtime_agents_healthcheck_handles_none_bundle() -> None:
    result = runtime_agents_healthcheck(None)
    assert result["status"] == "failed"
    assert result["snapshot"] == {}


def test_create_runtime_agents_builds_and_validates_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    """2.9: exercise the actual factory path with lightweight patched constructors."""
    from src.agents import runtime_factory

    class _Supervisor(_Role):
        pass

    class _Department(_Role):
        def __init__(self, department: str, *, search_cache=None) -> None:
            self.department = department
            self.search_cache = search_cache

    class _Synthesis(_Role):
        pass

    class _Report(_Role):
        pass

    monkeypatch.setattr(runtime_factory, "SupervisorAgent", _Supervisor)
    monkeypatch.setattr(runtime_factory, "DepartmentRuntime", _Department)
    monkeypatch.setattr(runtime_factory, "SynthesisRuntime", _Synthesis)
    monkeypatch.setattr(runtime_factory, "ReportWriterRuntime", _Report)

    bundle = runtime_factory.create_runtime_agents(
        RuntimeFactoryConfig(runtime_profile="test", model_profile="stubbed")
    )

    assert set(bundle.departments) == set(DOMAIN_DEPARTMENT_NAMES)
    assert validate_runtime_agents(bundle).is_valid
    assert bundle.config.runtime_profile == "test"
    assert bundle.snapshot()["model_profile"] == "stubbed"
    assert all(dept.search_cache is bundle.search_cache for dept in bundle.departments.values())


def test_create_runtime_agents_supports_isolated_cache_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents import runtime_factory

    class _Department(_Role):
        def __init__(self, department: str, *, search_cache=None) -> None:
            self.department = department
            self.search_cache = search_cache

    monkeypatch.setattr(runtime_factory, "SupervisorAgent", _Role)
    monkeypatch.setattr(runtime_factory, "DepartmentRuntime", _Department)
    monkeypatch.setattr(runtime_factory, "SynthesisRuntime", _Role)
    monkeypatch.setattr(runtime_factory, "ReportWriterRuntime", _Role)

    bundle = runtime_factory.create_runtime_agents(RuntimeFactoryConfig(shared_cache=False))

    assert bundle.config.shared_cache is False
    assert all(dept.search_cache is None for dept in bundle.departments.values())


# ── 2.7 pipeline_runner integration ───────────────────────────────────────────

def test_run_pipeline_maps_factory_error_to_failed_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When create_runtime_agents() raises, the run result must show failed_phase='runtime_agent_factory'."""
    from src import pipeline_runner

    def _boom(*_args, **_kw):
        raise RuntimeAgentFactoryError(
            code=RUNTIME_AGENT_FACTORY_FAILED,
            reason="constructor crash",
            errors=("supervisor init failed",),
        )

    monkeypatch.setattr(pipeline_runner, "create_runtime_agents", _boom)

    result = pipeline_runner.run_pipeline(
        company_name="Example AG",
        web_domain="https://www.example.com",
    )

    assert result["status"] == "failed"
    assert result["failed_phase"] == "runtime_agent_factory"
    assert result["error_code"] == RUNTIME_AGENT_FACTORY_FAILED
    assert "supervisor init failed" in result["error_detail"]["errors"]
    rs = result["run_context"]["resolution_state"]
    assert rs["current_phase"] == "runtime_agent_factory"
    assert rs["runtime_agents"]["status"] == "failed"


def test_factory_logger_emits_event_on_success() -> None:
    """2.10: log_factory_event with status=ok emits a structured payload."""
    import logging as _logging

    from src.orchestration.factory_logging import log_factory_event

    captured: list[_logging.LogRecord] = []

    class _Collector(_logging.Handler):
        def emit(self, record): captured.append(record)

    logger = _logging.getLogger("liquisto.runtime_factory")
    handler = _Collector(level=_logging.DEBUG)
    logger.addHandler(handler)
    try:
        log_factory_event(
            run_id="20260512T120000Z",
            status="ok",
            duration_ms=42,
            factory_version=FACTORY_VERSION,
            role_count=7,
        )
    finally:
        logger.removeHandler(handler)

    assert captured
    payload = captured[-1].payload  # type: ignore[attr-defined]
    assert payload["component"] == "runtime_factory"
    assert payload["phase"] == "runtime_agent_factory"
    assert payload["status"] == "ok"
    assert payload["role_count"] == 7
    assert payload["factory_version"] == FACTORY_VERSION


def test_factory_logger_emits_event_on_failure() -> None:
    import logging as _logging

    from src.orchestration.factory_logging import log_factory_event

    captured: list[_logging.LogRecord] = []

    class _Collector(_logging.Handler):
        def emit(self, record): captured.append(record)

    logger = _logging.getLogger("liquisto.runtime_factory")
    handler = _Collector(level=_logging.DEBUG)
    logger.addHandler(handler)
    try:
        log_factory_event(
            run_id="20260512T120000Z",
            status="failed",
            error_code=RUNTIME_COMPOSITION_INVALID,
            errors=("missing department 'ContactDepartment'",),
        )
    finally:
        logger.removeHandler(handler)

    payload = captured[-1].payload  # type: ignore[attr-defined]
    assert payload["status"] == "failed"
    assert payload["error_code"] == RUNTIME_COMPOSITION_INVALID
    assert "ContactDepartment" in payload["errors"][0]
