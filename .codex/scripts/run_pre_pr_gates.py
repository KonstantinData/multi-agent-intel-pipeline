"""Run compliance-security-ai gates locally before opening a PR."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from check_workflow_needs_result import evaluate_needs  # noqa: E402

REPORT_PATH = ROOT / "artifacts" / "pre_pr_gate_report.json"
PROGRESS_PATH = ROOT / "artifacts" / "pre_pr_gate_progress.json"

GITLEAKS_IMAGE = "zricethezav/gitleaks@sha256:105ac66a57b2bb8afb61a3b8a5dcc4817773d03724a7e8a515214cfe58225556"
TRIVY_IMAGE = "aquasec/trivy@sha256:fc10faf341a1d8fa8256c5ff1a6662ef74dd38b65034c8ce42346cf958a02d5d"
CONFTEST_IMAGE = "openpolicyagent/conftest@sha256:97b5f4e3f964ed4a7e8e0840a16b0ac88c082fd2ca3dc5d2f999f5cd35860c38"


@dataclass(frozen=True)
class Gate:
    name: str
    commands: tuple[str, ...]


def build_gates(base_ref: str) -> list[Gate]:
    base_lock = "artifacts/base_requirements.lock"
    return [
        Gate("lint", ("ruff check src scripts tests",)),
        Gate("type-check", ("mypy",)),
        Gate("bandit-sast", ("bandit -q -r src scripts -x tests",)),
        Gate(
            "dependency-lock-gate",
            (
                "uv pip compile requirements.txt --python-version 3.12 --output-file requirements.lock",
                "git diff --exit-code requirements.lock",
            ),
        ),
        Gate("dependency-vuln-gate", ("python scripts/run_pip_audit_with_policy.py",)),
        Gate(
            "secret-scan",
            (
                r"detect-secrets scan . --all-files --exclude-files \"(^|[\\/])(\\.git|\\.mypy_cache|\\.ruff_cache|\\.pytest_cache|venv|\\.venv|runs|reports|bom[\\/]sbom|bom[\\/]ai-bom)([\\/]|$)\" > .secrets.scan.json",
                "python scripts/validate_secret_scan.py detect-secrets .secrets.scan.json",
                (
                    "docker run --rm --platform linux/amd64 "
                    "-v \"%cd%:/repo\" -w /repo "
                    f"{GITLEAKS_IMAGE} detect --source . --config .gitleaks.toml "
                    "--report-format json --report-path .gitleaks.report.json --redact"
                ),
                "python scripts/validate_secret_scan.py gitleaks .gitleaks.report.json",
            ),
        ),
        Gate(
            "governance-gates",
            (
                "python scripts/check_no_dotenv_files.py",
                "python scripts/validate_audit_schema.py repository-structure",
                "python scripts/validate_ruleset_config.py",
            ),
        ),
        Gate(
            "policy-as-code-gate",
            (
                "python scripts/generate_actions_bom.py --output bom/actions/actions-bom.json",
                "python scripts/validate_actions_bom.py bom/actions/actions-bom.json",
                (
                    "docker run --rm --platform linux/amd64 "
                    "-v \"%cd%:/project\" -w /project "
                    f"{CONFTEST_IMAGE} verify -p policies/rego"
                ),
                (
                    "docker run --rm --platform linux/amd64 "
                    "-v \"%cd%:/project\" -w /project "
                    f"{CONFTEST_IMAGE} test .github/workflows .github/rulesets -p policies/rego"
                ),
            ),
        ),
        Gate("scorecard-policy-gate", ("python scripts/check_scorecard_policy.py",)),
        Gate("actions-hardening-gate", ("python scripts/check_github_actions_hardening.py",)),
        Gate("dependency-policy-gate", ("python scripts/validate_dependency_policy.py",)),
        Gate(
            "dependency-diff-gate",
            (
                f"git show {base_ref}:requirements.lock > {base_lock}",
                f"python scripts/dependency_diff.py {base_lock} requirements.lock --output bom/actions/dependency-diff.json",
            ),
        ),
        Gate(
            "vuln-scan-gate",
            (
                "python scripts/generate_trivyignore.py",
                (
                    "docker run --rm --platform linux/amd64 -v \"%cd%:/project\" "
                    f"{TRIVY_IMAGE} fs /project --exit-code 1 --severity HIGH,CRITICAL "
                    "--ignore-unfixed --ignorefile /project/.trivyignore --scanners vuln "
                    "--timeout 15m "
                    "--skip-dirs '.git' --skip-dirs '.mypy_cache' --skip-dirs '.ruff_cache' "
                    "--skip-dirs '.pytest_cache' --skip-dirs 'bom'"
                ),
                (
                    "docker run --rm --platform linux/amd64 -v \"%cd%:/project\" "
                    f"{TRIVY_IMAGE} config /project --exit-code 1 --severity HIGH,CRITICAL "
                    "--timeout 15m "
                    "--misconfig-scanners dockerfile --skip-dirs '.git' --skip-dirs 'bom'"
                ),
            ),
        ),
        Gate("script-contract-tests", ("pytest -q tests/test_scripts_contracts.py",)),
        Gate(
            "architecture-tests",
            (
                "pytest -q tests/architecture --collect-only --junitxml=reports/architecture-collect.xml",
                "pytest -q tests/architecture --junitxml=reports/architecture.xml",
            ),
        ),
        Gate(
            "runtime-contract-tests",
            (
                (
                    "pytest -q tests/meeting_readiness tests/golden "
                    "tests/test_query_migration.py tests/test_query_consistency.py tests/smoke "
                    "--junitxml=reports/runtime-contracts.xml"
                ),
            ),
        ),
        Gate("integration-tests", ("pytest -q -m integration --junitxml=reports/integration.xml",)),
        Gate(
            "ai-bom-gate",
            (
                "python scripts/generate_ai_bom.py --output bom/ai-bom/ai-bom.json",
                "python scripts/validate_ai_bom.py bom/ai-bom/ai-bom.json",
            ),
        ),
        Gate(
            "sbom-gate",
            (
                "python scripts/generate_sbom.py --mode files --output bom/sbom/sbom.json",
                "python scripts/validate_sbom.py bom/sbom/sbom.json",
            ),
        ),
        Gate(
            "provenance-gate",
            (
                (
                    "python -c \"from pathlib import Path;import hashlib;"
                    "out=Path('bom/attestations/compliance-manifest.sha256');"
                    "out.parent.mkdir(parents=True,exist_ok=True);"
                    "targets=['.github/workflows/compliance-security-ai.yml','requirements.txt','requirements.lock'];"
                    "out.write_text(''.join(f'{hashlib.sha256(Path(p).read_bytes()).hexdigest()}  {p}\\\\n' for p in targets),encoding='utf-8')\""
                ),
            ),
        ),
    ]


def _run(cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        shell=True,
        text=True,
        capture_output=True,
    )


def _run_capture(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def _subset_gates(all_gates: list[Gate], *, only: set[str], skip: set[str], start_at: str) -> list[Gate]:
    selected = all_gates
    if start_at:
        names = [g.name for g in selected]
        if start_at not in names:
            raise SystemExit(f"Unknown gate for --start-at: {start_at}")
        selected = selected[names.index(start_at):]
    if only:
        unknown = sorted(only - {g.name for g in selected})
        if unknown:
            raise SystemExit(f"Unknown gate(s) in --only: {unknown}")
        selected = [g for g in selected if g.name in only]
    if skip:
        unknown = sorted(skip - {g.name for g in selected})
        if unknown:
            raise SystemExit(f"Unknown gate(s) in --skip: {unknown}")
        selected = [g for g in selected if g.name not in skip]
    return selected


def _parse_set(raw: str) -> set[str]:
    if not raw.strip():
        return set()
    return {item.strip() for item in raw.split(",") if item.strip()}


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _extract_previous_results(report_path: Path) -> dict[str, str]:
    payload = _load_json(report_path)
    if payload is None:
        return {}
    raw_gates = payload.get("gates", [])
    if not isinstance(raw_gates, list):
        return {}
    results: dict[str, str] = {}
    for gate_item in raw_gates:
        if not isinstance(gate_item, dict):
            continue
        name = str(gate_item.get("name", "")).strip()
        result = str(gate_item.get("result", "")).strip()
        if name:
            results[name] = result
    return results


def _resolve_resume_start(
    *,
    gates: list[Gate],
    explicit_start: str,
    resume: bool,
    report_path: Path,
) -> str:
    if explicit_start:
        return explicit_start
    if not resume:
        return ""
    previous = _extract_previous_results(report_path)
    if not previous:
        return ""
    for gate in gates:
        if previous.get(gate.name) != "success":
            return gate.name
    return ""


def _gate_index(gates: list[Gate], gate_name: str) -> int:
    for idx, gate in enumerate(gates):
        if gate.name == gate_name:
            return idx
    return 10**9


def _min_gate(gates: list[Gate], gate_a: str, gate_b: str) -> str:
    if not gate_a:
        return gate_b
    if not gate_b:
        return gate_a
    if _gate_index(gates, gate_a) <= _gate_index(gates, gate_b):
        return gate_a
    return gate_b


def _extract_previous_head(report_path: Path) -> str:
    payload = _load_json(report_path)
    if payload is None:
        return ""
    head = str(payload.get("head_sha", "")).strip()
    return head


def _git_file_lines(args: list[str]) -> list[str]:
    proc = _run_capture(args)
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _changed_files_since(previous_head: str) -> list[str]:
    changed: set[str] = set()
    if previous_head:
        changed.update(
            _git_file_lines(
                [
                    "git",
                    "diff",
                    "--name-only",
                    "--diff-filter=ACMRTUXB",
                    f"{previous_head}..HEAD",
                ]
            )
        )
    changed.update(_git_file_lines(["git", "diff", "--name-only", "--diff-filter=ACMRTUXB"]))
    changed.update(_git_file_lines(["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", "--cached"]))
    changed.update(_git_file_lines(["git", "ls-files", "--others", "--exclude-standard"]))
    return sorted(changed)


def _current_head_sha() -> str:
    proc = _run_capture(["git", "rev-parse", "HEAD"])
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _is_python_or_python_config(path: str) -> bool:
    python_configs = {
        "mypy.ini",
        ".ruff.toml",
        "ruff.toml",
        "pyproject.toml",
    }
    return (
        path in python_configs
        or path.startswith("src/")
        or path.startswith("scripts/")
        or path.startswith("tests/")
    )


def _resolve_start_from_changes(gates: list[Gate], changed_files: list[str]) -> str:
    if not changed_files:
        return ""

    files = set(changed_files)

    if any(_is_python_or_python_config(path) for path in files):
        return "lint"
    if any(path in {"requirements.txt", "requirements.lock"} for path in files):
        return "dependency-lock-gate"
    if any(
        path.startswith(prefix)
        for path in files
        for prefix in (".github/workflows/", ".github/rulesets/", "policies/")
    ):
        return "policy-as-code-gate"
    if any(path in {"AGENTS.md", "README.md"} or path.startswith("docs/") for path in files):
        return "governance-gates"
    if any(path.startswith("knowledge/") for path in files):
        return "runtime-contract-tests"
    if any(path.startswith(".codex/") or path.startswith(".githooks/") for path in files):
        return "script-contract-tests"

    known_gate_names = {gate.name for gate in gates}
    if "secret-scan" in known_gate_names:
        return "secret-scan"
    return gates[0].name if gates else ""


def _write_progress(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="List gate names and exit.")
    parser.add_argument("--status", action="store_true", help="Print last known progress status and exit.")
    parser.add_argument("--resume", action="store_true", help="Resume from last failed gate in previous report.")
    parser.add_argument(
        "--resume-from-changes",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When resuming, rerun from the earliest gate affected by code changes since last run.",
    )
    parser.add_argument("--start-at", default="", help="Start execution from this gate.")
    parser.add_argument("--only", default="", help="Comma-separated gate names to run.")
    parser.add_argument("--skip", default="", help="Comma-separated gate names to skip.")
    parser.add_argument("--base-ref", default="origin/main", help="Base ref for dependency-diff-gate.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop at first failed gate.")
    parser.add_argument("--report", default=str(REPORT_PATH), help="JSON report output path.")
    parser.add_argument("--progress", default=str(PROGRESS_PATH), help="JSON progress output path.")
    return parser.parse_args()


def _print_status(progress_path: Path) -> None:
    payload = _load_json(progress_path)
    if not payload:
        print(f"No status yet. Progress file not found: {progress_path.as_posix()}")
        return
    status = str(payload.get("status", "running")).strip() or "running"
    updated_at = str(payload.get("updated_at", "")).strip()
    current_gate = str(payload.get("current_gate", "")).strip()
    gate_pos = payload.get("current_gate_index")
    gate_total = payload.get("total_gates")
    step_pos = payload.get("current_command_index")
    step_total = payload.get("current_command_total")
    command = str(payload.get("command", "")).strip()
    pipeline_result = str(payload.get("pipeline_result", "")).strip()
    failed_gates = payload.get("failed_gates", {})

    print(f"status: {status}")
    if updated_at:
        print(f"updated_at: {updated_at}")
    if current_gate:
        print(f"gate: {current_gate} ({gate_pos}/{gate_total})")
    if step_pos and step_total:
        print(f"step: {step_pos}/{step_total}")
    if command:
        print(f"command: {command}")
    if pipeline_result:
        print(f"pipeline_result: {pipeline_result}")
    if isinstance(failed_gates, dict) and failed_gates:
        print("failed_gates:")
        for gate_name, result in failed_gates.items():
            print(f"  - {gate_name}: {result}")


def main() -> None:
    args = parse_args()
    gates = build_gates(args.base_ref)

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    progress_path = Path(args.progress)
    if not progress_path.is_absolute():
        progress_path = ROOT / progress_path

    if args.list:
        for gate in gates:
            print(gate.name)
        return
    if args.status:
        _print_status(progress_path)
        return

    resume_start = _resolve_resume_start(
        gates=gates,
        explicit_start=args.start_at.strip(),
        resume=args.resume,
        report_path=report_path,
    )
    previous_head = _extract_previous_head(report_path) if args.resume else ""
    changed_files = _changed_files_since(previous_head) if args.resume_from_changes else []
    changed_start = _resolve_start_from_changes(gates, changed_files) if args.resume else ""
    start_at = _min_gate(gates, resume_start, changed_start)
    selected = _subset_gates(
        gates,
        only=_parse_set(args.only),
        skip=_parse_set(args.skip),
        start_at=start_at,
    )
    if not selected:
        raise SystemExit("No gates selected.")

    previous_results = _extract_previous_results(report_path) if args.resume else {}
    canonical_order = [g.name for g in gates]
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "resume_mode": bool(args.resume),
        "resume_from_changes": bool(args.resume and args.resume_from_changes),
        "resolved_start_at": start_at or "",
        "resume_start_at": resume_start or "",
        "changed_start_at": changed_start or "",
        "changed_files_since_last_run": changed_files,
        "previous_head_sha": previous_head,
        "head_sha": _current_head_sha(),
        "gates": [],
    }
    needs: dict[str, dict[str, str]] = {}
    selected_names = {gate.name for gate in selected}

    for gate_name in canonical_order:
        if gate_name in selected_names:
            continue
        if previous_results.get(gate_name) == "success":
            report["gates"].append({"name": gate_name, "result": "success", "source": "previous_report"})
            needs[gate_name] = {"result": "success"}

    total = len(selected)
    for gate_index, gate in enumerate(selected, start=1):
        gate_started_at = datetime.now(UTC)
        print(f"\n=== [{gate_index}/{total}] {gate.name} ===", flush=True)
        gate_ok = True
        steps: list[dict[str, Any]] = []
        for step_index, cmd in enumerate(gate.commands, start=1):
            print(f"[{gate.name} {step_index}/{len(gate.commands)}] $ {cmd}", flush=True)
            _write_progress(
                progress_path,
                {
                    "updated_at": datetime.now(UTC).isoformat(),
                    "current_gate": gate.name,
                    "current_gate_index": gate_index,
                    "total_gates": total,
                    "current_command_index": step_index,
                    "current_command_total": len(gate.commands),
                    "command": cmd,
                    "report_path": report_path.as_posix(),
                },
            )
            proc = _run(cmd)
            steps.append(
                {
                    "command": cmd,
                    "returncode": proc.returncode,
                    "stdout": proc.stdout[-4000:],
                    "stderr": proc.stderr[-4000:],
                }
            )
            if proc.returncode != 0:
                gate_ok = False
                if proc.stdout:
                    print(proc.stdout, flush=True)
                if proc.stderr:
                    print(proc.stderr, flush=True)
                break
        result = "success" if gate_ok else "failure"
        needs[gate.name] = {"result": result}
        gate_elapsed_seconds = (datetime.now(UTC) - gate_started_at).total_seconds()
        report["gates"].append(
            {
                "name": gate.name,
                "result": result,
                "elapsed_seconds": round(gate_elapsed_seconds, 2),
                "steps": steps,
            }
        )
        print(f"[{result.upper()}] {gate.name} ({gate_elapsed_seconds:.1f}s)", flush=True)
        if not gate_ok and args.fail_fast:
            break

    failures = evaluate_needs(needs)
    report["pipeline_status"] = {
        "result": "success" if not failures else "failure",
        "failed_gates": failures,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_progress(
        progress_path,
        {
            "updated_at": datetime.now(UTC).isoformat(),
            "status": "completed",
            "pipeline_result": report["pipeline_status"]["result"],
            "failed_gates": failures,
            "report_path": report_path.as_posix(),
        },
    )
    print(f"\nReport written: {report_path.as_posix()}", flush=True)
    print(f"Progress written: {progress_path.as_posix()}", flush=True)

    if failures:
        print("\nFailed gates:", flush=True)
        for name, result in failures.items():
            print(f"- {name}: {result}", flush=True)
        raise SystemExit(1)
    print("\nAll required compliance-security-ai gates passed.", flush=True)


if __name__ == "__main__":
    main()
