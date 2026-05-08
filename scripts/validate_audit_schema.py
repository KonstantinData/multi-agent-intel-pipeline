"""Validate repository audit-related schemas and governance structure."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REQUIRED_GOVERNANCE_FILES = [
    "docs/en/ai-act/risk-classification.md",
    "docs/en/ai-act/provider-deployer-role-classification.md",
    "docs/en/privacy/data-classification-policy.md",
    "docs/en/privacy/model-privacy-policy.md",
    "docs/en/privacy/audit-log-minimization-policy.md",
    "docs/en/security/threat-model.md",
    "docs/en/security/agent-to-agent-security.md",
    "docs/en/models/model-routing-policy.md",
    "docs/en/agents/agent-permission-matrix.md",
    "docs/en/audit/logging-schema.md",
    "SECURITY.md",
    ".github/CODEOWNERS",
    ".github/dependabot.yml",
    ".github/dependency-review-config.yml",
    ".github/workflows/compliance-security-ai.yml",
    ".github/workflows/dependency-review.yml",
    ".github/workflows/codeql.yml",
    ".github/workflows/release-attestation.yml",
    ".github/workflows/scorecard.yml",
    ".github/rulesets/main-protection.json",
    "policies/rego/ci_supply_chain.rego",
    "policies/license/dependency-license-policy.json",
    "policies/license/dependency-risk-exceptions.json",
    "policies/license/direct-dependency-owners.json",
]

REQUIRED_GOVERNANCE_DIRS = [
    "bom/sbom",
    "bom/ai-bom",
    "bom/ml-bom",
    "policies/rego",
    "policies/opa",
    "policies/agent-guardrails",
    "policies/model-routing",
    "policies/data-classification",
    "policies/license",
    "policies/tool-access",
]

REQUIRED_ATTESTATION_TOP_LEVEL = {
    "release_id",
    "commit",
    "generated_at",
    "repository",
    "workflow_run_id",
    "workflow_run_url",
    "container_image",
    "image_digest",
    "slsa_target",
    "provenance_attested",
    "sbom_attested",
    "artifacts",
    "gate_results",
}

IMAGE_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(message)


def validate_repository_structure(repo_root: Path) -> None:
    missing_files = [
        p
        for p in REQUIRED_GOVERNANCE_FILES
        if not (repo_root / p).is_file()
    ]
    missing_dirs = [
        p
        for p in REQUIRED_GOVERNANCE_DIRS
        if not (repo_root / p).is_dir()
    ]

    problems: list[str] = []
    if missing_files:
        problems.append("Missing required files:\n- " + "\n- ".join(missing_files))
    if missing_dirs:
        problems.append("Missing required directories:\n- " + "\n- ".join(missing_dirs))
    _require(not problems, "\n\n".join(problems))


def validate_release_attestation(path: Path) -> None:
    _require(path.is_file(), f"Release attestation file missing: {path.as_posix()}")
    data = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(data, dict), "Release attestation must be a JSON object.")

    missing = REQUIRED_ATTESTATION_TOP_LEVEL - set(data.keys())
    _require(not missing, f"Release attestation missing keys: {sorted(missing)}")

    artifacts = data.get("artifacts")
    _require(isinstance(artifacts, dict), "Release attestation artifacts must be an object.")
    for key in ("ai_bom", "sbom"):
        _require(key in artifacts, f"Release attestation missing artifacts.{key}")
        entry = artifacts[key]
        _require(isinstance(entry, dict), f"Release attestation artifacts.{key} must be an object.")
        _require("path" in entry, f"Release attestation artifacts.{key} missing path")
        _require("sha256" in entry, f"Release attestation artifacts.{key} missing sha256")
    _require("container_image" in artifacts, "Release attestation missing artifacts.container_image")
    image_entry = artifacts["container_image"]
    _require(isinstance(image_entry, dict), "Release attestation artifacts.container_image must be an object.")
    _require("image" in image_entry, "Release attestation artifacts.container_image missing image")
    _require("digest" in image_entry, "Release attestation artifacts.container_image missing digest")
    _require(str(data["container_image"]) == str(image_entry["image"]), "Container image mismatch.")
    _require(str(data["image_digest"]) == str(image_entry["digest"]), "Container image digest mismatch.")
    _require(
        IMAGE_DIGEST_PATTERN.fullmatch(str(data["image_digest"])) is not None,
        "Release attestation image_digest must be sha256:<64 hex>.",
    )
    _require(data["slsa_target"] == "build-l2", "Release attestation slsa_target must be build-l2.")
    _require(data["provenance_attested"] is True, "Release attestation provenance_attested must be true.")
    _require(data["sbom_attested"] is True, "Release attestation sbom_attested must be true.")

    gate_results = data.get("gate_results")
    _require(isinstance(gate_results, dict), "Release attestation gate_results must be an object.")
    for gate in ("governance", "security", "release_integrity"):
        _require(gate_results.get(gate) == "PASSED", f"Gate {gate} must be PASSED.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_attestation = sub.add_parser("release-attestation")
    p_attestation.add_argument(
        "--path",
        default="bom/attestations/release-attestation.json",
    )

    p_structure = sub.add_parser("repository-structure")
    p_structure.add_argument("--repo-root", default=".")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "release-attestation":
        path = Path(args.path)
        validate_release_attestation(path)
        print(f"Release attestation validation passed: {path.as_posix()}")
        return

    if args.command == "repository-structure":
        repo_root = Path(args.repo_root)
        validate_repository_structure(repo_root)
        print("Repository governance structure validation passed.")
        return

    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
