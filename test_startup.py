"""DEPRECATED — heavy end-to-end startup test (subprocess-based).

Not yet migrated to tests/. Run directly with: python test_startup.py
See TESTING.md for the new test structure.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request

os.chdir(os.path.dirname(os.path.abspath(__file__)))
PYTHON = sys.executable


def step(num: int, total: int, label: str) -> None:
    print(f"\n[{num}/{total}] {label}")


def port_is_free(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _pick_free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _popen_streamlit(port: int) -> subprocess.Popen:
    popen_kwargs = {
        "args": [
            PYTHON, "-m", "streamlit", "run", "ui/app.py",
            "--server.headless", "true", "--server.port", str(port),
        ],
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    return subprocess.Popen(**popen_kwargs)


def main() -> int:
    errors: list[str] = []
    proc: subprocess.Popen | None = None
    port = _pick_free_port()
    url = f"http://localhost:{port}"

    step(1, 5, f"Select a free test port ({port})")
    if port_is_free(port):
        print("  PASS - port is free")
    else:
        errors.append(f"Port {port} is unexpectedly busy")
        print(f"  FAIL - port {port} is unexpectedly busy")

    step(2, 5, "Preflight checks")
    if not errors:
        preflight = subprocess.run([PYTHON, "preflight.py"], capture_output=True, text=True)
        if preflight.returncode != 0:
            print(preflight.stdout)
            if preflight.stderr:
                print(preflight.stderr)
            errors.append("Preflight failed")
        else:
            print("  PASS - all checks OK")
    else:
        print("  SKIPPED (previous errors)")

    step(3, 5, "Start Streamlit subprocess")
    if not errors:
        proc = _popen_streamlit(port)
        print(f"  Started PID {proc.pid}")
    else:
        print("  SKIPPED (previous errors)")

    step(4, 5, "Wait for server to accept connections")
    if proc:
        ready = False
        for i in range(30):
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                probe.settimeout(1)
                probe.connect(("127.0.0.1", port))
                ready = True
                print(f"  PASS - server ready after {i + 1}s")
                break
            except (ConnectionRefusedError, OSError):
                time.sleep(1)
            finally:
                probe.close()
        if not ready:
            errors.append("Server did not start within 30s")
            print("  FAIL - timeout")
            proc.kill()
            proc = None
    else:
        print("  SKIPPED")

    step(5, 5, "HTTP response check")
    if proc and not errors:
        try:
            resp = urllib.request.urlopen(url, timeout=5)
            if resp.status == 200:
                print(f"  PASS - HTTP {resp.status}")
            else:
                errors.append(f"HTTP {resp.status}")
                print(f"  FAIL - HTTP {resp.status}")
        except Exception as exc:
            errors.append(f"HTTP error: {exc}")
            print(f"  FAIL - {exc}")
    else:
        print("  SKIPPED")

    print("\n" + "=" * 60)
    if errors:
        print(f"FAILED - {len(errors)} error(s):")
        for error in errors:
            print(f"  - {error}")
        if proc and proc.poll() is None:
            proc.kill()
        return 1

    print("ALL 5 STEPS PASSED")
    print(f"Streamlit reachable at {url} (PID {proc.pid})")
    if proc and proc.poll() is None:
        proc.kill()
        print("Test server stopped.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
