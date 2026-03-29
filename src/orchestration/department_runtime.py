"""Department-level runtime.

The department works autonomously inside its contract.  The Supervisor
sees only the contract handoff and the final package.

Thin entry point that delegates all orchestration to the DepartmentLeadAgent.
"""
from __future__ import annotations

from typing import Any, Callable

from src.agents.lead import DepartmentLeadAgent
from src.domain.intake import SupervisorBrief
from src.models.meeting_ready import AnswerMatrixUpdate, EvidencePacket, GapCandidate
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
        memory_store=None,
        role_memory: dict[str, list[dict[str, Any]]] | None = None,
        on_message: MessageHook = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        section_payload, package_messages, department_package = self.lead.run(
            brief=brief,
            assignments=assignments,
            current_section=current_section,
            memory_store=memory_store,
            role_memory=role_memory,
            on_message=on_message,
        )
        department_package["evidence_packages"] = [
            EvidencePacket.model_validate(item).model_dump(mode="json")
            for item in department_package.get("evidence_packages", [])
        ]
        department_package["gap_candidates"] = [
            GapCandidate.model_validate(item).model_dump(mode="json")
            for item in department_package.get("gap_candidates", [])
        ]
        department_package["answer_matrix_updates"] = [
            AnswerMatrixUpdate.model_validate(item).model_dump(mode="json")
            for item in department_package.get("answer_matrix_updates", [])
        ]
        return section_payload, package_messages, department_package

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
