"""Policies for what may enter long-term memory."""
from __future__ import annotations

from typing import Any

from src.app.use_cases import BLOCKED_RUN_STATUS, DISCOVERY_READY_RUN_STATUS, SUCCESS_RUN_STATUS

# Minimum readiness score to persist patterns.  Runs below this threshold
# produced evidence too weak to serve as reusable process guidance.
MIN_READINESS_SCORE = 70

# Maximum fraction of degraded tasks allowed.  If more than this share of
# tasks ended degraded, the run's process patterns are not trustworthy.
MAX_DEGRADED_RATIO = 0.25

SUCCESS_MEMORY_STATUSES = frozenset({"completed", SUCCESS_RUN_STATUS})
TASK_POSITIVE_MEMORY_STATUSES = frozenset(
    {
        "completed",
        SUCCESS_RUN_STATUS,
        DISCOVERY_READY_RUN_STATUS,
        BLOCKED_RUN_STATUS,
    }
)


def should_store_strategy(
    *,
    status: str,
    usable: bool,
    readiness_score: int = 100,
    task_statuses: dict[str, str] | None = None,
) -> bool:
    """Persist only runs that are completed, usable, AND meet quality thresholds."""
    if status not in SUCCESS_MEMORY_STATUSES or not usable:
        return False
    if readiness_score < MIN_READINESS_SCORE:
        return False
    if task_statuses:
        total = len(task_statuses)
        degraded = sum(1 for s in task_statuses.values() if s in {"degraded", "blocked", "skipped"})
        if total > 0 and degraded / total > MAX_DEGRADED_RATIO:
            return False
    return True


def should_store_positive_task_pattern(
    *,
    status: str,
    task_status: str,
) -> bool:
    """Allow positive learning from accepted tasks inside non-failed runs.

    This deliberately does not weaken the full-run gate above. It only admits
    task-local best-practice patterns when the task itself was accepted and the
    surrounding run reached a controlled terminal state.
    """
    return status in TASK_POSITIVE_MEMORY_STATUSES and task_status == "accepted"


def should_store_memory_pattern(
    *,
    pattern: dict[str, Any],
    status: str,
    usable: bool,
    readiness_score: int = 100,
    task_statuses: dict[str, str] | None = None,
) -> bool:
    """Pattern-level admission policy for long-term process memory."""
    admission_level = str(pattern.get("admission_level") or "full_run")
    if admission_level == "task_positive":
        task_key = str(pattern.get("task_key") or "")
        task_status = str(pattern.get("task_status") or "")
        if not task_status and task_statuses:
            task_status = str(task_statuses.get(task_key) or "")
        return should_store_positive_task_pattern(status=status, task_status=task_status)
    return should_store_strategy(
        status=status,
        usable=usable,
        readiness_score=readiness_score,
        task_statuses=task_statuses,
    )
