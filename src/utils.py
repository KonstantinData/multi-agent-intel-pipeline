"""Shared utility functions — canonical implementations.

P2-6: Eliminates duplicated _dedup_safe across 7+ modules.
"""
from __future__ import annotations

import json
import math
from typing import Any


def dedup_safe(items: list) -> list:
    """Deduplicate a list whose items may be dicts (unhashable).

    Uses JSON serialization as a stable key so both strings and dicts
    are handled without raising 'unhashable type: dict'.
    """
    seen: set[str] = set()
    result = []
    for item in items:
        key = (
            json.dumps(item, sort_keys=True, ensure_ascii=False)
            if isinstance(item, (dict, list))
            else str(item)
        )
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def sanitize_for_json(value: Any) -> Any:
    """Recursively sanitize values for strict JSON serialization.

    Removes invalid Unicode surrogate code points, strips disallowed control
    characters, and converts non-finite floats to ``None`` so downstream
    API clients never emit malformed JSON bodies.
    """
    if isinstance(value, dict):
        return {str(key): sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_for_json(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        cleaned: list[str] = []
        for char in value:
            codepoint = ord(char)
            if 0xD800 <= codepoint <= 0xDFFF:
                continue
            if codepoint < 32 and char not in "\n\r\t":
                continue
            cleaned.append(char)
        return "".join(cleaned)
    return value


def strict_json_dumps(value: Any, *, ensure_ascii: bool = False, sort_keys: bool = False) -> str:
    """Serialize with strict JSON guarantees for API-bound payloads."""
    return json.dumps(
        sanitize_for_json(value),
        ensure_ascii=ensure_ascii,
        sort_keys=sort_keys,
        allow_nan=False,
    )
