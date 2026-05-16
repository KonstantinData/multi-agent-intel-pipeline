"""Context-aware file compliance evaluation."""
from __future__ import annotations

import ast
import re
import shlex
import subprocess  # nosec B404
from pathlib import Path
from uuid import uuid4

from compliance.contracts import ComplianceArtifact, ComplianceViolation
from compliance.policies import CompliancePolicy, ComplianceRule, select_rules


def _line_from_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, max(offset, 0)) + 1


def _run_rule(
    *,
    file_path: Path,
    file_text: str,
    rule: ComplianceRule,
) -> list[ComplianceViolation]:
    violations: list[ComplianceViolation] = []
    check_type = rule.check_type

    if check_type == "regex_forbidden":
        pattern = re.compile(str(rule.check_payload.get("pattern", "")), re.MULTILINE)
        match = pattern.search(file_text)
        if match:
            violations.append(
                ComplianceViolation(
                    rule_id=rule.rule_id,
                    category=rule.category,
                    severity=rule.severity,
                    message=f"Forbidden pattern matched for rule {rule.rule_id}.",
                    line=_line_from_offset(file_text, match.start()),
                    blocking=rule.blocking,
                    fix_hint=rule.fix_hint,
                )
            )
        return violations

    if check_type == "regex_required":
        pattern = re.compile(str(rule.check_payload.get("pattern", "")), re.MULTILINE)
        if not pattern.search(file_text):
            violations.append(
                ComplianceViolation(
                    rule_id=rule.rule_id,
                    category=rule.category,
                    severity=rule.severity,
                    message=f"Required pattern missing for rule {rule.rule_id}.",
                    line=1,
                    blocking=rule.blocking,
                    fix_hint=rule.fix_hint,
                )
            )
        return violations

    if check_type == "python_module_docstring":
        if file_path.suffix.lower() != ".py":
            return violations
        try:
            parsed = ast.parse(file_text)
        except SyntaxError as exc:
            violations.append(
                ComplianceViolation(
                    rule_id=rule.rule_id,
                    category=rule.category,
                    severity=rule.severity,
                    message=f"Python parsing failed: {exc.msg}",
                    line=exc.lineno or 1,
                    blocking=rule.blocking,
                    fix_hint=rule.fix_hint,
                )
            )
            return violations
        if ast.get_docstring(parsed) is None:
            violations.append(
                ComplianceViolation(
                    rule_id=rule.rule_id,
                    category=rule.category,
                    severity=rule.severity,
                    message="Module docstring is required but missing.",
                    line=1,
                    blocking=rule.blocking,
                    fix_hint=rule.fix_hint,
                )
            )
        return violations

    if check_type == "command":
        raw_command = str(rule.check_payload.get("cmd", "")).strip()
        if not raw_command:
            return violations
        command = raw_command.replace("{file}", str(file_path))
        try:
            completed = subprocess.run(
                shlex.split(command),
                capture_output=True,
                text=True,
                check=False,
            )  # nosec B603
        except FileNotFoundError:
            violations.append(
                ComplianceViolation(
                    rule_id=rule.rule_id,
                    category=rule.category,
                    severity=rule.severity,
                    message=f"Required tool not found for command check: {command}",
                    line=None,
                    blocking=rule.blocking,
                    fix_hint=rule.fix_hint or "Install the required command-line tool.",
                )
            )
            return violations

        if completed.returncode != 0:
            details = (completed.stdout + "\n" + completed.stderr).strip()
            violations.append(
                ComplianceViolation(
                    rule_id=rule.rule_id,
                    category=rule.category,
                    severity=rule.severity,
                    message=(
                        f"Command check failed for rule {rule.rule_id}: "
                        f"{details[:500]}"
                    ),
                    line=None,
                    blocking=rule.blocking,
                    fix_hint=rule.fix_hint,
                )
            )
        return violations

    violations.append(
        ComplianceViolation(
            rule_id=rule.rule_id,
            category=rule.category,
            severity=rule.severity,
            message=f"Unsupported check type '{check_type}'.",
            line=None,
            blocking=rule.blocking,
            fix_hint="Update the compliance checker to support this check type.",
        )
    )
    return violations


def evaluate_file_compliance(
    *,
    file_path: str | Path,
    policy: CompliancePolicy,
    purpose: str,
    risk_level: str,
    run_id: str = "",
    attempt_count: int = 1,
) -> ComplianceArtifact:
    target = Path(file_path)
    file_text = target.read_text(encoding="utf-8")
    file_type = target.suffix.lower()

    rules = select_rules(
        policy,
        file_type=file_type,
        purpose=purpose,
        risk_level=risk_level,
    )
    violations: list[ComplianceViolation] = []
    for rule in rules:
        violations.extend(_run_rule(file_path=target, file_text=file_text, rule=rule))

    blocking_failure = any(item.blocking for item in violations)
    status = "fail" if violations else "pass"
    validator_output = "All active rules passed." if not violations else (
        f"{len(violations)} rule violation(s) detected."
    )
    return ComplianceArtifact(
        artifact_id=f"cmp-{uuid4().hex[:12]}",
        run_id=run_id,
        file_path=str(target),
        file_type=file_type,
        purpose=purpose,
        risk_level=risk_level,
        policy_version=policy.version,
        status=status,
        blocking_failure=blocking_failure,
        evaluated_rule_ids=[rule.rule_id for rule in rules],
        violations=violations,
        attempt_count=max(attempt_count, 1),
        validator_output=validator_output,
        metadata={
            "evaluated_rule_categories": {
                rule.rule_id: rule.category
                for rule in rules
            }
        },
    )
