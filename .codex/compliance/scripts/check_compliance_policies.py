"""Run context-aware compliance checks and emit learning artifacts."""
from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPLIANCE_SRC = Path(__file__).resolve().parents[1] / "src"
LEARNING_RECORDER = REPO_ROOT / ".codex" / "scripts" / "record_learning_event.py"
if str(COMPLIANCE_SRC) not in sys.path:
    sys.path.insert(0, str(COMPLIANCE_SRC))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _serialize_artifacts(artifacts: list[Any]) -> list[dict[str, Any]]:
    return [artifact.to_dict() for artifact in artifacts]


def _load_artifacts(path: Path) -> list[Any]:
    from compliance import ComplianceArtifact

    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return [
        ComplianceArtifact.from_dict(item)
        for item in payload
        if isinstance(item, dict)
    ]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _is_relevant_file(path: Path) -> bool:
    return path.suffix.lower() in {".py", ".md", ".yml", ".yaml", ".json", ".toml"}


def _git_lines(command: list[str]) -> list[str]:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)  # nosec B603
    except FileNotFoundError:
        return []
    if completed.returncode != 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _discover_changed_files() -> list[str]:
    paths: set[str] = set()

    # Tracked and unstaged changes
    for rel_path in _git_lines(["git", "diff", "--name-only", "HEAD"]):
        candidate = Path(rel_path)
        if candidate.exists() and _is_relevant_file(candidate):
            paths.add(str(candidate))

    # Untracked non-ignored files
    for rel_path in _git_lines(["git", "ls-files", "--others", "--exclude-standard"]):
        candidate = Path(rel_path)
        if candidate.exists() and _is_relevant_file(candidate):
            paths.add(str(candidate))

    # Ignored files below compliance scope still need checking
    compliance_root = Path(".codex/compliance")
    if compliance_root.exists():
        for candidate in compliance_root.rglob("*"):
            if candidate.is_file() and _is_relevant_file(candidate):
                paths.add(str(candidate))

    return sorted(paths)


def _run_tool(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )  # nosec B603
    except FileNotFoundError:
        return {
            "tool": command[0],
            "status": "failed",
            "exit_code": 127,
            "stdout": "",
            "stderr": f"Tool not found: {command[0]}",
            "command": command,
        }
    return {
        "tool": command[0],
        "status": "passed" if completed.returncode == 0 else "failed",
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "command": command,
    }


def _record_learning_event(
    *,
    event_type: str,
    payload: dict[str, Any],
    run_id: str,
    status: str,
    correlation_suffix: str = "",
) -> None:
    if not LEARNING_RECORDER.is_file():
        return
    correlation_id = run_id or "compliance-local"
    if correlation_suffix:
        correlation_id = f"{correlation_id}-{correlation_suffix}"
    subprocess.run(  # nosec B603 - fixed local recorder invocation
        [
            sys.executable,
            str(LEARNING_RECORDER),
            "record",
            "--event-type",
            event_type,
            "--area",
            "learning",
            "--source",
            "compliance_policy_check",
            "--status",
            status,
            "--correlation-id",
            correlation_id,
            "--run-id",
            run_id or "compliance-local",
            "--payload-json",
            json.dumps(payload, ensure_ascii=False),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _record_report_learning_events(*, report: dict[str, Any], run_id: str, status: str) -> None:
    summary_payload = {
        "policy_version": report.get("policy_version"),
        "files_checked": report.get("files_checked", 0),
        "blocking_violation_count": report.get("blocking_violation_count", 0),
        "failed_tool_checks_count": report.get("failed_tool_checks_count", 0),
        "pattern_count": len(report.get("patterns", [])),
        "proposal_count": len(report.get("proposals", [])),
        "proposal_validation_count": len(report.get("proposal_validations", [])),
        "status": status,
    }
    _record_learning_event(
        event_type="compliance_check_completed",
        payload=summary_payload,
        run_id=run_id,
        status=status,
    )

    proposals = report.get("proposals", [])
    if proposals:
        _record_learning_event(
            event_type="learning_pattern_candidate_created",
            payload={
                "policy_version": report.get("policy_version"),
                "proposal_count": len(proposals),
                "proposal_ids": [
                    str(item.get("proposal_id", ""))
                    for item in proposals
                    if isinstance(item, dict) and item.get("proposal_id")
                ][:25],
            },
            run_id=run_id,
            status="proposed",
            correlation_suffix="candidates",
        )

    accepted = [
        item
        for item in report.get("proposal_validations", [])
        if isinstance(item, dict) and item.get("verdict") == "accepted"
    ]
    if accepted:
        _record_learning_event(
            event_type="learning_pattern_accepted",
            payload={
                "policy_version": report.get("policy_version"),
                "accepted_count": len(accepted),
                "proposal_ids": [str(item.get("proposal_id", "")) for item in accepted if item.get("proposal_id")][:25],
            },
            run_id=run_id,
            status="accepted",
            correlation_suffix="accepted-patterns",
        )


def main() -> int:
    from compliance import (
        build_compliance_patterns,
        evaluate_file_compliance,
        generate_rule_proposals,
        load_compliance_policy,
        validate_rule_proposal,
    )
    
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="File paths to evaluate.")
    parser.add_argument("--purpose", default="runtime_code")
    parser.add_argument("--risk-level", default="medium")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--attempt-count", type=int, default=1)
    parser.add_argument(
        "--policy-path",
        default=".codex/compliance/policies/file_compliance_policy.json",
    )
    parser.add_argument(
        "--history-path",
        default="artifacts/compliance/history.json",
        help="Path used to persist compliance artifacts for learning.",
    )
    parser.add_argument(
        "--output-path",
        default="",
        help="Optional JSON output path for the current execution report.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 when at least one blocking violation is found.",
    )
    parser.add_argument(
        "--skip-ruff",
        action="store_true",
        help="Skip integrated ruff lint step.",
    )
    parser.add_argument(
        "--skip-bandit",
        action="store_true",
        help="Skip integrated bandit security step.",
    )
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Evaluate all relevant changed files in the working tree, including ignored files under .codex/compliance.",
    )
    args = parser.parse_args()

    policy = load_compliance_policy(args.policy_path)
    file_inputs = list(args.files)
    if args.changed_only:
        file_inputs = _discover_changed_files()
    if not file_inputs:
        report = {
            "policy_version": policy.version,
            "files_checked": 0,
            "artifacts": [],
            "patterns": [],
            "proposals": [],
            "proposal_validations": [],
            "blocking_violation_count": 0,
            "tool_checks": [],
            "failed_tool_checks_count": 0,
        }
        if args.output_path:
            _write_json(Path(args.output_path), report)
        else:
            sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        _record_report_learning_events(report=report, run_id=args.run_id, status="passed")
        return 0

    artifacts: list[Any] = []
    for entry in file_inputs:
        artifact = evaluate_file_compliance(
            file_path=entry,
            policy=policy,
            purpose=args.purpose,
            risk_level=args.risk_level,
            run_id=args.run_id,
            attempt_count=args.attempt_count,
        )
        artifacts.append(artifact)

    history_path = Path(args.history_path)
    history = _load_artifacts(history_path)
    combined_artifacts = history + artifacts
    _write_json(history_path, _serialize_artifacts(combined_artifacts))

    patterns = build_compliance_patterns(combined_artifacts)
    proposals = generate_rule_proposals(
        patterns,
        min_repeat_failures=policy.min_repeat_failures_for_optimizer,
    )
    indexed_patterns = {item.key: item for item in patterns}
    validations = [
        validate_rule_proposal(proposal=proposal, pattern=indexed_patterns[proposal.source_pattern_key])
        for proposal in proposals
        if proposal.source_pattern_key in indexed_patterns
    ]
    blocking_violations = [
        item
        for artifact in artifacts
        for item in artifact.violations
        if item.blocking
    ]
    tool_checks: list[dict[str, Any]] = []
    python_files = [entry for entry in file_inputs if Path(entry).suffix.lower() == ".py"]

    if python_files and not args.skip_ruff:
        tool_checks.append(_run_tool(["ruff", "check", "--fix", *python_files]))

    if python_files and not args.skip_bandit:
        bandit_targets = [
            entry
            for entry in python_files
            if (
                entry.startswith("src/")
                or entry.startswith("src\\")
                or entry.startswith("scripts/")
                or entry.startswith("scripts\\")
                or entry.startswith(".codex/compliance/src/")
                or entry.startswith(".codex\\compliance\\src\\")
                or entry.startswith(".codex/compliance/scripts/")
                or entry.startswith(".codex\\compliance\\scripts\\")
            )
            and "/tests/" not in entry.replace("\\", "/")
        ]
        if bandit_targets:
            tool_checks.append(_run_tool(["bandit", "-q", "-x", "tests", *bandit_targets]))

    failed_tool_checks = [item for item in tool_checks if item["status"] == "failed"]

    report = {
        "policy_version": policy.version,
        "files_checked": len(artifacts),
        "artifacts": _serialize_artifacts(artifacts),
        "patterns": [item.to_dict() for item in patterns],
        "proposals": [item.to_dict() for item in proposals],
        "proposal_validations": [item.to_dict() for item in validations],
        "blocking_violation_count": len(blocking_violations),
        "tool_checks": tool_checks,
        "failed_tool_checks_count": len(failed_tool_checks),
    }

    if args.output_path:
        _write_json(Path(args.output_path), report)
    else:
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    status = "failed" if blocking_violations or failed_tool_checks else "passed"
    _record_report_learning_events(report=report, run_id=args.run_id, status=status)

    if args.strict and (blocking_violations or failed_tool_checks):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
