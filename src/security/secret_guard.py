"""Runtime guardrails that block accidental secret leakage into model prompts."""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

_SECRET_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE)),
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("bearer_token_header", re.compile(r"authorization\s*:\s*bearer\s+[A-Za-z0-9._\-]{16,}", re.IGNORECASE)),
    (
        "credential_assignment",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*[\"']?[A-Za-z0-9._\-/+=]{16,}",
        ),
    ),
)

_MAX_RULE_IDS = 6
_MAX_PATHS = 6


@dataclass(frozen=True, slots=True)
class _LeakFinding:
    rule_id: str
    path: str


class PromptSecretLeakError(ValueError):
    """Raised when prompt payload appears to include a credential or token."""

    def __init__(self, *, context: str, findings: Iterable[_LeakFinding]):
        unique_rules: list[str] = []
        paths: list[str] = []
        for finding in findings:
            if finding.rule_id not in unique_rules and len(unique_rules) < _MAX_RULE_IDS:
                unique_rules.append(finding.rule_id)
            if finding.path not in paths and len(paths) < _MAX_PATHS:
                paths.append(finding.path)
        details = ", ".join(unique_rules) if unique_rules else "unknown_rule"
        location_text = ", ".join(paths) if paths else "<unknown>"
        super().__init__(
            f"prompt secret guard blocked request in {context}; "
            f"matched rules: {details}; locations: {location_text}",
        )
        self.context = context
        self.rule_ids = tuple(unique_rules)
        self.paths = tuple(paths)


def _scan_text(text: str) -> list[str]:
    hits: list[str] = []
    for rule_id, pattern in _SECRET_RULES:
        if pattern.search(text):
            hits.append(rule_id)
    return hits


def assert_no_secrets_in_text(text: str, *, context: str) -> None:
    findings = [_LeakFinding(rule_id=rule_id, path="$") for rule_id in _scan_text(str(text or ""))]
    if findings:
        raise PromptSecretLeakError(context=context, findings=findings)


def assert_no_secrets_in_payload(payload: Any, *, context: str) -> None:
    findings: list[_LeakFinding] = []

    def _walk(value: Any, path: str) -> None:
        if isinstance(value, str):
            for rule_id in _scan_text(value):
                findings.append(_LeakFinding(rule_id=rule_id, path=path))
            return
        if isinstance(value, dict):
            for key, item in value.items():
                key_text = str(key)
                key_path = f"{path}.{key_text}" if path else key_text
                _walk(item, key_path)
            return
        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                _walk(item, f"{path}[{index}]")
            return

    _walk(payload, "$")
    if findings:
        raise PromptSecretLeakError(context=context, findings=findings)
