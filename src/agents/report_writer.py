"""Report writer agent for final operator-facing report packaging."""
from __future__ import annotations

from typing import Any

from src.orchestration.envelope import resolve_visual_focus


class ReportWriterAgent:
    """Build a stable report package from validated pipeline artifacts."""

    _RECOMMENDED_SECTIONS: tuple[str, ...] = (
        "Executive summary",
        "Company snapshot",
        "Market and inventory pressure signals",
        "Buyer and redeployment paths",
        "Contact intelligence and outreach angles",
        "Liquisto opportunity assessment",
        "Negotiation relevance and next steps",
        "Evidence appendix",
    )

    def build_report_package(
        self,
        *,
        pipeline_data: dict[str, Any],
        department_packages: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        synthesis = pipeline_data.get("synthesis", {})
        company = pipeline_data.get("company_profile", {})
        quality = pipeline_data.get("quality_review", {})
        return {
            "report_status": "ready",
            "report_title": f"Liquisto Briefing - {company.get('company_name', 'n/v')}",
            "executive_summary": synthesis.get("executive_summary", "n/v"),
            "department_visual_focus": {
                name: resolve_visual_focus(package)
                for name, package in department_packages.items()
            },
            "recommended_sections": list(self._RECOMMENDED_SECTIONS),
            "open_gaps": quality.get("open_gaps", []),
        }

