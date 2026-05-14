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

from check_workflow_needs_result import evaluate_needs

REPORT_PATH = ROOT / "artifacts" / "pre_pr_gate_report.json"

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
                    "-v \"$PWD:/repo\" -w /repo "
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
                    "-v \"$PWD:/project\" -w /project "
                    f"{CONFTEST_IMAGE} verify -p policies/rego"
                ),
                (
                    "docker run --rm --platform linux/amd64 "
                    "-v \"$PWD:/project\" -w /project "
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
                    "docker run --rm --platform linux/amd64 -v \"$PWD:/project\" "
                    f"{TRIVY_IMAGE} fs /project --exit-code 1 --severity HIGH,CRITICAL "
                    "--ignore-unfixed --ignorefile /project/.trivyignore --scanners vuln "
                    "--skip-dirs '.git' --skip-dirs '.mypy_cache' --skip-dirs '.ruff_cache' "
                    "--skip-dirs '.pytest_cache' --skip-dirs 'bom'"
                ),
                (
                    "docker run --rm --platform linux/amd64 -v \"$PWD:/project\" "
                    f"{TRIVY_IMAGE} config /project --exit-code 1 --severity HIGH,CRITICAL "
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
                "pytest -q tests/meeting_readiness tests/golden tests/test_query_*.py tests/smoke --junitxml=reports/runtime-contracts.xml",
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
                    "root=Path('.');out=root/'bom/attestations/compliance-manifest.sha256';"
                    "out.parent.mkdir(parents=True,exist_ok=True);"
                    "targets=[Path('.github/workflows/compliance-security-ai.yml'),Path('requirements.txt'),Path('requirements.lock')];"
                    "lines=[];"
                    "for p in targets:"
                    " data=p.read_bytes();"
                    " lines.append(f'{hashlib.sha256(data).hexdigest()}  {p.as_posix()}');"
                    "out.write_text('\\\\n'.join(lines)+'\\\\n',encoding='utf-8')\""
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="List gate names and exit.")
    parser.add_argument("--start-at", default="", help="Start execution from this gate.")
    parser.add_argument("--only", default="", help="Comma-separated gate names to run.")
    parser.add_argument("--skip", default="", help="Comma-separated gate names to skip.")
    parser.add_argument("--base-ref", default="origin/main", help="Base ref for dependency-diff-gate.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop at first failed gate.")
    parser.add_argument("--report", default=str(REPORT_PATH), help="JSON report output path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gates = build_gates(args.base_ref)

    if args.list:
        for gate in gates:
            print(gate.name)
        return

    selected = _subset_gates(
        gates,
        only=_parse_set(args.only),
        skip=_parse_set(args.skip),
        start_at=args.start_at.strip(),
    )
    if not selected:
        raise SystemExit("No gates selected.")

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "gates": [],
    }
    needs: dict[str, dict[str, str]] = {}

    for gate in selected:
        print(f"\n=== {gate.name} ===")
        gate_ok = True
        steps: list[dict[str, Any]] = []
        for cmd in gate.commands:
            print(f"$ {cmd}")
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
                print(proc.stdout)
                print(proc.stderr)
                break
        result = "success" if gate_ok else "failure"
        needs[gate.name] = {"result": result}
        report["gates"].append({"name": gate.name, "result": result, "steps": steps})
        print(f"[{result.upper()}] {gate.name}")
        if not gate_ok and args.fail_fast:
            break

    failures = evaluate_needs(needs)
    report["pipeline_status"] = {
        "result": "success" if not failures else "failure",
        "failed_gates": failures,
    }

    out_path = Path(args.report)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport written: {out_path.as_posix()}")

    if failures:
        print("\nFailed gates:")
        for name, result in failures.items():
            print(f"- {name}: {result}")
        raise SystemExit(1)
    print("\nAll required compliance-security-ai gates passed.")


if __name__ == "__main__":
    main()
