"""Learning loop utilities for compliance artifacts."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from compliance.contracts import (
    ComplianceArtifact,
    CompliancePattern,
    ComplianceRuleProposal,
)


def _proposal_target(category: str) -> tuple[str, str]:
    normalized = category.strip().lower()
    if normalized in {"security", "privacy", "governance", "legal"}:
        return ("instruction", f"instructions/{normalized}.md")
    if normalized in {"format", "quality"}:
        return ("template", f"templates/{normalized}.md")
    return ("policy", ".codex/compliance/policies/file_compliance_policy.json")


def build_compliance_patterns(
    artifacts: list[ComplianceArtifact],
) -> list[CompliancePattern]:
    grouped: dict[str, dict[str, Any]] = {}

    for artifact in artifacts:
        violations_by_rule: dict[str, str] = {}
        category_map = {
            str(rule_id): str(category)
            for rule_id, category in dict(
                artifact.metadata.get("evaluated_rule_categories", {})
            ).items()
            if str(rule_id).strip() and str(category).strip()
        }
        for violation in artifact.violations:
            key = (
                f"{violation.rule_id}|{artifact.file_type}|"
                f"{artifact.purpose}|{artifact.risk_level}"
            )
            violations_by_rule[key] = violation.category

        for rule_id in artifact.evaluated_rule_ids:
            key = f"{rule_id}|{artifact.file_type}|{artifact.purpose}|{artifact.risk_level}"
            bucket = grouped.setdefault(
                key,
                {
                    "rule_id": rule_id,
                    "category": violations_by_rule.get(
                        key,
                        category_map.get(rule_id, "quality"),
                    ),
                    "file_type": artifact.file_type,
                    "purpose": artifact.purpose,
                    "risk_level": artifact.risk_level,
                    "total_checks": 0,
                    "fail_count": 0,
                    "attempts_sum": 0.0,
                    "fix_success_count": 0,
                    "false_positive_count": 0,
                    "time_to_fix_sum": 0.0,
                    "time_to_fix_count": 0,
                },
            )
            bucket["total_checks"] += 1
            if key in violations_by_rule:
                bucket["fail_count"] += 1
                bucket["attempts_sum"] += float(max(artifact.attempt_count, 1))
                if artifact.fix_success is True:
                    bucket["fix_success_count"] += 1
                if bool(artifact.metadata.get("false_positive", False)):
                    bucket["false_positive_count"] += 1
                if artifact.time_to_fix_sec is not None:
                    bucket["time_to_fix_sum"] += float(artifact.time_to_fix_sec)
                    bucket["time_to_fix_count"] += 1

    patterns: list[CompliancePattern] = []
    for bucket in grouped.values():
        fail_count = int(bucket["fail_count"])
        total_checks = int(bucket["total_checks"])
        failure_rate = round(fail_count / total_checks, 4) if total_checks else 0.0
        avg_attempts = round(bucket["attempts_sum"] / fail_count, 4) if fail_count else 0.0
        fix_success_rate = (
            round(bucket["fix_success_count"] / fail_count, 4)
            if fail_count else 0.0
        )
        false_positive_rate = (
            round(bucket["false_positive_count"] / fail_count, 4)
            if fail_count else 0.0
        )
        mean_time_to_fix = (
            round(bucket["time_to_fix_sum"] / bucket["time_to_fix_count"], 4)
            if bucket["time_to_fix_count"] else 0.0
        )
        patterns.append(
            CompliancePattern(
                rule_id=str(bucket["rule_id"]),
                category=str(bucket["category"]),
                file_type=str(bucket["file_type"]),
                purpose=str(bucket["purpose"]),
                risk_level=str(bucket["risk_level"]),
                total_checks=total_checks,
                fail_count=fail_count,
                failure_rate=failure_rate,
                repeat_fail_count=fail_count,
                avg_attempts_to_fix=avg_attempts,
                fix_success_rate=fix_success_rate,
                false_positive_rate=false_positive_rate,
                mean_time_to_fix_sec=mean_time_to_fix,
            )
        )
    patterns.sort(key=lambda item: (-item.fail_count, item.rule_id, item.file_type))
    return patterns


def generate_rule_proposals(
    patterns: list[CompliancePattern],
    *,
    min_repeat_failures: int = 4,
) -> list[ComplianceRuleProposal]:
    threshold = max(min_repeat_failures, 4)
    created_at = datetime.now(UTC).isoformat()
    proposals: list[ComplianceRuleProposal] = []

    for pattern in patterns:
        if pattern.repeat_fail_count < threshold:
            continue
        target_kind, target_identifier = _proposal_target(pattern.category)
        digest = hashlib.sha256(
            f"{pattern.key}|{created_at}".encode()
        ).hexdigest()[:12]
        proposals.append(
            ComplianceRuleProposal(
                proposal_id=f"prop-{digest}",
                created_at=created_at,
                source_pattern_key=pattern.key,
                target_kind=target_kind,  # type: ignore[arg-type]
                target_identifier=target_identifier,
                reason=(
                    f"Rule {pattern.rule_id} repeated more than three times "
                    f"({pattern.repeat_fail_count} failures)."
                ),
                evidence_summary=(
                    f"Failure rate={pattern.failure_rate}, "
                    f"average attempts to fix={pattern.avg_attempts_to_fix}, "
                    f"false positive rate={pattern.false_positive_rate}."
                ),
                suggested_change=(
                    f"Add clearer guidance and examples for rule {pattern.rule_id} "
                    f"in {target_identifier}."
                ),
                expected_effect=(
                    "Lower repeat failures and lower average attempts to fix "
                    "for this rule."
                ),
                min_repetitions_required=threshold,
                status="proposed",
            )
        )
    return proposals
