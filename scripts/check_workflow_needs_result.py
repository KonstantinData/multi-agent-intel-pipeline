"""Validate the aggregate GitHub Actions needs result payload."""

from __future__ import annotations

import json
import os

def evaluate_needs(needs: dict) -> dict[str, str]:
    """Return a mapping of gate name → result for every gate that did not pass.

    A gate passes when its result is either "success" or "skipped".

    Skipped jobs are expected in this workflow when an upstream dependency
    fails or when event-specific conditional jobs do not run.

    Any other result (for example: failure or cancelled) is treated as a
    pipeline failure.
    """
    return {
        name: meta["result"]
        for name, meta in sorted(needs.items())
        if meta["result"] not in {"success", "skipped"}
    }


def main() -> None:
    needs = json.loads(os.environ["NEEDS_JSON"])
    failures = evaluate_needs(needs)
    if failures:
        print("Failed gates:")
        for name, result in failures.items():
            print(f"- {name}: {result}")
        raise SystemExit(1)
    print("All required compliance-security-ai gates passed.")


if __name__ == "__main__":
    main()
