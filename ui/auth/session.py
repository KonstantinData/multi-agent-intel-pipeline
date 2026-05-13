"""Auth session management: login, logout, brute-force lockout."""
from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from ui.auth.db import (
    get_user_by_email,
    init_db,
    log_audit,
    record_login_failure,
    record_login_success,
)


def check_auth() -> None:
    """Stop page rendering if the user is not authenticated (defense-in-depth)."""
    init_db()
    if not st.session_state.get("user"):
        st.error("Sitzung abgelaufen. Bitte neu anmelden.")
        st.stop()


def get_current_user() -> dict:
    return st.session_state.get("user", {})


def do_logout() -> None:
    user = get_current_user()
    if user.get("email"):
        log_audit(user["email"], "logout", user["email"])
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


def attempt_login(email: str, password: str) -> None:
    """Verify credentials and populate session state on success."""
    import bcrypt

    if not email or not password:
        st.session_state["_login_error"] = "E-Mail und Passwort erforderlich."
        st.rerun()
        return

    user = get_user_by_email(email)

    if not user:
        st.session_state["_login_error"] = "Ungültige E-Mail oder Passwort."
        st.rerun()
        return

    if not user["is_active"]:
        st.session_state["_login_error"] = (
            "Konto deaktiviert. Bitte Administrator kontaktieren."
        )
        st.rerun()
        return

    locked_until = user.get("locked_until")
    if locked_until:
        locked_dt = datetime.fromisoformat(locked_until)
        if datetime.now(timezone.utc) < locked_dt:
            remaining = max(1, int((locked_dt - datetime.now(timezone.utc)).total_seconds() / 60) + 1)
            st.session_state["_login_error"] = (
                f"Konto gesperrt. Bitte in {remaining} Minute(n) erneut versuchen."
            )
            st.rerun()
            return

    try:
        valid = bcrypt.checkpw(password.encode(), user["password_hash"].encode())
    except Exception:
        valid = False

    if not valid:
        record_login_failure(user["id"], email)
        attempts = (user.get("failed_login_attempts") or 0) + 1
        left = max(0, 5 - attempts)
        msg = (
            f"Ungültige E-Mail oder Passwort. Noch {left} Versuch(e) vor Sperrung."
            if left > 0
            else "Konto gesperrt für 15 Minuten nach zu vielen Fehlversuchen."
        )
        st.session_state["_login_error"] = msg
        st.rerun()
        return

    record_login_success(user["id"], email)
    st.session_state["user"] = {
        "id":         user["id"],
        "email":      user["email"],
        "first_name": user["first_name"],
        "last_name":  user["last_name"],
        "company":    user["company"],
        "role":       user["role"],
        "is_admin":   bool(user["is_admin"]),
        "language":   user.get("language", "de"),
    }
    st.session_state["lang"] = user.get("language", "de")
    st.rerun()
