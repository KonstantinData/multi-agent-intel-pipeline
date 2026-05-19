"""Validate repository ruleset desired-state policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

REQUIRED_STATUS_CHECKS = {
    "pipeline-status",
    "analyze",
    "dependency-review",
    "policy-as-code-gate",
    "scorecard-policy-gate",
}
REQUIRED_RULE_TYPES = {
    "deletion",
    "non_fast_forward",
    "pull_request",
    "required_signatures",
    "required_status_checks",
}


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(message)


def _rules_by_type(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rules_obj = data.get("rules")
    _require(isinstance(rules_obj, list), "Ruleset rules must be a list.")
    rules = cast(list[Any], rules_obj)
    by_type: dict[str, dict[str, Any]] = {}
    for rule in rules:
        _require(isinstance(rule, dict), "Each ruleset rule must be an object.")
        rule_type = str(rule.get("type", ""))
        _require(bool(rule_type), "Ruleset rule missing type.")
        by_type[rule_type] = rule
    return by_type


def validate_ruleset(path: Path) -> None:
    _require(path.is_file(), f"Ruleset file missing: {path.as_posix()}")
    data = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(data, dict), "Ruleset must be a JSON object.")
    _require(data.get("name") == "main-protection", "Ruleset name must be main-protection.")
    _require(data.get("target") == "branch", "Ruleset target must be branch.")
    _require(data.get("enforcement") == "active", "Ruleset enforcement must be active.")
    _require(data.get("bypass_actors") == [], "Ruleset must not define bypass actors.")

    conditions = data.get("conditions")
    _require(isinstance(conditions, dict), "Ruleset conditions must be an object.")
    ref_name = conditions.get("ref_name")
    _require(isinstance(ref_name, dict), "Ruleset conditions.ref_name must be an object.")
    _require("~DEFAULT_BRANCH" in ref_name.get("include", []), "Ruleset must target the default branch.")

    rules = _rules_by_type(data)
    missing_rules = REQUIRED_RULE_TYPES - set(rules)
    _require(not missing_rules, f"Ruleset missing rules: {sorted(missing_rules)}")

    pr_params_obj = rules["pull_request"].get("parameters")
    _require(isinstance(pr_params_obj, dict), "Pull request rule missing parameters.")
    pr_params = cast(dict[str, Any], pr_params_obj)
    _require(pr_params.get("required_approving_review_count", 0) >= 2, "Ruleset must require at least two approvals.")
    _require(pr_params.get("require_code_owner_review") is True, "Ruleset must require Code Owner review.")
    _require(pr_params.get("dismiss_stale_reviews_on_push") is True, "Ruleset must dismiss stale reviews.")
    _require(pr_params.get("require_last_push_approval") is True, "Ruleset must require last push approval.")

    checks_params_obj = rules["required_status_checks"].get("parameters")
    _require(isinstance(checks_params_obj, dict), "Required status checks rule missing parameters.")
    checks_params = cast(dict[str, Any], checks_params_obj)
    _require(
        checks_params.get("strict_required_status_checks_policy") is True,
        "Ruleset must require branches to be up to date.",
    )
    checks_obj = checks_params.get("required_status_checks")
    _require(isinstance(checks_obj, list), "required_status_checks must be a list.")
    checks = cast(list[Any], checks_obj)
    contexts = {str(item.get("context", "")) for item in checks if isinstance(item, dict)}
    missing_checks = REQUIRED_STATUS_CHECKS - contexts
    _require(not missing_checks, f"Ruleset missing status checks: {sorted(missing_checks)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        default=".github/rulesets/main-protection.json",
        help="Path to the GitHub ruleset desired-state JSON file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_ruleset(Path(args.path))
    print(f"Ruleset validation passed: {args.path}")


if __name__ == "__main__":
    main()
