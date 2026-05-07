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
    "role_bindings",
    "sources",
}

REQUIRED_LEGAL_SCOPE = {
    "role",
    "use_case",
    "deployment_context",
    "cra_scope",
    "foss_scope",
    "reviewed_at",
    "policy_source",
}

PLACEHOLDER_VALUES = {"", "unknown", "REVIEW_REQUIRED", "sha256:REVIEW_REQUIRED"}


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

    model_ids: set[str] = set()
    for index, model in enumerate(data["models"]):
        _require(isinstance(model, dict), f"AI-BOM model entry {index} must be an object.")
        for field in (
            "id",
            "name",
            "version",
            "provider",
            "runtime",
            "route",
            "license",
            "integrity",
            "hosting_location",
            "purposes",
            "source",
        ):
            _require(field in model, f"AI-BOM model entry {index} missing field: {field}")
            _require(str(model[field]) not in PLACEHOLDER_VALUES, f"AI-BOM model {model.get('id')} has placeholder {field}")
        _require(model["id"] not in model_ids, f"AI-BOM duplicate model id: {model['id']}")
        model_ids.add(model["id"])
        _require(isinstance(model["purposes"], list) and model["purposes"], f"AI-BOM model {model['id']} needs purposes")

    for index, agent in enumerate(data["agents"]):
        _require(isinstance(agent, dict), f"AI-BOM agent entry {index} must be an object.")
        for field in ("id", "version", "role", "permissions", "chat_model", "structured_model"):
            _require(field in agent, f"AI-BOM agent entry {index} missing field: {field}")
        _require(agent["chat_model"] in model_ids, f"AI-BOM agent {agent['id']} references unknown chat_model")
        _require(agent["structured_model"] in model_ids, f"AI-BOM agent {agent['id']} references unknown structured_model")

    for index, tool in enumerate(data["tools"]):
        _require(isinstance(tool, dict), f"AI-BOM tool entry {index} must be an object.")
        for field in ("id", "version", "scope"):
            _require(field in tool, f"AI-BOM tool entry {index} missing field: {field}")

    role_bindings = data["role_bindings"]
    _require(isinstance(role_bindings, list) and role_bindings, "AI-BOM role_bindings must be a non-empty list.")
    for binding in role_bindings:
        _require(isinstance(binding, dict), "AI-BOM role binding must be an object.")
        _require(binding.get("chat_model") in model_ids, f"AI-BOM role {binding.get('role')} references unknown chat model")
        _require(
            binding.get("structured_model") in model_ids,
            f"AI-BOM role {binding.get('role')} references unknown structured model",
        )

    sources = data["sources"]
    _require(isinstance(sources, list) and sources, "AI-BOM sources must be a non-empty list.")


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
