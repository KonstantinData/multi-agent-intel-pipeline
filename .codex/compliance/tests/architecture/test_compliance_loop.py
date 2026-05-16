"""Architecture tests for compliance checking and learning loop."""
from __future__ import annotations

# ruff: noqa: E402
import sys
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[4]
COMPLIANCE_SRC = Path(__file__).resolve().parents[2] / "src"
if str(COMPLIANCE_SRC) not in sys.path:
    sys.path.insert(0, str(COMPLIANCE_SRC))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from compliance import (
    ComplianceArtifact,
    CompliancePattern,
    ComplianceRuleProposal,
    ComplianceViolation,
    build_compliance_patterns,
    evaluate_file_compliance,
    generate_rule_proposals,
    load_compliance_policy,
    record_compliance_cycle,
    resolve_voting_decision,
    validate_rule_proposal,
)


def test_evaluate_file_compliance_detects_blocking_secret_rule():
    tmp_dir = Path("artifacts") / "tmp_compliance_tests" / f"compliance-{uuid4().hex[:8]}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    file_path = tmp_dir / "unsafe.py"
    file_path.write_text(
        "\"\"\"Test module.\"\"\"\nfrom __future__ import annotations\napi_key = \"hardcoded\"\n",
        encoding="utf-8",
    )
    policy = load_compliance_policy(".codex/compliance/policies/file_compliance_policy.json")
    artifact = evaluate_file_compliance(
        file_path=file_path,
        policy=policy,
        purpose="runtime_code",
        risk_level="high",
        run_id="run-test",
    )
    rule_ids = {item.rule_id for item in artifact.violations}
    assert artifact.status == "fail"
    assert artifact.blocking_failure is True
    assert "SEC-001" in rule_ids


def test_generate_rule_proposals_starts_only_above_three_repetitions():
    pattern = CompliancePattern(
        rule_id="SEC-001",
        category="security",
        file_type=".py",
        purpose="runtime_code",
        risk_level="high",
        total_checks=10,
        fail_count=3,
        failure_rate=0.3,
        repeat_fail_count=3,
        avg_attempts_to_fix=2.0,
        fix_success_rate=0.8,
        false_positive_rate=0.0,
        mean_time_to_fix_sec=12.0,
    )
    assert generate_rule_proposals([pattern], min_repeat_failures=4) == []
    pattern.repeat_fail_count = 4  # type: ignore[misc]
    proposals = generate_rule_proposals([pattern], min_repeat_failures=4)
    assert len(proposals) == 1
    assert proposals[0].source_pattern_key == pattern.key


def test_build_compliance_patterns_aggregates_frequency_metrics():
    violation = ComplianceViolation(
        rule_id="GOV-001",
        category="governance",
        severity="medium",
        message="title missing",
        line=1,
        blocking=True,
    )
    artifacts = [
        ComplianceArtifact(
            artifact_id="a1",
            run_id="r1",
            file_path="docs/a.md",
            file_type=".md",
            purpose="internal_docs",
            risk_level="medium",
            policy_version="1",
            status="fail",
            blocking_failure=True,
            evaluated_rule_ids=["GOV-001"],
            violations=[violation],
            attempt_count=2,
            fix_success=True,
            time_to_fix_sec=20,
        ),
        ComplianceArtifact(
            artifact_id="a2",
            run_id="r1",
            file_path="docs/b.md",
            file_type=".md",
            purpose="internal_docs",
            risk_level="medium",
            policy_version="1",
            status="pass",
            blocking_failure=False,
            evaluated_rule_ids=["GOV-001"],
            violations=[],
        ),
    ]
    patterns = build_compliance_patterns(artifacts)
    assert len(patterns) == 1
    assert patterns[0].rule_id == "GOV-001"
    assert patterns[0].total_checks == 2
    assert patterns[0].fail_count == 1
    assert patterns[0].failure_rate == 0.5


def test_validator_and_voting_flow():
    pattern = CompliancePattern(
        rule_id="PRIV-001",
        category="privacy",
        file_type=".py",
        purpose="runtime_code",
        risk_level="high",
        total_checks=12,
        fail_count=6,
        failure_rate=0.5,
        repeat_fail_count=6,
        avg_attempts_to_fix=2.2,
        fix_success_rate=0.9,
        false_positive_rate=0.05,
        mean_time_to_fix_sec=15.0,
    )
    proposal = ComplianceRuleProposal(
        proposal_id="p1",
        created_at="2026-05-16T00:00:00+00:00",
        source_pattern_key=pattern.key,
        target_kind="instruction",
        target_identifier="instructions/privacy.md",
        reason="repeat failures",
        evidence_summary="high failure rate",
        suggested_change="improve instruction",
        expected_effect="lower failures",
    )
    validation = validate_rule_proposal(proposal=proposal, pattern=pattern)
    assert validation.verdict == "accepted"

    tie = resolve_voting_decision(
        proposal_id=proposal.proposal_id,
        votes_for=2,
        votes_against=2,
        rationale="split decision",
    )
    assert tie.outcome == "revised"


def test_record_compliance_cycle_persists_in_codex_bucket():
    class Sink:
        pass

    store = Sink()
    artifact = ComplianceArtifact(
        artifact_id="a1",
        run_id="r1",
        file_path="src/sample.py",
        file_type=".py",
        purpose="runtime_code",
        risk_level="high",
        policy_version="1",
        status="fail",
        blocking_failure=True,
        evaluated_rule_ids=["SEC-001"],
        violations=[
            ComplianceViolation(
                rule_id="SEC-001",
                category="security",
                severity="critical",
                message="secret",
                blocking=True,
            )
        ],
    )
    pattern = CompliancePattern(
        rule_id="SEC-001",
        category="security",
        file_type=".py",
        purpose="runtime_code",
        risk_level="high",
        total_checks=8,
        fail_count=4,
        failure_rate=0.5,
        repeat_fail_count=4,
        avg_attempts_to_fix=2.0,
        fix_success_rate=0.8,
        false_positive_rate=0.0,
        mean_time_to_fix_sec=18.0,
    )
    proposal = ComplianceRuleProposal(
        proposal_id="p1",
        created_at="2026-05-16T00:00:00+00:00",
        source_pattern_key=pattern.key,
        target_kind="instruction",
        target_identifier="instructions/security.md",
        reason="repeated failures",
        evidence_summary="4 failures",
        suggested_change="strengthen security instruction",
        expected_effect="fewer repeats",
    )

    record_compliance_cycle(
        store=store,
        artifacts=[artifact],
        patterns=[pattern],
        proposals=[proposal],
        validations=[validate_rule_proposal(proposal=proposal, pattern=pattern)],
    )
    assert hasattr(store, "_codex_compliance")
    bucket = store._codex_compliance
    assert len(bucket["compliance_artifacts"]) == 1
    assert len(bucket["compliance_learning_patterns"]) == 1
