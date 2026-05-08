"""Generate a Bill of Materials for all GitHub Actions used in workflows."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

USES_PATTERN = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
SHA_PIN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_PIN = re.compile(r"@sha256:[0-9a-f]{64}")


def _classify(ref: str) -> str:
    if ref.startswith("./"):
        return "local"
    if ref.startswith("docker://"):
        return "docker"
    return "external"


def _sha_pinned(ref: str) -> bool:
    if "@" not in ref:
        return False
    _, pin = ref.rsplit("@", maxsplit=1)
    return bool(SHA_PIN.fullmatch(pin))


def _docker_digest_pinned(ref: str) -> bool:
    return bool(DIGEST_PIN.search(ref))


def collect_actions(workflow_dir: Path) -> list[dict]:
    entries: list[dict] = []
    for wf in sorted(workflow_dir.glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        lines = text.splitlines()
        for lineno, line in enumerate(lines, 1):
            m = USES_PATTERN.match(line)
            if not m:
                continue
            ref = m.group(1)
            kind = _classify(ref)
            action = ref.split("@")[0] if "@" in ref else ref
            pin = ref.split("@", 1)[1] if "@" in ref else ""
            entries.append(
                {
                    "workflow": wf.name,
                    "line": lineno,
                    "action": action,
                    "ref": ref,
                    "pin": pin,
                    "kind": kind,
                    "sha_pinned": _sha_pinned(ref) if kind == "external" else None,
                    "docker_digest_pinned": _docker_digest_pinned(ref) if kind == "docker" else None,
                }
            )
    return entries


def build_actions_bom(workflow_dir: Path) -> dict:
    entries = collect_actions(workflow_dir)
    return {"schema_version": "1.0", "entries": entries}


def write_actions_bom(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow-dir", default=".github/workflows")
    parser.add_argument("--output", default="bom/actions/actions-bom.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = build_actions_bom(Path(args.workflow_dir))
    out = Path(args.output)
    write_actions_bom(out, data)
    print(f"Actions-BOM written: {out} ({len(data['entries'])} entries)")


if __name__ == "__main__":
    main()
