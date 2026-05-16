"""Helpers to persist compliance loop outputs into the run brain."""
from __future__ import annotations

from typing import Any

from compliance.contracts import (
    ComplianceArtifact,
    CompliancePattern,
    ComplianceRuleProposal,
    ProposalValidationResult,
    VotingDecision,
)


def record_compliance_cycle(
    *,
    store: Any | None,
    artifacts: list[ComplianceArtifact],
    patterns: list[CompliancePattern],
    proposals: list[ComplianceRuleProposal],
    validations: list[ProposalValidationResult],
    voting_decisions: list[VotingDecision] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    payload = {
        "compliance_artifacts": [artifact.to_dict() for artifact in artifacts],
        "compliance_learning_patterns": [pattern.to_dict() for pattern in patterns],
        "compliance_rule_proposals": [proposal.to_dict() for proposal in proposals],
        "compliance_validation_results": [result.to_dict() for result in validations],
        "compliance_voting_decisions": [decision.to_dict() for decision in voting_decisions or []],
    }
    if store is None:
        return payload

    if not hasattr(store, "__dict__"):
        return payload
    bucket = store.__dict__.get("_codex_compliance")
    if not isinstance(bucket, dict):
        bucket = {}
        store._codex_compliance = bucket
    for key, values in payload.items():
        bucket.setdefault(key, [])
        bucket[key].extend(values)
    return payload
