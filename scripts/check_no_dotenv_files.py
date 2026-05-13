"""Fail when `.env*` files are tracked in git."""

from __future__ import annotations

import subprocess  # nosec B404 - required for fixed local `git ls-files` call
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _tracked_files() -> list[str]:
    result = subprocess.run(  # nosec B603,B607 - fixed argv, no shell, repo-local command
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _is_forbidden_env_filename(path: str) -> bool:
    name = Path(path).name.lower()
    return name == ".env" or name == ".envrc" or name.startswith(".env.")


def find_forbidden_dotenv_files() -> list[str]:
    violations = [
        path
        for path in _tracked_files()
        if _is_forbidden_env_filename(path)
    ]
    return sorted(violations)


def main() -> None:
    violations = find_forbidden_dotenv_files()
    if violations:
        listing = "\n".join(f"- {item}" for item in violations)
        raise SystemExit(
            "Tracked .env-style files are forbidden. Remove them from git:\n"
            f"{listing}",
        )
    print("No tracked .env-style files detected.")


if __name__ == "__main__":
    main()
