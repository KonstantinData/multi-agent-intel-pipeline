"""Dependency-light contract validation helpers."""
from __future__ import annotations

from typing import Any

from src.models.registry import resolve_output_schema
from src.orchestration.contracts import ContractViolation


def validate_payload_against_task_schema(
    schema_key: str,
    payload_updates: dict[str, Any],
) -> list[ContractViolation]:
    """Validate payload updates against the task-level output schema."""
    if not schema_key:
        return []
    try:
        schema_cls = resolve_output_schema(schema_key)
    except KeyError:
        return []
    try:
        schema_cls.model_validate(payload_updates)
        return []
    except Exception as exc:
        violations: list[ContractViolation] = []
        errors = getattr(exc, "errors", lambda: [])() if hasattr(exc, "errors") else []
        if errors:
            for err in errors:
                field_path = ".".join(str(p) for p in err.get("loc", ["unknown"]))
                err_type = str(err.get("type", "unknown"))
                violation_type = "type_mismatch" if "type" in err_type else "missing_required_field"
                violations.append(ContractViolation(
                    field_path=field_path,
                    violation_type=violation_type,
                    severity="medium",
                    message=str(err.get("msg", str(exc)))[:200],
                ))
        else:
            violations.append(ContractViolation(
                field_path="*",
                violation_type="type_mismatch",
                severity="high",
                message=str(exc)[:200],
            ))
        schema_fields = set(schema_cls.model_fields.keys()) - {"sources"}
        filled = {k for k, v in payload_updates.items() if k in schema_fields and v and v != "n/v"}
        if not filled:
            for violation in violations:
                violation.severity = "high"
        return violations

