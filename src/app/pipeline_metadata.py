"""UI-facing pipeline metadata."""
from __future__ import annotations

from src.agents.specs import AGENT_SPECS

AGENT_META = {
    name: {"icon": spec.icon, "color": spec.color, "summary": spec.summary}
    for name, spec in AGENT_SPECS.items()
}

PIPELINE_STEPS = [
    ("Supervisor", "Intake + Routing"),
    ("CompanyDepartment", "Company"),
    ("MarketDepartment", "Market"),
    ("BuyerDepartment", "Buyer"),
    ("ContactDepartment", "Contact Intelligence"),
    ("SynthesisDepartment", "Strategic Synthesis"),
    ("ReportWriter", "Report"),
]
