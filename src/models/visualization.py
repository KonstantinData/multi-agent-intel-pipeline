"""Typed contracts for the shared dashboard visualization layer.

Both the Streamlit UI and the PDF report renderer consume the same
DashboardBundle — no duplicate business logic for chart/KPI derivation.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ChartType = Literal[
    "kpi", "donut", "treemap", "bar", "stacked_bar",
    "line", "table", "callout", "map",
]


class ChartSeries(BaseModel):
    label: str
    values: list[float | int | str] = Field(default_factory=list)
    color: str = ""


class KpiCard(BaseModel):
    title: str
    value: str
    subtitle: str = ""
    trend: Literal["up", "down", "neutral", ""] = ""
    color: str = ""
    source: str = ""


class ChartSpec(BaseModel):
    chart_id: str
    chart_type: ChartType
    title: str
    subtitle: str = ""
    labels: list[str] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)
    source: str = ""
    annotation: str = ""


class TableBlock(BaseModel):
    table_id: str
    title: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    source: str = ""


class InsightCallout(BaseModel):
    callout_id: str
    icon: str = "▸"
    title: str = ""
    body: str = ""
    severity: Literal["info", "success", "warning", "error"] = "info"
    source: str = ""


class DashboardSection(BaseModel):
    section_id: str
    title: str
    kpis: list[KpiCard] = Field(default_factory=list)
    charts: list[ChartSpec] = Field(default_factory=list)
    tables: list[TableBlock] = Field(default_factory=list)
    callouts: list[InsightCallout] = Field(default_factory=list)


class DashboardBundle(BaseModel):
    run_id: str = ""
    company_name: str = ""
    status: str = ""
    sections: list[DashboardSection] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
