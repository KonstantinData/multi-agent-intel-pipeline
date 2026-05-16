"""Post-tool hook: store diff metrics and iteration patterns."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--lines-added", type=int, default=0)
    parser.add_argument("--lines-removed", type=int, default=0)
    parser.add_argument(
        "--events-path",
        default="artifacts/compliance/session_events.jsonl",
    )
    args = parser.parse_args()

    event = {
        "event_type": "post_tool_use",
        "timestamp": _utc_now_iso(),
        "run_id": args.run_id,
        "file_path": args.file,
        "iterations": max(args.iterations, 1),
        "lines_added": max(args.lines_added, 0),
        "lines_removed": max(args.lines_removed, 0),
    }

    path = Path(args.events_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
