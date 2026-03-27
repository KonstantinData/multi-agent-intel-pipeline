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
import logging
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
            self.task_statuses.setdefault(task_key, "pending")  # F7: was "submitted"
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
                ws["task_statuses"].setdefault(task_key, "pending")  # F7: was "submitted"
            ws["worker_reports"].append(report)
            ws["facts"].extend(report.get("facts", []))
            ws["sources"].extend(report.get("sources", []))
            ws["open_questions"].extend(report.get("open_questions", []))

    def mark_critic_review(self, task_key: str, approved: bool, issues: list[str] | None = None, review: dict[str, Any] | None = None, *, department: str | None = None) -> None:
        self.critic_approvals[task_key] = approved
        self.task_statuses[task_key] = "accepted" if approved else "pending"  # F7: was "needs_revision"
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
            ws["task_statuses"][task_key] = "accepted" if approved else "pending"  # F7: was "needs_revision"
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

    def create_working_set(self) -> "ShortTermMemoryStore":
        """F5: Create an isolated working-set store seeded with a read-only snapshot.

        The working set starts with a frozen copy of the current state so
        parallel departments can read existing context without mutating the
        main store.  Only new writes go into the working set and are later
        merged back via ``merge_from()``.
        """
        ws = ShortTermMemoryStore()
        # Seed with read-only copies of current state
        ws.facts = list(self.facts)
        ws.sources = list(self.sources)
        ws.market_signals = list(self.market_signals)
        ws.buyer_hypotheses = list(self.buyer_hypotheses)
        ws.open_questions = list(self.open_questions)
        ws.next_actions = list(self.next_actions)
        ws.task_statuses = dict(self.task_statuses)
        ws.section_outputs = {k: dict(v) for k, v in self.section_outputs.items()}
        return ws

    def delta_from(self, baseline: "ShortTermMemoryStore") -> "ShortTermMemoryStore":
        """F5: Extract only the new writes relative to a baseline snapshot.

        Returns a new store containing only the data that was added after
        the baseline was taken.  Used to merge only the delta back into
        the main store, avoiding double-counting of seeded data.
        """
        delta = ShortTermMemoryStore()
        # Lists: only items not in baseline
        baseline_facts = set(baseline.facts)
        delta.facts = [f for f in self.facts if f not in baseline_facts]
        baseline_source_urls = {s.get("url", "") for s in baseline.sources if isinstance(s, dict)}
        delta.sources = [s for s in self.sources if isinstance(s, dict) and s.get("url", "") not in baseline_source_urls]
        baseline_signals = set(baseline.market_signals)
        delta.market_signals = [s for s in self.market_signals if s not in baseline_signals]
        baseline_hypotheses = set(baseline.buyer_hypotheses)
        delta.buyer_hypotheses = [h for h in self.buyer_hypotheses if h not in baseline_hypotheses]
        baseline_questions = set(baseline.open_questions)
        delta.open_questions = [q for q in self.open_questions if q not in baseline_questions]
        baseline_actions = set(baseline.next_actions)
        delta.next_actions = [a for a in self.next_actions if a not in baseline_actions]
        delta.rejected_claims = list(self.rejected_claims)  # typically empty at parallel start
        delta.worker_reports = list(self.worker_reports)[len(baseline.worker_reports):]
        # Dicts: only new keys
        for k, v in self.task_outputs.items():
            if k not in baseline.task_outputs:
                delta.task_outputs[k] = v
        for k, v in self.task_statuses.items():
            if k not in baseline.task_statuses or v != baseline.task_statuses.get(k):
                delta.task_statuses[k] = v
        for k, v in self.section_outputs.items():
            if k not in baseline.section_outputs:
                delta.section_outputs[k] = v
        for k, v in self.critic_approvals.items():
            if k not in baseline.critic_approvals:
                delta.critic_approvals[k] = v
        for k, v in self.critic_reviews.items():
            if k not in baseline.critic_reviews:
                delta.critic_reviews[k] = v
        for k, v in self.accepted_points.items():
            if k not in baseline.accepted_points:
                delta.accepted_points[k] = v
        for k, v in self.open_points.items():
            if k not in baseline.open_points:
                delta.open_points[k] = v
        delta.revision_history = {k: v for k, v in self.revision_history.items() if k not in baseline.revision_history}
        delta.department_packages = dict(self.department_packages)
        delta.department_conversations = dict(self.department_conversations)
        delta.department_workspaces = dict(self.department_workspaces)
        delta.department_run_states = dict(self.department_run_states)
        # Usage: delta = current - baseline
        for k in self.usage_totals:
            delta.usage_totals[k] = self.usage_totals.get(k, 0) - baseline.usage_totals.get(k, 0)
        return delta

    def merge_from(self, other: "ShortTermMemoryStore") -> None:
        """F5: Merge an isolated working-set store into this store.

        Used after parallel department runs to consolidate results
        deterministically without concurrent mutation.

        Raises ValueError on unexpected key conflicts in dict fields
        that are expected to be disjoint across departments.
        """
        # Lists: extend
        self.facts.extend(other.facts)
        self.sources.extend(other.sources)
        self.market_signals.extend(other.market_signals)
        self.buyer_hypotheses.extend(other.buyer_hypotheses)
        self.open_questions.extend(other.open_questions)
        self.next_actions.extend(other.next_actions)
        self.rejected_claims.extend(other.rejected_claims)
        self.worker_reports.extend(other.worker_reports)
        self.follow_up_sessions.extend(other.follow_up_sessions)
        # Dicts: update with disjointness assertion for task-keyed fields
        _DISJOINT_DICTS = [
            ("task_outputs", self.task_outputs, other.task_outputs),
            ("task_statuses", self.task_statuses, other.task_statuses),
            ("critic_approvals", self.critic_approvals, other.critic_approvals),
            ("critic_reviews", self.critic_reviews, other.critic_reviews),
            ("accepted_points", self.accepted_points, other.accepted_points),
            ("open_points", self.open_points, other.open_points),
            ("department_packages", self.department_packages, other.department_packages),
            ("department_run_states", self.department_run_states, other.department_run_states),
            ("department_conversations", self.department_conversations, other.department_conversations),
            ("department_workspaces", self.department_workspaces, other.department_workspaces),
        ]
        for name, target, source in _DISJOINT_DICTS:
            conflicts = set(target.keys()) & set(source.keys())
            if conflicts:
                logging.warning(
                    "merge_from: unexpected key conflict in %s: %s (last-writer-wins)",
                    name, conflicts,
                )
            target.update(source)
        # section_outputs: may overlap (same section from different tasks) — last-writer-wins is acceptable
        self.section_outputs.update(other.section_outputs)
        # revision_history: merge per task_key
        for k, v in other.revision_history.items():
            self.revision_history.setdefault(k, []).extend(v)
        # Usage totals: additive
        for k, v in other.usage_totals.items():
            if k in self.usage_totals:
                self.usage_totals[k] += int(v or 0)
            else:
                self.usage_totals[k] = int(v or 0)

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
