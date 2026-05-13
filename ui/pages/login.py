"""Login page — nur für nicht-authentifizierte Benutzer."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from ui.auth.db import user_count
from ui.auth.session import attempt_login

_LOGO = Path(__file__).resolve().parents[2] / "assets" / "image" / "liquisto_logo.png"

err = st.session_state.pop("_login_error", None)

_, col, _ = st.columns([1, 2, 1])
with col:
    if _LOGO.exists():
        st.image(str(_LOGO), use_container_width=True)
    st.markdown("<br>", unsafe_allow_html=True)

    if err:
        st.error(err)

    if user_count() == 0:
        st.warning(
            "Keine Benutzer angelegt. "
            "Bitte `python -m ui.auth.setup` auf dem Server ausführen."
        )
    else:
        with st.form("liquisto_login", border=True):
            email    = st.text_input("E-Mail", placeholder="name@firma.de")
            password = st.text_input("Passwort", type="password")
            submitted = st.form_submit_button("Anmelden", use_container_width=True)

        if submitted:
            attempt_login(email.strip().lower(), password)
