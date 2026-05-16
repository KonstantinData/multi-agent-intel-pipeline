"""Policy loader and selector for file compliance checks."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RuleScope:
    filetypes: tuple[str, ...]
    purposes: tuple[str, ...]
    risk_levels: tuple[str, ...]

    def matches(self, *, file_type: str, purpose: str, risk_level: str) -> bool:
        return (
            file_type in self.filetypes
            and purpose in self.purposes
            and risk_level in self.risk_levels
        )


@dataclass(frozen=True, slots=True)
class ComplianceRule:
    rule_id: str
    category: str
    severity: str
    blocking: bool
    fix_hint: str
    check_type: str
    check_payload: dict[str, Any]
    applies_to: RuleScope


@dataclass(frozen=True, slots=True)
class CompliancePolicy:
    version: str
    min_repeat_failures_for_optimizer: int = 4
    rules: tuple[ComplianceRule, ...] = field(default_factory=tuple)


def _tuple_values(payload: dict[str, Any], key: str) -> tuple[str, ...]:
    values = payload.get(key, [])
    return tuple(str(item) for item in values if str(item).strip())


def load_compliance_policy(path: str | Path) -> CompliancePolicy:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Compliance policy must be a JSON object.")

    version = str(raw.get("version", "1"))
    optimizer = dict(raw.get("optimizer", {}))
    min_repeat_failures = int(optimizer.get("min_repeat_failures_for_optimizer", 4))
    if min_repeat_failures < 4:
        min_repeat_failures = 4

    rules: list[ComplianceRule] = []
    for item in raw.get("rules", []):
        if not isinstance(item, dict):
            continue
        applies_to = dict(item.get("applies_to", {}))
        scope = RuleScope(
            filetypes=_tuple_values(applies_to, "filetypes"),
            purposes=_tuple_values(applies_to, "purposes"),
            risk_levels=_tuple_values(applies_to, "risk_levels"),
        )
        check = dict(item.get("check", {}))
        rule = ComplianceRule(
            rule_id=str(item.get("id", "")).strip(),
            category=str(item.get("category", "quality")).strip(),
            severity=str(item.get("severity", "medium")).strip(),
            blocking=bool(item.get("blocking", True)),
            fix_hint=str(item.get("fix_hint", "")).strip(),
            check_type=str(check.get("type", "")).strip(),
            check_payload={k: v for k, v in check.items() if k != "type"},
            applies_to=scope,
        )
        if (
            rule.rule_id
            and rule.check_type
            and rule.applies_to.filetypes
            and rule.applies_to.purposes
            and rule.applies_to.risk_levels
        ):
            rules.append(rule)
    return CompliancePolicy(
        version=version,
        min_repeat_failures_for_optimizer=min_repeat_failures,
        rules=tuple(rules),
    )


def select_rules(
    policy: CompliancePolicy,
    *,
    file_type: str,
    purpose: str,
    risk_level: str,
) -> list[ComplianceRule]:
    return [
        rule
        for rule in policy.rules
        if rule.applies_to.matches(
            file_type=file_type,
            purpose=purpose,
            risk_level=risk_level,
        )
    ]
