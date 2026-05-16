"""Session-end hook: aggregate events and trigger optimization summary."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _load_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--events-path",
        default="artifacts/compliance/session_events.jsonl",
    )
    parser.add_argument(
        "--summary-path",
        default="artifacts/compliance/session_summary.json",
    )
    parser.add_argument(
        "--trigger-threshold",
        type=int,
        default=4,
        help="Threshold greater than three for optimization trigger.",
    )
    args = parser.parse_args()

    events = _load_events(Path(args.events_path))
    error_counter: Counter[str] = Counter()
    iteration_counter: Counter[str] = Counter()
    for item in events:
        if item.get("event_type") == "error_occurred":
            error_counter[str(item.get("error_type", "unknown"))] += 1
        if item.get("event_type") == "post_tool_use":
            file_key = str(item.get("file_path", "unknown"))
            if int(item.get("iterations", 1) or 1) > 1:
                iteration_counter[file_key] += 1

    frequent_errors = [
        {"error_type": key, "count": count}
        for key, count in error_counter.items()
        if count >= max(args.trigger_threshold, 4)
    ]

    summary = {
        "run_id": args.run_id,
        "generated_at": _utc_now_iso(),
        "event_count": len(events),
        "error_frequencies": dict(error_counter),
        "multi_iteration_files": dict(iteration_counter),
        "optimizer_triggered": bool(frequent_errors),
        "optimizer_candidates": frequent_errors,
    }
    path = Path(args.summary_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
