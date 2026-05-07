"""Generate AI-BOM artifacts from repository model-routing configuration."""

from __future__ import annotations

import argparse
import ast
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MODEL_SOURCE = "src/config/settings.py"
POLICY_SOURCE = "docs/en/models/model-routing-policy.md"


@dataclass(frozen=True)
class AiBomContext:
    release_id: str
    commit: str
    generated_at: str
    reviewed_at: str
    repo_root: Path


def resolve_context(
    release_id: str | None = None,
    commit: str | None = None,
    generated_at: str | None = None,
    repo_root: Path | None = None,
) -> AiBomContext:
    now = datetime.now(UTC)
    return AiBomContext(
        release_id=release_id or os.environ.get("GITHUB_REF_NAME", "manual"),
        commit=commit or os.environ.get("GITHUB_SHA", "unknown"),
        generated_at=generated_at or now.isoformat(),
        reviewed_at=now.date().isoformat(),
        repo_root=repo_root or Path("."),
    )


def _literal_from_assignment(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise SystemExit(f"Could not resolve {name} from {MODEL_SOURCE}")


def _load_model_routing(repo_root: Path) -> dict[str, Any]:
    settings_path = repo_root / MODEL_SOURCE
    tree = ast.parse(settings_path.read_text(encoding="utf-8"), filename=settings_path.as_posix())
    defaults = {
        "default_chat_model": _literal_from_assignment(tree, "DEFAULT_MODEL"),
        "default_structured_model": _literal_from_assignment(tree, "DEFAULT_STRUCTURED_MODEL"),
        "default_search_model": _literal_from_assignment(tree, "DEFAULT_SEARCH_MODEL"),
        "default_translation_model": _literal_from_assignment(tree, "DEFAULT_TRANSLATION_MODEL"),
        "default_extraction_model": _literal_from_assignment(tree, "DEFAULT_EXTRACTION_MODEL"),
    }
    role_models = _literal_from_assignment(tree, "ROLE_MODEL_DEFAULTS")
    structured_role_models = _literal_from_assignment(tree, "ROLE_STRUCTURED_MODEL_DEFAULTS")
    if not isinstance(role_models, dict) or not isinstance(structured_role_models, dict):
        raise SystemExit("Role model defaults must be dictionaries.")
    return {
        "defaults": defaults,
        "role_models": role_models,
        "structured_role_models": structured_role_models,
    }


def _model_entry(model_id: str, *, purposes: list[str], source: str) -> dict[str, Any]:
    return {
        "id": model_id,
        "name": model_id,
        "version": "vendor-managed",
        "provider": "openai",
        "runtime": "external_api",
        "route": "openai",
        "license": "vendor-service-terms",
        "integrity": "vendor-managed-no-local-weights",
        "hosting_location": "vendor-managed",
        "purposes": sorted(set(purposes)),
        "source": source,
    }


def build_ai_bom(context: AiBomContext) -> dict[str, Any]:
    routing = _load_model_routing(context.repo_root)
    model_purposes: dict[str, list[str]] = {}
    for purpose, model in routing["defaults"].items():
        model_purposes.setdefault(str(model), []).append(purpose)
    for role, model in routing["role_models"].items():
        model_purposes.setdefault(str(model), []).append(f"chat:{role}")
    for role, model in routing["structured_role_models"].items():
        model_purposes.setdefault(str(model), []).append(f"structured:{role}")

    role_bindings = [
        {
            "role": role,
            "chat_model": routing["role_models"][role],
            "structured_model": routing["structured_role_models"].get(role),
        }
        for role in sorted(routing["role_models"])
    ]

    return {
        "release_id": context.release_id,
        "commit": context.commit,
        "generated_at": context.generated_at,
        "legal_scope": {
            "role": "application-provider-and-deployer",
            "use_case": "pre-meeting intelligence briefing",
            "deployment_context": "operator-supervised business intelligence workflow",
            "cra_scope": "software-application-controls-only",
            "foss_scope": "runtime-dependencies-covered-by-sbom",
            "reviewed_at": context.reviewed_at,
            "policy_source": POLICY_SOURCE,
        },
        "models": [
            _model_entry(model_id, purposes=purposes, source=MODEL_SOURCE)
            for model_id, purposes in sorted(model_purposes.items())
        ],
        "agents": [
            {
                "id": role,
                "version": "repo-configured",
                "role": role,
                "permissions": ["role_scoped_llm_access"],
                "chat_model": binding["chat_model"],
                "structured_model": binding["structured_model"],
            }
            for role, binding in ((item["role"], item) for item in role_bindings)
        ],
        "tools": [
            {"id": "openai-api", "version": "vendor-managed", "scope": "model_inference"},
            {"id": "web-search", "version": "vendor-managed", "scope": "evidence_retrieval"},
            {"id": "python", "version": "ci-runtime", "scope": "validation_and_bom_generation"},
        ],
        "datasets": [],
        "role_bindings": role_bindings,
        "sources": [MODEL_SOURCE, POLICY_SOURCE],
    }


def write_ai_bom(output_path: Path, data: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="bom/ai-bom/ai-bom.json",
        help="Target path for generated AI-BOM JSON.",
    )
    parser.add_argument("--release-id", default=None)
    parser.add_argument("--commit", default=None)
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--repo-root", default=".")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = resolve_context(
        release_id=args.release_id,
        commit=args.commit,
        generated_at=args.generated_at,
        repo_root=Path(args.repo_root),
    )
    data = build_ai_bom(context)
    out = Path(args.output)
    write_ai_bom(out, data)
    print(f"Generated {out.as_posix()} with {len(data['models'])} models.")


if __name__ == "__main__":
    main()
