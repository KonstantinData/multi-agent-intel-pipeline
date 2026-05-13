from __future__ import annotations

import pytest

from src.agents import supervisor as supervisor_module
from src.agents.supervisor import SupervisorAgent
from src.domain.intake import IntakeRequest, IntakeValidationError
from src.research.extract import infer_company_identity
from src.research.fetch import fetch_website_snapshot
from src.research.normalize import (
    IntakeErrorCode,
    NormalizedDomainResult,
    normalize_domain,
    normalize_domain_result,
)
from src.orchestration.runtime_agents import (
    DOMAIN_DEPARTMENT_NAMES,
    DEPARTMENT_REQUIRED_METHODS,
    REPORT_WRITER_REQUIRED_METHODS,
    SUPERVISOR_REQUIRED_METHODS,
    SYNTHESIS_REQUIRED_METHODS,
    RuntimeAgents,
    RuntimeAgentSpec,
    RuntimeFactoryConfig,
    SearchCache,
)
from src.research.ssrf_guard import (
    BLOCKED_PRIVATE_HOST,
    BLOCKED_REDIRECT_TARGET,
    SSRFBlockedError,
    UNSUPPORTED_SCHEME,
    assert_safe_url,
    resolve_and_validate_host,
)


class _StubRole:
    """Minimal stand-in role that satisfies every method validator."""

    def build_intake_brief(self, *args, **kwargs): return None
    def opening_message(self, *args, **kwargs): return ""
    def accept_department_package(self, *args, **kwargs): return {}
    def accept_synthesis(self, *args, **kwargs): return {}
    def run(self, *args, **kwargs): return None


def _stub_runtime_agents() -> RuntimeAgents:
    cache = SearchCache()
    supervisor = _StubRole()
    synthesis = _StubRole()
    report_writer = _StubRole()
    departments = {name: _StubRole() for name in DOMAIN_DEPARTMENT_NAMES}
    specs: dict[str, RuntimeAgentSpec] = {
        "supervisor": RuntimeAgentSpec(
            role_name="supervisor",
            runtime_type="StubSupervisor",
            required_methods=SUPERVISOR_REQUIRED_METHODS,
        ),
        "synthesis": RuntimeAgentSpec(
            role_name="synthesis",
            runtime_type="StubSynthesis",
            required_methods=SYNTHESIS_REQUIRED_METHODS,
        ),
        "report_writer": RuntimeAgentSpec(
            role_name="report_writer",
            runtime_type="StubReportWriter",
            required_methods=REPORT_WRITER_REQUIRED_METHODS,
        ),
    }
    for dept in DOMAIN_DEPARTMENT_NAMES:
        specs[dept] = RuntimeAgentSpec(
            role_name=dept,
            runtime_type="StubDepartment",
            required_methods=DEPARTMENT_REQUIRED_METHODS,
            department_name=dept,
        )
    return RuntimeAgents(
        supervisor=supervisor,
        departments=departments,
        synthesis=synthesis,
        report_writer=report_writer,
        search_cache=cache,
        config=RuntimeFactoryConfig(),
        specs=specs,
    )


def _stub_create_runtime_agents() -> RuntimeAgents:
    return _stub_runtime_agents()


# ── IntakeRequest ─────────────────────────────────────────────────────────────

def test_intake_request_rejects_blank_required_fields() -> None:
    with pytest.raises(IntakeValidationError) as exc:
        IntakeRequest(company_name="  ", web_domain="example.com")
    assert exc.value.field == "company_name"
    assert exc.value.code == IntakeErrorCode.COMPANY_NAME_REQUIRED

    with pytest.raises(IntakeValidationError) as exc:
        IntakeRequest(company_name="Example GmbH", web_domain="  ")
    assert exc.value.field == "web_domain"
    assert exc.value.code == IntakeErrorCode.WEB_DOMAIN_REQUIRED


def test_intake_request_trims_values() -> None:
    intake = IntakeRequest(company_name="  Example   GmbH  ", web_domain="  www.example.com  ")

    assert intake.company_name == "Example GmbH"
    assert intake.web_domain == "www.example.com"


def test_intake_request_rejects_placeholder_company_names() -> None:
    for placeholder in ("n/v", "n/a", "unknown", "none", "null", "tbd"):
        with pytest.raises(IntakeValidationError) as exc:
            IntakeRequest(company_name=placeholder, web_domain="example.com")
        assert exc.value.field == "company_name"
        assert exc.value.code == IntakeErrorCode.COMPANY_NAME_PLACEHOLDER


def test_intake_request_rejects_oversized_company_name() -> None:
    with pytest.raises(IntakeValidationError) as exc:
        IntakeRequest(company_name="A" * 201, web_domain="example.com")
    assert exc.value.field == "company_name"
    assert exc.value.code == IntakeErrorCode.COMPANY_NAME_TOO_LONG


def test_intake_request_rejects_oversized_web_domain() -> None:
    with pytest.raises(IntakeValidationError) as exc:
        IntakeRequest(company_name="Example GmbH", web_domain="a" * 2049)
    assert exc.value.field == "web_domain"
    assert exc.value.code == IntakeErrorCode.WEB_DOMAIN_TOO_LONG


def test_run_pipeline_propagates_company_name_error_code() -> None:
    """P1: company_name failures must yield a field-specific error_code."""
    from src.pipeline_runner import run_pipeline

    result = run_pipeline(company_name="n/v", web_domain="https://www.example.com")
    assert result["status"] == "failed"
    assert result["error_code"] == IntakeErrorCode.COMPANY_NAME_PLACEHOLDER
    assert result["error_detail"]["field"] == "company_name"
    iv = result["run_context"]["resolution_state"]["intake_validation"]
    assert iv["error_code"] == IntakeErrorCode.COMPANY_NAME_PLACEHOLDER
    assert iv["field"] == "company_name"


# ── normalize_domain (backward-compat wrapper) ────────────────────────────────

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


# ── NormalizedDomainResult contract ──────────────────────────────────────────

def test_normalize_domain_result_returns_dataclass() -> None:
    result = normalize_domain_result("zf.com")
    assert isinstance(result, NormalizedDomainResult)


def test_normalize_domain_result_valid_standard_domains() -> None:
    cases = [
        ("zf.com",                              "zf.com"),
        ("ZF.COM",                              "zf.com"),
        ("https://www.zf.com/",                 "zf.com"),
        ("https://www.zf.com/products?a=b#top", "zf.com"),
        ("www.siemens.com",                     "siemens.com"),
        ("HTTP://example.org",                  "example.org"),
    ]
    for domain_input, expected in cases:
        r = normalize_domain_result(domain_input)
        assert r.is_valid, f"{domain_input!r} expected valid, got {r.rejection_reason}"
        assert r.canonical_domain == expected, f"{domain_input!r} → {r.canonical_domain!r}"
        assert r.canonical_url == f"https://{expected}"
        assert r.scheme == "https"


def test_normalize_domain_result_normalization_steps_audit() -> None:
    r = normalize_domain_result("www.zf.com")
    assert "scheme_added:https" in r.normalization_steps
    assert "www_stripped" in r.normalization_steps
    assert "canonical:https" in r.normalization_steps

    r2 = normalize_domain_result("https://zf.com")
    assert "scheme_added:https" not in r2.normalization_steps
    assert "www_stripped" not in r2.normalization_steps


# ── Empty and placeholder rejection ──────────────────────────────────────────

def test_normalize_domain_result_rejects_empty_input() -> None:
    for empty in ("", "   "):
        r = normalize_domain_result(empty)
        assert not r.is_valid
        assert r.rejection_code == IntakeErrorCode.EMPTY_INPUT
        assert r.canonical_domain == ""


def test_normalize_domain_result_rejects_placeholder_values() -> None:
    placeholders = ["n/v", "n/a", "unknown", "none", "null", "test", "example", "tbd", "N/A"]
    for ph in placeholders:
        r = normalize_domain_result(ph)
        assert not r.is_valid, f"Expected {ph!r} to be rejected"
        assert r.rejection_code == IntakeErrorCode.PLACEHOLDER_VALUE, f"Wrong code for {ph!r}"


# ── Private / loopback / reserved host rejection ──────────────────────────────

@pytest.mark.security
def test_normalize_domain_result_blocks_loopback_and_private_ipv4() -> None:
    private_cases = [
        "localhost",
        "127.0.0.1",
        "10.0.0.1",
        "192.168.1.1",
        "172.16.0.1",
        "169.254.169.254",  # link-local / cloud metadata
    ]
    for host in private_cases:
        r = normalize_domain_result(host)
        assert not r.is_valid, f"Expected {host!r} blocked, got valid"
        assert r.rejection_code == IntakeErrorCode.BLOCKED_PRIVATE_HOST, \
            f"Wrong code for {host!r}: {r.rejection_code}"


@pytest.mark.security
def test_normalize_domain_result_blocks_ipv6_loopback_and_private() -> None:
    ipv6_cases = ["::1", "fd00::1"]
    for host in ipv6_cases:
        r = normalize_domain_result(host)
        assert not r.is_valid, f"Expected {host!r} blocked"
        assert r.rejection_code == IntakeErrorCode.BLOCKED_PRIVATE_HOST, \
            f"Wrong code for {host!r}: {r.rejection_code}"


def test_normalize_domain_result_accepts_public_ipv4() -> None:
    r = normalize_domain_result("8.8.8.8")
    assert r.is_valid
    assert r.canonical_domain == "8.8.8.8"


# ── Scheme validation ─────────────────────────────────────────────────────────

@pytest.mark.security
def test_normalize_domain_result_rejects_non_http_schemes() -> None:
    bad_schemes = ["ftp://zf.com", "file:///etc/passwd", "ssh://server.com", "mailto:a@b.com"]
    for url in bad_schemes:
        r = normalize_domain_result(url)
        assert not r.is_valid, f"Expected {url!r} rejected"
        assert r.rejection_code == IntakeErrorCode.UNSUPPORTED_SCHEME, f"Wrong code for {url!r}"


# ── Userinfo rejection ────────────────────────────────────────────────────────

@pytest.mark.security
def test_normalize_domain_result_rejects_userinfo() -> None:
    r = normalize_domain_result("https://user:pass@zf.com")
    assert not r.is_valid
    assert r.rejection_code == IntakeErrorCode.USERINFO_NOT_ALLOWED


# ── Invalid hostname syntax ───────────────────────────────────────────────────

@pytest.mark.security
def test_normalize_domain_result_rejects_invalid_hostname_syntax() -> None:
    invalid_cases = [
        ("foo..bar",   IntakeErrorCode.INVALID_HOSTNAME),  # empty label
        (".com",       IntakeErrorCode.INVALID_HOSTNAME),  # leading dot → empty label
        ("-bad.com",   IntakeErrorCode.INVALID_HOSTNAME),  # label starts with hyphen
        ("bad-.com",   IntakeErrorCode.INVALID_HOSTNAME),  # label ends with hyphen
    ]
    for domain_input, expected_code in invalid_cases:
        r = normalize_domain_result(domain_input)
        assert not r.is_valid, f"{domain_input!r} should be invalid"
        assert r.rejection_code == expected_code, \
            f"{domain_input!r}: expected {expected_code}, got {r.rejection_code}"


# ── IDN / Unicode ─────────────────────────────────────────────────────────────

def test_normalize_domain_result_normalizes_umlaut_domain() -> None:
    # "münchen.de" → "xn--mnchen-3ya.de" via IDNA
    r = normalize_domain_result("münchen.de")
    assert r.is_valid
    assert r.canonical_domain == "xn--mnchen-3ya.de"
    assert "idna_normalized" in r.normalization_steps


def test_normalize_domain_result_ascii_domain_unchanged_by_idna() -> None:
    r = normalize_domain_result("example.com")
    assert r.is_valid
    assert "idna_normalized" not in r.normalization_steps


# ── Public-suffix / registrable-domain (1.4) ──────────────────────────────────

def test_normalize_domain_result_populates_public_suffix_and_registrable_domain() -> None:
    r = normalize_domain_result("https://www.zf.com/products")
    assert r.is_valid
    assert r.public_suffix == "com"
    assert r.registrable_domain == "zf.com"


def test_normalize_domain_result_handles_multi_part_tld() -> None:
    r = normalize_domain_result("https://example.co.uk")
    assert r.is_valid
    assert r.public_suffix == "co.uk"
    assert r.registrable_domain == "example.co.uk"


def test_normalize_domain_result_rejects_single_label_without_tld() -> None:
    r = normalize_domain_result("intranet")
    assert not r.is_valid
    assert r.rejection_code == IntakeErrorCode.NO_REGISTRABLE_DOMAIN


def test_normalize_domain_result_ip_literal_skips_psl() -> None:
    # IP literals are still valid; they just have no registrable_domain.
    r = normalize_domain_result("8.8.8.8")
    assert r.is_valid
    assert r.canonical_domain == "8.8.8.8"
    assert r.registrable_domain == ""
    assert r.public_suffix == ""


# ── IDN / original hostname (1.5) ─────────────────────────────────────────────

def test_normalize_domain_result_records_original_hostname() -> None:
    r = normalize_domain_result("münchen.de")
    assert r.is_valid
    assert r.original_hostname == "münchen.de"  # pre-IDNA, lowercased
    assert r.canonical_domain == "xn--mnchen-3ya.de"  # post-IDNA


# ── URL-component audit steps (1.4) ───────────────────────────────────────────

def test_normalize_domain_result_audits_path_query_fragment() -> None:
    """1.4: path/query/fragment are dropped, but each appears in normalization_steps."""
    r = normalize_domain_result("https://www.zf.com/products?ref=ad#hero")
    assert r.is_valid
    assert "path_dropped" in r.normalization_steps
    assert "query_dropped" in r.normalization_steps
    assert "fragment_dropped" in r.normalization_steps


def test_normalize_domain_result_audits_non_standard_port() -> None:
    """1.4: non-standard ports show up explicitly in normalization_steps."""
    r = normalize_domain_result("https://zf.com:8443/")
    assert r.is_valid
    assert any(s.startswith("port_ignored:") for s in r.normalization_steps)


def test_normalize_domain_result_no_port_step_for_standard_ports() -> None:
    """Standard ports (80, 443) do not pollute the audit trail."""
    r = normalize_domain_result("https://zf.com:443/")
    assert r.is_valid
    assert not any(s.startswith("port_ignored:") for s in r.normalization_steps)


# ── Unicode / homograph risk flags (1.5) ──────────────────────────────────────

@pytest.mark.security
def test_normalize_domain_result_flags_mixed_script_homograph() -> None:
    """Cyrillic 'е' (U+0435) mixed with Latin letters → mixed_script flag."""
    # 'googlе.com' — second 'е' is Cyrillic, looks identical to Latin 'e'
    r = normalize_domain_result("googlе.com")
    assert r.is_valid  # still passes validation; we surface a risk flag
    assert any(s.startswith("mixed_script:") for s in r.unicode_risk_flags)
    assert "unicode_risk_flagged" in r.normalization_steps


def test_normalize_domain_result_ascii_domain_has_no_risk_flags() -> None:
    r = normalize_domain_result("zf.com")
    assert r.unicode_risk_flags == ()


# ── Intake-time DNS pre-flight (1.6) ──────────────────────────────────────────

@pytest.mark.security
def test_initialize_run_hard_blocks_dns_rebinding(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """1.6: a public hostname that resolves to a private IP must hard-fail intake."""
    from src import pipeline_runner

    def _fake_resolve(host: str):
        # Simulate "evil.example.com" → 192.168.1.1
        raise SSRFBlockedError(BLOCKED_PRIVATE_HOST, f"'{host}' resolves to private IP.")

    monkeypatch.setattr(pipeline_runner, "resolve_and_validate_host", _fake_resolve)
    monkeypatch.setattr(pipeline_runner, "create_runtime_agents", _stub_create_runtime_agents)

    with pytest.raises(IntakeValidationError) as exc_info:
        pipeline_runner._initialize_run(
            start_time=0.0,
            run_id="20260512T000000Z",
            run_dir=tmp_path,
            company_name="Example AG",
            web_domain="https://www.example.com",
        )
    assert exc_info.value.field == "web_domain"
    assert exc_info.value.code == IntakeErrorCode.BLOCKED_PRIVATE_HOST


@pytest.mark.security
def test_run_pipeline_preserves_dns_ssrf_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1.6/1.7: DNS-rebinding hits must carry blocked_private_host through to the run result."""
    from src import pipeline_runner

    def _fake_resolve(host: str):
        raise SSRFBlockedError(BLOCKED_PRIVATE_HOST, f"'{host}' resolves to 192.168.1.1.")

    monkeypatch.setattr(pipeline_runner, "resolve_and_validate_host", _fake_resolve)

    result = pipeline_runner.run_pipeline(
        company_name="Example AG",
        web_domain="https://www.example.com",
    )

    assert result["status"] == "failed"
    assert result["error_code"] == IntakeErrorCode.BLOCKED_PRIVATE_HOST
    assert result["error_detail"]["field"] == "web_domain"
    assert result["error_detail"]["rejection_code"] == IntakeErrorCode.BLOCKED_PRIVATE_HOST
    iv = result["run_context"]["resolution_state"]["intake_validation"]
    assert iv["error_code"] == IntakeErrorCode.BLOCKED_PRIVATE_HOST
    assert iv["status"] == "failed"


@pytest.mark.security
def test_run_pipeline_preserves_dns_resolution_failure_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DNS resolution failures get the dns_resolution_failed code, not blocked_private_host."""
    from src import pipeline_runner
    from src.research.ssrf_guard import DNS_RESOLUTION_FAILED

    def _fake_resolve(host: str):
        raise SSRFBlockedError(DNS_RESOLUTION_FAILED, f"DNS failed for '{host}'")

    monkeypatch.setattr(pipeline_runner, "resolve_and_validate_host", _fake_resolve)

    result = pipeline_runner.run_pipeline(
        company_name="Example AG",
        web_domain="https://www.unresolvable-test.com",
    )

    assert result["status"] == "failed"
    assert result["error_code"] == IntakeErrorCode.DNS_RESOLUTION_FAILED
    assert result["error_detail"]["rejection_code"] == IntakeErrorCode.DNS_RESOLUTION_FAILED


# ── IP-pinning (1.6 hardening) ────────────────────────────────────────────────

@pytest.mark.security
def test_build_guarded_opener_with_pinned_ip_routes_to_pinned_address() -> None:
    """1.6 hardening: build_guarded_opener(pinned_ip=...) installs pinned handlers."""
    from src.research.ssrf_guard import (
        _PinnedHTTPHandler,
        _PinnedHTTPSHandler,
        build_guarded_opener,
    )

    opener = build_guarded_opener(pinned_ip="1.2.3.4")
    handler_types = {type(h) for h in opener.handlers}
    assert _PinnedHTTPHandler in handler_types
    assert _PinnedHTTPSHandler in handler_types


@pytest.mark.security
def test_build_guarded_opener_without_pin_has_no_pinned_handlers() -> None:
    from src.research.ssrf_guard import (
        _PinnedHTTPHandler,
        _PinnedHTTPSHandler,
        build_guarded_opener,
    )

    opener = build_guarded_opener(pinned_ip=None)
    handler_types = {type(h) for h in opener.handlers}
    assert _PinnedHTTPHandler not in handler_types
    assert _PinnedHTTPSHandler not in handler_types


# ── SSRF guard (1.6) ──────────────────────────────────────────────────────────

@pytest.mark.security
def test_ssrf_guard_blocks_private_ip_literal() -> None:
    with pytest.raises(SSRFBlockedError) as exc_info:
        resolve_and_validate_host("127.0.0.1")
    assert exc_info.value.code == BLOCKED_PRIVATE_HOST


@pytest.mark.security
def test_ssrf_guard_blocks_ipv6_loopback_literal() -> None:
    with pytest.raises(SSRFBlockedError) as exc_info:
        resolve_and_validate_host("::1")
    assert exc_info.value.code == BLOCKED_PRIVATE_HOST


@pytest.mark.security
def test_ssrf_guard_blocks_hostname_resolving_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate "evil.example.com" → 192.168.1.1
    def _fake_getaddrinfo(host, port, *args, **kw):
        return [(2, 1, 0, "", ("192.168.1.1", 0))]

    monkeypatch.setattr("socket.getaddrinfo", _fake_getaddrinfo)

    with pytest.raises(SSRFBlockedError) as exc_info:
        resolve_and_validate_host("evil.example.com")
    assert exc_info.value.code == BLOCKED_PRIVATE_HOST


@pytest.mark.security
def test_ssrf_guard_rejects_dns_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket as _socket

    def _fake_getaddrinfo(*args, **kw):
        raise _socket.gaierror("name not resolved")

    monkeypatch.setattr("socket.getaddrinfo", _fake_getaddrinfo)

    with pytest.raises(SSRFBlockedError) as exc_info:
        resolve_and_validate_host("does-not-resolve.invalid")
    assert exc_info.value.code == "dns_resolution_failed"


@pytest.mark.security
def test_assert_safe_url_rejects_non_http_scheme() -> None:
    with pytest.raises(SSRFBlockedError) as exc_info:
        assert_safe_url("ftp://zf.com")
    assert exc_info.value.code == UNSUPPORTED_SCHEME


@pytest.mark.security
def test_fetch_website_snapshot_reports_ssrf_block(monkeypatch: pytest.MonkeyPatch) -> None:
    """Integration: fetch returns structured error when the SSRF guard blocks."""
    from src.research.fetch import fetch_website_snapshot as _fetch

    def _block(url, **kw):
        raise SSRFBlockedError(BLOCKED_PRIVATE_HOST, "synthetic block for test")

    monkeypatch.setattr("src.research.fetch.assert_safe_url", _block)

    snapshot = _fetch("https://example.com")
    assert snapshot["reachable"] is False
    assert snapshot["error_type"] == BLOCKED_PRIVATE_HOST
    assert "synthetic block" in snapshot["error_message"]


@pytest.mark.security
def test_fetch_website_snapshot_reports_redirect_block(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect target that would resolve to a private IP is reported distinctly."""
    from src.research.fetch import fetch_website_snapshot as _fetch

    def _block_as_redirect(url, **kw):
        raise SSRFBlockedError(
            BLOCKED_REDIRECT_TARGET,
            "Redirect target rejected: synthetic test",
        )

    # First call (initial URL) passes; second call (simulated redirect) blocks.
    calls = {"n": 0}

    def _maybe_block(url, *, _redirect: bool = False) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            return  # initial URL ok
        _block_as_redirect(url)

    monkeypatch.setattr("src.research.fetch.assert_safe_url", _maybe_block)

    def _raise_blocked(self, req, timeout):
        raise SSRFBlockedError(
            BLOCKED_REDIRECT_TARGET,
            "Redirect target rejected: synthetic test",
        )

    monkeypatch.setattr("urllib.request.OpenerDirector.open", _raise_blocked)

    snapshot = _fetch("https://example.com")
    assert snapshot["reachable"] is False
    assert snapshot["error_type"] == BLOCKED_REDIRECT_TARGET


# ── Phase durations (0.5 budgets) ─────────────────────────────────────────────

def test_initialize_run_records_phase_durations(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """0.5: _initialize_run() must populate phase_durations_ms for the sub-phases."""
    from src import pipeline_runner

    monkeypatch.setattr(pipeline_runner, "create_runtime_agents", _stub_create_runtime_agents)

    state = pipeline_runner._initialize_run(
        start_time=0.0,
        run_id="20260512T000000Z",
        run_dir=tmp_path,
        company_name="Example AG",
        web_domain="https://www.example.com",
    )

    durations = state.run_context.resolution_state.get("phase_durations_ms", {})
    assert "intake_validation" in durations
    assert "agent_factory" in durations
    assert "memory_retrieval" in durations
    assert all(isinstance(v, int) and v >= 0 for v in durations.values())


def test_initialize_run_records_storage_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """3.x: initialized runs expose the selected storage boundary in run_context."""
    from src import pipeline_runner

    monkeypatch.setattr(pipeline_runner, "create_runtime_agents", _stub_create_runtime_agents)

    state = pipeline_runner._initialize_run(
        start_time=0.0,
        run_id="20260512T000000Z",
        run_dir=tmp_path,
        company_name="Example AG",
        web_domain="https://www.example.com",
    )

    storage = state.run_context.resolution_state["storage"]
    assert storage["profile"] == "local_dev"
    assert storage["memory_backend"] == "file"
    assert storage["run_state_backend"] == "local_file_export"
    assert storage["long_term_memory_health"]["status"] == "ok"
    assert storage["run_state_health"]["status"] == "ok"


def test_run_pipeline_reports_storage_init_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """3.14: production storage misconfiguration fails before department execution."""
    from src import pipeline_runner
    from src.storage.contracts import RuntimeStorageConfig

    monkeypatch.setattr(pipeline_runner, "create_runtime_agents", _stub_create_runtime_agents)
    monkeypatch.setattr(
        pipeline_runner,
        "resolve_and_validate_host",
        lambda host: ("93.184.216.34",),
    )

    def _misconfigured_stores(*, runs_root, long_term_memory_path):
        from src.storage.runtime_stores import create_runtime_stores

        return create_runtime_stores(
            config=RuntimeStorageConfig(
                profile="production",
                run_state_backend="postgres",
                memory_backend="postgres_pgvector",
                object_storage_backend="cloudflare_r2",
                postgres_dsn_present=False,
                cloudflare_tunnel_required=True,
            ),
            runs_root=tmp_path / "runs",
            long_term_memory_path=tmp_path / "memory.json",
        )

    monkeypatch.setattr(pipeline_runner, "create_runtime_stores", _misconfigured_stores)

    result = pipeline_runner.run_pipeline(
        company_name="Example AG",
        web_domain="https://www.example.com",
    )

    assert result["status"] == "failed"
    assert result["failed_phase"] == "storage_init"
    assert result["error_code"] == "postgres_dsn_missing"
    storage = result["run_context"]["resolution_state"]["storage"]
    assert storage["status"] == "failed"
    assert storage["component"] == "long_term_memory"


def test_supervisor_brief_refreshes_role_retrieval_with_industry_hint(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """4.3/4.8: role retrieval is refreshed after the brief provides industry context."""
    from dataclasses import asdict

    from src import pipeline_runner
    from src.domain.intake import SupervisorBrief

    monkeypatch.setattr(pipeline_runner, "create_runtime_agents", _stub_create_runtime_agents)
    monkeypatch.setattr(pipeline_runner, "LONG_TERM_MEMORY_PATH", tmp_path / "memory.json")

    state = pipeline_runner._initialize_run(
        start_time=0.0,
        run_id="20260512T000000Z",
        run_dir=tmp_path,
        company_name="Example AG",
        web_domain="https://www.example.com",
    )
    state.memory_store.upsert_strategy({
        "name": "company-research-manufacturing",
        "role": "CompanyResearcher",
        "pattern_scope": "researcher_strategy",
        "industry_hint": "Manufacturing",
        "structural_queries": ["manufacturer inventory surplus signals"],
        "score": 1.0,
    })
    brief = SupervisorBrief(
        submitted_company_name="Example AG",
        submitted_web_domain="https://www.example.com",
        verified_company_name="Example",
        verified_legal_name="",
        name_confidence="medium",
        website_reachable=True,
        homepage_url="https://example.com",
        page_title="Example",
        meta_description="",
        raw_homepage_excerpt="",
        normalized_domain="example.com",
        industry_hint="Manufacturing",
    )

    def _build_intake_brief(*args, **kwargs):
        return brief, {
            "section": "supervisor_brief",
            "payload": asdict(brief),
            "status": "ready_for_department_routing",
        }

    state.agents.supervisor.build_intake_brief = _build_intake_brief

    pipeline_runner._build_supervisor_brief(state, on_message=None)

    memory_state = state.run_context.resolution_state["memory_retrieval"]
    assert memory_state["final_source"] in {"initial", "brief_context"}
    assert memory_state["brief_context"]["query_summary"]["industry_hint_present"] is True
    company_researcher = state.run_context.retrieved_role_strategies["CompanyResearcher"]
    assert company_researcher
    assert company_researcher[0]["retrieval_query_summary"]["industry_hint_present"] is True
    assert company_researcher[0]["pattern_scope"] == "researcher_strategy"
    assert "example.com" not in repr(memory_state["brief_context"]["query_summary"])


# ── intake_validation in resolution_state (1.7) ──────────────────────────────

def test_initialize_run_populates_intake_validation_on_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """1.7: resolution_state['intake_validation'] is populated with structured fields."""
    from src import pipeline_runner

    monkeypatch.setattr(pipeline_runner, "create_runtime_agents", _stub_create_runtime_agents)

    state = pipeline_runner._initialize_run(
        start_time=0.0,
        run_id="20260512T000000Z",
        run_dir=tmp_path,
        company_name="Example AG",
        web_domain="https://www.example.com",
    )

    iv = state.run_context.resolution_state["intake_validation"]
    assert iv["status"] == "ok"
    assert iv["error_code"] == ""
    assert iv["canonical_domain"] == "example.com"
    assert iv["registrable_domain"] == "example.com"
    assert iv["public_suffix"] == "com"
    assert isinstance(iv["normalization_steps"], list)
    assert "duration_ms" in iv


def test_run_pipeline_populates_intake_validation_on_failure(tmp_path) -> None:
    """1.7: failed runs return a structured intake_validation in run_context."""
    from src.pipeline_runner import run_pipeline

    result = run_pipeline(company_name="Example AG", web_domain="localhost")

    assert result["status"] == "failed"
    assert result["error_code"] == IntakeErrorCode.BLOCKED_PRIVATE_HOST
    iv = result["run_context"]["resolution_state"]["intake_validation"]
    assert iv["status"] == "failed"
    assert iv["error_code"] == IntakeErrorCode.BLOCKED_PRIVATE_HOST
    assert iv["field"] == "web_domain"
    assert iv["original_value"] == "localhost"


# ── Structured logging (1.10) ─────────────────────────────────────────────────

def test_intake_logging_emits_structured_event() -> None:
    """1.10: log_intake_event emits a structured payload to the named logger."""
    import logging as _logging

    from src.orchestration.intake_logging import log_intake_event

    captured: list[_logging.LogRecord] = []

    class _CollectingHandler(_logging.Handler):
        def emit(self, record: _logging.LogRecord) -> None:
            captured.append(record)

    handler = _CollectingHandler(level=_logging.DEBUG)
    logger = _logging.getLogger("liquisto.intake")
    logger.addHandler(handler)
    try:
        log_intake_event(
            run_id="20260512T000000Z",
            status="ok",
            duration_ms=12,
            canonical_domain="zf.com",
            registrable_domain="zf.com",
        )
    finally:
        logger.removeHandler(handler)

    assert captured, "expected at least one liquisto.intake record"
    payload = getattr(captured[-1], "payload", None)
    assert payload is not None
    assert payload["schema_version"] == "1"
    assert payload["component"] == "intake"
    assert payload["phase"] == "intake_validation"
    assert payload["run_id"] == "20260512T000000Z"
    assert payload["status"] == "ok"
    assert payload["canonical_domain"] == "zf.com"
    assert payload["duration_ms"] == 12


def test_intake_logging_failure_includes_error_code() -> None:
    """1.10: failure path emits status=failed with rejection_reason but no canonical_domain."""
    import logging as _logging

    from src.orchestration.intake_logging import log_intake_event

    captured: list[_logging.LogRecord] = []

    class _CollectingHandler(_logging.Handler):
        def emit(self, record: _logging.LogRecord) -> None:
            captured.append(record)

    handler = _CollectingHandler(level=_logging.DEBUG)
    logger = _logging.getLogger("liquisto.intake")
    logger.addHandler(handler)
    try:
        log_intake_event(
            run_id="20260512T000000Z",
            status="failed",
            error_code=IntakeErrorCode.BLOCKED_PRIVATE_HOST,
            rejection_reason="Host 'localhost' is a private, loopback, or reserved address.",
        )
    finally:
        logger.removeHandler(handler)

    assert captured
    payload = captured[-1].payload  # type: ignore[attr-defined]
    assert payload["status"] == "failed"
    assert payload["error_code"] == IntakeErrorCode.BLOCKED_PRIVATE_HOST
    assert "rejection_reason" in payload
    assert "canonical_domain" not in payload


# ── Canonical consistency (1.8) ───────────────────────────────────────────────

def test_normalize_domain_result_same_canonical_for_domain_variants() -> None:
    variants = [
        "zf.com",
        "ZF.COM",
        "https://zf.com",
        "https://www.zf.com/",
        "http://www.zf.com/path?a=b#x",
    ]
    canonical = {normalize_domain_result(v).canonical_domain for v in variants}
    assert canonical == {"zf.com"}, f"Expected single canonical, got: {canonical}"


# ── Existing agent / extract tests (regression) ───────────────────────────────

def test_legal_suffix_detection_uses_token_boundary() -> None:
    false_positive = infer_company_identity("Frag", title="", description="", text="")
    actual_legal_name = infer_company_identity("Acme AG", title="", description="", text="")

    assert false_positive["verified_legal_name"] == ""
    assert actual_legal_name["verified_legal_name"] == ""
    assert actual_legal_name["brand_name"] == "Acme AG"
    assert actual_legal_name["name_confidence"] == "high"


def test_fetch_website_snapshot_extracts_meta_description_with_flexible_attrs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    # Bypass DNS-level SSRF guard (no real network) and the urllib opener.
    monkeypatch.setattr("src.research.fetch.assert_safe_url", lambda url, **kw: None)
    monkeypatch.setattr(
        "urllib.request.OpenerDirector.open",
        lambda self, req, timeout: _Response(),
    )

    snapshot = fetch_website_snapshot("https://example.com")

    assert snapshot["reachable"] is True
    assert snapshot["title"] == "Example"
    assert snapshot["meta_description"] == "Muller Maschinen"
    assert snapshot["visible_text"] == "Example Muller baut Anlagen."
    assert snapshot["error_type"] == ""
    assert snapshot["error_message"] == ""


def test_fetch_website_snapshot_returns_structured_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_timeout(self, request: object, timeout: int) -> object:
        raise TimeoutError("network timed out")

    monkeypatch.setattr("src.research.fetch.assert_safe_url", lambda url, **kw: None)
    monkeypatch.setattr("urllib.request.OpenerDirector.open", _raise_timeout)

    snapshot = fetch_website_snapshot("https://example.com")

    assert snapshot["reachable"] is False
    assert snapshot["error_type"] == "fetch_timeout"
    assert snapshot["error_message"] == "network timed out"


def test_fetch_website_snapshot_flags_js_limited_content(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Headers:
        def get(self, name: str, default: str = "") -> str:
            if name.lower() == "content-type":
                return "text/html; charset=utf-8"
            return default

        def get_content_charset(self) -> str:
            return "utf-8"

    class _Response:
        url = "https://example.com"
        status = 200
        headers = _Headers()

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return (
                b'<html><head><title>Example</title></head>'
                b'<body><div id="root"></div><script src="/app.js"></script></body></html>'
            )

    monkeypatch.setattr("src.research.fetch.assert_safe_url", lambda url, **kw: None)
    monkeypatch.setattr("src.research.fetch.resolve_and_validate_host", lambda host: ("93.184.216.34",))
    monkeypatch.setattr("urllib.request.OpenerDirector.open", lambda self, req, timeout: _Response())

    snapshot = fetch_website_snapshot("https://example.com")

    assert snapshot["reachable"] is True
    assert snapshot["js_content_detected"] is True
    assert snapshot["extraction_quality"] == "js_limited"
    assert snapshot["content_hash"]


def test_build_company_research_uses_normalized_domain_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.research.contracts import WebsiteSnapshot
    from src.research.tools import build_company_research

    contract = NormalizedDomainResult(
        original_input="https://www.example.com/path",
        canonical_domain="example.com",
        canonical_url="https://example.com",
        hostname="example.com",
        scheme="https",
        is_valid=True,
    )

    def _fail_renormalize(domain: str):
        raise AssertionError("build_company_research must not re-normalize typed contracts")

    monkeypatch.setattr("src.research.tools.normalize_domain_result", _fail_renormalize)
    monkeypatch.setattr(
        "src.research.tools.fetch_website_snapshot",
        lambda url, **kw: WebsiteSnapshot(
            requested_url=url,
            final_url=url,
            reachable=True,
            title="Example AG",
            meta_description="Industrial automation",
            visible_text="Example AG manufactures automation systems.",
            extraction_quality="ok",
        ),
    )

    result = build_company_research(contract, "Example AG")

    assert result.normalized_domain == "example.com"
    assert result.homepage_url == "https://example.com"
    assert result.snapshot.requested_url == "https://example.com"
    assert result.identity.verified_legal_name == ""
    assert result.industry.confidence in {"high", "low"}
    assert result.schema_version


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

    intake = IntakeRequest(company_name=" Example AG ", web_domain=" https://www.example.com/about ")
    supervisor = SupervisorAgent.__new__(SupervisorAgent)
    brief, message = supervisor.build_intake_brief(intake, normalized_domain="example.com")

    assert brief.company_name == "Example AG"
    assert brief.normalized_domain == "example.com"
    assert brief.website_reachable is False
    assert brief.fetch_error_type == "TimeoutError"
    assert brief.fetch_error_message == "network timed out"
    assert message["section"] == "supervisor_brief"
    # Punkt 5: unreachable homepage → blocked_for_department_routing
    # (BriefingReadiness.BLOCKED_WEBSITE_UNREACHABLE), no longer a blanket "ready".
    assert message["status"] == "blocked_for_department_routing"
    assert message["briefing_readiness"] == "blocked_website_unreachable"
    assert "homepage_unreachable" in message["routing_gaps"]
    assert message["identity_confidence"] == "unverified"
