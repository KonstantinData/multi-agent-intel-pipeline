"""Generate a CycloneDX SBOM baseline from repository files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

EXCLUDED_DIR_NAMES = {".git", "venv", "__pycache__", ".pytest_cache"}


def should_exclude(path: Path) -> bool:
    return any(part in EXCLUDED_DIR_NAMES for part in path.parts)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_sbom(repo_root: Path) -> dict:
    components: list[dict] = []
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        if should_exclude(p):
            continue
        rel = p.relative_to(repo_root).as_posix()
        components.append(
            {
                "type": "file",
                "name": rel,
                "version": "1",
                "hashes": [{"alg": "SHA-256", "content": sha256_of(p)}],
            }
        )

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "tools": [{"vendor": "github-actions", "name": "sbom-gate", "version": "1"}],
            "component": {
                "type": "application",
                "name": os.environ.get("GITHUB_REPOSITORY", "repository"),
                "version": os.environ.get("GITHUB_SHA", "unknown"),
            },
        },
        "components": components,
    }


def write_sbom(output_path: Path, data: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="bom/sbom/sbom.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root)
    data = build_sbom(repo_root)
    out = Path(args.output)
    write_sbom(out, data)
    print(f"Generated {out.as_posix()} with {len(data['components'])} components.")


if __name__ == "__main__":
    main()
