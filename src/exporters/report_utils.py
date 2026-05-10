"""Dependency-light report export helpers."""
from __future__ import annotations

from typing import Any


def select_composed_report(report_package: Any, lang: str) -> dict[str, Any]:
    if not isinstance(report_package, dict):
        return {}
    composed = report_package.get("composed_report")
    if not isinstance(composed, dict):
        return {}
    validation = report_package.get("composition_validation")
    validation_by_lang = validation if isinstance(validation, dict) else {}
    preferred = composed.get(lang)
    if isinstance(preferred, dict) and preferred:
        return preferred
    for candidate in ("en", "de"):
        draft = composed.get(candidate)
        if not isinstance(draft, dict) or not draft:
            continue
        checks = validation_by_lang.get(candidate)
        if isinstance(checks, dict) and checks.get("passed") is False:
            continue
        return draft
    return {}

