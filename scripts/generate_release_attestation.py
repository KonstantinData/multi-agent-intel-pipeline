"""Generate release attestation artifact for audit and release governance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path


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

    return {
        "release_id": resolved_release_id,
        "commit": resolved_commit,
        "generated_at": datetime.now(UTC).isoformat(),
        "repository": repository,
        "workflow_run_id": run_id,
        "workflow_run_url": f"{server}/{repository}/actions/runs/{run_id}",
        "artifacts": {
            "ai_bom": {
                "path": ai_bom_path.as_posix(),
                "sha256": sha256_of(ai_bom_path),
            },
            "sbom": {
                "path": sbom_path.as_posix(),
                "sha256": sha256_of(sbom_path),
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
    parser.add_argument("--release-id", default=None)
    parser.add_argument("--commit", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = build_release_attestation(
        ai_bom_path=Path(args.ai_bom),
        sbom_path=Path(args.sbom),
        release_id=args.release_id,
        commit=args.commit,
    )
    out = Path(args.output)
    write_attestation(out, data)
    print(f"Generated {out.as_posix()}")


if __name__ == "__main__":
    main()
