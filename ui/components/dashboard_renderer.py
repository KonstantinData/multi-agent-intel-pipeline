"""Streamlit renderer for DashboardBundle.

Pure rendering — all data derivation happens in dashboard_composer.
Supports: kpi, donut, treemap, bar, stacked_bar, line, map, table, callout.
"""
from __future__ import annotations

import streamlit as st

from src.models.visualization import (
    ChartSpec,
    DashboardBundle,
    DashboardSection,
    InsightCallout,
    KpiCard,
    TableBlock,
)


_SEVERITY_RENDER = {
    "success": st.success,
    "warning": st.warning,
    "error": st.error,
    "info": st.info,
}


def _render_kpi_row(kpis: list[KpiCard]) -> None:
    if not kpis:
        return
    cols = st.columns(min(len(kpis), 6))
    for col, kpi in zip(cols, kpis[:6]):
        with col:
            delta = kpi.subtitle if kpi.subtitle else None
            st.metric(kpi.title, kpi.value, delta=delta)


def _render_donut(chart: ChartSpec) -> None:
    if not chart.series or not chart.series[0].values:
        return
    try:
        import plotly.graph_objects as go
        labels = chart.labels
        values = [v if isinstance(v, (int, float)) else 0 for v in chart.series[0].values]
        _colors = {"answered": "#16B688", "partially_answered": "#c47f00", "pending": "#d0d5dd", "blocked": "#b83232"}
        marker_colors = [_colors.get(l, "#0D95C5") for l in labels]
        fig = go.Figure(data=[go.Pie(
            labels=labels, values=values, hole=0.45,
            marker=dict(colors=marker_colors),
            textinfo="label+value", textposition="outside",
        )])
        fig.update_layout(
            margin=dict(t=10, b=10, l=10, r=10), height=280,
            showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        # Fallback: text-based rendering
        for label, val in zip(chart.labels, chart.series[0].values):
            _icons = {"answered": "🟢", "partially_answered": "🟡", "pending": "⚪", "blocked": "🔴"}
            st.markdown(f"{_icons.get(label, '⚪')} **{label}**: {val}")


def _render_treemap(chart: ChartSpec) -> None:
    if not chart.series or not chart.series[0].values:
        return
    try:
        import plotly.graph_objects as go
        labels = chart.labels
        values = [v if isinstance(v, (int, float)) else 0 for v in chart.series[0].values]
        parents = [""] * len(labels)
        fig = go.Figure(go.Treemap(
            labels=labels, parents=parents, values=values,
            textinfo="label+value",
            marker=dict(cornerradius=4),
        ))
        fig.update_layout(
            margin=dict(t=10, b=10, l=10, r=10), height=300,
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        # Fallback: horizontal list
        for label, val in zip(chart.labels, chart.series[0].values):
            st.write(f"- **{label}**: {val}")


def _render_bar(chart: ChartSpec) -> None:
    if not chart.series or not chart.labels:
        return
    try:
        import plotly.graph_objects as go
        fig = go.Figure()
        for series in chart.series:
            values = [v if isinstance(v, (int, float)) else 0 for v in series.values]
            fig.add_trace(go.Bar(
                x=chart.labels, y=values, name=series.label,
                marker_color=series.color or "#0D95C5",
            ))
        fig.update_layout(
            margin=dict(t=10, b=30, l=40, r=10), height=280,
            showlegend=len(chart.series) > 1,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(gridcolor="#e5e7eb"),
        )
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        import pandas as pd
        data = {s.label: s.values for s in chart.series}
        df = pd.DataFrame(data, index=chart.labels)
        st.bar_chart(df)


def _render_map(chart: ChartSpec) -> None:
    """Render a geographic distribution chart. Uses a horizontal bar as a
    reliable cross-platform representation of country-level counts."""
    if not chart.series or not chart.labels:
        return
    try:
        import plotly.graph_objects as go
        labels = chart.labels
        values = [v if isinstance(v, (int, float)) else 0 for v in chart.series[0].values]
        # Sort descending
        paired = sorted(zip(labels, values), key=lambda x: x[1], reverse=True)
        labels, values = zip(*paired) if paired else ([], [])
        fig = go.Figure(go.Bar(
            y=list(labels), x=list(values), orientation="h",
            marker_color="#004E99",
            text=list(values), textposition="outside",
        ))
        fig.update_layout(
            margin=dict(t=10, b=10, l=10, r=40), height=max(180, len(labels) * 32),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(gridcolor="#e5e7eb", title="Companies"),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        for label, val in zip(chart.labels, chart.series[0].values):
            st.write(f"- **{label}**: {val}")


def _render_chart(chart: ChartSpec) -> None:
    st.markdown(f"**{chart.title}**")
    if chart.subtitle:
        st.caption(chart.subtitle)
    renderers = {
        "donut": _render_donut,
        "treemap": _render_treemap,
        "bar": _render_bar,
        "stacked_bar": _render_bar,
        "map": _render_map,
    }
    renderer = renderers.get(chart.chart_type)
    if renderer:
        renderer(chart)
    else:
        # Fallback for line / unknown
        for series in chart.series:
            for label, val in zip(chart.labels, series.values):
                st.write(f"- {label}: {val}")


def _render_table(table: TableBlock) -> None:
    if not table.rows:
        return
    st.markdown(f"**{table.title}**")
    import pandas as pd
    df = pd.DataFrame(table.rows, columns=table.columns if table.columns else None)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_callout(callout: InsightCallout) -> None:
    renderer = _SEVERITY_RENDER.get(callout.severity, st.info)
    text = f"{callout.icon} **{callout.title}**" if callout.title else ""
    if callout.body:
        text += f"\n\n{callout.body}" if text else callout.body
    renderer(text)


def _render_section(section: DashboardSection) -> None:
    st.markdown(f"### {section.title}")
    _render_kpi_row(section.kpis)
    for chart in section.charts:
        _render_chart(chart)
    for table in section.tables:
        _render_table(table)
    for callout in section.callouts:
        _render_callout(callout)


def render_dashboard(bundle: DashboardBundle) -> None:
    """Render a full DashboardBundle in Streamlit."""
    for section in bundle.sections:
        _render_section(section)
        st.divider()
