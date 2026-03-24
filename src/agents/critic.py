"""Critic agent — generic deterministic rule evaluator.

Reads validation_rules from the task contract (use_cases.py) so there is
one canonical source of truth.  No LLM is used here.

Rule check types
----------------
non_placeholder  — field value must not be "n/v" and must not be empty/None
min_items        — field must be a sequence with at least ``value`` items
min_length       — field must be a string with at least ``value`` characters

Dot-notation field paths (e.g. "economic_situation.assessment") are resolved
by walking the payload dict level by level.

Output structure
----------------
The review result exposes per-class pass/fail counts so the Judge can make a
class-aware three-outcome decision without re-reading the payload.
"""
from __future__ import annotations

import json
from typing import Any

from src.app.use_cases import get_task_validation_rules
from src.config import get_role_model_selection
from src.orchestration.tool_policy import resolve_allowed_tools


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


# ---------------------------------------------------------------------------
# Generic check evaluators
# ---------------------------------------------------------------------------

def _resolve_field(payload: dict[str, Any], field_path: str) -> Any:
    """Walk a dot-separated path into a nested dict.  Returns None on miss."""
    value: Any = payload
    for part in field_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _check_non_placeholder(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        stripped = value.strip()
        return bool(stripped) and stripped != "n/v"
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _check_min_items(value: Any, threshold: int) -> bool:
    if not isinstance(value, (list, tuple)):
        return False
    return len(value) >= threshold


def _check_min_length(value: Any, threshold: int) -> bool:
    if not isinstance(value, str):
        return False
    return len(value.strip()) >= threshold


def _evaluate_rule(rule: dict[str, Any], payload: dict[str, Any]) -> bool:
    """Return True if the rule passes for the given payload."""
    check = rule.get("check", "")
    field = rule.get("field", "")
    value = _resolve_field(payload, field)
    threshold = rule.get("value", 1)

    if check == "non_placeholder":
        return _check_non_placeholder(value)
    if check == "min_items":
        return _check_min_items(value, threshold)
    if check == "min_length":
        return _check_min_length(value, threshold)
    # Unknown check type — fail safe
    return False


# ---------------------------------------------------------------------------
# CriticAgent
# ---------------------------------------------------------------------------

class CriticAgent:
    def __init__(self, name: str = "CompanyCritic") -> None:
        self.name = name
        self.model_name = get_role_model_selection(self.name)[0]
        self.allowed_tools = resolve_allowed_tools(self.name, "critic_review")

    def review(
        self,
        *,
        task_key: str,
        section: str,
        objective: str,
        payload: dict[str, Any],
        report: dict[str, Any] | None = None,
        role_memory: list[dict[str, Any]] | None = None,
        validation_rules: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Evaluate payload against validation_rules from the task contract.

        If ``validation_rules`` is supplied explicitly it takes priority;
        otherwise the rules are looked up from the canonical task contract by
        ``task_key``.  This allows callers in tests or special paths to inject
        rules directly.
        """
        rules = validation_rules if validation_rules is not None else get_task_validation_rules(task_key)

        accepted_points: list[str] = []
        rejected_points: list[str] = []
        missing_points: list[str] = []
        issues: list[str] = []
        core_passed: int = 0
        core_total: int = 0
        supporting_passed: int = 0
        supporting_total: int = 0
        failed_rule_messages: list[str] = []

        for rule in rules:
            rule_name = rule.get("field", rule.get("check", "unknown"))
            rule_class = rule.get("class", "supporting")
            try:
                passed = _evaluate_rule(rule, payload)
            except Exception:
                passed = False

            if rule_class == "core":
                core_total += 1
                if passed:
                    core_passed += 1
            else:
                supporting_total += 1
                if passed:
                    supporting_passed += 1

            if passed:
                accepted_points.append(rule_name)
            else:
                rejected_points.append(rule_name)
                missing_points.append(rule_name)
                failure_msg = rule.get("message", f"Rule '{rule_name}' not satisfied for {task_key}.")
                issues.append(failure_msg)
                if rule_class == "core":
                    failed_rule_messages.append(failure_msg)

        # Source quality check (always supporting)
        sources = payload.get("sources", []) if isinstance(payload, dict) else []
        if not sources:
            issues.append("No supporting source recorded.")
            missing_points.append("supporting_sources")
        external_sources = [
            s for s in sources
            if isinstance(s, dict) and s.get("source_type") not in {"owned", "first_party"}
        ]
        evidence_strength = "strong" if len(external_sources) >= 2 else "moderate" if sources else "weak"

        # Schicht 4: surface worker-reported field_issues (e.g. Pydantic
        # validation failures that caused a salvage/fallback) so the Critic
        # can flag them and request a revision.
        worker_field_issues = (report or {}).get("field_issues", [])
        if worker_field_issues:
            for fi in worker_field_issues:
                issues.append(f"Worker field issue: {fi}")

        method_issue = False
        if report:
            queries_used = report.get("queries_used", [])
            search_calls = report.get("usage", {}).get("search_calls", 0)
            if rejected_points and search_calls and not external_sources and queries_used:
                method_issue = True

        # Legacy approved flag — True only when all rules pass and evidence is present
        approved = bool(rules) and not rejected_points and evidence_strength != "weak"
        if not rules:
            approved = not issues

        feedback_to_worker = [
            {
                "point": rp,
                "status": "revise",
                "guidance": f"Rework the missing or weak point '{rp}' so it directly satisfies the task objective.",
            }
            for rp in rejected_points
        ]

        coding_brief = {
            "task_key": task_key,
            "objective": objective,
            "rejected_points": rejected_points,
            "missing_points": _dedup_safe(missing_points),
            "issues": issues,
            "method_issue": method_issue,
            "research_gap": (
                "The search and evidence path needs to be improved before the same worker retries the open points."
                if method_issue
                else "Direct worker revision should be sufficient."
            ),
        }

        return {
            "approved": approved,
            "issues": issues,
            "accepted_points": accepted_points,
            "rejected_points": rejected_points,
            "missing_points": _dedup_safe(missing_points),
            "evidence_strength": evidence_strength,
            "method_issue": method_issue,
            # Class-aware counts for the Judge
            "core_passed": core_passed,
            "core_total": core_total,
            "supporting_passed": supporting_passed,
            "supporting_total": supporting_total,
            # Failed core rule messages become open_questions on degraded output
            "failed_rule_messages": failed_rule_messages,
            "revision_instructions": [
                "Keep already accepted points stable.",
                "Revise only the rejected or missing points.",
                "Downgrade unsupported claims if stronger evidence cannot be found.",
            ] if issues else [],
            "feedback_to_worker": feedback_to_worker,
            "coding_brief": coding_brief,
            "field_issues": [],
            "objective": objective,
            "role_memory_used": bool(role_memory),
        }
