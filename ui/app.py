"""Liquisto — entry point: auth gate, global sidebar, page navigation."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from ui.auth.db import init_db
from ui.auth.session import do_logout, get_current_user
from ui.theme import BRAND_CSS

_LOGO = PROJECT_ROOT / "assets" / "image" / "liquisto_logo.png"

st.set_page_config(page_title="Liquisto", page_icon="📋", layout="wide")
st.markdown(BRAND_CSS, unsafe_allow_html=True)

init_db()

# ── Not authenticated: show only the login page (sidebar nav hidden) ──────────
if not st.session_state.get("user"):
    pg = st.navigation(
        [st.Page("pages/login.py", title="Login", icon="🔐", default=True)],
        position="hidden",
    )
    pg.run()

# ── Authenticated: full sidebar + navigation ───────────────────────────────────
else:
    user = get_current_user()
    lang = st.session_state.get("lang", user.get("language", "de"))

    with st.sidebar:
        if _LOGO.exists():
            st.image(str(_LOGO), use_container_width=True)

        st.divider()

        full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
        company   = user.get("company", "")
        st.markdown(f"**{full_name}**")
        if company:
            st.caption(company)

        st.divider()

        lang_label = "🌐 Deutsch / English" if lang == "de" else "🌐 English / Deutsch"
        if st.button(lang_label, use_container_width=True):
            st.session_state["lang"] = "en" if lang == "de" else "de"
            st.rerun()

        if st.button(
            "Abmelden" if lang == "de" else "Sign out",
            use_container_width=True,
            type="secondary",
        ):
            do_logout()

    _pages = [
        st.Page("pages/home.py",       title="Home",                    icon="🏠", default=True),
        st.Page("pages/recherche.py",  title="Unternehmens-Recherche",  icon="🔍"),
    ]
    if user.get("is_admin"):
        _pages.append(st.Page("pages/admin.py", title="Admin", icon="⚙️"))

    pg = st.navigation(_pages)
    pg.run()
