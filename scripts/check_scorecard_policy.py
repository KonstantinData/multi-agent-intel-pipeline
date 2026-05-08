"""Local scorecard-adjacent policy gate – validates controllable Scorecard-like controls."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_SHA_PATTERN = re.compile(r"uses:.*@[0-9a-f]{40}")


def check_scorecard_policy(root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    wf_dir = root / ".github" / "workflows"

    for wf in sorted(wf_dir.glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "uses:" in stripped and "@" in stripped and "./" not in stripped:
                if not _SHA_PATTERN.search(line):
                    failures.append(f"{wf.name}: unpinned action: {stripped}")
        if "permissions:" not in text:
            failures.append(f"{wf.name}: missing permissions block")

    if not (wf_dir / "codeql.yml").is_file():
        failures.append("codeql.yml missing")
    if not (root / "SECURITY.md").is_file():
        failures.append("SECURITY.md missing")
    if not (wf_dir / "release-attestation.yml").is_file():
        failures.append("release-attestation.yml missing")

    return failures


def main() -> None:
    failures = check_scorecard_policy()
    if failures:
        sys.exit("Scorecard policy gate failed:\n- " + "\n- ".join(failures))
    print("Scorecard policy gate passed.")


if __name__ == "__main__":
    main()
