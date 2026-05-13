"""Liquisto — Home page with function tiles."""
from __future__ import annotations

import streamlit as st

from ui.auth.session import get_current_user

user = get_current_user()
first_name = user.get("first_name", "")
lang = st.session_state.get("lang", "de")

if lang == "de":
    st.markdown(f"## Willkommen zurück, {first_name}!")
    st.caption("Was möchten Sie heute tun?")
else:
    st.markdown(f"## Welcome back, {first_name}!")
    st.caption("What would you like to do today?")

st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    with st.container(border=True):
        st.markdown("### 🔍 " + ("Unternehmens-Recherche" if lang == "de" else "Company Research"))
        st.caption(
            "Intelligence Report für Ihr nächstes Vertriebsmeeting"
            if lang == "de" else
            "Intelligence report for your next sales meeting"
        )
        st.page_link(
            "pages/recherche.py",
            label="Öffnen →" if lang == "de" else "Open →",
            use_container_width=True,
        )

with col2:
    with st.container(border=True):
        st.markdown("### 📊 " + ("Berichte" if lang == "de" else "Reports"))
        st.caption(
            "Gespeicherte Briefings und Berichte abrufen"
            if lang == "de" else
            "Access saved briefings and reports"
        )
        st.button(
            "Demnächst" if lang == "de" else "Coming soon",
            disabled=True,
            use_container_width=True,
            key="tile_reports",
        )

with col3:
    with st.container(border=True):
        st.markdown("### 🎯 Pipeline")
        st.caption(
            "Vertriebspipeline und offene Deals"
            if lang == "de" else
            "Sales pipeline and open deals"
        )
        st.button(
            "Demnächst" if lang == "de" else "Coming soon",
            disabled=True,
            use_container_width=True,
            key="tile_pipeline",
        )
