"""Validate GitHub Actions workflow hardening baseline."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

DISALLOWED_PATTERNS = [
    r"\bpull_request_target\b",
    r"permissions:\s*write-all",
    r"permissions:\s*\{\s*\}",
    r"ENABLE_CODEQL",
]

PLACEHOLDER_PATTERNS = [
    r"run:\s*echo\s+['\"]TODO['\"]",
    r"^\s*placeholder:\s*$",
    r"python\s*-\s*<<['\"]?PY['\"]?",
]

USES_PATTERN = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
SHA_PIN_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_PIN_PATTERN = re.compile(r"@sha256:[0-9a-f]{64}")


def _is_allowed_action_reference(reference: str) -> bool:
    if reference.startswith("./"):
        return True
    if reference.startswith("docker://"):
        return DIGEST_PIN_PATTERN.search(reference) is not None
    if "@" not in reference:
        return False
    action, ref = reference.rsplit("@", maxsplit=1)
    if SHA_PIN_PATTERN.fullmatch(ref):
        return True
    return False


def check_dockerfile_hardening(dockerfile: Path) -> list[str]:
    failures: list[str] = []
    if not dockerfile.is_file():
        failures.append("Dockerfile missing for OCI release artifact.")
        return failures
    text = dockerfile.read_text(encoding="utf-8")
    from_lines = [line for line in text.splitlines() if line.strip().startswith("FROM ")]
    if not from_lines:
        failures.append("Dockerfile missing FROM instruction.")
    for line in from_lines:
        if DIGEST_PIN_PATTERN.search(line) is None:
            failures.append("Dockerfile base image must be pinned by sha256 digest.")
    if "USER liquisto" not in text:
        failures.append("Dockerfile must run as the non-root liquisto user.")
    if "streamlit" not in text or "--server.address=0.0.0.0" not in text:
        failures.append("Dockerfile must start the Streamlit app on 0.0.0.0.")
    return failures


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
            image_env = re.match(r"^\s+[A-Z0-9_]*IMAGE:\s*(\S+)", line)
            if image_env and DIGEST_PIN_PATTERN.search(image_env.group(1)) is None:
                failures.append(f"{wf.as_posix()}: Docker-based scanner image must be digest-pinned: `{line.strip()}`")
            match = USES_PATTERN.match(line)
            if not match:
                continue
            ref = match.group(1)
            if not _is_allowed_action_reference(ref):
                failures.append(
                    f"{wf.as_posix()}: action reference must be pinned to a full-length SHA: `{ref}`"
                )

    return failures


def check_release_attestation_workflow(path: Path) -> list[str]:
    if not path.is_file():
        return [f"{path.as_posix()}: release attestation workflow missing"]
    text = path.read_text(encoding="utf-8")
    failures: list[str] = []
    for required in (
        "packages: write",
        "ghcr.io",
        "subject-digest:",
        "push-to-registry: true",
        "sbom-path:",
        "gh attestation verify",
        "--predicate-type https://cyclonedx.org/bom",
    ):
        if required not in text:
            failures.append(f"{path.as_posix()}: missing release hardening marker `{required}`")
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
    failures.extend(check_dockerfile_hardening(Path("Dockerfile")))
    failures.extend(check_release_attestation_workflow(workflow_dir / "release-attestation.yml"))
    if failures:
        raise SystemExit("Hardening gate failed:\n- " + "\n- ".join(failures))
    print("Workflow hardening baseline passed.")


if __name__ == "__main__":
    main()
