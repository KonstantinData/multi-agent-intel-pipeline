"""Policies for what may enter long-term memory."""
from __future__ import annotations

from typing import Any

# Minimum readiness score to persist patterns.  Runs below this threshold
# produced evidence too weak to serve as reusable process guidance.
MIN_READINESS_SCORE = 70

# Maximum fraction of degraded tasks allowed.  If more than this share of
# tasks ended degraded, the run's process patterns are not trustworthy.
MAX_DEGRADED_RATIO = 0.25


def should_store_strategy(
    *,
    status: str,
    usable: bool,
    readiness_score: int = 100,
    task_statuses: dict[str, str] | None = None,
) -> bool:
    """Persist only runs that are completed, usable, AND meet quality thresholds."""
    if status != "completed" or not usable:
        return False
    if readiness_score < MIN_READINESS_SCORE:
        return False
    if task_statuses:
        total = len(task_statuses)
        degraded = sum(1 for s in task_statuses.values() if s in {"degraded", "blocked", "skipped"})
        if total > 0 and degraded / total > MAX_DEGRADED_RATIO:
            return False
    return True

