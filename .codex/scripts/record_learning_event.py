"""Record Codex learning events with local outbox and optional MAIP sync.

The recorder is intentionally dependency-light and safe for Git hooks:
- writes append-only JSONL events locally first
- optionally posts to the MAIP memory worker
- never fails a hook because remote sync is unavailable unless --strict-sync is used
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, request

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / ".codex" / "runtime" / "learning_event_schema.json"
DEFAULT_OUTBOX_DIR = ROOT / "artifacts" / "codex-learning" / "outbox"
DEFAULT_SENT_PATH = ROOT / "artifacts" / "codex-learning" / "sent_event_ids.json"
DEFAULT_TOKEN_ENV = "MAIP_MEMORY_INGEST_API_TOKEN"
DEFAULT_BASE_URL_ENV = "MAIP_MEMORY_BASE_URL"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Learning event schema missing: {path.as_posix()}")
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise SystemExit("Learning event schema must be a JSON object.")
    return payload


def _allowed_event_types(schema: dict[str, Any]) -> set[str]:
    values = schema.get("allowed_event_types")
    if not isinstance(values, list) or not all(isinstance(item, str) and item for item in values):
        raise SystemExit("Learning event schema must define allowed_event_types.")
    return set(values)


def _allowed_areas(schema: dict[str, Any]) -> set[str]:
    values = schema.get("allowed_areas", [])
    if not isinstance(values, list) or not all(isinstance(item, str) and item for item in values):
        raise SystemExit("Learning event schema must define allowed_areas.")
    return set(values)


def _parse_json_object(raw: str, *, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SystemExit(f"{label} must be a JSON object.")
    return parsed


def _sanitize_for_memory(value: Any) -> Any:
    """Remove URL-like fields before sending to MAIP memory policy gates."""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered.endswith("url") or lowered in {"url", "details_url", "html_url", "run_url"}:
                sanitized[f"{key}_sha256"] = hashlib.sha256(str(item).encode()).hexdigest()
                continue
            sanitized[str(key)] = _sanitize_for_memory(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_for_memory(item) for item in value]
    return value


def _build_event(args: argparse.Namespace, schema: dict[str, Any]) -> dict[str, Any]:
    allowed = _allowed_event_types(schema)
    if args.event_type not in allowed:
        raise SystemExit(f"Unsupported event type: {args.event_type}")
    if args.area not in _allowed_areas(schema):
        raise SystemExit(f"Unsupported area: {args.area}")

    payload: dict[str, Any] = {}
    if args.payload_json:
        payload.update(_parse_json_object(args.payload_json, label="--payload-json"))
    if args.payload_file:
        loaded = _load_json(Path(args.payload_file))
        if not isinstance(loaded, dict):
            raise SystemExit("--payload-file must contain a JSON object.")
        payload.update(loaded)

    created_at = _utc_now_iso()
    event_id = args.event_id.strip() or str(uuid.uuid4())
    correlation_id = args.correlation_id.strip() or event_id
    return {
        "schema_version": schema.get("schema_version", "2026-05-17.1"),
        "event_id": event_id,
        "event_type": args.event_type,
        "area": args.area,
        "source": args.source,
        "run_id": args.run_id.strip() or correlation_id,
        "correlation_id": correlation_id,
        "status": args.status,
        "created_at": created_at,
        "payload": payload,
    }


def _outbox_path(outbox_dir: Path, created_at: str) -> Path:
    day = created_at[:10].replace("-", "") or datetime.now().strftime("%Y%m%d")
    return outbox_dir / f"{day}.jsonl"


def _append_outbox(event: dict[str, Any], outbox_dir: Path) -> Path:
    path = _outbox_path(outbox_dir, str(event["created_at"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def _load_sent_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        payload = _load_json(path)
    except Exception:
        return set()
    if not isinstance(payload, list):
        return set()
    return {str(item) for item in payload if str(item).strip()}


def _save_sent_ids(path: Path, sent_ids: set[str]) -> None:
    _write_json(path, sorted(sent_ids))


def _maip_body(event: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "schema_version": event["schema_version"],
        "event_id": event["event_id"],
        "run_id": event["run_id"],
        "status": event["status"],
        "created_at": event["created_at"],
        **dict(event.get("payload", {})),
    }
    return {
        "area": event["area"],
        "event_type": event["event_type"],
        "source": event["source"],
        "correlation_id": event["correlation_id"],
        "payload": _sanitize_for_memory(payload),
    }


def _post_event(event: dict[str, Any], *, base_url: str, token: str, timeout_sec: float) -> tuple[bool, str]:
    if not base_url or not token:
        return False, "missing MAIP_MEMORY_BASE_URL or MAIP_MEMORY_INGEST_API_TOKEN"
    url = f"{base_url.rstrip('/')}/v1/events"
    body = json.dumps(_maip_body(event), ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=url,
        method="POST",
        data=body,
        headers={
            "authorization": f"Bearer {token}",
            "content-type": "application/json; charset=utf-8",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout_sec) as response:  # nosec B310 - explicit operator URL
            return 200 <= response.status < 300, f"http {response.status}"
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:500]
        return False, f"http {exc.code}: {raw}"
    except Exception as exc:  # nosec B110 - best-effort sync path reports error text
        return False, str(exc)


def _iter_outbox_events(outbox_dir: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not outbox_dir.exists():
        return events
    for path in sorted(outbox_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("event_id"):
                events.append(payload)
    return events


def _sync_events(events: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    sent_path = Path(args.sent_path)
    if not sent_path.is_absolute():
        sent_path = ROOT / sent_path
    sent_ids = _load_sent_ids(sent_path)
    base_url = args.base_url or os.getenv(args.base_url_env, "").strip()
    token = os.getenv(args.token_env, "").strip()
    attempted = 0
    sent = 0
    failures: list[dict[str, str]] = []

    for event in events:
        event_id = str(event.get("event_id", ""))
        if not event_id or event_id in sent_ids:
            continue
        attempted += 1
        ok, message = _post_event(event, base_url=base_url, token=token, timeout_sec=args.timeout_sec)
        if ok:
            sent_ids.add(event_id)
            sent += 1
        else:
            failures.append({"event_id": event_id, "error": message})

    if sent:
        _save_sent_ids(sent_path, sent_ids)
    return {"attempted": attempted, "sent": sent, "failed": len(failures), "failures": failures[:20]}


def cmd_record(args: argparse.Namespace) -> int:
    schema = _load_schema()
    event = _build_event(args, schema)
    outbox_dir = Path(args.outbox_dir)
    if not outbox_dir.is_absolute():
        outbox_dir = ROOT / outbox_dir
    outbox_path = _append_outbox(event, outbox_dir)
    result: dict[str, Any] = {
        "recorded": True,
        "event_id": event["event_id"],
        "event_type": event["event_type"],
        "outbox_path": outbox_path.as_posix(),
    }
    exit_code = 0
    if args.sync:
        sync_result = _sync_events([event], args)
        result["sync"] = sync_result
        if args.strict_sync and sync_result["failed"]:
            exit_code = 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return exit_code


def cmd_flush(args: argparse.Namespace) -> int:
    outbox_dir = Path(args.outbox_dir)
    if not outbox_dir.is_absolute():
        outbox_dir = ROOT / outbox_dir
    events = _iter_outbox_events(outbox_dir)
    result = _sync_events(events, args)
    result["events_seen"] = len(events)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if args.strict_sync and result["failed"] else 0


def _add_common_sync_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--outbox-dir", default=str(DEFAULT_OUTBOX_DIR))
    parser.add_argument("--sent-path", default=str(DEFAULT_SENT_PATH))
    parser.add_argument("--base-url", default="")
    parser.add_argument("--base-url-env", default=DEFAULT_BASE_URL_ENV)
    parser.add_argument("--token-env", default=DEFAULT_TOKEN_ENV)
    parser.add_argument("--timeout-sec", type=float, default=8.0)
    parser.add_argument("--strict-sync", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record", help="Append a learning event to the outbox.")
    record.add_argument("--event-type", required=True)
    record.add_argument("--area", default="learning")
    record.add_argument("--source", default="codex_local")
    record.add_argument("--run-id", default="")
    record.add_argument("--correlation-id", default="")
    record.add_argument("--event-id", default="")
    record.add_argument("--status", default="observed")
    record.add_argument("--payload-json", default="{}")
    record.add_argument("--payload-file", default="")
    record.add_argument("--sync", action="store_true")
    _add_common_sync_args(record)
    record.set_defaults(func=cmd_record)

    flush = subparsers.add_parser("flush", help="Best-effort sync pending outbox events to MAIP memory.")
    _add_common_sync_args(flush)
    flush.set_defaults(func=cmd_flush)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
