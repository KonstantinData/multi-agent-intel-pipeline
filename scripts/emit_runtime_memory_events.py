"""Emit runtime memory events from .codex/runtime/runtime_memory_reference.json.

This helper is intentionally small and explicit:
- loads allowed event kinds from the runtime memory reference file
- emits one or multiple events to /v1/memory/events
- reads back events for the same run_id from /v1/memory/events
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = ROOT / ".codex" / "runtime" / "runtime_memory_reference.json"
DEFAULT_BASE_URL = "https://liquisto-app-memory-worker-runtime-dev.still-butterfly-bbff.workers.dev"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Emit runtime memory events to the Cloudflare memory worker using event kinds "
            "declared in .codex/runtime/runtime_memory_reference.json."
        )
    )
    parser.add_argument(
        "--reference-file",
        default=str(DEFAULT_REFERENCE),
        help="Path to runtime_memory_reference.json (default: repo .codex runtime reference).",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Worker base URL (default: runtime_dev worker URL).",
    )
    parser.add_argument(
        "--run-id",
        default=f"runtime-emitter-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        help="Run id for emitted events.",
    )
    parser.add_argument(
        "--department",
        default="runtime",
        help="Department field for emitted events.",
    )
    parser.add_argument(
        "--source",
        default="codex_runtime_emitter",
        help="Source field for emitted events.",
    )
    parser.add_argument(
        "--kind",
        help="Single event kind to emit (must be in allowed_event_types).",
    )
    parser.add_argument(
        "--all-kinds",
        action="store_true",
        help="Emit one event for each allowed_event_types entry.",
    )
    parser.add_argument(
        "--payload-json",
        default="{}",
        help="JSON object merged into payload for each event.",
    )
    parser.add_argument(
        "--token-env",
        default="APP_MEMORY_INGEST_API_TOKEN",
        help="Environment variable containing ingest bearer token.",
    )
    parser.add_argument(
        "--skip-healthcheck",
        action="store_true",
        help="Skip GET /healthz before emitting.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Limit for readback GET /v1/memory/events (1..200).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be sent without making network requests.",
    )
    return parser


def _load_reference(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Reference file not found: {path.as_posix()}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Reference file is invalid JSON: {path.as_posix()} ({exc})") from exc

    allowed = data.get("allowed_event_types")
    if not isinstance(allowed, list) or not all(isinstance(item, str) and item for item in allowed):
        raise SystemExit("Reference file must contain non-empty string list: allowed_event_types")
    return data


def _resolve_kinds(*, allowed: list[str], selected_kind: str | None, all_kinds: bool) -> list[str]:
    if all_kinds:
        return allowed
    if selected_kind:
        if selected_kind not in allowed:
            raise SystemExit(
                f"Unsupported --kind '{selected_kind}'. Allowed: {', '.join(allowed)}"
            )
        return [selected_kind]
    return [allowed[0]]


def _parse_payload(payload_json: str) -> dict[str, Any]:
    try:
        parsed = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--payload-json must be valid JSON object: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SystemExit("--payload-json must decode to a JSON object.")
    return parsed


def _http_json(
    *,
    method: str,
    url: str,
    token: str | None = None,
    body_obj: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    headers = {"content-type": "application/json; charset=utf-8"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    body_bytes = None
    if body_obj is not None:
        body_bytes = json.dumps(body_obj, ensure_ascii=False).encode("utf-8")
    req = request.Request(url=url, method=method, headers=headers, data=body_bytes)
    try:
        with request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        err_raw = exc.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(err_raw) if err_raw else {}
        except json.JSONDecodeError:
            err_json = {"raw_error": err_raw}
        return exc.code, err_json
    except error.URLError as exc:
        raise SystemExit(f"HTTP request failed for {method} {url}: {exc}") from exc


def main() -> None:
    args = _build_arg_parser().parse_args()
    reference_path = (ROOT / args.reference_file).resolve() if not Path(args.reference_file).is_absolute() else Path(args.reference_file)
    reference = _load_reference(reference_path)
    allowed_types = reference["allowed_event_types"]
    kinds = _resolve_kinds(allowed=allowed_types, selected_kind=args.kind, all_kinds=args.all_kinds)
    payload_extra = _parse_payload(args.payload_json)

    if args.limit < 1 or args.limit > 200:
        raise SystemExit("--limit must be in range 1..200.")

    token = os.getenv(args.token_env, "").strip()
    if not args.dry_run and not token:
        raise SystemExit(
            f"Missing token env var '{args.token_env}'. Set it before running this script."
        )

    base_url = args.base_url.rstrip("/")
    print(f"reference_file={reference_path.as_posix()}")
    print(f"base_url={base_url}")
    print(f"run_id={args.run_id}")
    print(f"department={args.department}")
    print(f"kinds={','.join(kinds)}")
    print(f"dry_run={args.dry_run}")

    if args.dry_run:
        for kind in kinds:
            event_obj = {
                "run_id": args.run_id,
                "department": args.department,
                "kind": kind,
                "source": args.source,
                "payload": {
                    "emitted_at": _utc_now_iso(),
                    "kind": kind,
                    **payload_extra,
                },
            }
            print("would_post=" + json.dumps(event_obj, ensure_ascii=False))
        print(
            "would_get="
            + f"{base_url}/v1/memory/events?run_id={parse.quote(args.run_id)}&limit={args.limit}"
        )
        return

    if not args.skip_healthcheck:
        status, health = _http_json(method="GET", url=f"{base_url}/healthz")
        print(f"healthz_status={status}")
        print("healthz_body=" + json.dumps(health, ensure_ascii=False))
        if status != 200:
            raise SystemExit(f"Healthcheck failed with status {status}.")

    expected_kinds: list[str] = []
    for kind in kinds:
        event_obj = {
            "run_id": args.run_id,
            "department": args.department,
            "kind": kind,
            "source": args.source,
            "payload": {
                "emitted_at": _utc_now_iso(),
                "kind": kind,
                **payload_extra,
            },
        }
        status, post_body = _http_json(
            method="POST",
            url=f"{base_url}/v1/memory/events",
            token=token,
            body_obj=event_obj,
        )
        print(f"post_status[{kind}]={status}")
        print(f"post_body[{kind}]=" + json.dumps(post_body, ensure_ascii=False))
        if status != 201:
            raise SystemExit(f"POST failed for kind '{kind}' with status {status}.")
        expected_kinds.append(kind)

    list_url = f"{base_url}/v1/memory/events?run_id={parse.quote(args.run_id)}&limit={args.limit}"
    status, list_body = _http_json(method="GET", url=list_url, token=token)
    print(f"get_status={status}")
    print("get_body=" + json.dumps(list_body, ensure_ascii=False))
    if status != 200:
        raise SystemExit(f"GET failed with status {status}.")
    events = list_body.get("events") if isinstance(list_body, dict) else None
    if not isinstance(events, list):
        raise SystemExit("GET response does not contain an events list.")

    seen_kinds = {item.get("kind") for item in events if isinstance(item, dict)}
    missing = [kind for kind in expected_kinds if kind not in seen_kinds]
    if missing:
        raise SystemExit(f"Readback missing emitted kinds: {', '.join(missing)}")

    print("result=ok")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
