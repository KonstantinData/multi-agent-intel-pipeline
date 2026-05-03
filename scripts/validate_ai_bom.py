"""Validate AI-BOM artifacts for CI/CD governance gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_TOP_LEVEL = {
    "release_id",
    "commit",
    "generated_at",
    "legal_scope",
    "models",
    "agents",
    "tools",
    "datasets",
}

REQUIRED_LEGAL_SCOPE = {
    "role",
    "use_case",
    "deployment_context",
    "cra_scope",
    "foss_scope",
    "reviewed_at",
}


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(message)


def validate_ai_bom_data(data: dict) -> None:
    missing = REQUIRED_TOP_LEVEL - set(data.keys())
    _require(not missing, f"AI-BOM missing keys: {sorted(missing)}")

    legal_scope = data.get("legal_scope", {})
    _require(isinstance(legal_scope, dict), "AI-BOM legal_scope must be an object.")
    missing_legal = REQUIRED_LEGAL_SCOPE - set(legal_scope.keys())
    _require(not missing_legal, f"AI-BOM legal_scope missing keys: {sorted(missing_legal)}")

    for key in ("models", "agents", "tools"):
        entries = data.get(key)
        if not isinstance(entries, list):
            raise SystemExit(f"AI-BOM {key} must be a list.")
        _require(len(entries) > 0, f"AI-BOM {key} must contain at least one entry.")

    _require(isinstance(data.get("datasets"), list), "AI-BOM datasets must be a list.")

    model = data["models"][0]
    _require(isinstance(model, dict), "AI-BOM first model entry must be an object.")
    for field in ("id", "name", "version", "runtime", "route", "license", "hash", "hosting_location"):
        _require(field in model, f"AI-BOM first model missing field: {field}")

    agent = data["agents"][0]
    _require(isinstance(agent, dict), "AI-BOM first agent entry must be an object.")
    for field in ("id", "version", "role", "permissions"):
        _require(field in agent, f"AI-BOM first agent missing field: {field}")

    tool = data["tools"][0]
    _require(isinstance(tool, dict), "AI-BOM first tool entry must be an object.")
    for field in ("id", "version", "scope"):
        _require(field in tool, f"AI-BOM first tool missing field: {field}")


def validate_ai_bom_file(path: Path) -> None:
    _require(path.is_file(), f"AI-BOM file missing: {path.as_posix()}")
    data = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(data, dict), "AI-BOM must be a JSON object.")
    validate_ai_bom_data(data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        default="bom/ai-bom/ai-bom.json",
        help="Path to AI-BOM JSON file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.path)
    validate_ai_bom_file(path)
    print(f"AI-BOM validation passed: {path.as_posix()}")


if __name__ == "__main__":
    main()
