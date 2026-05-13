"""Runtime agent factory — imports AG2-dependent concrete agent classes.

Pre-2026: returned a loose `dict[str, object]`.
Since 2026-05-12: returns a typed `RuntimeAgents` bundle from
`src/orchestration/runtime_agents.py`. The bundle keeps `__getitem__`/
`__contains__` for backward compatibility with legacy callers that still
use `agents["supervisor"]` / `agents["departments"][name]`.

Failures (missing roles, missing methods, instantiation crash) raise
`RuntimeAgentFactoryError`, which `pipeline_runner.run_pipeline()` maps to
a `failed_phase="runtime_agent_factory"` run result.
"""
from __future__ import annotations

from src.agents.supervisor import SupervisorAgent
from src.orchestration.department_runtime import DepartmentRuntime
from src.orchestration.report_runtime import ReportWriterRuntime
from src.orchestration.runtime_agents import (
    DEPARTMENT_REQUIRED_METHODS,
    DOMAIN_DEPARTMENT_NAMES,
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
    validate_runtime_agents,
)
from src.orchestration.synthesis_runtime import SynthesisRuntime


def _build_specs() -> dict[str, RuntimeAgentSpec]:
    specs: dict[str, RuntimeAgentSpec] = {
        "supervisor": RuntimeAgentSpec(
            role_name="supervisor",
            runtime_type="SupervisorAgent",
            required_methods=SUPERVISOR_REQUIRED_METHODS,
            tool_policy="intake_normalization",
            model_profile="supervisor",
            observability_role="control_plane",
        ),
        "synthesis": RuntimeAgentSpec(
            role_name="synthesis",
            runtime_type="SynthesisRuntime",
            required_methods=SYNTHESIS_REQUIRED_METHODS,
            tool_policy="synthesis",
            model_profile="synthesis",
            observability_role="synthesis_plane",
        ),
        "report_writer": RuntimeAgentSpec(
            role_name="report_writer",
            runtime_type="ReportWriterRuntime",
            required_methods=REPORT_WRITER_REQUIRED_METHODS,
            tool_policy="report_writer",
            model_profile="report_writer",
            observability_role="report_plane",
        ),
    }
    for dept in DOMAIN_DEPARTMENT_NAMES:
        specs[dept] = RuntimeAgentSpec(
            role_name=dept,
            runtime_type="DepartmentRuntime",
            required_methods=DEPARTMENT_REQUIRED_METHODS,
            department_name=dept,
            tool_policy="department_runtime",
            model_profile=dept,
            observability_role="research_plane",
        )
    return specs


def create_runtime_agents(
    config: RuntimeFactoryConfig | None = None,
) -> RuntimeAgents:
    """Instantiate, validate and return the runtime agent bundle.

    Raises `RuntimeAgentFactoryError` if any constructor crashes or the
    bundle fails the composition contract (missing role, missing method,
    unexpected department name).
    """
    cfg = config or RuntimeFactoryConfig()
    search_cache = SearchCache()

    try:
        supervisor = SupervisorAgent()
        cache_storage = search_cache if cfg.shared_cache else None
        departments: dict[str, object] = {
            name: DepartmentRuntime(name, search_cache=cache_storage)
            for name in DOMAIN_DEPARTMENT_NAMES
        }
        synthesis = SynthesisRuntime()
        report_writer = ReportWriterRuntime()
    except Exception as exc:  # noqa: BLE001 — convert any constructor crash to a typed factory error
        raise RuntimeAgentFactoryError(
            code=RUNTIME_AGENT_FACTORY_FAILED,
            reason=f"runtime agent constructor failed: {type(exc).__name__}: {exc}",
        ) from exc

    bundle = RuntimeAgents(
        supervisor=supervisor,
        departments=departments,
        synthesis=synthesis,
        report_writer=report_writer,
        search_cache=search_cache,
        config=cfg,
        specs=_build_specs(),
    )

    if cfg.strict_validation:
        result = validate_runtime_agents(bundle)
        if not result.is_valid:
            raise RuntimeAgentFactoryError(
                code=RUNTIME_COMPOSITION_INVALID,
                reason="runtime composition failed validation",
                errors=result.errors,
            )

    return bundle


__all__ = ["create_runtime_agents"]
