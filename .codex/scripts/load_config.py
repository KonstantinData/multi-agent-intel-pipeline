"""Bootstrap .codex configuration in deterministic order.

Load order:
1) .codex/config.toml
2) instruction_index JSON (required)
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit("Python 3.11+ is required (tomllib missing).") from exc


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / ".codex" / "config.toml"


@dataclass(frozen=True)
class LoadedConfig:
    config_path: str
    config: dict[str, Any]
    instruction_index_json_path: str
    instruction_index: dict[str, Any]


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Missing config file: {path.as_posix()}")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Missing instruction index JSON: {path.as_posix()}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid instruction index JSON: {path.as_posix()} ({exc})") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Instruction index JSON must be an object: {path.as_posix()}")
    return data


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> LoadedConfig:
    config = _load_toml(config_path)
    instruction_cfg = config.get("instruction_index")
    if not isinstance(instruction_cfg, dict):
        raise SystemExit("Missing [instruction_index] table in .codex/config.toml")

    json_rel = instruction_cfg.get("json")
    if not isinstance(json_rel, str) or not json_rel.strip():
        raise SystemExit("Missing or invalid instruction_index.json path in .codex/config.toml")

    json_path = ROOT / json_rel

    instruction_index = _load_json(json_path)

    return LoadedConfig(
        config_path=config_path.as_posix(),
        config=config,
        instruction_index_json_path=json_path.as_posix(),
        instruction_index=instruction_index,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH.as_posix(),
        help="Path to .codex/config.toml",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Print a compact machine-readable summary.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    loaded = load_config(Path(args.config))
    summary = {
        "config_path": loaded.config_path,
        "instruction_index_json_path": loaded.instruction_index_json_path,
        "required_files_count": len(loaded.instruction_index.get("required_files", [])),
        "groups_count": len(loaded.instruction_index.get("groups", [])),
    }
    if args.print_json:
        print(json.dumps(summary, ensure_ascii=False))
        return
    print("Loaded .codex config bootstrap successfully.")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
