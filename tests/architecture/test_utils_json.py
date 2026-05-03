from __future__ import annotations

import json

from src.utils import sanitize_for_json, strict_json_dumps


def test_sanitize_for_json_replaces_non_finite_floats() -> None:
    payload = {"value": float("nan"), "nested": [float("inf"), 1.5]}
    result = sanitize_for_json(payload)
    assert result == {"value": None, "nested": [None, 1.5]}


def test_sanitize_for_json_removes_surrogates_and_control_chars() -> None:
    payload = {"text": "ok\u0000bad\ud800text"}
    result = sanitize_for_json(payload)
    assert result == {"text": "okbadtext"}


def test_strict_json_dumps_emits_parseable_json() -> None:
    rendered = strict_json_dumps(
        {"value": float("nan"), "text": "ok\u0000bad\ud800text"},
        ensure_ascii=False,
    )
    assert json.loads(rendered) == {"value": None, "text": "okbadtext"}
