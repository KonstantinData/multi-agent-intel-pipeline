"""Generate a CycloneDX SBOM from repository files or installed Python packages."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXCLUDED_DIR_NAMES = {".git", "venv", ".venv", ".sbom-venv", "__pycache__", ".pytest_cache"}
LOCK_FILE = "requirements.lock"
PINNED_REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.!+-]+)$")


def should_exclude(path: Path) -> bool:
    return any(part in EXCLUDED_DIR_NAMES for part in path.parts)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalise_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _purl(name: str, version: str) -> str:
    return f"pkg:pypi/{_normalise_package_name(name)}@{version}"


def _read_locked_top_level(repo_root: Path) -> dict[str, str]:
    lock_path = repo_root / LOCK_FILE
    if not lock_path.is_file():
        return {}
    locked: dict[str, str] = {}
    for raw_line in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = PINNED_REQUIREMENT.fullmatch(line)
        if match is None:
            raise SystemExit(f"{LOCK_FILE} must contain exact pins only: {line}")
        name, version = match.groups()
        locked[_normalise_package_name(name)] = version
    return locked


def _metadata_component(dist: metadata.Distribution, locked: dict[str, str]) -> dict[str, Any]:
    name = dist.metadata["Name"]
    version = dist.version
    normalized = _normalise_package_name(name)
    component: dict[str, Any] = {
        "type": "library",
        "name": name,
        "version": version,
        "purl": _purl(name, version),
        "scope": "required",
        "properties": [
            {"name": "liquisto:dependency:top_level", "value": str(normalized in locked).lower()}
        ],
    }
    license_text = dist.metadata.get("License")
    if license_text:
        component["licenses"] = [{"license": {"name": license_text[:120]}}]
    summary = dist.metadata.get("Summary")
    if summary:
        component["description"] = summary
    return component


def _file_components(repo_root: Path) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
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
    return components


def build_sbom(repo_root: Path, *, mode: str = "files") -> dict[str, Any]:
    locked = _read_locked_top_level(repo_root)
    if mode == "environment":
        components = sorted(
            (_metadata_component(dist, locked) for dist in metadata.distributions()),
            key=lambda item: str(item["name"]).lower(),
        )
        missing = sorted(
            name
            for name, version in locked.items()
            if not any(
                _normalise_package_name(str(item["name"])) == name
                and str(item["version"]) == version
                for item in components
            )
        )
        if missing:
            raise SystemExit(f"Installed SBOM environment is missing locked dependencies: {missing}")
    elif mode == "files":
        components = _file_components(repo_root)
    else:
        raise SystemExit(f"Unsupported SBOM mode: {mode}")

    serial_seed = f"{os.environ.get('GITHUB_REPOSITORY', repo_root.resolve().name)}:{os.environ.get('GITHUB_SHA', 'local')}"
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, serial_seed)}",
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "tools": [
                {
                    "vendor": "liquisto",
                    "name": "scripts/generate_sbom.py",
                    "version": "2",
                }
            ],
            "component": {
                "type": "application",
                "name": os.environ.get("GITHUB_REPOSITORY", repo_root.resolve().name),
                "version": os.environ.get("GITHUB_SHA", "local"),
            },
            "properties": [
                {"name": "liquisto:sbom:mode", "value": mode},
                {"name": "liquisto:sbom:lock_file", "value": LOCK_FILE},
            ],
        },
        "components": components,
    }


def write_sbom(output_path: Path, data: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--mode", choices=("files", "environment"), default="files")
    parser.add_argument("--output", default="bom/sbom/sbom.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root)
    data = build_sbom(repo_root, mode=args.mode)
    out = Path(args.output)
    write_sbom(out, data)
    print(f"Generated {out.as_posix()} with {len(data['components'])} components.")


if __name__ == "__main__":
    main()
