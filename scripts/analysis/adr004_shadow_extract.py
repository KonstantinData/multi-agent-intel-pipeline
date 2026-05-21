"""Extract ADR-004 assurance shadow observations from persisted run artifacts.

The script is intentionally read-only with respect to runtime artifacts. It
loads one or more ``run_context.json`` files and emits row-level observations
plus aggregates for ADR-004 signal coverage analysis.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from src.orchestration.run_paths import RUNS_DIR, resolve_run_dir

SCHEMA_VERSION = "2026-05-21.1"

SIGNAL_FIELDS = (
    "required_fields_score",
    "source_mix_score",
    "source_freshness_score",
    "contradiction_score",
    "evidence_strength_score",
    "ltm_pattern_precision",
)

CSV_FIELDS = (
    "run_id",
    "run_status",
    "department",
    "task_key",
    "attempt",
    "approved",
    "shadow_present",
    "confidence_score",
    "requires_critic",
    "requires_judge",
    "would_auto_accept",
    "actual_critic_delta_present",
    "critic_severity",
    "would_have_blocked_auto_accept",
    "changed_outcome",
    "rejected_points_count",
    "failed_core_rules_count",
    "task_criticality",
    "ltm_pattern_match",
    "ltm_pattern_qualified",
    *SIGNAL_FIELDS,
    *(f"{field}_is_none" for field in SIGNAL_FIELDS),
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_run_input(run_input: str, *, runs_root: Path = RUNS_DIR) -> Path:
    """Resolve either a run_id or a filesystem path to an existing run directory."""
    candidate = Path(run_input)
    if candidate.exists():
        if not candidate.is_dir():
            raise NotADirectoryError(f"Run input is not a directory: {run_input}")
        return candidate.resolve()
    return resolve_run_dir(run_input, runs_root=runs_root, must_exist=True)


def _run_status(context: dict[str, Any]) -> str | None:
    status = context.get("status") or context.get("pipeline_status")
    return str(status) if status is not None else None


def _department_states(context: dict[str, Any]) -> dict[str, Any]:
    short_term = context.get("short_term_memory")
    if not isinstance(short_term, dict):
        return {}
    states = short_term.get("department_run_states")
    return states if isinstance(states, dict) else {}


def _review_items(review_artifacts: Any) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(review_artifacts, dict):
        return []
    items: list[tuple[str, dict[str, Any]]] = []
    for task_key, reviews in review_artifacts.items():
        if isinstance(reviews, list):
            for review in reviews:
                if isinstance(review, dict):
                    items.append((str(task_key), review))
        elif isinstance(reviews, dict):
            items.append((str(task_key), reviews))
    return items


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _number_or_none(value: Any) -> int | float | None:
    return value if isinstance(value, int | float) and not isinstance(value, bool) else None


def _row_for_review(
    *,
    run_id: str,
    run_status: str | None,
    department: str,
    task_key: str,
    review: dict[str, Any],
) -> dict[str, Any]:
    shadow = review.get("assurance_shadow")
    shadow_present = isinstance(shadow, dict)

    verdict = shadow.get("gate_verdict") if shadow_present else None
    signals = shadow.get("gate_signals") if shadow_present else None
    critic_delta = shadow.get("actual_critic_delta") if shadow_present else None

    verdict = verdict if isinstance(verdict, dict) else {}
    signals = signals if isinstance(signals, dict) else {}
    critic_delta = critic_delta if isinstance(critic_delta, dict) else {}

    row: dict[str, Any] = {
        "run_id": run_id,
        "run_status": run_status,
        "department": department,
        "task_key": task_key,
        "attempt": review.get("attempt"),
        "approved": _bool_or_none(review.get("approved")),
        "shadow_present": shadow_present,
        "confidence_score": _number_or_none(verdict.get("confidence_score")),
        "requires_critic": _bool_or_none(verdict.get("requires_critic")),
        "requires_judge": _bool_or_none(verdict.get("requires_judge")),
        "would_auto_accept": _bool_or_none(verdict.get("would_auto_accept")),
        "actual_critic_delta_present": bool(critic_delta),
        "critic_severity": critic_delta.get("critic_severity"),
        "would_have_blocked_auto_accept": _bool_or_none(
            critic_delta.get("would_have_blocked_auto_accept"),
        ),
        "changed_outcome": _bool_or_none(critic_delta.get("changed_outcome")),
        "rejected_points_count": critic_delta.get("rejected_points_count"),
        "failed_core_rules_count": len(critic_delta.get("failed_core_rules") or ()),
        "task_criticality": signals.get("task_criticality"),
        "ltm_pattern_match": _bool_or_none(signals.get("ltm_pattern_match")),
        "ltm_pattern_qualified": _bool_or_none(signals.get("ltm_pattern_qualified")),
    }

    for field in SIGNAL_FIELDS:
        value = signals.get(field)
        row[field] = value
        row[f"{field}_is_none"] = value is None

    return row


def extract_run(run_dir: Path) -> dict[str, Any]:
    """Extract row-level ADR-004 shadow observations for one run directory."""
    context_path = run_dir / "run_context.json"
    if not context_path.exists():
        raise FileNotFoundError(f"Missing run_context.json in {run_dir}")

    context = _load_json(context_path)
    run_id = str(context.get("run_id") or run_dir.name)
    run_status = _run_status(context)

    rows: list[dict[str, Any]] = []
    for department, state in sorted(_department_states(context).items()):
        if not isinstance(state, dict):
            continue
        for task_key, review in _review_items(state.get("review_artifacts")):
            rows.append(
                _row_for_review(
                    run_id=run_id,
                    run_status=run_status,
                    department=str(department),
                    task_key=task_key,
                    review=review,
                ),
            )

    return {
        "run_id": run_id,
        "run_status": run_status,
        "run_dir": str(run_dir),
        "rows": rows,
        "summary": summarize_rows(rows),
    }


def _fraction(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def _counter(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(Counter(str(row.get(field)) for row in rows))


def _confidence_summary(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    values = [
        row["confidence_score"]
        for row in rows
        if isinstance(row.get("confidence_score"), int | float)
    ]
    if not values:
        return {"min": None, "avg": None, "max": None}
    return {
        "min": min(values),
        "avg": round(sum(values) / len(values), 6),
        "max": max(values),
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build aggregate coverage metrics for extracted review rows."""
    review_count = len(rows)
    shadow_present_count = sum(1 for row in rows if row.get("shadow_present") is True)
    signal_none_fraction = {
        field: _fraction(
            sum(1 for row in rows if row.get(f"{field}_is_none") is True),
            review_count,
        )
        for field in SIGNAL_FIELDS
    }
    return {
        "review_count": review_count,
        "shadow_present_count": shadow_present_count,
        "shadow_coverage": _fraction(shadow_present_count, review_count),
        "signal_none_fraction": signal_none_fraction,
        "confidence_score": _confidence_summary(rows),
        "critic_severity_counts": _counter(rows, "critic_severity"),
        "department_counts": _counter(rows, "department"),
        "task_key_counts": _counter(rows, "task_key"),
        "would_auto_accept_counts": _counter(rows, "would_auto_accept"),
        "requires_critic_counts": _counter(rows, "requires_critic"),
        "requires_judge_counts": _counter(rows, "requires_judge"),
    }


def build_report(run_dirs: list[Path]) -> dict[str, Any]:
    runs = [extract_run(run_dir) for run_dir in run_dirs]
    rows = [row for run in runs for row in run["rows"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "run_count": len(runs),
        "runs": runs,
        "aggregate": summarize_rows(rows),
        "rows": rows,
    }


def _write_csv(report: dict[str, Any], output: Path | None) -> None:
    target = output.open("w", newline="", encoding="utf-8") if output else sys.stdout
    close_target = output is not None
    try:
        writer = csv.DictWriter(target, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report["rows"])
    finally:
        if close_target:
            target.close()


def _write_json(report: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if output:
        output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract ADR-004 AssuranceShadowRecord observations from run artifacts.",
    )
    parser.add_argument(
        "runs",
        nargs="+",
        help="Run IDs or paths to run directories containing run_context.json.",
    )
    parser.add_argument(
        "--runs-root",
        default=str(RUNS_DIR),
        help="Root directory used when resolving run IDs. Defaults to artifacts/runs.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "csv"),
        default="json",
        help="Output format. JSON includes rows and aggregates; CSV includes row data only.",
    )
    parser.add_argument("--output", help="Optional output file path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runs_root = Path(args.runs_root)
    run_dirs = [resolve_run_input(run_input, runs_root=runs_root) for run_input in args.runs]
    report = build_report(run_dirs)
    output = Path(args.output) if args.output else None
    if args.format == "csv":
        _write_csv(report, output)
    else:
        _write_json(report, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
