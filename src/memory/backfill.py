"""Bootstrap long-term memory from eligible historical run artifacts."""
from __future__ import annotations

import json
from pathlib import Path

from src.memory.consolidation import consolidate_role_patterns
from src.memory.policies import should_store_strategy


def backfill_long_term_memory_from_runs(*, memory_store, runs_dir: str | Path) -> int:
    """Populate an empty long-term memory store from existing run artifacts."""
    if memory_store.load():
        return 0

    inserted = 0
    root = Path(runs_dir)
    if not root.exists():
        return 0

    for run_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        meta_path = run_dir / "run_meta.json"
        pipeline_path = run_dir / "pipeline_data.json"
        context_path = run_dir / "run_context.json"
        if not (meta_path.exists() and pipeline_path.exists() and context_path.exists()):
            continue
        try:
            run_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            pipeline_data = json.loads(pipeline_path.read_text(encoding="utf-8"))
            run_context = json.loads(context_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        status = str(run_meta.get("status", ""))
        readiness = pipeline_data.get("research_readiness", {}) or {}
        task_statuses = (
            run_context.get("short_term_memory", {}).get("task_statuses", {})
            if isinstance(run_context, dict)
            else {}
        )
        usable = bool(readiness.get("usable"))
        if not should_store_strategy(
            status=status,
            usable=usable,
            readiness_score=int(readiness.get("score", 0) or 0),
            task_statuses=task_statuses if isinstance(task_statuses, dict) else {},
        ):
            continue

        patterns = consolidate_role_patterns(
            run_context=run_context,
            pipeline_data=pipeline_data,
            status=status,
            usable=usable,
        )
        for pattern in patterns:
            memory_store.upsert_strategy(pattern)
            inserted += 1

    return inserted
