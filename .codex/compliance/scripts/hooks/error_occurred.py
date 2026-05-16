"""Error hook: capture error class and processing step."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--step", required=True)
    parser.add_argument("--error-type", required=True)
    parser.add_argument("--message", default="")
    parser.add_argument(
        "--events-path",
        default="artifacts/compliance/session_events.jsonl",
    )
    args = parser.parse_args()

    event = {
        "event_type": "error_occurred",
        "timestamp": _utc_now_iso(),
        "run_id": args.run_id,
        "step": args.step,
        "error_type": args.error_type,
        "message": args.message,
    }

    path = Path(args.events_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
