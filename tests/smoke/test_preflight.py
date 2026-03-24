"""Smoke tests for preflight and basic importability.

NO AG2/autogen dependency.
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import preflight


class _OkHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        return


def test_load_openai_api_key_rejects_empty_or_commented_value(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (tmp_path / ".env").write_text("# OPENAI_API_KEY=test\nOPENAI_API_KEY=\n", encoding="utf-8")
    with pytest.raises(ValueError):
        preflight._load_openai_api_key()


def test_load_openai_api_key_accepts_non_empty_env_file(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
    key, source = preflight._load_openai_api_key()
    assert key == "test-key"
    assert source == ".env"


def test_port_status_accepts_reachable_local_http_service():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status = preflight._port_status(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert "reachable local http service" in status.lower()


def test_pure_modules_importable():
    """Verify that architecture-layer modules can be imported without AG2."""
    import src.orchestration.contracts
    import src.orchestration.follow_up
    import src.orchestration.task_router
    import src.orchestration.tool_policy
    import src.orchestration.synthesis
    import src.orchestration.run_context
    import src.memory.short_term_store
    import src.memory.consolidation
    import src.memory.policies
    import src.models.registry
    import src.models.schemas
    import src.app.use_cases
    import src.domain.intake
    import src.agents.critic
    import src.agents.judge
    import src.agents.supervisor
    import src.orchestration.speaker_selector
