"""Coding/search assistant used as a targeted escalation."""
from __future__ import annotations

from src.config import get_role_model_selection
from src.domain.intake import SupervisorBrief
from src.orchestration.tool_policy import resolve_allowed_tools
from src.research.extract import extract_product_keywords, infer_industry


class CodingAssistantAgent:
    def __init__(self, name: str = "CompanyCodingSpecialist") -> None:
        self.name = name
        self.model_name = get_role_model_selection(self.name)[0]
        self.allowed_tools = resolve_allowed_tools(self.name, "query_refinement")

    def suggest_queries(
        self,
        *,
        task_key: str,
        section: str,
        brief: SupervisorBrief,
        issues: list[str],
        review: dict | None = None,
        coding_brief: dict | None = None,
    ) -> dict:
        # Keep extraction calls for diagnostic context; runtime query text is
        # resolved later from knowledge/query_strategies via the variant token.
        product_keywords = extract_product_keywords(brief.raw_homepage_excerpt)
        industry_hint = infer_industry(brief.page_title, brief.meta_description, brief.raw_homepage_excerpt)
        variant_token = f"strategy:{task_key}:method_refinement"
        return {
            "task_key": task_key,
            "section": section,
            "issues": issues,
            "query_overrides": [variant_token],
            "revision_focus": list((review or {}).get("rejected_points", [])),
            "coding_brief": coding_brief or {},
            "summary": (
                "Refined search path selected from query strategy KB "
                f"(variant=method_refinement, industry_hint={industry_hint or 'n/v'}, "
                f"keyword_count={len(product_keywords)})."
            ),
            "model_name": self.model_name,
            "allowed_tools": list(self.allowed_tools),
        }
