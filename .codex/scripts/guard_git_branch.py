"""Block unsafe Git operations on main and record guard failures."""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404 - fixed git/recorder invocations only
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RECORDER = ROOT / ".codex" / "scripts" / "record_learning_event.py"
PROTECTED_BRANCH = "main"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)  # nosec B603


def _current_branch() -> str:
    result = _run(["git", "branch", "--show-current"])
    return result.stdout.strip() if result.returncode == 0 else ""


def _record_failure(*, hook: str, reason: str, details: dict[str, Any]) -> None:
    if not RECORDER.is_file():
        return
    payload = {
        "hook": hook,
        "reason": reason,
        "current_branch": _current_branch(),
        **details,
    }
    subprocess.run(  # nosec B603 - fixed local recorder path
        [
            sys.executable,
            str(RECORDER),
            "record",
            "--event-type",
            "git_branch_guard_failed",
            "--area",
            "governance",
            "--source",
            f"git_{hook}",
            "--correlation-id",
            f"git-{hook}-{payload.get('current_branch') or 'unknown'}",
            "--status",
            "blocked",
            "--payload-json",
            json.dumps(payload, ensure_ascii=False),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _fail(*, hook: str, reason: str, details: dict[str, Any]) -> int:
    _record_failure(hook=hook, reason=reason, details=details)
    print("Git branch guard blocked this operation.", file=sys.stderr)
    print(f"Reason: {reason}", file=sys.stderr)
    print("Required workflow: create a PR branch from origin/main and open a pull request to main.", file=sys.stderr)
    return 1


def _parse_pre_push_stdin(raw: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            refs.append(
                {
                    "local_ref": parts[0],
                    "local_sha": parts[1],
                    "remote_ref": parts[2],
                    "remote_sha": parts[3],
                }
            )
    return refs


def guard_pre_commit() -> int:
    branch = _current_branch()
    if branch == PROTECTED_BRANCH:
        return _fail(
            hook="pre-commit",
            reason="commits on local main are forbidden",
            details={"protected_branch": PROTECTED_BRANCH},
        )
    return 0


def guard_pre_push() -> int:
    branch = _current_branch()
    stdin_raw = sys.stdin.read() if not sys.stdin.closed else ""
    refs = _parse_pre_push_stdin(stdin_raw)
    if branch == PROTECTED_BRANCH:
        return _fail(
            hook="pre-push",
            reason="pushes from local main are forbidden",
            details={"protected_branch": PROTECTED_BRANCH, "refs": refs},
        )
    for item in refs:
        if item.get("remote_ref") == f"refs/heads/{PROTECTED_BRANCH}":
            return _fail(
                hook="pre-push",
                reason="direct pushes to remote main are forbidden",
                details={"protected_branch": PROTECTED_BRANCH, "refs": refs},
            )
        if item.get("local_ref") == f"refs/heads/{PROTECTED_BRANCH}":
            return _fail(
                hook="pre-push",
                reason="pushes from local main ref are forbidden",
                details={"protected_branch": PROTECTED_BRANCH, "refs": refs},
            )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hook", choices=["pre-commit", "pre-push"], required=True)
    args = parser.parse_args()
    if args.hook == "pre-commit":
        return guard_pre_commit()
    return guard_pre_push()


if __name__ == "__main__":
    raise SystemExit(main())
