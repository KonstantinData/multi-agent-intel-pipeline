"""Manage the local Codex PR lifecycle without granting GitHub Actions write-fix power.

This script is a thin orchestrator around Git, gh, local gates, and the Codex
learning recorder. It can create or find a PR, poll checks, record failures, and
run an explicit operator-provided auto-fix command. It does not invent fixes by
itself; intelligent fixes remain Codex-session work.
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404 - fixed local GitHub/Git commands plus explicit operator fix command
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RECORDER = ROOT / ".codex" / "scripts" / "record_learning_event.py"
PRE_PR_GATES = ROOT / ".codex" / "scripts" / "run_pre_pr_gates.py"
REPORT_PATH = ROOT / "artifacts" / "codex-pr-lifecycle" / "report.json"
PROTECTED_BRANCH = "main"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _run(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=check)  # nosec B603


def _run_shell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, shell=True, capture_output=True, text=True, check=False)  # nosec B602


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _current_branch() -> str:
    proc = _run(["git", "branch", "--show-current"])
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _head_sha() -> str:
    proc = _run(["git", "rev-parse", "HEAD"])
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _ensure_not_main() -> None:
    branch = _current_branch()
    if branch == PROTECTED_BRANCH:
        _record_event(
            event_type="git_branch_guard_failed",
            area="governance",
            source="pr_lifecycle",
            status="blocked",
            correlation_id="pr-lifecycle-main",
            payload={"reason": "pr lifecycle may not run on main", "branch": branch},
        )
        raise SystemExit("Refusing to run PR lifecycle on main. Create a PR branch first.")


def _record_event(
    *,
    event_type: str,
    area: str,
    source: str,
    status: str,
    correlation_id: str,
    payload: dict[str, Any],
    sync: bool = False,
) -> None:
    if not RECORDER.is_file():
        return
    command = [
        sys.executable,
        str(RECORDER),
        "record",
        "--event-type",
        event_type,
        "--area",
        area,
        "--source",
        source,
        "--status",
        status,
        "--correlation-id",
        correlation_id,
        "--run-id",
        correlation_id,
        "--payload-json",
        json.dumps(payload, ensure_ascii=False),
    ]
    if sync:
        command.append("--sync")
    _run(command)


def _create_branch(branch_name: str) -> None:
    status = _run(["git", "status", "--porcelain"])
    if status.stdout.strip():
        raise SystemExit("Working tree must be clean before creating a branch from origin/main.")
    _run(["git", "fetch", "origin", PROTECTED_BRANCH], check=True)
    _run(["git", "checkout", "-B", branch_name, f"origin/{PROTECTED_BRANCH}"], check=True)


def _run_local_gates(*, resume: bool, fail_fast: bool) -> dict[str, Any]:
    command = [sys.executable, str(PRE_PR_GATES)]
    if resume:
        command.append("--resume")
    if fail_fast:
        command.append("--fail-fast")
    started = _utc_now_iso()
    proc = _run(command)
    result = {
        "command": command,
        "started_at": started,
        "completed_at": _utc_now_iso(),
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }
    _record_event(
        event_type="pre_pr_gate_completed",
        area="ci",
        source="pr_lifecycle",
        status="passed" if proc.returncode == 0 else "failed",
        correlation_id=f"pre-pr-{_current_branch()}-{_head_sha()[:12]}",
        payload=result,
    )
    return result


def _pr_view() -> dict[str, Any] | None:
    proc = _run(["gh", "pr", "view", "--json", "number,url,state,headRefName,baseRefName,title"])
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _create_or_get_pr(*, title: str, body: str, draft: bool) -> dict[str, Any]:
    existing = _pr_view()
    if existing:
        return existing
    command = ["gh", "pr", "create", "--base", PROTECTED_BRANCH, "--head", _current_branch(), "--title", title, "--body", body]
    if draft:
        command.append("--draft")
    proc = _run(command)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip() or "gh pr create failed")
    created = _pr_view()
    if not created:
        raise SystemExit("PR was created but gh pr view could not read it.")
    return created


def _load_pr(pr: str) -> dict[str, Any]:
    target = pr or ""
    command = ["gh", "pr", "view"]
    if target:
        command.append(target)
    command.extend(["--json", "number,url,state,headRefName,baseRefName,title"])
    proc = _run(command)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or "Unable to read PR.")
    return json.loads(proc.stdout)


def _pr_checks(pr: str) -> list[dict[str, Any]]:
    command = [
        "gh",
        "pr",
        "checks",
    ]
    if pr:
        command.append(pr)
    command.extend([
        "--json",
        "name,state,conclusion,workflow,bucket,startedAt,completedAt,detailsUrl",
    ])
    proc = _run(command)
    if not proc.stdout.strip():
        return []
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def _check_bucket(check: dict[str, Any]) -> str:
    return str(check.get("bucket") or check.get("state") or check.get("conclusion") or "").lower()


def _failed_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failed_markers = {"fail", "failure", "cancelled", "timed_out", "action_required"}
    return [item for item in checks if _check_bucket(item) in failed_markers]


def _pending_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pending_markers = {"pending", "waiting", "queued", "in_progress", "skipping"}
    return [item for item in checks if _check_bucket(item) in pending_markers]


def _classify_policy(checks: list[dict[str, Any]]) -> list[str]:
    mapped: set[str] = set()
    for item in checks:
        text = " ".join(str(item.get(key, "")) for key in ("name", "workflow", "bucket", "conclusion")).lower()
        if any(word in text for word in ["dependency", "sbom", "license", "vuln"]):
            mapped.add(".codex/tasks/liquisto/dependency_lock_sbom_license_gate.toml")
        if any(word in text for word in ["secret", "gitleaks"]):
            mapped.add(".codex/tasks/liquisto/secret_guard_regression_gate.toml")
        if any(word in text for word in ["architecture", "contract"]):
            mapped.add(".codex/tasks/liquisto/contract_architecture_test_gate.toml")
        if any(word in text for word in ["runtime", "integration", "smoke", "test"]):
            mapped.add(".codex/tasks/liquisto/runtime_bugfix_repro_test_gate.toml")
        if any(word in text for word in ["policy", "scorecard", "hardening", "codeql", "bandit"]):
            mapped.add(".codex/tasks/liquisto/security_gate_regression.toml")
    return sorted(mapped) or [".codex/tasks/liquisto/security_gate_regression.toml"]


def _memory_safe_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    for item in checks:
        safe.append(
            {
                "name": item.get("name"),
                "workflow": item.get("workflow"),
                "bucket": item.get("bucket"),
                "state": item.get("state"),
                "conclusion": item.get("conclusion"),
            }
        )
    return safe


def cmd_create(args: argparse.Namespace) -> int:
    if args.create_branch:
        _create_branch(args.create_branch)
    _ensure_not_main()
    gate_result = _run_local_gates(resume=args.resume_gates, fail_fast=args.fail_fast) if args.run_gates else None
    pr = _create_or_get_pr(title=args.title, body=args.body, draft=args.draft)
    report = {
        "generated_at": _utc_now_iso(),
        "mode": "create",
        "branch": _current_branch(),
        "head_sha": _head_sha(),
        "pr": pr,
        "local_gates": gate_result,
    }
    _write_json(Path(args.report), report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.watch_checks:
        watch_args = argparse.Namespace(
            pr=str(pr["number"]),
            interval_sec=args.interval_sec,
            max_fix_cycles=args.max_fix_cycles,
            auto_fix_cmd=args.auto_fix_cmd,
            commit_message=args.commit_message,
            push=args.push,
            sync_learning=args.sync_learning,
            report=args.report,
        )
        return _watch_pr_checks(watch_args, pr)
    return 0


def _run_fix_cycle(args: argparse.Namespace, pr: dict[str, Any], failed: list[dict[str, Any]], cycle: int) -> dict[str, Any]:
    correlation_id = f"pr-{pr['number']}-fix-{cycle}"
    policies = _classify_policy(failed)
    _record_event(
        event_type="pr_fix_attempt_started",
        area="ci",
        source="pr_lifecycle",
        status="started",
        correlation_id=correlation_id,
        payload={"pr_number": pr["number"], "cycle": cycle, "policies": policies, "failed_checks": _memory_safe_checks(failed)},
    )
    proc = _run_shell(args.auto_fix_cmd)
    gate_result = _run_local_gates(resume=True, fail_fast=True)
    commit_result: dict[str, Any] = {"attempted": False}
    if args.commit_message:
        status = _run(["git", "status", "--porcelain"])
        if status.stdout.strip():
            _run(["git", "add", "-A"], check=True)
            commit = _run(["git", "commit", "-S", "-m", args.commit_message])
            commit_result = {"attempted": True, "returncode": commit.returncode, "stdout_tail": commit.stdout[-2000:], "stderr_tail": commit.stderr[-2000:]}
            if commit.returncode == 0 and args.push:
                _run(["git", "push"], check=True)
    result = {
        "cycle": cycle,
        "policies": policies,
        "auto_fix_returncode": proc.returncode,
        "auto_fix_stdout_tail": proc.stdout[-4000:],
        "auto_fix_stderr_tail": proc.stderr[-4000:],
        "local_gates": gate_result,
        "commit": commit_result,
    }
    _record_event(
        event_type="pr_fix_attempt_completed",
        area="ci",
        source="pr_lifecycle",
        status="passed" if proc.returncode == 0 and gate_result["returncode"] == 0 else "failed",
        correlation_id=correlation_id,
        payload={"pr_number": pr["number"], **result},
    )
    return result


def _watch_pr_checks(args: argparse.Namespace, pr: dict[str, Any]) -> int:
    cycles = 0
    observations: list[dict[str, Any]] = []
    while True:
        checks = _pr_checks(str(pr["number"]))
        failed = _failed_checks(checks)
        pending = _pending_checks(checks)
        observation = {
            "observed_at": _utc_now_iso(),
            "failed_count": len(failed),
            "pending_count": len(pending),
            "checks": checks,
        }
        observations.append(observation)
        _write_json(Path(args.report), {"pr": pr, "branch": _current_branch(), "head_sha": _head_sha(), "observations": observations[-20:]})

        if failed:
            policies = _classify_policy(failed)
            _record_event(
                event_type="pr_check_failed",
                area="ci",
                source="pr_lifecycle",
                status="failed",
                correlation_id=f"pr-{pr['number']}-{_head_sha()[:12]}",
                payload={"pr_number": pr["number"], "policies": policies, "failed_checks": _memory_safe_checks(failed)},
                sync=args.sync_learning,
            )
            if not args.auto_fix_cmd or cycles >= args.max_fix_cycles:
                print(json.dumps({"status": "failed", "pr": pr, "failed_checks": failed, "policies": policies}, indent=2, ensure_ascii=False))
                return 1
            cycles += 1
            _run_fix_cycle(args, pr, failed, cycles)
            _record_event(
                event_type="pr_recheck_completed",
                area="ci",
                source="pr_lifecycle",
                status="queued",
                correlation_id=f"pr-{pr['number']}-recheck-{cycles}",
                payload={"pr_number": pr["number"], "cycle": cycles},
            )
            time.sleep(args.interval_sec)
            continue

        if not pending and checks:
            _record_event(
                event_type="pr_recovered",
                area="ci",
                source="pr_lifecycle",
                status="passed",
                correlation_id=f"pr-{pr['number']}-{_head_sha()[:12]}",
                payload={"pr_number": pr["number"], "check_count": len(checks)},
                sync=args.sync_learning,
            )
            print(json.dumps({"status": "passed", "pr": pr, "check_count": len(checks)}, indent=2, ensure_ascii=False))
            return 0

        print(json.dumps({"status": "pending", "pr": pr["number"], "pending_count": len(pending)}, ensure_ascii=False))
        time.sleep(args.interval_sec)


def cmd_watch(args: argparse.Namespace) -> int:
    _ensure_not_main()
    pr = _load_pr(args.pr)
    return _watch_pr_checks(args, pr)


def cmd_status(args: argparse.Namespace) -> int:
    pr = _load_pr(args.pr)
    checks = _pr_checks(str(pr["number"]))
    payload = {"pr": pr, "branch": _current_branch(), "head_sha": _head_sha(), "checks": checks}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    payload = _read_json(Path(args.report))
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.set_defaults(report=str(REPORT_PATH))
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--create-branch", default="")
    create.add_argument("--title", default="Codex change")
    create.add_argument("--body", default="Created by .codex PR lifecycle.")
    create.add_argument("--draft", action=argparse.BooleanOptionalAction, default=True)
    create.add_argument("--run-gates", action="store_true")
    create.add_argument("--resume-gates", action="store_true")
    create.add_argument("--fail-fast", action="store_true")
    create.add_argument("--watch-checks", action=argparse.BooleanOptionalAction, default=True)
    create.add_argument("--interval-sec", type=int, default=180)
    create.add_argument("--max-fix-cycles", type=int, default=5)
    create.add_argument("--auto-fix-cmd", default="")
    create.add_argument("--commit-message", default="")
    create.add_argument("--push", action="store_true")
    create.add_argument("--sync-learning", action="store_true")
    create.add_argument("--report", default=str(REPORT_PATH))
    create.set_defaults(func=cmd_create)

    watch = subparsers.add_parser("watch")
    watch.add_argument("--pr", default="")
    watch.add_argument("--interval-sec", type=int, default=180)
    watch.add_argument("--max-fix-cycles", type=int, default=5)
    watch.add_argument("--auto-fix-cmd", default="")
    watch.add_argument("--commit-message", default="")
    watch.add_argument("--push", action="store_true")
    watch.add_argument("--sync-learning", action="store_true")
    watch.add_argument("--report", default=str(REPORT_PATH))
    watch.set_defaults(func=cmd_watch)

    status = subparsers.add_parser("status")
    status.add_argument("--pr", default="")
    status.set_defaults(func=cmd_status)

    report = subparsers.add_parser("report")
    report.add_argument("--report", default=str(REPORT_PATH))
    report.set_defaults(func=cmd_report)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
