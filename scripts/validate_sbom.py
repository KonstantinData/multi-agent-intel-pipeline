"""Validate CycloneDX SBOM artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_KEYS = {"bomFormat", "specVersion", "version", "metadata", "components"}


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

    components = data["components"]
    _require(isinstance(components, list), "SBOM components must be a list.")
    _require(len(components) > 0, "SBOM must contain at least one component.")


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
