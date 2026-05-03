"""Phase 8 — Permanent consistency tests for query strategy files.

These tests run on every pytest invocation and enforce the structural
contract of ``knowledge/query_strategies/*.yaml``.  They are permanent —
they do not depend on the migration being complete.

Invariants enforced
-------------------
- Every task key in the TASK_TO_DEPARTMENT mapping has a strategy entry.
- Every strategy entry has at least one query template.
- No template uses angle-bracket syntax (``<...>``).
- No template uses unknown placeholders.
- Task-to-department resolution is correct and complete.
- Strategy file is parsable JSON.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# Canonical placeholder set (must stay in sync with query_resolver.py)
_CANONICAL_PLACEHOLDERS = {"company", "domain", "industry", "keywords", "buyer"}
_ANGLE_BRACKET_RE = re.compile(r"<[^>]+>")
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")

_TASK_TO_DEPARTMENT = {
    "company_fundamentals": "company",
    "economic_commercial_situation": "company",
    "financial_deep_dive": "company",
    "product_asset_scope": "company",
    "transaction_event_intelligence": "company",
    "market_situation": "market",
    "peer_companies": "buyer",
    "monetization_redeployment": "buyer",
    "contact_discovery": "contact",
    "target_company_contacts": "contact",
    "contact_qualification": "contact",
}

ROOT = Path(__file__).resolve().parent.parent
STRATEGY_DIR = ROOT / "knowledge" / "query_strategies"
SOURCE_DIR = ROOT / "knowledge" / "sources"


def _strategy_path(slug: str) -> Path:
    return STRATEGY_DIR / f"{slug}.yaml"


def _collect_templates(obj: object) -> list[str]:
    """Recursively collect all string values from a nested structure."""
    results: list[str] = []
    if isinstance(obj, str):
        results.append(obj)
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_collect_templates(item))
    elif isinstance(obj, dict):
        for key, val in obj.items():
            if key in {"dedup", "buyer_limit", "result_limit", "department"}:
                continue
            results.extend(_collect_templates(val))
    return results


# ---------------------------------------------------------------------------
# File-level tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("slug", ["company", "market", "buyer", "contact"])
def test_strategy_file_exists(slug: str) -> None:
    assert _strategy_path(slug).is_file(), (
        f"Missing strategy file: {_strategy_path(slug)}"
    )


@pytest.mark.parametrize("slug", ["company", "market", "buyer", "contact"])
def test_strategy_file_parsable(slug: str) -> None:
    path = _strategy_path(slug)
    raw = path.read_text(encoding="utf-8").strip()
    assert raw, f"Strategy file is empty: {path}"
    data = json.loads(raw)  # raises on invalid JSON
    assert isinstance(data, dict), f"Strategy file must be a JSON object: {path}"
    assert "tasks" in data, f"Strategy file missing 'tasks' key: {path}"
    assert isinstance(data["tasks"], dict), f"'tasks' must be a dict in: {path}"


# ---------------------------------------------------------------------------
# Task coverage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("task_key,slug", _TASK_TO_DEPARTMENT.items())
def test_task_entry_exists(task_key: str, slug: str) -> None:
    path = _strategy_path(slug)
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks: dict = data["tasks"]
    assert task_key in tasks, (
        f"Missing task entry '{task_key}' in {path.name}. "
        f"Available: {sorted(tasks)}"
    )


@pytest.mark.parametrize("task_key,slug", _TASK_TO_DEPARTMENT.items())
def test_task_entry_has_templates(task_key: str, slug: str) -> None:
    path = _strategy_path(slug)
    data = json.loads(path.read_text(encoding="utf-8"))
    entry = data["tasks"][task_key]
    templates = _collect_templates(entry)
    assert templates, f"Task entry '{task_key}' in {path.name} has no query templates"


# ---------------------------------------------------------------------------
# Placeholder hygiene
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("task_key,slug", _TASK_TO_DEPARTMENT.items())
def test_no_angle_bracket_placeholders(task_key: str, slug: str) -> None:
    path = _strategy_path(slug)
    data = json.loads(path.read_text(encoding="utf-8"))
    entry = data["tasks"][task_key]
    templates = _collect_templates(entry)
    offenders = [t for t in templates if _ANGLE_BRACKET_RE.search(t)]
    assert not offenders, (
        f"Angle-bracket placeholders found in '{task_key}' ({path.name}):\n"
        + "\n".join(f"  {t!r}" for t in offenders)
    )


@pytest.mark.parametrize("task_key,slug", _TASK_TO_DEPARTMENT.items())
def test_only_canonical_placeholders(task_key: str, slug: str) -> None:
    path = _strategy_path(slug)
    data = json.loads(path.read_text(encoding="utf-8"))
    entry = data["tasks"][task_key]
    templates = _collect_templates(entry)
    unknown: list[tuple[str, str]] = []
    for tmpl in templates:
        for name in _PLACEHOLDER_RE.findall(tmpl):
            if name not in _CANONICAL_PLACEHOLDERS:
                unknown.append((name, tmpl))
    assert not unknown, (
        f"Unknown placeholders in '{task_key}' ({path.name}):\n"
        + "\n".join(f"  {{{name}}} in {tmpl!r}" for name, tmpl in unknown)
    )


# ---------------------------------------------------------------------------
# Task-to-department mapping
# ---------------------------------------------------------------------------

def test_all_standard_tasks_have_department_mapping() -> None:
    """Every entry in _TASK_TO_DEPARTMENT must be covered by a strategy file."""
    for task_key, slug in _TASK_TO_DEPARTMENT.items():
        path = _strategy_path(slug)
        assert path.is_file(), f"No strategy file for department '{slug}' (task: {task_key})"


def test_department_mapping_completeness() -> None:
    """The 11 standard tasks must all be present in _TASK_TO_DEPARTMENT."""
    standard_tasks = {
        "company_fundamentals", "economic_commercial_situation", "financial_deep_dive",
        "product_asset_scope", "transaction_event_intelligence", "market_situation",
        "peer_companies", "monetization_redeployment", "contact_discovery",
        "target_company_contacts", "contact_qualification",
    }
    missing = standard_tasks - set(_TASK_TO_DEPARTMENT)
    assert not missing, f"Standard tasks missing from department mapping: {missing}"


def test_no_extra_strategy_tasks_without_mapping() -> None:
    """Every task key in any strategy file must appear in _TASK_TO_DEPARTMENT."""
    extra: list[str] = []
    for slug in ("company", "market", "buyer", "contact"):
        path = _strategy_path(slug)
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for task_key in data.get("tasks", {}):
            if task_key not in _TASK_TO_DEPARTMENT:
                extra.append(f"{slug}.yaml: {task_key}")
    assert not extra, (
        "Strategy files contain task keys not in department mapping:\n"
        + "\n".join(f"  {e}" for e in extra)
    )


# ---------------------------------------------------------------------------
# validate_all_strategies helper (uses resolver's own validator)
# ---------------------------------------------------------------------------

def test_validate_all_strategies_passes() -> None:
    from src.research.query_resolver import validate_all_strategies, clear_strategy_cache
    clear_strategy_cache()
    errors = validate_all_strategies()
    assert not errors, (
        "validate_all_strategies() reported errors:\n"
        + "\n".join(f"  {slug}: {e}" for slug, errs in errors.items() for e in errs)
    )


def test_source_kb_contains_no_runtime_query_patterns() -> None:
    forbidden_prefixes = ("search_patterns", "queries", "template")
    offenders: list[str] = []
    for path in SOURCE_DIR.glob("*.yaml"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for idx, source in enumerate(data.get("sources", [])):
            if not isinstance(source, dict):
                continue
            for key in source:
                if key.startswith(forbidden_prefixes):
                    offenders.append(f"{path.name}: sources[{idx}].{key}")
    assert not offenders, "Source KB must not contain runtime query templates:\n" + "\n".join(offenders)
