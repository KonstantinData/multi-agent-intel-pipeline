"""Preflight check: validates everything needed before starting Streamlit."""
from __future__ import annotations

import os
import socket
import sys
import urllib.request
from pathlib import Path
from typing import Callable

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parent
STREAMLIT_PORT = 8501
STREAMLIT_URL = f"http://127.0.0.1:{STREAMLIT_PORT}"


def _project_path(*parts: str) -> Path:
    return ROOT.joinpath(*parts)


def _load_openai_api_key() -> tuple[str, str]:
    env_path = _project_path(".env")
    env_values = dotenv_values(env_path) if env_path.exists() else {}
    env_file_key = str(env_values.get("OPENAI_API_KEY", "") or "").strip()
    if env_file_key:
        return env_file_key, ".env"

    process_key = str(os.environ.get("OPENAI_API_KEY", "") or "").strip()
    if process_key:
        return process_key, "environment"

    raise ValueError("OPENAI_API_KEY not found or empty in .env/environment")


def _port_status(port: int) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        return "free"
    except OSError:
        try:
            response = urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=2)
        except Exception as exc:
            raise OSError(f"PORT {port} IS IN USE and did not answer HTTP locally: {exc}") from exc
        status = getattr(response, "status", "unknown")
        return f"in use by reachable local HTTP service (HTTP {status})"
    finally:
        sock.close()


def check(label: str, fn: Callable[[], str], counters: dict[str, int]) -> None:
    try:
        result = fn()
        print(f"  [OK] {label}: {result}")
        counters["pass"] += 1
    except Exception as exc:
        print(f"  [FAIL] {label}: {exc}")
        counters["fail"] += 1


def main() -> int:
    os.chdir(ROOT)
    counters = {"pass": 0, "fail": 0}

    print("=" * 60)
    print("PREFLIGHT CHECK")
    print("=" * 60)

    print("\n1. Python")
    check("Version", lambda: sys.version.split()[0], counters)
    check("Executable", lambda: sys.executable, counters)

    print("\n2. Packages")
    for pkg, imp in [
        ("streamlit", "streamlit"),
        ("autogen (ag2)", "autogen"),
        ("openai", "openai"),
        ("pydantic", "pydantic"),
        ("python-dotenv", "dotenv"),
        ("fpdf2", "fpdf"),
    ]:
        check(pkg, lambda i=imp: (m := __import__(i)) and getattr(m, "__version__", "ok"), counters)

    print("\n3. Project files")
    for path in [
        "ui/app.py",
        "src/pipeline_runner.py",
        "src/config/settings.py",
        "src/agents/definitions.py",
        "src/models/schemas.py",
        "src/exporters/pdf_report.py",
        "src/exporters/json_export.py",
        ".env",
        ".streamlit/config.toml",
    ]:
        check(
            path,
            lambda path=path: (
                "exists"
                if _project_path(path).is_file()
                else (_ for _ in ()).throw(FileNotFoundError(f"NOT FOUND: {path}"))
            ),
            counters,
        )

    print("\n4. Environment")
    check("OPENAI_API_KEY available", lambda: f"set via {_load_openai_api_key()[1]}", counters)

    print("\n5. Import chain (simulates Streamlit loading app.py)")
    sys.path.insert(0, str(ROOT))
    check("src.config", lambda: __import__("src.config") and "ok", counters)
    check("src.models.schemas", lambda: __import__("src.models.schemas") and "ok", counters)
    check("src.agents.definitions", lambda: __import__("src.agents.definitions") and "ok", counters)
    check("src.pipeline_runner", lambda: __import__("src.pipeline_runner") and "ok", counters)
    check("src.exporters.pdf_report", lambda: __import__("src.exporters.pdf_report") and "ok", counters)
    check("src.exporters.json_export", lambda: __import__("src.exporters.json_export") and "ok", counters)

    print(f"\n6. Port {STREAMLIT_PORT}")
    check(f"Port {STREAMLIT_PORT}", lambda: _port_status(STREAMLIT_PORT), counters)

    print("\n7. Streamlit CLI")
    check("streamlit.web.cli", lambda: __import__("streamlit.web.cli") and "ok", counters)

    print("\n" + "=" * 60)
    if counters["fail"] == 0:
        print(f"ALL {counters['pass']} CHECKS PASSED - ready to start Streamlit!")
    else:
        print(f"{counters['fail']} CHECK(S) FAILED out of {counters['pass'] + counters['fail']} - fix before starting!")
    print("=" * 60)

    return counters["fail"]


if __name__ == "__main__":
    raise SystemExit(main())
