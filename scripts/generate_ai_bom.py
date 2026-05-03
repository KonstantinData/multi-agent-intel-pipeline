"""Generate AI-BOM artifacts for CI/CD governance."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class AiBomContext:
    release_id: str
    commit: str
    generated_at: str
    reviewed_at: str


def resolve_context(
    release_id: str | None = None,
    commit: str | None = None,
    generated_at: str | None = None,
) -> AiBomContext:
    now = datetime.now(UTC)
    return AiBomContext(
        release_id=release_id or os.environ.get("GITHUB_REF_NAME", "manual"),
        commit=commit or os.environ.get("GITHUB_SHA", "unknown"),
        generated_at=generated_at or now.isoformat(),
        reviewed_at=now.date().isoformat(),
    )


def build_ai_bom(context: AiBomContext) -> dict:
    return {
        "release_id": context.release_id,
        "commit": context.commit,
        "generated_at": context.generated_at,
        "legal_scope": {
            "role": "REVIEW_REQUIRED",
            "use_case": "REVIEW_REQUIRED",
            "deployment_context": "REVIEW_REQUIRED",
            "cra_scope": "REVIEW_REQUIRED",
            "foss_scope": "REVIEW_REQUIRED",
            "reviewed_at": context.reviewed_at,
        },
        "models": [
            {
                "id": "local-llm-001",
                "name": "example-local-model",
                "version": "0.0.0",
                "runtime": "local",
                "route": "local",
                "license": "REVIEW_REQUIRED",
                "hash": "sha256:REVIEW_REQUIRED",
                "hosting_location": "local",
            }
        ],
        "agents": [
            {
                "id": "code-agent",
                "version": "1.0.0",
                "role": "code_generation",
                "permissions": ["repo_read", "repo_write"],
            }
        ],
        "tools": [
            {
                "id": "python",
                "version": "system",
                "scope": "ci",
            }
        ],
        "datasets": [],
    }


def write_ai_bom(output_path: Path, data: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = resolve_context(
        release_id=args.release_id,
        commit=args.commit,
        generated_at=args.generated_at,
    )
    data = build_ai_bom(context)
    out = Path(args.output)
    write_ai_bom(out, data)
    print(f"Generated {out.as_posix()}")


if __name__ == "__main__":
    main()
