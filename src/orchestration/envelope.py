"""Canonical resolvers for department package envelopes.

P0-1 / P0-2 — Single source of truth for Envelope vs Raw access.

After the F2 admission gate, ``department_packages`` stores envelopes::

    {
        "admission": {"decision": ..., "reason": ..., "downstream_visible": bool},
        "raw_package": { ... original DepartmentPackage ... },
        "admitted_payload": { ... section payload or None ... },
    }

All consumers MUST use these resolvers instead of ad-hoc ``.get()`` chains.
"""
from __future__ import annotations

from typing import Any, cast


def is_envelope(pkg: dict[str, Any]) -> bool:
    """Return True if ``pkg`` is an admission envelope (vs a raw package).

    RF2-1 compat: also recognises legacy envelopes that used ``raw_synthesis``
    instead of ``raw_package`` (written before the canonical-shape fix).
    """
    if "admission" not in pkg:
        return False
    return "raw_package" in pkg or "raw_synthesis" in pkg


def resolve_raw_package(pkg: dict[str, Any]) -> dict[str, Any]:
    """Extract the raw department package from an envelope or pass-through.

    RF2-1 compat: falls back to ``raw_synthesis`` for legacy envelopes.
    """
    if is_envelope(pkg):
        return pkg.get("raw_package") or pkg.get("raw_synthesis") or {}
    return pkg


def resolve_admitted_payload(pkg: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the admitted section payload (None if rejected)."""
    if is_envelope(pkg):
        return pkg.get("admitted_payload")
    return pkg.get("section_payload")


def resolve_admission(pkg: dict[str, Any]) -> dict[str, Any]:
    """Extract the admission metadata dict."""
    if is_envelope(pkg):
        return cast(dict[str, Any], pkg.get("admission", {}))
    return {"decision": "unknown", "reason": "not an envelope", "downstream_visible": True}


def resolve_report_segment(pkg: dict[str, Any]) -> dict[str, Any]:
    """Extract report_segment from an envelope or raw package."""
    raw = resolve_raw_package(pkg)
    return cast(dict[str, Any], raw.get("report_segment", {}))


def resolve_visual_focus(pkg: dict[str, Any]) -> list[str]:
    """Extract visual_focus from an envelope or raw package."""
    raw = resolve_raw_package(pkg)
    return cast(list[str], raw.get("visual_focus", []))


def resolve_confidence(pkg: dict[str, Any]) -> str:
    """Extract confidence from an envelope or raw package."""
    raw = resolve_raw_package(pkg)
    return cast(str, raw.get("confidence", "low"))


def resolve_open_questions(pkg: dict[str, Any]) -> list[str]:
    """Extract open_questions from an envelope or raw package."""
    raw = resolve_raw_package(pkg)
    return cast(list[str], raw.get("open_questions", []))
