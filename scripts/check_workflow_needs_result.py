"""Validate the aggregate GitHub Actions needs result payload."""

from __future__ import annotations

import json
import os

# Jobs that are allowed to be skipped due to conditional triggers:
#   integration-tests  – only runs on workflow_dispatch
#   provenance-gate    – only runs on non-pull_request events
ALLOWED_SKIPS = {"integration-tests", "provenance-gate"}


def evaluate_needs(needs: dict) -> dict[str, str]:
    """Return a mapping of gate name → result for every gate that did not pass.

    A gate passes when its result is "success", or when it is in ALLOWED_SKIPS
    and its result is "skipped".  Any other result (failure, cancelled, or an
    unexpected skip of a non-allowed job) is treated as a failure.
    """
    return {
        name: meta["result"]
        for name, meta in sorted(needs.items())
        if meta["result"] != "success"
        and not (name in ALLOWED_SKIPS and meta["result"] == "skipped")
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
