"""Liquisto Admin — Benutzerverwaltung und Audit Log."""
from __future__ import annotations

import streamlit as st

from ui.auth.session import get_current_user

user = get_current_user()
if not user.get("is_admin"):
    st.error("Kein Zugriff. Diese Seite ist nur für Administratoren.")
    st.stop()

import bcrypt

from ui.auth.db import (
    create_user,
    get_audit_log,
    get_user_by_id,
    list_users,
    update_user,
)

st.title("⚙️ Benutzerverwaltung")

tab_users, tab_audit = st.tabs(["👥 Benutzer", "📋 Audit Log"])


# ── Users tab ─────────────────────────────────────────────────────────────────
with tab_users:
    col_h, col_btn = st.columns([5, 1])
    with col_btn:
        if st.button("+ Neuer Benutzer", use_container_width=True):
            st.session_state["admin_action"] = "create"
            st.rerun()

    action = st.session_state.get("admin_action", "")

    # ── Create ────────────────────────────────────────────────────────────────
    if action == "create":
        with st.container(border=True):
            st.markdown("### Neuen Benutzer anlegen")
            with st.form("create_user_form", border=False):
                c1, c2 = st.columns(2)
                with c1:
                    fn       = st.text_input("Vorname *")
                    company  = st.text_input("Unternehmen")
                    email    = st.text_input("E-Mail *")
                    is_admin = st.checkbox("Administrator")
                with c2:
                    ln       = st.text_input("Nachname *")
                    role     = st.text_input("Rolle")
                    mobile   = st.text_input("Mobil")
                    language = st.selectbox("Sprache", ["de", "en"])
                pw1 = st.text_input("Passwort *", type="password")
                pw2 = st.text_input("Passwort bestätigen *", type="password")
                col_save, col_cancel = st.columns(2)
                with col_save:
                    save = st.form_submit_button("Anlegen", use_container_width=True, type="primary")
                with col_cancel:
                    cancel = st.form_submit_button("Abbrechen", use_container_width=True)

            if cancel:
                st.session_state.pop("admin_action", None)
                st.rerun()

            if save:
                errors = []
                if not fn.strip():
                    errors.append("Vorname erforderlich")
                if not ln.strip():
                    errors.append("Nachname erforderlich")
                if not email.strip():
                    errors.append("E-Mail erforderlich")
                if not pw1:
                    errors.append("Passwort erforderlich")
                elif len(pw1) < 8:
                    errors.append("Passwort muss mindestens 8 Zeichen haben")
                elif pw1 != pw2:
                    errors.append("Passwörter stimmen nicht überein")

                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    pw_hash = bcrypt.hashpw(pw1.encode(), bcrypt.gensalt()).decode()
                    try:
                        create_user(
                            actor_email=user["email"],
                            email=email.strip().lower(),
                            password_hash=pw_hash,
                            first_name=fn.strip(),
                            last_name=ln.strip(),
                            company=company.strip(),
                            role=role.strip(),
                            mobile=mobile.strip(),
                            language=language,
                            is_admin=is_admin,
                        )
                        st.success(f"Benutzer '{email.strip()}' erfolgreich angelegt.")
                        st.session_state.pop("admin_action", None)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Fehler: {exc}")

    # ── Edit ──────────────────────────────────────────────────────────────────
    elif action.startswith("edit_"):
        edit_id = int(action.split("_", 1)[1])
        edit_u = get_user_by_id(edit_id)
        if edit_u:
            with st.container(border=True):
                st.markdown(f"### Bearbeiten: {edit_u['first_name']} {edit_u['last_name']}")
                with st.form("edit_user_form", border=False):
                    c1, c2 = st.columns(2)
                    with c1:
                        fn      = st.text_input("Vorname *",   value=edit_u["first_name"])
                        company = st.text_input("Unternehmen", value=edit_u["company"])
                        mobile  = st.text_input("Mobil",       value=edit_u["mobile"])
                    with c2:
                        ln       = st.text_input("Nachname *", value=edit_u["last_name"])
                        role     = st.text_input("Rolle",      value=edit_u["role"])
                        language = st.selectbox(
                            "Sprache", ["de", "en"],
                            index=0 if edit_u["language"] == "de" else 1,
                        )
                    col_flags1, col_flags2 = st.columns(2)
                    with col_flags1:
                        is_admin_val = st.checkbox("Administrator", value=bool(edit_u["is_admin"]))
                    with col_flags2:
                        is_active_val = st.checkbox("Aktiv", value=bool(edit_u["is_active"]))

                    st.divider()
                    st.caption("Neues Passwort — leer lassen um unverändert zu lassen")
                    new_pw  = st.text_input("Neues Passwort",    type="password")
                    new_pw2 = st.text_input("Passwort bestätigen", type="password")

                    col_save, col_cancel = st.columns(2)
                    with col_save:
                        save = st.form_submit_button("Speichern", use_container_width=True, type="primary")
                    with col_cancel:
                        cancel = st.form_submit_button("Abbrechen", use_container_width=True)

                if cancel:
                    st.session_state.pop("admin_action", None)
                    st.rerun()

                if save:
                    errors = []
                    if not fn.strip():
                        errors.append("Vorname erforderlich")
                    if not ln.strip():
                        errors.append("Nachname erforderlich")
                    if new_pw:
                        if len(new_pw) < 8:
                            errors.append("Passwort muss mindestens 8 Zeichen haben")
                        elif new_pw != new_pw2:
                            errors.append("Passwörter stimmen nicht überein")

                    if errors:
                        for e in errors:
                            st.error(e)
                    else:
                        fields: dict = {
                            "first_name": fn.strip(),
                            "last_name":  ln.strip(),
                            "company":    company.strip(),
                            "role":       role.strip(),
                            "mobile":     mobile.strip(),
                            "language":   language,
                            "is_admin":   int(is_admin_val),
                            "is_active":  int(is_active_val),
                        }
                        if new_pw:
                            fields["password_hash"] = bcrypt.hashpw(
                                new_pw.encode(), bcrypt.gensalt()
                            ).decode()
                        update_user(user["email"], edit_id, **fields)
                        st.success("Gespeichert.")
                        st.session_state.pop("admin_action", None)
                        st.rerun()

    # ── User list ─────────────────────────────────────────────────────────────
    st.divider()
    users = list_users()
    st.caption(f"{len(users)} Benutzer")

    for u in users:
        active_icon = "✅" if u["is_active"] else "⛔"
        admin_badge = " 🔑" if u["is_admin"] else ""
        last_login  = (u.get("last_login") or "—")[:10]

        col_name, col_email, col_company, col_last, col_status, col_edit, col_toggle = st.columns(
            [2, 2, 2, 1, 1, 1, 1]
        )
        with col_name:
            st.write(f"**{u['first_name']} {u['last_name']}**{admin_badge}")
        with col_email:
            st.write(u["email"])
        with col_company:
            st.write(u.get("company") or "—")
        with col_last:
            st.caption(last_login)
        with col_status:
            st.write(active_icon)
        with col_edit:
            if st.button("Bearbeiten", key=f"edit_{u['id']}", use_container_width=True):
                st.session_state["admin_action"] = f"edit_{u['id']}"
                st.rerun()
        with col_toggle:
            if u["id"] != user["id"]:
                label = "Deaktiv." if u["is_active"] else "Aktivier."
                if st.button(label, key=f"toggle_{u['id']}", use_container_width=True):
                    update_user(user["email"], u["id"], is_active=int(not u["is_active"]))
                    st.rerun()


# ── Audit log tab ─────────────────────────────────────────────────────────────
with tab_audit:
    st.markdown("### Audit Log")
    entries = get_audit_log(200)
    if not entries:
        st.caption("Noch keine Einträge.")
    else:
        st.caption(f"{len(entries)} Einträge — neueste zuerst")
        for e in entries:
            ts     = e["timestamp"][:19].replace("T", " ")
            actor  = e["actor_email"]
            action = e["action"]
            target = e.get("target_email") or ""
            detail = e.get("detail") or ""
            st.text(f"{ts}  {actor:<30}  {action:<22}  {target}  {detail}")
