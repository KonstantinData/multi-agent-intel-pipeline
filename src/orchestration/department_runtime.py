"""Department-level runtime.

CHG-03: ``supervisor`` parameter is now optional and ignored by the Lead.
The department works autonomously inside its contract.  The Supervisor
sees only the contract handoff and the final package.

Thin entry point that delegates all orchestration to the DepartmentLeadAgent.
"""
from __future__ import annotations

from typing import Any, Callable

from src.agents.lead import DepartmentLeadAgent
from src.domain.intake import SupervisorBrief
from src.orchestration.task_router import Assignment


MessageHook = Callable[[dict[str, Any]], None] | None


class DepartmentRuntime:
    """Container that exposes a department as a runnable unit.

    All orchestration logic lives in DepartmentLeadAgent. This class exists
    so that supervisor_loop.py can treat each department uniformly via
    ``agents["departments"][name].run(...)``.
    """

    def __init__(self, department: str, *, search_cache: dict | None = None) -> None:
        self.department = department
        self.lead = DepartmentLeadAgent(department)
        if search_cache is not None:
            # Separate namespaces within the shared cache to avoid collisions
            self.lead.worker._search_cache = search_cache.setdefault("__search__", {})
            self.lead.worker._page_cache = search_cache.setdefault("__pages__", {})

    def run(
        self,
        *,
        brief: SupervisorBrief,
        assignments: list[Assignment],
        current_section: dict[str, Any] | None,
        supervisor=None,   # CHG-03: optional — department works autonomously
        memory_store=None,
        role_memory: dict[str, list[dict[str, Any]]] | None = None,
        on_message: MessageHook = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        return self.lead.run(
            brief=brief,
            assignments=assignments,
            current_section=current_section,
            supervisor=supervisor,  # passed through; Lead ignores it (CHG-03)
            memory_store=memory_store,
            role_memory=role_memory,
            on_message=on_message,
        )

    def run_followup(
        self,
        *,
        question: str,
        context: str,
        brief: SupervisorBrief,
        memory_store=None,
        on_message: MessageHook = None,
    ) -> dict[str, Any]:
        """Run a targeted mini-session to answer a specific follow-up question.

        Used by the Strategic Synthesis Department for back-requests and by
        the UI follow-up mechanism via run_id. Returns an updated report_segment.
        """
        return self.lead.run_followup(
            question=question,
            context=context,
            brief=brief,
            memory_store=memory_store,
            on_message=on_message,
        )
