"""Typed runtime-agent composition contract used by `create_runtime_agents()`.

This module is intentionally AG2-light: it only defines dataclasses, validation
and audit helpers. The actual agent instances are created by
`src/agents/runtime_factory.py`, which pulls in the AG2-heavy concrete types
(`SupervisorAgent`, `DepartmentRuntime`, `SynthesisRuntime`, `ReportWriterRuntime`).

Why a separate module?
- Tests that exercise the runtime-composition contract should not need AG2.
- The `RuntimeAgents` dataclass exposes a `__getitem__` so legacy call sites
  using `agents["supervisor"]`/`agents["departments"][name]` keep working
  without changes during migration.
- `validate_runtime_agents()` enforces role completeness, method presence and
  cache isolation at composition time — failures abort the run in Step 1
  rather than later in Step 2 routing.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass, field
from typing import Any

# Canonical, exhaustive list of domain-department names. Mismatches against
# this tuple are treated as composition errors so typos like
# "CompanyDepartmnt" cannot pass through silently.
DOMAIN_DEPARTMENT_NAMES: tuple[str, ...] = (
    "CompanyDepartment",
    "MarketDepartment",
    "BuyerDepartment",
    "ContactDepartment",
)

# Methods each role must expose. Used by `validate_runtime_agents()`.
SUPERVISOR_REQUIRED_METHODS: tuple[str, ...] = (
    "build_intake_brief",
    "opening_message",
    "accept_department_package",
    "accept_synthesis",
)
DEPARTMENT_REQUIRED_METHODS: tuple[str, ...] = ("run",)
SYNTHESIS_REQUIRED_METHODS: tuple[str, ...] = ("run",)
REPORT_WRITER_REQUIRED_METHODS: tuple[str, ...] = ("run",)

# Current factory-version label persisted into composition snapshots.
# Bump when the runtime-agent contract changes shape (new role, new method,
# different cache strategy).
FACTORY_VERSION = "2026-05-12.2"


@dataclass(slots=True)
class SearchCacheNamespace(MutableMapping):
    """Thread-safe dict-like namespace used by worker search/page caches."""

    _data: dict[Any, Any] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def __getitem__(self, key: Any) -> Any:
        with self._lock:
            return self._data[key]

    def __setitem__(self, key: Any, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def __delitem__(self, key: Any) -> None:
        with self._lock:
            del self._data[key]

    def __iter__(self) -> Iterator[Any]:
        with self._lock:
            return iter(tuple(self._data.keys()))

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def __contains__(self, key: object) -> bool:
        with self._lock:
            return key in self._data

    def get(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def setdefault(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            return self._data.setdefault(key, default)

    def snapshot(self) -> dict[Any, Any]:
        """Return a shallow copy for diagnostics."""
        with self._lock:
            return dict(self._data)


@dataclass(slots=True)
class SearchCache:
    """Run-scoped cache container shared by department runtimes.

    Holds thread-safe namespace objects keyed by namespace (`__search__`,
    `__pages__`). Workers still see a dict-like object, but each read/write is
    guarded by a re-entrant lock rather than relying on CPython implementation
    details.

    The cache is created fresh per `create_runtime_agents()` call so that
    runs for different customers cannot share search results.
    """

    storage: dict[str, SearchCacheNamespace] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def get_namespace(self, name: str) -> SearchCacheNamespace:
        """Return the nested dict for the given namespace, creating it on first use."""
        with self._lock:
            return self.storage.setdefault(name, SearchCacheNamespace())

    def namespaces(self) -> tuple[str, ...]:
        """Return the namespaces currently allocated (for audit/metrics)."""
        return tuple(self.storage.keys())

    def entry_count(self) -> int:
        """Total entries across all namespaces. Diagnostic only."""
        return sum(len(ns) for ns in self.storage.values())

    def as_dict(self) -> dict[str, SearchCacheNamespace]:
        """Underlying namespace map for compatibility with legacy callers."""
        return self.storage


@dataclass(frozen=True, slots=True)
class RuntimeAgentSpec:
    """Capability metadata for one runtime role.

    Persisted into the composition snapshot for audit + preflight diagnostics.
    """

    role_name: str
    runtime_type: str
    required_methods: tuple[str, ...]
    department_name: str = ""
    tool_policy: str = "runtime_default"
    model_profile: str = "settings_default"
    observability_role: str = "runtime_agent"


@dataclass(frozen=True, slots=True)
class RuntimeFactoryConfig:
    """Explicit factory configuration.

    Default values produce production behaviour. Tests inject overrides.
    Carries no secrets — model selection lives in `src.config.settings`.
    """

    strict_validation: bool = True
    shared_cache: bool = True
    factory_version: str = FACTORY_VERSION
    cache_strategy: str = "per_run_shared_threadsafe"
    tool_policy_mode: str = "role_resolved"
    model_profile: str = "settings_default"
    runtime_profile: str = "production"
    observability_enabled: bool = True


@dataclass(slots=True)
class RuntimeAgentValidationResult:
    """Outcome of `validate_runtime_agents()`."""

    is_valid: bool
    errors: tuple[str, ...] = ()


class RuntimeAgentFactoryError(RuntimeError):
    """Raised when `create_runtime_agents()` cannot produce a valid composition.

    Carries a stable `code` for `_failed_intake_result()`-style mapping.
    """

    def __init__(self, *, code: str, reason: str, errors: tuple[str, ...] = ()) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.errors = errors


# Stable factory error codes.
RUNTIME_COMPOSITION_INVALID = "runtime_composition_invalid"
RUNTIME_AGENT_FACTORY_FAILED = "runtime_agent_factory_failed"


@dataclass(slots=True)
class RuntimeAgents:
    """Typed bundle returned by `create_runtime_agents()`.

    Exposes `__getitem__` for legacy callers that still use
    `agents["supervisor"]` / `agents["departments"][name]`. New code should
    prefer attribute access (`agents.supervisor`).
    """

    supervisor: Any
    departments: dict[str, Any]
    synthesis: Any
    report_writer: Any
    search_cache: SearchCache
    config: RuntimeFactoryConfig
    specs: dict[str, RuntimeAgentSpec]

    def __getitem__(self, key: str) -> Any:
        if key == "supervisor":
            return self.supervisor
        if key == "departments":
            return self.departments
        if key == "synthesis":
            return self.synthesis
        if key == "report_writer":
            return self.report_writer
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        return key in {"supervisor", "departments", "synthesis", "report_writer"}

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-compatible lookup for legacy runtime callers."""
        try:
            return self[key]
        except KeyError:
            return default

    def as_dict(self) -> dict[str, Any]:
        """Dict-shaped view, identical to the pre-2026 factory return type."""
        return {
            "supervisor": self.supervisor,
            "departments": dict(self.departments),
            "synthesis": self.synthesis,
            "report_writer": self.report_writer,
        }

    def snapshot(self) -> dict[str, Any]:
        """Non-sensitive composition snapshot for `RunContext.resolution_state`.

        Records role names, runtime types, department names, cache strategy
        and factory version. Excludes prompts, secrets, model parameters or
        any tool configuration.
        """
        return {
            "factory_version": self.config.factory_version,
            "shared_cache": self.config.shared_cache,
            "cache_strategy": self.config.cache_strategy,
            "tool_policy_mode": self.config.tool_policy_mode,
            "model_profile": self.config.model_profile,
            "runtime_profile": self.config.runtime_profile,
            "observability_enabled": self.config.observability_enabled,
            "search_cache_namespaces": list(self.search_cache.namespaces()),
            "search_cache_entries": self.search_cache.entry_count(),
            "departments": sorted(self.departments.keys()),
            "specs": {
                role: {
                    "runtime_type": spec.runtime_type,
                    "required_methods": list(spec.required_methods),
                    "department_name": spec.department_name,
                    "tool_policy": spec.tool_policy,
                    "model_profile": spec.model_profile,
                    "observability_role": spec.observability_role,
                }
                for role, spec in sorted(self.specs.items())
            },
        }


def _missing_methods(obj: Any, methods: tuple[str, ...]) -> list[str]:
    return [m for m in methods if not callable(getattr(obj, m, None))]


def validate_runtime_agents(agents: RuntimeAgents) -> RuntimeAgentValidationResult:
    """Verify role completeness and method presence on the composition.

    Returns a `RuntimeAgentValidationResult` with a list of errors. The
    factory wraps a non-empty error list in `RuntimeAgentFactoryError`
    when `RuntimeFactoryConfig.strict_validation` is `True`.
    """
    errors: list[str] = []

    if agents.supervisor is None:
        errors.append("supervisor role is missing")
    else:
        for method in _missing_methods(agents.supervisor, SUPERVISOR_REQUIRED_METHODS):
            errors.append(f"supervisor is missing required method '{method}'")

    if agents.synthesis is None:
        errors.append("synthesis role is missing")
    else:
        for method in _missing_methods(agents.synthesis, SYNTHESIS_REQUIRED_METHODS):
            errors.append(f"synthesis is missing required method '{method}'")

    if agents.report_writer is None:
        errors.append("report_writer role is missing")
    else:
        for method in _missing_methods(agents.report_writer, REPORT_WRITER_REQUIRED_METHODS):
            errors.append(f"report_writer is missing required method '{method}'")

    expected = set(DOMAIN_DEPARTMENT_NAMES)
    actual = set(agents.departments.keys())
    for missing_name in sorted(expected - actual):
        errors.append(f"missing department '{missing_name}'")
    for extra_name in sorted(actual - expected):
        errors.append(f"unexpected department '{extra_name}'")
    for name, runtime in agents.departments.items():
        if runtime is None:
            errors.append(f"department '{name}' is None")
            continue
        for method in _missing_methods(runtime, DEPARTMENT_REQUIRED_METHODS):
            errors.append(f"department '{name}' is missing required method '{method}'")

    if agents.config.shared_cache:
        if not isinstance(agents.search_cache, SearchCache):
            errors.append("shared cache is enabled but search_cache is not a SearchCache")
        for namespace in agents.search_cache.storage.values():
            if not isinstance(namespace, SearchCacheNamespace):
                errors.append("shared cache namespace is not thread-safe")

    return RuntimeAgentValidationResult(is_valid=not errors, errors=tuple(errors))


def runtime_agents_healthcheck(agents: RuntimeAgents | None) -> dict[str, Any]:
    """Side-effect-free preflight summary.

    Returns a dict with `status`, `errors`, and the composition snapshot.
    Safe to call in `tests/smoke/test_preflight.py` — no LLM calls, no
    web fetches, no DNS lookups.
    """
    if agents is None:
        return {
            "status": "failed",
            "errors": ("runtime agents bundle is None",),
            "snapshot": {},
        }
    result = validate_runtime_agents(agents)
    return {
        "status": "ok" if result.is_valid else "failed",
        "errors": result.errors,
        "snapshot": agents.snapshot(),
    }


__all__ = [
    "DEPARTMENT_REQUIRED_METHODS",
    "DOMAIN_DEPARTMENT_NAMES",
    "FACTORY_VERSION",
    "REPORT_WRITER_REQUIRED_METHODS",
    "RUNTIME_AGENT_FACTORY_FAILED",
    "RUNTIME_COMPOSITION_INVALID",
    "RuntimeAgentFactoryError",
    "RuntimeAgentSpec",
    "RuntimeAgentValidationResult",
    "RuntimeAgents",
    "RuntimeFactoryConfig",
    "SUPERVISOR_REQUIRED_METHODS",
    "SYNTHESIS_REQUIRED_METHODS",
    "SearchCache",
    "SearchCacheNamespace",
    "runtime_agents_healthcheck",
    "validate_runtime_agents",
]
