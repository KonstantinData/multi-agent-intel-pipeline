"""Run-level context shared across the pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.memory.short_term_store import ShortTermMemoryStore
from src.models.meeting_ready import FinalBriefing, MeetingReadinessAssessment, RunStatus


@dataclass
class RunContext:
    run_id: str
    intake: dict[str, Any]
    short_term_memory: ShortTermMemoryStore = field(default_factory=ShortTermMemoryStore)
    supervisor_brief: dict[str, Any] = field(default_factory=dict)
    retrieved_strategies: list[dict[str, Any]] = field(default_factory=list)
    retrieved_role_strategies: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    active_tasks: list[dict[str, Any]] = field(default_factory=list)
    report_package: dict[str, Any] = field(default_factory=dict)
    question_registry: dict[str, dict[str, Any]] = field(default_factory=dict)
    answer_matrix: dict[str, dict[str, Any]] = field(default_factory=dict)
    meeting_readiness_assessment: MeetingReadinessAssessment = field(default_factory=MeetingReadinessAssessment)
    final_briefing: FinalBriefing | None = None
    status: RunStatus = "running"
    resolution_state: dict[str, Any] = field(default_factory=dict)

    def record_task(
        self,
        *,
        assignee: str,
        objective: str,
        section: str,
        task_key: str | None = None,
        status: str = "assigned",
        model_name: str | None = None,
        allowed_tools: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        entry = {"assignee": assignee, "objective": objective, "section": section, "status": status}
        if task_key:
            entry["task_key"] = task_key
        if model_name:
            entry["model_name"] = model_name
        if allowed_tools is not None:
            entry["allowed_tools"] = list(allowed_tools)
        self.active_tasks.append(entry)

    def update_task_status(self, *, task_key: str, status: str) -> None:
        for item in self.active_tasks:
            if item.get("task_key") == task_key:
                item["status"] = status

    def snapshot(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "intake": self.intake,
            "supervisor_brief": self.supervisor_brief,
            "retrieved_strategies": self.retrieved_strategies,
            "retrieved_role_strategies": self.retrieved_role_strategies,
            "active_tasks": self.active_tasks,
            "report_package": self.report_package,
            "question_registry": self.question_registry,
            "answer_matrix": self.answer_matrix,
            "meeting_readiness_assessment": self.meeting_readiness_assessment.model_dump(mode="json"),
            "final_briefing": self.final_briefing.model_dump(mode="json") if self.final_briefing else None,
            "short_term_memory": self.short_term_memory.snapshot(),
            "status": self.status,
            "resolution_state": self.resolution_state,
        }


    @classmethod
    def from_snapshot(cls, payload: dict[str, Any]) -> RunContext:
        return cls(
            run_id=str(payload.get("run_id", "")),
            intake=dict(payload.get("intake", {})),
            short_term_memory=ShortTermMemoryStore.from_snapshot(payload.get("short_term_memory", {})),
            supervisor_brief=dict(payload.get("supervisor_brief", {})),
            retrieved_strategies=list(payload.get("retrieved_strategies", [])),
            retrieved_role_strategies=dict(payload.get("retrieved_role_strategies", {})),
            active_tasks=list(payload.get("active_tasks", [])),
            report_package=dict(payload.get("report_package", {})),
            question_registry=dict(payload.get("question_registry", {})),
            answer_matrix=dict(payload.get("answer_matrix", {})),
            meeting_readiness_assessment=MeetingReadinessAssessment.model_validate(
                payload.get("meeting_readiness_assessment", {})
            ),
            final_briefing=(
                FinalBriefing.model_validate(payload.get("final_briefing"))
                if payload.get("final_briefing")
                else None
            ),
            status=payload.get("status", "running"),
            resolution_state=dict(payload.get("resolution_state", {})),
        )
