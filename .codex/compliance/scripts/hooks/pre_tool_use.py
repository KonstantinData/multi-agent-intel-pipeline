"""Pre-tool hook: block writes when compliance checks fail."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
COMPLIANCE_SRC = Path(__file__).resolve().parents[2] / "src"
if str(COMPLIANCE_SRC) not in sys.path:
    sys.path.insert(0, str(COMPLIANCE_SRC))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    from compliance import evaluate_file_compliance, load_compliance_policy

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="File to validate before next tool step.")
    parser.add_argument("--purpose", default="runtime_code")
    parser.add_argument("--risk-level", default="medium")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--attempt-count", type=int, default=1)
    parser.add_argument(
        "--policy-path",
        default=".codex/compliance/policies/file_compliance_policy.json",
    )
    parser.add_argument(
        "--artifact-path",
        default="artifacts/compliance/latest_pre_tool_artifact.json",
    )
    args = parser.parse_args()

    policy = load_compliance_policy(args.policy_path)
    artifact = evaluate_file_compliance(
        file_path=args.file,
        policy=policy,
        purpose=args.purpose,
        risk_level=args.risk_level,
        run_id=args.run_id,
        attempt_count=args.attempt_count,
    )

    out_path = Path(args.artifact_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return 1 if artifact.blocking_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
