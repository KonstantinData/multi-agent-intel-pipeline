"""File-backed long-term memory focused on reusable strategies."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from filelock import FileLock


_UNSAFE_URL_OR_DOMAIN_RE = re.compile(
    r"https?://|www\.|\b[\w\-]+\.(com|de|io|net|org|co\.uk|eu|at|ch)\b",
    re.IGNORECASE,
)
_UNSAFE_EMAIL_RE = re.compile(r"\b[\w.\-+]+@[\w.\-]+\.\w+\b", re.IGNORECASE)
_UNSAFE_LEGAL_NAME_RE = re.compile(r"\b[A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){0,4}\s+(GmbH|AG|SE|Inc|Ltd|BV|SAS|SA|NV|KG)\b")
_KNOWN_AUDIT_TARGET_RE = re.compile(r"\b(Tesla|Siemens|ACME)\b", re.IGNORECASE)


class FileLongTermMemoryStore:
    """Persist reusable strategy patterns across runs."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(str(self.path) + ".lock")
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def load(self) -> list[dict[str, Any]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            candidates = payload.get("strategies", [])
            if isinstance(candidates, list):
                return [item for item in candidates if isinstance(item, dict)]
        return []

    def retrieve(self, *, domain: str, industry_hint: str = "", role: str = "", limit: int = 5) -> list[dict[str, Any]]:
        items = self.load()
        scored: list[tuple[float, dict[str, Any]]] = []
        for item in items:
            score = 0.0
            # No domain-match bonus — domain-specific entries violate memory policy.
            # Only industry_hint and role contribute to retrieval scoring.
            if industry_hint and item.get("industry_hint") == industry_hint:
                score += 0.5
            if role and item.get("role") == role:
                score += 0.75
            score += float(item.get("score", 0.0))
            if score > 0:
                enriched = dict(item)
                enriched["score"] = round(score, 2)
                scored.append((score, enriched))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def upsert_strategy(self, pattern: dict[str, Any]) -> None:
        # Memory policy guard: reject patterns with company-specific domain
        if pattern.get("domain") or self._contains_case_specific_data(pattern):
            import logging
            logging.getLogger(__name__).warning(
                "upsert_strategy: rejected unsafe pattern '%s' — "
                "only scrubbed structural patterns may enter long-term memory",
                pattern.get("name", "?"),
            )
            return
        with self._lock:
            items = self.load()
            existing_index = next((idx for idx, item in enumerate(items) if item.get("name") == pattern.get("name")), None)
            if existing_index is None:
                items.append(pattern)
            else:
                # Score decay: reduce existing score by 10% so newer patterns
                # from tighter rules can replace older ones even at equal score.
                existing = items[existing_index]
                decayed_score = float(existing.get("score", 0.0)) * 0.9
                if float(pattern.get("score", 0.0)) >= decayed_score:
                    items[existing_index] = pattern
            self.path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

    def _contains_case_specific_data(self, value: Any) -> bool:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in {"contact", "contact_name", "person", "person_name", "url", "website"}:
                    if str(item).strip():
                        return True
                if self._contains_case_specific_data(item):
                    return True
            return False
        if isinstance(value, list):
            return any(self._contains_case_specific_data(item) for item in value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return False
            return bool(
                _UNSAFE_URL_OR_DOMAIN_RE.search(text)
                or _UNSAFE_EMAIL_RE.search(text)
                or _UNSAFE_LEGAL_NAME_RE.search(text)
                or _KNOWN_AUDIT_TARGET_RE.search(text)
            )
        return False
