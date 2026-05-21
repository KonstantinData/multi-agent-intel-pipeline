"""Memory-side data structures."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RetrievalHit:
    name: str
    score: float
    rationale: str
    pattern_type: str = "strategy"


@dataclass(slots=True)
class StrategyPattern:
    name: str
    role: str
    industry_hint: str
    domain: str
    pattern_scope: str = "role_strategy"
    pattern_type: str = "query_strategy"
    best_practice_type: str = "query_strategy"
    admission_level: str = "full_run"
    task_key: str = ""
    task_status: str = ""
    successful_queries: list[str] = field(default_factory=list)
    structural_queries: list[str] = field(default_factory=list)
    useful_source_types: list[str] = field(default_factory=list)
    source_strategy: dict[str, object] = field(default_factory=dict)
    evidence_pattern: dict[str, object] = field(default_factory=dict)
    task_recipe: dict[str, object] = field(default_factory=dict)
    critic_acceptance_heuristic: dict[str, object] = field(default_factory=dict)
    rationale: str = ""
    score: float = 0.0
