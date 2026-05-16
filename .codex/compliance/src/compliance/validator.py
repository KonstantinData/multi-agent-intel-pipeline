"""Validation and voting helpers for compliance optimization proposals."""
from __future__ import annotations

from compliance.contracts import (
    CompliancePattern,
    ComplianceRuleProposal,
    ProposalValidationResult,
    VotingDecision,
)


def validate_rule_proposal(
    *,
    proposal: ComplianceRuleProposal,
    pattern: CompliancePattern,
) -> ProposalValidationResult:
    notes: list[str] = []
    metrics = pattern.to_dict()

    if pattern.repeat_fail_count <= 3:
        notes.append("Rule did not exceed the required repetition threshold (>3).")
        return ProposalValidationResult(
            proposal_id=proposal.proposal_id,
            verdict="rejected",
            confidence="high",
            notes=notes,
            metrics=metrics,
        )

    if pattern.false_positive_rate > 0.2:
        notes.append("False positive rate is too high for an automatic recommendation.")
        return ProposalValidationResult(
            proposal_id=proposal.proposal_id,
            verdict="rejected",
            confidence="high",
            notes=notes,
            metrics=metrics,
        )

    if pattern.total_checks < 6 or pattern.failure_rate < 0.35:
        notes.append(
            "Evidence is mixed (small sample size or lower failure rate); "
            "forward to voting team."
        )
        return ProposalValidationResult(
            proposal_id=proposal.proposal_id,
            verdict="needs_voting",
            confidence="medium",
            notes=notes,
            metrics=metrics,
        )

    notes.append("Proposal has enough evidence and low false positives.")
    return ProposalValidationResult(
        proposal_id=proposal.proposal_id,
        verdict="accepted",
        confidence="high",
        notes=notes,
        metrics=metrics,
    )


def resolve_voting_decision(
    *,
    proposal_id: str,
    votes_for: int,
    votes_against: int,
    abstentions: int = 0,
    rationale: str = "",
) -> VotingDecision:
    if votes_for > votes_against:
        outcome = "accepted"
    elif votes_against > votes_for:
        outcome = "rejected"
    else:
        outcome = "revised"

    return VotingDecision(
        proposal_id=proposal_id,
        outcome=outcome,
        votes_for=max(votes_for, 0),
        votes_against=max(votes_against, 0),
        abstentions=max(abstentions, 0),
        rationale=rationale,
    )
