"""Typed models for intelligent report composition."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ReportSectionDraft(BaseModel):
    section_id: str = "n/v"
    heading: str = "n/v"
    summary: str = "n/v"
    key_points: list[str] = Field(default_factory=list)
    decision_impact: str = "n/v"


class ReportDraft(BaseModel):
    language: Literal["de", "en"] = "en"
    run_id: str = "n/v"
    run_status: str = "n/v"
    company_name: str = "n/v"
    report_title: str = "n/v"
    executive_summary: str = "n/v"
    primary_opportunity_path: str = "n/v"
    primary_opportunity_reasoning: str = "n/v"
    confidence: str = "n/v"
    top_risks: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    blocker_summary: str = ""
    data_request_summary: str = ""
    outreach_playbook_summary: str = ""
    sections: list[ReportSectionDraft] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)

