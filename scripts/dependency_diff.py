"""Produce a transitive dependency diff between two requirements.lock snapshots."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PKG_LINE = re.compile(r"^([A-Za-z0-9_.\-]+)==([^\s]+)")


def _parse_lockfile(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = PKG_LINE.match(line.strip())
        if m:
            result[m.group(1).lower()] = m.group(2)
    return result


def compute_diff(base: dict[str, str], head: dict[str, str]) -> dict:
    added = {k: head[k] for k in head if k not in base}
    removed = {k: base[k] for k in base if k not in head}
    changed = {k: {"from": base[k], "to": head[k]} for k in head if k in base and base[k] != head[k]}
    return {"added": added, "removed": removed, "changed": changed}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_lockfile", help="Base requirements.lock (e.g. from main branch)")
    parser.add_argument("head_lockfile", help="Head requirements.lock (current PR)")
    parser.add_argument("--output", default="bom/actions/dependency-diff.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base = _parse_lockfile(Path(args.base_lockfile))
    head = _parse_lockfile(Path(args.head_lockfile))
    diff = compute_diff(base, head)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(diff, indent=2), encoding="utf-8")
    total = len(diff["added"]) + len(diff["removed"]) + len(diff["changed"])
    print(f"Dependency diff written: {out} ({total} changes)")


if __name__ == "__main__":
    main()
