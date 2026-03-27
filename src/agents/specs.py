"""Agent metadata specs — pure, no runtime dependencies."""
from __future__ import annotations

from src.agents.registry import AgentSpec

AGENT_SPECS = {
    "Supervisor": AgentSpec("Supervisor", "🧭", "#0f4c81", "Owns intake normalization, routing, and run control."),
    "CompanyDepartment": AgentSpec("CompanyDepartment", "🏢", "#1b7f5a", "AutoGen group for company facts, asset scope, and economic signals."),
    "MarketDepartment": AgentSpec("MarketDepartment", "📡", "#cc6f16", "AutoGen group for market context, circularity, and analytics signals."),
    "BuyerDepartment": AgentSpec("BuyerDepartment", "🌐", "#167d7f", "AutoGen group for peers, buyers, and redeployment paths."),
    "ContactDepartment": AgentSpec("ContactDepartment", "👤", "#0e7490", "AutoGen group for contact discovery at prioritized buyer firms."),
    "SynthesisDepartment": AgentSpec("SynthesisDepartment", "🧠", "#7b4bc4", "AG2 group that synthesizes all domain reports into a Liquisto briefing."),
    "ReportWriter": AgentSpec("ReportWriter", "📄", "#374151", "Turns the approved analysis into an operator-facing report."),
    "CompanyLead": AgentSpec("CompanyLead", "🧩", "#1b7f5a", "Leads the Company Department group."),
    "MarketLead": AgentSpec("MarketLead", "🧩", "#cc6f16", "Leads the Market Department group."),
    "BuyerLead": AgentSpec("BuyerLead", "🧩", "#167d7f", "Leads the Buyer Department group."),
    "ContactLead": AgentSpec("ContactLead", "🧩", "#0e7490", "Leads the Contact Intelligence Department group."),
    "SynthesisLead": AgentSpec("SynthesisLead", "🧩", "#7b4bc4", "Leads the Strategic Synthesis Department group."),
    "CompanyResearcher": AgentSpec("CompanyResearcher", "🔎", "#1b7f5a", "Research specialist inside the Company Department."),
    "MarketResearcher": AgentSpec("MarketResearcher", "🔎", "#cc6f16", "Research specialist inside the Market Department."),
    "BuyerResearcher": AgentSpec("BuyerResearcher", "🔎", "#167d7f", "Research specialist inside the Buyer Department."),
    "ContactResearcher": AgentSpec("ContactResearcher", "🔎", "#0e7490", "Contact discovery specialist inside the Contact Department."),
    "CompanyCritic": AgentSpec("CompanyCritic", "🔍", "#b42318", "Reviews Company Department outputs."),
    "MarketCritic": AgentSpec("MarketCritic", "🔍", "#b42318", "Reviews Market Department outputs."),
    "BuyerCritic": AgentSpec("BuyerCritic", "🔍", "#b42318", "Reviews Buyer Department outputs."),
    "ContactCritic": AgentSpec("ContactCritic", "🔍", "#b42318", "Reviews Contact Intelligence outputs."),
    "SynthesisCritic": AgentSpec("SynthesisCritic", "🔍", "#b42318", "Reviews synthesis quality and cross-domain consistency."),
    "CompanyJudge": AgentSpec("CompanyJudge", "⚖️", "#6941c6", "Resolves unresolved Company Department conflicts."),
    "MarketJudge": AgentSpec("MarketJudge", "⚖️", "#6941c6", "Resolves unresolved Market Department conflicts."),
    "BuyerJudge": AgentSpec("BuyerJudge", "⚖️", "#6941c6", "Resolves unresolved Buyer Department conflicts."),
    "ContactJudge": AgentSpec("ContactJudge", "⚖️", "#6941c6", "Resolves unresolved Contact Intelligence conflicts."),
    "SynthesisJudge": AgentSpec("SynthesisJudge", "⚖️", "#6941c6", "Final decision-maker for synthesis edge cases."),
    "CompanyCodingSpecialist": AgentSpec("CompanyCodingSpecialist", "🧰", "#475467", "Refines blocked Company Department research paths."),
    "MarketCodingSpecialist": AgentSpec("MarketCodingSpecialist", "🧰", "#475467", "Refines blocked Market Department research paths."),
    "BuyerCodingSpecialist": AgentSpec("BuyerCodingSpecialist", "🧰", "#475467", "Refines blocked Buyer Department research paths."),
    "ContactCodingSpecialist": AgentSpec("ContactCodingSpecialist", "🧰", "#475467", "Refines blocked Contact Intelligence research paths."),
}
