"""Validate GitHub Actions workflow hardening baseline."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

DISALLOWED_PATTERNS = [
    r"\bpull_request_target\b",
    r"permissions:\s*write-all",
    r"permissions:\s*\{\s*\}",
]

PLACEHOLDER_PATTERNS = [
    r"run:\s*echo\s+['\"]TODO['\"]",
    r"^\s*placeholder:\s*$",
    r"python\s*-\s*<<['\"]?PY['\"]?",
]

USES_PATTERN = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
SHA_PIN_PATTERN = re.compile(r"^[0-9a-f]{40}$")

# Trusted exceptions where the upstream guidance recommends major-version tracking.
TRUSTED_MAJOR_TAG_ACTIONS = {
    "github/codeql-action/init@v4",
    "github/codeql-action/analyze@v4",
    "actions/dependency-review-action@v4",
    "actions/attest@v4",
}


def _is_allowed_action_reference(reference: str) -> bool:
    if reference.startswith("./") or reference.startswith("docker://"):
        return True
    if "@" not in reference:
        return False
    action, ref = reference.rsplit("@", maxsplit=1)
    if SHA_PIN_PATTERN.fullmatch(ref):
        return True
    return f"{action}@{ref}" in TRUSTED_MAJOR_TAG_ACTIONS


def check_workflow_hardening(workflow_files: list[Path]) -> list[str]:
    failures: list[str] = []
    if not workflow_files:
        failures.append("No workflow files found.")
        return failures

    for wf in workflow_files:
        text = wf.read_text(encoding="utf-8")
        if "permissions:" not in text:
            failures.append(f"{wf.as_posix()}: missing top-level permissions block")
        if "concurrency:" not in text:
            failures.append(f"{wf.as_posix()}: missing concurrency block")
        if "cancel-in-progress:" not in text:
            failures.append(f"{wf.as_posix()}: missing cancel-in-progress in concurrency block")
        if "timeout-minutes:" not in text:
            failures.append(f"{wf.as_posix()}: missing timeout-minutes in jobs")

        for pattern in DISALLOWED_PATTERNS:
            if re.search(pattern, text):
                failures.append(f"{wf.as_posix()}: matched disallowed pattern `{pattern}`")

        for pattern in PLACEHOLDER_PATTERNS:
            if re.search(pattern, text, flags=re.MULTILINE):
                failures.append(f"{wf.as_posix()}: matched placeholder pattern `{pattern}`")

        for line in text.splitlines():
            match = USES_PATTERN.match(line)
            if not match:
                continue
            ref = match.group(1)
            if not _is_allowed_action_reference(ref):
                failures.append(
                    f"{wf.as_posix()}: action reference must be SHA-pinned or trusted major tag: `{ref}`"
                )

    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory containing workflow *.yml files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    workflow_dir = Path(args.workflow_dir)
    files = sorted(workflow_dir.glob("*.yml"))
    failures = check_workflow_hardening(files)
    if failures:
        raise SystemExit("Hardening gate failed:\n- " + "\n- ".join(failures))
    print("Workflow hardening baseline passed.")


if __name__ == "__main__":
    main()
