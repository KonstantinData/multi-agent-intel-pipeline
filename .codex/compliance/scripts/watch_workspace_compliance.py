"""Continuously check changed files for compliance, independent of commits."""
from __future__ import annotations

import argparse
import subprocess  # nosec B404
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER = REPO_ROOT / ".codex" / "compliance" / "scripts" / "check_compliance_policies.py"


def _run_once(*, purpose: str, risk_level: str, strict: bool) -> int:
    command = [
        sys.executable,
        str(CHECKER),
        "--changed-only",
        "--purpose",
        purpose,
        "--risk-level",
        risk_level,
    ]
    if strict:
        command.append("--strict")
    completed = subprocess.run(command, check=False)  # nosec B603
    return int(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval-sec", type=float, default=5.0)
    parser.add_argument("--purpose", default="runtime_code")
    parser.add_argument("--risk-level", default="medium")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    interval = max(args.interval_sec, 1.0)
    while True:
        _run_once(purpose=args.purpose, risk_level=args.risk_level, strict=args.strict)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
