"""File-backed long-term memory focused on reusable strategies."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from filelock import FileLock


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
        if pattern.get("domain"):
            import logging
            logging.getLogger(__name__).warning(
                "upsert_strategy: rejected pattern '%s' with domain='%s' — "
                "only domain-free structural patterns may enter long-term memory",
                pattern.get("name", "?"), pattern.get("domain"),
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
