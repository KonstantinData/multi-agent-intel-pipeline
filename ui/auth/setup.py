"""Bootstrap script: create the first Liquisto admin user.

Usage (from project root):
    python -m ui.auth.setup
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> None:
    try:
        import bcrypt
    except ImportError:
        print("ERROR: 'bcrypt' nicht installiert. Ausführen: pip install bcrypt")
        sys.exit(1)

    from ui.auth.db import create_user, init_db, user_count

    init_db()

    if user_count() > 0:
        print("Hinweis: Es existieren bereits Benutzer in der Datenbank.")
        answer = input("Trotzdem fortfahren? (j/N): ").strip().lower()
        if answer not in ("j", "ja", "y", "yes"):
            print("Abgebrochen.")
            sys.exit(0)

    print("\n=== Ersten Admin-Benutzer anlegen ===\n")
    first_name = input("Vorname       : ").strip()
    last_name  = input("Nachname      : ").strip()
    company    = input("Unternehmen   : ").strip()
    role       = input("Rolle         : ").strip()
    email      = input("E-Mail        : ").strip().lower()

    while True:
        pw1 = getpass.getpass("Passwort      : ")
        pw2 = getpass.getpass("Bestätigen    : ")
        if pw1 != pw2:
            print("Passwörter stimmen nicht überein.\n")
            continue
        if len(pw1) < 8:
            print("Passwort muss mindestens 8 Zeichen lang sein.\n")
            continue
        break

    pw_hash = bcrypt.hashpw(pw1.encode(), bcrypt.gensalt()).decode()

    create_user(
        actor_email="setup",
        email=email,
        password_hash=pw_hash,
        first_name=first_name,
        last_name=last_name,
        company=company,
        role=role,
        is_admin=True,
    )

    print(f"\n✓ Admin-Benutzer '{email}' erfolgreich angelegt.")
    print("App starten und anmelden.\n")


if __name__ == "__main__":
    main()
