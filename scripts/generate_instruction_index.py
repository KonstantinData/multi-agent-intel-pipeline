"""Generate a canonical instruction index for .codex app-level rules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Minimal non-negotiable .codex app-level entry points.
REQUIRED_FILES = (
    ".codex/README.md",
    ".codex/config.toml",
    ".codex/policies/README.md",
    ".codex/policies/liquisto/README.md",
    ".codex/policies/liquisto/secret_policy.md",
    ".codex/policies/liquisto/tool_allowlist.md",
    ".codex/policies/liquisto/prompt_budget_policy.md",
    ".codex/config/README.md",
    ".codex/config/profiles/liquisto_fast.toml",
    ".codex/config/profiles/liquisto_standard.toml",
    ".codex/config/profiles/liquisto_deep.toml",
    ".codex/config/routing/model_routing.toml",
    ".codex/config/routing/tool_routing.toml",
    ".codex/tasks/README.md",
    ".codex/tasks/liquisto/README.md",
    ".codex/skills/README.md",
    ".codex/skills/liquisto/README.md",
)

INSTRUCTION_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "id": "codex_core",
        "title": "Codex Core Layer",
        "description": "Operating-layer objective, precedence, and trust model.",
        "globs": (
            ".codex/README.md",
            ".codex/config.toml",
        ),
    },
    {
        "id": "codex_policies",
        "title": "Codex Policies",
        "description": "Hard constraints for secrets, tools, memory, and budgets.",
        "globs": (
            ".codex/policies/README.md",
            ".codex/policies/liquisto/*.md",
        ),
    },
    {
        "id": "codex_profiles_and_routing",
        "title": "Codex Profiles and Routing",
        "description": "Risk/effort profiles and model/tool routing defaults.",
        "globs": (
            ".codex/config/README.md",
            ".codex/config/profiles/*.toml",
            ".codex/config/routing/*.toml",
        ),
    },
    {
        "id": "codex_tasks",
        "title": "Codex Task Gates",
        "description": "Executable rule tasks with trigger paths and acceptance criteria.",
        "globs": (
            ".codex/tasks/README.md",
            ".codex/tasks/liquisto/README.md",
            ".codex/tasks/liquisto/*.toml",
        ),
    },
    {
        "id": "codex_skills",
        "title": "Codex Skills",
        "description": "Deterministic execution playbooks for recurring task classes.",
        "globs": (
            ".codex/skills/README.md",
            ".codex/skills/liquisto/**/README.md",
            ".codex/skills/shared/**/README.md",
        ),
    },
)

PRECEDENCE_RULES = (
    ".codex policies",
    ".codex config (profiles + routing)",
    ".codex task gates",
    ".codex skills",
    ".codex memory/eval/telemetry (observational, non-normative)",
)

REQUIRED_STARTUP_MESSAGE = (
    "Pflicht-Startmeldung: Ich habe die .codex-App-Ebene vollständig gelesen und verstanden "
    "(Instruction-Index, Policies, Config/Routing, Tasks, Skills). "
    "Ich beginne jetzt mit der Ausführung gemäß diesen Regeln und dokumentiere jede "
    "Abweichung sofort mit Begründung."
)


def _collect_files(root: Path, globs: tuple[str, ...]) -> list[str]:
    collected: set[str] = set()
    for pattern in globs:
        for match in root.glob(pattern):
            if match.is_file():
                collected.add(match.relative_to(root).as_posix())
    return sorted(collected)


def build_instruction_index(root: Path = ROOT) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    all_paths: set[str] = set()
    for group in INSTRUCTION_GROUPS:
        files = _collect_files(root, tuple(group["globs"]))
        groups.append(
            {
                "id": group["id"],
                "title": group["title"],
                "description": group["description"],
                "files": files,
            }
        )
        all_paths.update(files)

    return {
        "schema_version": 1,
        "root": root.as_posix(),
        "precedence": list(PRECEDENCE_RULES),
        "required_startup_message": REQUIRED_STARTUP_MESSAGE,
        "required_files": list(REQUIRED_FILES),
        "groups": groups,
        "all_files": sorted(all_paths),
    }


def validate_instruction_index(index: dict[str, Any], root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    all_files = set(index.get("all_files", []))

    for rel in REQUIRED_FILES:
        if rel not in all_files:
            failures.append(f"Missing required instruction file in index: {rel}")
        elif not (root / rel).is_file():
            failures.append(f"Required instruction file does not exist on disk: {rel}")

    groups = index.get("groups", [])
    if not isinstance(groups, list) or not groups:
        failures.append("Instruction index has no groups.")
        return failures

    for group in groups:
        if not isinstance(group, dict):
            failures.append("Instruction group entry is not an object.")
            continue
        files = group.get("files")
        if not isinstance(files, list):
            failures.append(f"Instruction group missing file list: {group.get('id', 'unknown')}")
            continue
        if not files:
            failures.append(f"Instruction group has no resolved files: {group.get('id', 'unknown')}")
    return failures


def render_markdown(index: dict[str, Any]) -> str:
    lines = [
        "# Instruction Index",
        "",
        "Canonical index of instruction sources for `.codex` app-level rule loading.",
        "",
        "## Precedence",
        "",
    ]
    for idx, item in enumerate(index["precedence"], start=1):
        lines.append(f"{idx}. {item}")

    lines.extend(
        [
            "",
            "## Required Startup Confirmation",
            "",
            REQUIRED_STARTUP_MESSAGE,
            "",
            "## Groups",
            "",
        ]
    )
    for group in index["groups"]:
        lines.append(f"### {group['title']}")
        lines.append("")
        lines.append(group["description"])
        lines.append("")
        for rel in group["files"]:
            lines.append(f"- [{rel}]({rel})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(index: dict[str, Any], *, md_path: Path, json_path: Path | None = None) -> None:
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(index), encoding="utf-8")
    if json_path is not None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


def _normalize_text(value: str) -> str:
    return value.replace("\r\n", "\n").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=".codex/config/instruction_index.md",
        help="Markdown output path relative to repository root.",
    )
    parser.add_argument(
        "--json-output",
        default=".codex/config/instruction_index.json",
        help="JSON output path relative to repository root.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if existing output differs from generated output.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    index = build_instruction_index(ROOT)
    failures = validate_instruction_index(index, ROOT)
    if failures:
        raise SystemExit("Instruction index validation failed:\n- " + "\n- ".join(failures))

    output_path = ROOT / args.output
    json_output_path = ROOT / args.json_output if args.json_output else None
    new_md = render_markdown(index)
    new_json = json.dumps(index, indent=2, ensure_ascii=False)

    if args.check:
        if not output_path.is_file():
            raise SystemExit(f"Instruction index missing: {output_path.as_posix()}")
        current_md = output_path.read_text(encoding="utf-8")
        if _normalize_text(current_md) != _normalize_text(new_md):
            raise SystemExit(f"Instruction index markdown drift: {output_path.as_posix()}")
        if json_output_path is not None:
            if not json_output_path.is_file():
                raise SystemExit(f"Instruction index JSON missing: {json_output_path.as_posix()}")
            current_json = json_output_path.read_text(encoding="utf-8")
            if json.loads(current_json) != json.loads(new_json):
                raise SystemExit(f"Instruction index JSON drift: {json_output_path.as_posix()}")
        print("Instruction index check passed.")
        return

    write_outputs(index, md_path=output_path, json_path=json_output_path)
    print(f"Instruction index generated: {output_path.as_posix()}")
    if json_output_path is not None:
        print(f"Instruction index JSON generated: {json_output_path.as_posix()}")


if __name__ == "__main__":
    main()
