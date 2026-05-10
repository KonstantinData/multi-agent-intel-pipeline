"""Validate secret scanner JSON reports used by CI gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "runs",
    "reports",
}


def _load_json(path: Path) -> Any:
    if not path.is_file():
        raise SystemExit(f"Secret scan report missing: {path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8"))


def _is_excluded_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = set(normalized.split("/"))
    if parts & EXCLUDED_PARTS:
        return True
    return normalized.startswith("bom/sbom/") or normalized.startswith("bom/ai-bom/")


def validate_detect_secrets(path: Path) -> None:
    data = _load_json(path)
    if not isinstance(data, dict):
        raise SystemExit("detect-secrets report must be a JSON object.")
    results = data.get("results", {})
    if not isinstance(results, dict):
        raise SystemExit("detect-secrets report results must be an object.")
    count = sum(
        len(v)
        for filename, v in results.items()
        if isinstance(v, list) and not _is_excluded_path(str(filename))
    )
    print(f"detect-secrets potential secrets: {count}")
    if count:
        raise SystemExit("detect-secrets found potential secrets.")


def validate_gitleaks(path: Path) -> None:
    data = _load_json(path)
    if not isinstance(data, list):
        raise SystemExit("Gitleaks report must be a JSON array.")
    count = len(data)
    print(f"Gitleaks historical findings: {count}")
    if count:
        raise SystemExit("Gitleaks found historical secret findings.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("scanner", choices=("detect-secrets", "gitleaks"))
    parser.add_argument("report")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.report)
    if args.scanner == "detect-secrets":
        validate_detect_secrets(path)
        return
    validate_gitleaks(path)


if __name__ == "__main__":
    main()
