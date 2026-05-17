"""Repair local git hook wiring and install pre-commit hooks for this repo.

This script intentionally targets local repository config only.
It does not modify global git configuration.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess  # nosec B404 - fixed local tooling invocations only
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    # Fixed argv with shell=False and repo-local cwd is deterministic.
    return subprocess.run(  # nosec B603
        cmd,
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


def _get_local_hooks_path() -> str | None:
    result = _run(["git", "config", "--local", "--get", "core.hooksPath"], check=False)
    value = (result.stdout or "").strip()
    return value or None


def _unset_local_hooks_path() -> bool:
    result = _run(["git", "config", "--local", "--unset", "core.hooksPath"], check=False)
    return result.returncode == 0


def _ensure_pre_commit_available() -> None:
    pre_commit_exe = shutil.which("pre-commit")
    if pre_commit_exe:
        return
    result = _run([sys.executable, "-m", "pre_commit", "--version"], check=False)
    if result.returncode == 0:
        return
    raise SystemExit(
        "pre-commit is not available. Install it first, e.g.:\n"
        "  python -m pip install pre-commit"
    )


def _install_pre_commit() -> None:
    pre_commit_exe = shutil.which("pre-commit")
    if pre_commit_exe:
        for hook_type in ("pre-commit", "pre-push"):
            _run(
                [
                    "pre-commit",
                    "install",
                    "--hook-type",
                    hook_type,
                    "--install-hooks",
                ]
            )
        return
    for hook_type in ("pre-commit", "pre-push"):
        _run(
            [
                sys.executable,
                "-m",
                "pre_commit",
                "install",
                "--hook-type",
                hook_type,
                "--install-hooks",
            ]
        )


def _verify_hook_files() -> list[Path]:
    hook_paths = [ROOT / ".git" / "hooks" / name for name in ("pre-commit", "pre-push")]
    missing = [path.as_posix() for path in hook_paths if not path.is_file()]
    if missing:
        raise SystemExit(f"Git hook(s) not found at expected path(s): {missing}")
    return hook_paths


def _run_compliance_hook() -> None:
    pre_commit_exe = shutil.which("pre-commit")
    if pre_commit_exe:
        _run(["pre-commit", "run", "compliance-policy-check", "--all-files"])
        return
    _run(
        [
            sys.executable,
            "-m",
            "pre_commit",
            "run",
            "compliance-policy-check",
            "--all-files",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Repair local git hook wiring for this repository and install pre-commit."
        )
    )
    parser.add_argument(
        "--run-check",
        action="store_true",
        help="Run compliance-policy-check once after installation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    hooks_path_before = _get_local_hooks_path()
    if hooks_path_before:
        removed = _unset_local_hooks_path()
        if removed:
            print(f"unset local core.hooksPath (was: {hooks_path_before})")
        else:
            print(
                "local core.hooksPath was set but could not be unset automatically; "
                "continue with pre-commit install."
            )
    else:
        print("local core.hooksPath is not set (using default .git/hooks).")

    _ensure_pre_commit_available()
    _install_pre_commit()
    hook_paths = _verify_hook_files()

    hooks_path_after = _get_local_hooks_path()
    for hook_path in hook_paths:
        print(f"git hook installed: {hook_path.as_posix()}")
    print(f"local core.hooksPath after setup: {hooks_path_after or '<default .git/hooks>'}")

    if args.run_check:
        _run_compliance_hook()
        print("compliance-policy-check completed.")

    print("local git hook setup complete.")


if __name__ == "__main__":
    main()
