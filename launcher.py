"""Launcher: preflight check, start Streamlit, open browser automatically."""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

os.chdir(os.path.dirname(os.path.abspath(__file__)))
PYTHON = sys.executable
ROOT = Path(__file__).resolve().parent


def _repo_python_candidates() -> list[Path]:
    return [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / "venv" / "Scripts" / "python.exe",
    ]


def _same_path(a: Path, b: Path) -> bool:
    try:
        return a.samefile(b)
    except Exception:
        return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))


def _maybe_reexec_with_repo_python(argv: list[str]) -> None:
    current = Path(sys.executable).resolve()
    for candidate in _repo_python_candidates():
        if not candidate.is_file():
            continue
        target = candidate.resolve()
        if _same_path(current, target):
            return
        print(f"[bootstrap] Re-launching with repo interpreter: {target}", flush=True)
        cmd = [str(target), str(ROOT / "launcher.py"), *argv]
        raise SystemExit(subprocess.run(cmd, check=False).returncode)


def port_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def wait_for_server(port, timeout=30):
    """Wait until the server accepts connections."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return False


def _streamlit_command(port: int) -> list[str]:
    streamlit_exe = Path(PYTHON).with_name("streamlit.exe")
    if os.name == "nt" and streamlit_exe.is_file():
        return [
            str(streamlit_exe),
            "run", "ui/app.py",
            "--server.headless", "true", "--server.port", str(port),
        ]
    return [
        PYTHON, "-m", "streamlit", "run", "ui/app.py",
        "--server.headless", "true", "--server.port", str(port),
    ]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the Streamlit UI for the Liquisto pipeline.")
    parser.add_argument(
        "--port",
        type=int,
        default=8501,
        help="Port for the Streamlit server.",
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Keep the launcher attached to the Streamlit process instead of exiting after startup.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    _maybe_reexec_with_repo_python(argv)

    args = parse_args(argv)
    port = args.port
    url = f"http://localhost:{port}"

    print("=" * 60)
    print("  Liquisto Market Intelligence Pipeline")
    print("=" * 60)

    # Step 1: Validate port
    print(f"\n[1/4] Checking port {port}...")
    if not port_free(port):
        print(f"  ERROR: Port {port} is already in use. Stop the existing service or start with --port.")
        return 1
    print(f"  Port {port} is free.")

    # Step 2: Preflight
    print("\n[2/4] Running preflight checks...")
    ret = subprocess.run([PYTHON, "preflight.py"], capture_output=True, text=True)
    if ret.returncode != 0:
        print(ret.stdout)
        print(ret.stderr)
        print("\nPreflight FAILED. Cannot start.")
        return 1
    print("  All checks passed.")

    # Step 3: Start Streamlit
    print("\n[3/4] Starting Streamlit server...")
    popen_kwargs = {
        "args": _streamlit_command(port),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(**popen_kwargs)

    print(f"  Waiting for server (PID {proc.pid})...")
    if not wait_for_server(port, timeout=30):
        print("  ERROR: Server did not start within 30 seconds.")
        proc.kill()
        return 1
    print(f"  Server is running on {url}")

    # Step 4: Open browser
    print("\n[4/4] Opening browser...")
    webbrowser.open(url)
    print("  Browser opened.")

    print("\n" + "=" * 60)
    print(f"  Streamlit running at {url}")
    if args.foreground:
        print("  Press Ctrl+C to stop the server.")
    else:
        print("  Launcher exits now. Streamlit continues in the background.")
    print("=" * 60)

    if not args.foreground:
        return 0

    try:
        while proc.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        proc.terminate()
        proc.wait(timeout=5)

    print("Server stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
