"""Short-term / run-brain memory for the current run.

CHG-02 — This store is the canonical run brain.  It holds everything that is
case-specific and must be reloadable by ``run_id`` for follow-up sessions:

- evidence gathered per department
- task artifacts, review artifacts, decision artifacts (via ``department_run_states``)
- critic reviews and approved/open points
- strategy changes and rejected paths (via department_run_states)
- department conversations / execution trace
- follow-up sessions

The run brain is exported to ``artifacts/runs/{run_id}/run_context.json`` at the
end of every pipeline execution.  ``follow_up.py`` rehydrates it by loading that
file when a follow-up question arrives.

Memory policy: this store NEVER feeds directly into the long-term process brain.
Only sanitised process patterns extracted by ``consolidation.py`` may be stored
in long-term memory.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


def _dedup_safe(items: list) -> list:
    """Deduplicate a list whose items may be dicts (unhashable)."""
    seen: set[str] = set()
    result = []
    for item in items:
        key = (
            json.dumps(item, sort_keys=True, ensure_ascii=False)
            if isinstance(item, (dict, list))
            else str(item)
        )
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


@dataclass
class ShortTermMemoryStore:
    facts: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    market_signals: list[str] = field(default_factory=list)
    buyer_hypotheses: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    rejected_claims: list[str] = field(default_factory=list)
    task_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    task_statuses: dict[str, str] = field(default_factory=dict)
    section_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    critic_approvals: dict[str, bool] = field(default_factory=dict)
    critic_reviews: dict[str, dict[str, Any]] = field(default_factory=dict)
    accepted_points: dict[str, list[str]] = field(default_factory=dict)
    open_points: dict[str, list[str]] = field(default_factory=dict)
    revision_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    worker_reports: list[dict[str, Any]] = field(default_factory=list)
    department_packages: dict[str, dict[str, Any]] = field(default_factory=dict)
    department_conversations: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    department_workspaces: dict[str, dict[str, Any]] = field(default_factory=dict)
    # CHG-02: Per-department serialised DepartmentRunState — the full artifact record.
    # Keyed by department name. Stored by DepartmentLeadAgent after each run.
    department_run_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    follow_up_sessions: list[dict[str, Any]] = field(default_factory=list)
    usage_totals: dict[str, int] = field(
        default_factory=lambda: {
            "llm_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "search_calls": 0,
            "page_fetches": 0,
        }
    )

    def open_department_workspace(self, department: str) -> None:
        """Reserve an isolated namespace for a department run."""
        self.department_workspaces[department] = {
            "task_outputs": {},
            "task_statuses": {},
            "critic_approvals": {},
            "critic_reviews": {},
            "accepted_points": {},
            "open_points": {},
            "revision_history": {},
            "worker_reports": [],
            "facts": [],
            "sources": [],
            "open_questions": [],
        }

    def ingest_worker_report(self, report: dict[str, Any], *, department: str | None = None) -> None:
        task_key = str(report.get("task_key", "")).strip()
        section = str(report.get("section", "")).strip()
        payload = report.get("payload", {})
        if task_key:
            self.task_outputs[task_key] = payload
            self.task_statuses.setdefault(task_key, "submitted")
        if section:
            self.section_outputs[section] = payload
        self.worker_reports.append(report)
        self.facts.extend(report.get("facts", []))
        self.market_signals.extend(report.get("market_signals", []))
        self.buyer_hypotheses.extend(report.get("buyer_hypotheses", []))
        self.open_questions.extend(report.get("open_questions", []))
        self.next_actions.extend(report.get("next_actions", []))
        self.sources.extend(report.get("sources", []))
        for key, value in report.get("usage", {}).items():
            if key in self.usage_totals:
                self.usage_totals[key] += int(value or 0)
        if department and department in self.department_workspaces:
            ws = self.department_workspaces[department]
            if task_key:
                ws["task_outputs"][task_key] = payload
                ws["task_statuses"].setdefault(task_key, "submitted")
            ws["worker_reports"].append(report)
            ws["facts"].extend(report.get("facts", []))
            ws["sources"].extend(report.get("sources", []))
            ws["open_questions"].extend(report.get("open_questions", []))

    def mark_critic_review(self, task_key: str, approved: bool, issues: list[str] | None = None, review: dict[str, Any] | None = None, *, department: str | None = None) -> None:
        self.critic_approvals[task_key] = approved
        self.task_statuses[task_key] = "accepted" if approved else "needs_revision"
        if review:
            self.critic_reviews[task_key] = review
            self.accepted_points[task_key] = list(review.get("accepted_points", []))
            self.open_points[task_key] = list(review.get("rejected_points", []))
            self.revision_history.setdefault(task_key, []).append(review)
        if issues and not approved:
            self.open_questions.extend(issues)
        if department and department in self.department_workspaces:
            ws = self.department_workspaces[department]
            ws["critic_approvals"][task_key] = approved
            ws["task_statuses"][task_key] = "accepted" if approved else "needs_revision"
            if review:
                ws["critic_reviews"][task_key] = review
                ws["accepted_points"][task_key] = list(review.get("accepted_points", []))
                ws["open_points"][task_key] = list(review.get("rejected_points", []))
                ws["revision_history"].setdefault(task_key, []).append(review)

    def store_department_package(self, department: str, package: dict[str, Any]) -> None:
        self.department_packages[department] = package

    def append_department_conversation(self, department: str, conversation: list[dict[str, Any]]) -> None:
        existing = self.department_conversations.setdefault(department, [])
        existing.extend(conversation)

    def record_department_run_state(self, department: str, run_state_dict: dict[str, Any]) -> None:
        """Store the serialised DepartmentRunState for a completed department run.

        CHG-02: This is the primary mechanism for persisting the full artifact
        history (task_artifacts, review_artifacts, decision_artifacts,
        strategy_changes, judge_escalations, coding_support_used) in the run brain.
        """
        self.department_run_states[department] = run_state_dict

    def record_follow_up(self, answer: dict[str, Any]) -> None:
        self.follow_up_sessions.append(answer)

    def snapshot(self) -> dict[str, Any]:
        _seen_urls: set[str] = set()
        _unique_sources: list[dict[str, Any]] = []
        for _s in self.sources:
            _url = _s.get("url", "") if isinstance(_s, dict) else ""
            if _url and _url not in _seen_urls:
                _seen_urls.add(_url)
                _unique_sources.append(_s)
            elif not _url:
                _unique_sources.append(_s)
        return {
            "facts": _dedup_safe(self.facts),
            "sources": _unique_sources,
            "market_signals": _dedup_safe(self.market_signals),
            "buyer_hypotheses": _dedup_safe(self.buyer_hypotheses),
            "open_questions": _dedup_safe(self.open_questions),
            "next_actions": _dedup_safe(self.next_actions),
            "rejected_claims": _dedup_safe(self.rejected_claims),
            "task_outputs": self.task_outputs,
            "task_statuses": self.task_statuses,
            "section_outputs": self.section_outputs,
            "critic_approvals": self.critic_approvals,
            "critic_reviews": self.critic_reviews,
            "accepted_points": self.accepted_points,
            "open_points": self.open_points,
            "revision_history": self.revision_history,
            "worker_reports": self.worker_reports,
            "department_packages": self.department_packages,
            "department_conversations": self.department_conversations,
            "department_workspaces": self.department_workspaces,
            # CHG-02: full artifact history — reloadable for follow-up rehydration
            "department_run_states": self.department_run_states,
            "follow_up_sessions": self.follow_up_sessions,
            "usage_totals": self.usage_totals,
        }
