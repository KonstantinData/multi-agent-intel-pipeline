"""Synthesis-level runtime — thin wrapper around SynthesisDepartmentAgent."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.domain.intake import SupervisorBrief

MessageHook = Callable[[dict[str, Any]], None] | None


class SynthesisRuntime:
    """Exposes the Strategic Synthesis Department as a runnable unit."""

    def __init__(self) -> None:
        # Deferred to avoid pulling autogen into the module-import graph.
        from src.agents.synthesis_department import SynthesisDepartmentAgent

        self.agent = SynthesisDepartmentAgent()

    def run(
        self,
        *,
        brief: SupervisorBrief,
        department_packages: dict[str, dict[str, Any]],
        memory_store=None,
        on_message: MessageHook = None,
        synthesis_context: dict[str, Any] | None = None,
        step_emitter: Any | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        return self.agent.run(
            brief=brief,
            department_packages=department_packages,
            memory_store=memory_store,
            on_message=on_message,
            synthesis_context=synthesis_context,
            step_emitter=step_emitter,
        )
