# Liquisto Department Runtime — Executive Overview

## What Is This?

An AI-powered research system that automatically generates pre-meeting
briefings for Liquisto customer conversations. Input: company name and web
domain. Output: a structured briefing document as PDF (German + English),
delivering in minutes what an analyst would need several hours to produce.

## What Problem Does It Solve?

Before every initial meeting with a potential customer, a Liquisto colleague
needs to understand:

- What does the company do, what does it sell or manufacture?
- Are there signs of economic pressure, excess inventory, or restructuring?
- Which goods, materials, or assets are visible?
- Who are the competitors and potential buyers?
- Which specific contacts exist at those buyer firms?
- Where is the most plausible Liquisto opportunity — inventory monetization,
  repurposing/circular economy, or analytics/decision support?
- What negotiation leverage and next steps emerge from the evidence?

This system answers all of these questions automatically and delivers a
print-ready briefing with source references.

## How Does It Work?

The system operates like an internal research department with specialized
teams. Each team has a lead, a researcher, a critic, and additional
specialists as needed. The teams work sequentially:

```
Input: Company Name + Web Domain
    │
    ▼
┌─────────────────────────────────────────────┐
│  Supervisor — Intake & Coordination         │
└──────────────────┬──────────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
┌────────┐   ┌─────────┐   ┌─────────┐
│Company │   │ Market  │   │ Buyer   │
│  Team  │   │  Team   │   │  Team   │
└───┬────┘   └────┬────┘   └────┬────┘
    │              │              │
    │              │              ▼
    │              │        ┌──────────┐
    │              │        │ Contact  │
    │              │        │  Team    │
    │              │        └────┬─────┘
    ▼              ▼             ▼
┌─────────────────────────────────────────────┐
│  Strategic Synthesis — Cross-Domain Review  │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│  Report Writer — PDF Briefing (DE + EN)     │
└─────────────────────────────────────────────┘
```

### The Four Research Teams

| Team | Scope |
|------|-------|
| **Company** | Company profile, products, economic situation, asset scope |
| **Market** | Market conditions, demand trends, repurposing potential, analytics signals |
| **Buyer** | Competitors, buyers, monetization and redeployment paths |
| **Contact** | Decision-makers at prioritized buyer firms with outreach suggestions |

Each team independently researches the open web, validates findings through
an internal critic, and delivers a reviewed result package. The Supervisor
controls the workflow but does not interpret domain-level content.

### Strategic Synthesis

After all teams complete their work, a synthesis unit evaluates the results
across domains: Where is the strongest Liquisto opportunity? What risks exist?
What concrete next steps make sense?

## What Does It Produce?

### PDF Briefing (German + English)

A professional document containing:

- **Key Facts** — industry, revenue, employees, location
- **Executive Summary** — overall assessment in one paragraph
- **Liquisto Opportunity** — evaluation of the three service areas (inventory monetization, repurposing, analytics) with relevance ratings
- **Company Profile** — products, assets, economic situation
- **Market & Demand Context** — trends, overcapacity, demand outlook
- **Buyer & Redeployment Landscape** — competitors, buyers, service providers, cross-industry buyers with relevance ratings
- **Contact Intelligence** — prioritized contacts with function, seniority, and a concrete outreach angle
- **Risks & Next Steps**
- **Evidence Appendix**

### Quality Assessment

Every briefing includes a Research Readiness Score (0–100) indicating how
reliable the results are. Briefings below a threshold are flagged as
"not usable."

### Follow-Up Questions

After a completed run, targeted follow-up questions can be asked through the
user interface. The system automatically routes the question to the
responsible team and answers it from the stored research context.

## User Interface

A web interface provides:

- Start a new run (enter company name + domain)
- Track live progress across all pipeline steps
- Load and browse completed runs
- View results per team
- Review synthesis and report package
- Ask follow-up questions
- Download PDF briefings (DE + EN)

## Cost Per Run

The system uses OpenAI language models (GPT-4.1 and GPT-4.1-mini).
Cost per briefing depends on the complexity of the target company.

| Model | Role | Price (Input / Output per 1M Tokens) |
|-------|------|--------------------------------------|
| gpt-4.1 | Team leads, critics, judges, synthesis | $2.00 / $8.00 |
| gpt-4.1-mini | Researchers, coding specialists, report writer | $0.40 / $1.60 |

Typical cost per complete briefing: **$0.10 – $0.80 USD**,
depending on research depth and number of revision loops.
Actual costs are tracked per run and displayed in the UI.

## Learning Capability

After every successful run, the system stores reusable work patterns — e.g.,
which search strategies worked well or which review heuristics led to better
results. It does **not** store unverified company facts as permanent truth.

## Technical Requirements

- Python 3.11+
- OpenAI API key
- No dedicated infrastructure required — runs locally on a laptop or server
- No database — all results are stored as JSON files

## Status

The system is operational and produces complete briefings. Every run is
archived under `artifacts/runs/<run_id>/` and is fully traceable at any time.
