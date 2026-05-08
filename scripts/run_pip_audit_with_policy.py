"""Run pip-audit and apply CVE exceptions only when valid and not expired."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCEPTIONS_FILE = ROOT / "policies" / "license" / "dependency-risk-exceptions.json"
LOCKFILE = ROOT / "requirements.lock"


def _load_exceptions() -> dict[str, dict]:
    data = json.loads(EXCEPTIONS_FILE.read_text(encoding="utf-8"))
    today = date.today()
    valid: dict[str, dict] = {}
    expired: list[str] = []
    for exc in data.get("exceptions", []):
        cve_id = exc.get("id", "")
        try:
            expires = date.fromisoformat(exc["expires"])
        except (KeyError, ValueError):
            expired.append(f"{cve_id}: invalid or missing expires")
            continue
        if expires < today:
            expired.append(f"{cve_id} (package: {exc.get('package', '?')}, expired: {exc['expires']})")
        else:
            valid[cve_id] = exc
    if expired:
        raise SystemExit("Expired CVE exceptions block pip-audit run:\n- " + "\n- ".join(expired))
    return valid


def main() -> None:
    valid_exceptions = _load_exceptions()

    cmd = [
        sys.executable, "-m", "pip_audit",
        "--strict",
        "--progress-spinner", "off",
        "--format", "json",
        "-r", str(LOCKFILE),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    raw = result.stdout.strip()

    try:
        report = json.loads(raw) if raw else {"dependencies": []}
    except json.JSONDecodeError as err:
        raise SystemExit(f"pip-audit produced non-JSON output:\n{raw}\n{result.stderr}") from err

    unexcepted: list[str] = []
    for dep in report.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            vid = vuln.get("id", "")
            if vid not in valid_exceptions:
                unexcepted.append(
                    f"{dep.get('name', '?')}=={dep.get('version', '?')}: {vid} – {vuln.get('description', '')[:120]}"
                )

    if unexcepted:
        raise SystemExit("pip-audit found unexcepted vulnerabilities:\n- " + "\n- ".join(unexcepted))

    print(f"pip-audit passed. {len(valid_exceptions)} active exception(s) applied.")


if __name__ == "__main__":
    main()
