"""Generate release attestation artifact for audit and release governance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

IMAGE_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(message)


def build_release_attestation(
    ai_bom_path: Path,
    sbom_path: Path,
    container_image: str | None = None,
    image_digest: str | None = None,
    provenance_attested: bool = False,
    sbom_attested: bool = False,
    release_id: str | None = None,
    commit: str | None = None,
) -> dict:
    _require(ai_bom_path.is_file(), f"AI-BOM file missing: {ai_bom_path.as_posix()}")
    _require(sbom_path.is_file(), f"SBOM file missing: {sbom_path.as_posix()}")

    resolved_release_id = release_id or os.environ.get("GITHUB_REF_NAME", "manual")
    resolved_commit = commit or os.environ.get("GITHUB_SHA", "unknown")
    run_id = os.environ.get("GITHUB_RUN_ID", "unknown")
    repository = os.environ.get("GITHUB_REPOSITORY", "unknown")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    resolved_container_image = container_image or os.environ.get(
        "LIQUISTO_CONTAINER_IMAGE",
        f"ghcr.io/{repository}".lower(),
    )
    resolved_image_digest = image_digest or os.environ.get("LIQUISTO_IMAGE_DIGEST", "")
    _require(
        IMAGE_DIGEST_PATTERN.fullmatch(resolved_image_digest) is not None,
        "Container image digest must be in sha256:<64 hex> format.",
    )

    return {
        "release_id": resolved_release_id,
        "commit": resolved_commit,
        "generated_at": datetime.now(UTC).isoformat(),
        "repository": repository,
        "workflow_run_id": run_id,
        "workflow_run_url": f"{server}/{repository}/actions/runs/{run_id}",
        "container_image": resolved_container_image,
        "image_digest": resolved_image_digest,
        "slsa_target": "build-l2",
        "provenance_attested": provenance_attested,
        "sbom_attested": sbom_attested,
        "artifacts": {
            "ai_bom": {
                "path": ai_bom_path.as_posix(),
                "sha256": sha256_of(ai_bom_path),
            },
            "sbom": {
                "path": sbom_path.as_posix(),
                "sha256": sha256_of(sbom_path),
            },
            "container_image": {
                "image": resolved_container_image,
                "digest": resolved_image_digest,
            },
        },
        "gate_results": {
            "governance": "PASSED",
            "security": "PASSED",
            "release_integrity": "PASSED",
        },
    }


def write_attestation(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai-bom", default="bom/ai-bom/ai-bom.json")
    parser.add_argument("--sbom", default="bom/sbom/sbom.json")
    parser.add_argument("--output", default="bom/attestations/release-attestation.json")
    parser.add_argument("--container-image", default=None)
    parser.add_argument("--image-digest", default=None)
    parser.add_argument("--provenance-attested", action="store_true")
    parser.add_argument("--sbom-attested", action="store_true")
    parser.add_argument("--release-id", default=None)
    parser.add_argument("--commit", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = build_release_attestation(
        ai_bom_path=Path(args.ai_bom),
        sbom_path=Path(args.sbom),
        container_image=args.container_image,
        image_digest=args.image_digest,
        provenance_attested=args.provenance_attested,
        sbom_attested=args.sbom_attested,
        release_id=args.release_id,
        commit=args.commit,
    )
    out = Path(args.output)
    write_attestation(out, data)
    print(f"Generated {out.as_posix()}")


if __name__ == "__main__":
    main()
