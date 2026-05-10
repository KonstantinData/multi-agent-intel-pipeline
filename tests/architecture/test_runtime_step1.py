from __future__ import annotations

import pytest

from src.agents import supervisor as supervisor_module
from src.agents.supervisor import SupervisorAgent
from src.domain.intake import IntakeRequest
from src.research.extract import infer_company_identity
from src.research.fetch import fetch_website_snapshot
from src.research.normalize import normalize_domain


def test_intake_request_rejects_blank_required_fields() -> None:
    with pytest.raises(ValueError, match="company_name is required"):
        IntakeRequest(company_name="  ", web_domain="example.com")

    with pytest.raises(ValueError, match="web_domain is required"):
        IntakeRequest(company_name="Example GmbH", web_domain="  ")


def test_intake_request_trims_values() -> None:
    intake = IntakeRequest(company_name="  Example   GmbH  ", web_domain="  www.example.com  ")

    assert intake.company_name == "Example GmbH"
    assert intake.web_domain == "www.example.com"


def test_normalize_domain_handles_www_scheme_and_path() -> None:
    assert normalize_domain("HTTPS://www.Example.COM/path/to/page?x=1") == "example.com"
    assert normalize_domain("www.example.com/path/to/page") == "example.com"


def test_normalize_domain_blocks_private_and_reserved_hosts() -> None:
    # loopback
    assert normalize_domain("localhost") == ""
    assert normalize_domain("127.0.0.1") == ""
    # RFC1918 private ranges
    assert normalize_domain("10.0.0.1") == ""
    assert normalize_domain("192.168.1.100") == ""
    assert normalize_domain("172.16.0.1") == ""
    # link-local / cloud metadata
    assert normalize_domain("169.254.169.254") == ""
    # IPv6 loopback and private
    assert normalize_domain("::1") == ""
    assert normalize_domain("fd00::1") == ""
    # legitimate public domain must pass through
    assert normalize_domain("siemens.com") == "siemens.com"
    assert normalize_domain("8.8.8.8") == "8.8.8.8"


def test_legal_suffix_detection_uses_token_boundary() -> None:
    false_positive = infer_company_identity("Frag", title="", description="", text="")
    actual_legal_name = infer_company_identity("Acme AG", title="", description="", text="")

    assert false_positive["verified_legal_name"] == "n/v"
    assert actual_legal_name["verified_legal_name"] == "Acme AG"
    assert actual_legal_name["name_confidence"] == "high"


def test_fetch_website_snapshot_extracts_meta_description_with_flexible_attrs(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Headers:
        def get(self, name: str, default: str = "") -> str:
            if name.lower() == "content-type":
                return "text/html; charset=iso-8859-1"
            return default

        def get_content_charset(self) -> str:
            return "iso-8859-1"

    class _Response:
        headers = _Headers()

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            html = (
                "<html><head><title>Example</title>"
                '<meta content="Muller Maschinen" name="description">'
                "</head><body>Muller baut Anlagen.</body></html>"
            )
            return html.encode("iso-8859-1")

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _Response())

    snapshot = fetch_website_snapshot("https://example.com")

    assert snapshot["reachable"] is True
    assert snapshot["title"] == "Example"
    assert snapshot["meta_description"] == "Muller Maschinen"
    assert snapshot["visible_text"] == "Example Muller baut Anlagen."
    assert snapshot["error_type"] == ""
    assert snapshot["error_message"] == ""


def test_fetch_website_snapshot_returns_structured_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_timeout(request: object, timeout: int) -> object:
        raise TimeoutError("network timed out")

    monkeypatch.setattr("urllib.request.urlopen", _raise_timeout)

    snapshot = fetch_website_snapshot("https://example.com")

    assert snapshot["reachable"] is False
    assert snapshot["error_type"] == "TimeoutError"
    assert snapshot["error_message"] == "network timed out"


def test_build_intake_brief_uses_mocked_company_research(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_company_research(domain: str, company_name: str) -> dict:
        return {
            "normalized_domain": "example.com",
            "homepage_url": "https://example.com",
            "snapshot": {
                "reachable": False,
                "title": "Example AG",
                "meta_description": "Industrial automation supplier",
                "visible_text": "",
                "content_type": "",
                "is_pdf": False,
                "error_type": "TimeoutError",
                "error_message": "network timed out",
            },
            "summary": "Industrial automation supplier",
            "verified_company_name": "Example AG",
            "verified_legal_name": "Example AG",
            "name_confidence": "high",
        }

    monkeypatch.setattr(supervisor_module, "build_company_research", _fake_company_research)

    supervisor = SupervisorAgent.__new__(SupervisorAgent)
    brief, message = supervisor.build_intake_brief(
        IntakeRequest(company_name=" Example AG ", web_domain=" https://www.example.com/about ")
    )

    assert brief.company_name == "Example AG"
    assert brief.normalized_domain == "example.com"
    assert brief.website_reachable is False
    assert brief.fetch_error_type == "TimeoutError"
    assert brief.fetch_error_message == "network timed out"
    assert message["section"] == "supervisor_brief"
    assert message["status"] == "ready_for_department_routing"
