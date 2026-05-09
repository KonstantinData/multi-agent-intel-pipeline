"""Validate CycloneDX SBOM artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_KEYS = {"bomFormat", "specVersion", "version", "metadata", "components"}
SUPPORTED_SPEC_VERSIONS = {"1.5", "1.6"}


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(message)


def validate_sbom(path: Path) -> None:
    _require(path.is_file(), f"SBOM file missing: {path.as_posix()}")
    data = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(data, dict), "SBOM must be a JSON object.")

    missing = REQUIRED_KEYS - set(data.keys())
    _require(not missing, f"SBOM missing keys: {sorted(missing)}")
    _require(data["bomFormat"] == "CycloneDX", "SBOM bomFormat must be CycloneDX.")
    _require(str(data["specVersion"]) in SUPPORTED_SPEC_VERSIONS, "SBOM specVersion must be supported.")

    components = data["components"]
    _require(isinstance(components, list), "SBOM components must be a list.")
    _require(len(components) > 0, "SBOM must contain at least one component.")
    seen_components: set[tuple[str, str, str, str]] = set()
    for index, component in enumerate(components):
        _require(isinstance(component, dict), f"SBOM component {index} must be an object.")
        _require(component.get("type"), f"SBOM component {index} missing type.")
        _require(component.get("name"), f"SBOM component {index} missing name.")
        identity = (
            str(component.get("type", "")),
            str(component.get("name", "")),
            str(component.get("version", "")),
            str(component.get("purl", component.get("bom-ref", ""))),
        )
        if identity in seen_components:
            continue
        seen_components.add(identity)
        if component.get("type") == "library":
            _require(component.get("version"), f"SBOM library {component.get('name')} missing version.")
            _require(component.get("purl"), f"SBOM library {component.get('name')} missing purl.")
            _require(str(component["purl"]).startswith("pkg:"), f"SBOM library {component.get('name')} purl must start with pkg:")

    metadata = data["metadata"]
    _require(isinstance(metadata, dict), "SBOM metadata must be an object.")
    metadata_component = metadata.get("component")
    _require(isinstance(metadata_component, dict), "SBOM metadata.component missing.")
    _require(metadata_component.get("name"), "SBOM metadata.component missing name.")
    _require(metadata_component.get("type"), "SBOM metadata.component missing type.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        default="bom/sbom/sbom.json",
        help="Path to SBOM JSON file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.path)
    validate_sbom(path)
    print(f"SBOM validation passed: {path.as_posix()}")


if __name__ == "__main__":
    main()
