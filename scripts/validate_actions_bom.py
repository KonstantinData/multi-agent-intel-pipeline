"""Validate an Actions-BOM file produced by generate_actions_bom.py."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def validate_actions_bom_file(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "entries" not in data:
        raise SystemExit(f"Invalid Actions-BOM structure: {path}")

    failures: list[str] = []
    for entry in data["entries"]:
        ref = entry.get("ref", "")
        kind = entry.get("kind", "")
        wf = entry.get("workflow", "?")
        line = entry.get("line", "?")

        if kind == "external" and not entry.get("sha_pinned"):
            failures.append(f"{wf}:{line}: external action not SHA-pinned: {ref}")
        if kind == "docker" and not entry.get("docker_digest_pinned"):
            failures.append(f"{wf}:{line}: docker action not digest-pinned: {ref}")
        if kind not in ("local", "docker", "external"):
            failures.append(f"{wf}:{line}: unknown action kind '{kind}': {ref}")

    if failures:
        raise SystemExit("Actions-BOM validation failed:\n- " + "\n- ".join(failures))
    print(f"Actions-BOM validation passed: {len(data['entries'])} entries checked.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("bom_path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_actions_bom_file(Path(args.bom_path))


if __name__ == "__main__":
    main()
