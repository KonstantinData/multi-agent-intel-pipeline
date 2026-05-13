"""DNS-level SSRF guard + IP-pinned fetch used by `fetch_website_snapshot`.

The intake-phase `normalize_domain_result()` already blocks private IP *literals*.
This module adds protection against the cases the string check cannot cover:

1. **Public hostnames that resolve to private IPs.** Someone registers
   `evil.example.com` → `192.168.1.1`; string-level checks pass, but the actual
   socket would talk to a private host. `resolve_and_validate_host()`
   pre-flights `getaddrinfo()` and rejects if any resolved IP is non-global.
2. **Redirects to internal hosts.** A public site responds with `Location:
   http://169.254.169.254/...`. The `_SSRFGuardRedirectHandler` re-validates
   each redirect URL before urllib follows it.
3. **DNS rebinding between validation and connect.** Without IP pinning, an
   attacker can return a public IP to `getaddrinfo()` for the SSRF check, then
   flip the DNS record to a private IP before urllib opens the actual socket.
   `_PinnedHTTPSConnection` / `_PinnedHTTPConnection` close this window by
   connecting to a pre-validated IP while preserving the original hostname for
   SNI and the `Host:` header.
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import urllib.request
from urllib.parse import urlparse


class SSRFBlockedError(ValueError):
    """Raised when a URL or hostname is rejected by the SSRF guard."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


# Public error codes returned via `SSRFBlockedError.code`.
DNS_RESOLUTION_FAILED = "dns_resolution_failed"
BLOCKED_PRIVATE_HOST = "blocked_private_host"
BLOCKED_REDIRECT_TARGET = "blocked_redirect_target"
UNSUPPORTED_SCHEME = "unsupported_scheme"
INVALID_URL = "invalid_url"

MAX_REDIRECTS = 5


def resolve_and_validate_host(hostname: str) -> tuple[str, ...]:
    """Resolve hostname via DNS and reject if any IP is private / reserved.

    Returns the sorted tuple of resolved IP strings on success; raises
    SSRFBlockedError otherwise. IP literals are validated directly without DNS.
    """
    hostname = (hostname or "").strip().strip("[]").lower()
    if not hostname:
        raise SSRFBlockedError(INVALID_URL, "Empty hostname.")

    # If the hostname is already an IP literal, validate it directly.
    try:
        literal = ipaddress.ip_address(hostname)
        if not literal.is_global:
            raise SSRFBlockedError(
                BLOCKED_PRIVATE_HOST,
                f"Host '{hostname}' is a private or reserved IP.",
            )
        return (hostname,)
    except ValueError:
        pass  # not an IP literal — resolve via DNS

    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFBlockedError(
            DNS_RESOLUTION_FAILED,
            f"DNS resolution failed for '{hostname}': {exc}",
        ) from exc

    seen: set[str] = set()
    ips: list[str] = []
    for info in infos:
        sockaddr = info[4]
        ip_str = str(sockaddr[0]) if sockaddr else ""
        if not ip_str or ip_str in seen:
            continue
        seen.add(ip_str)
        ips.append(ip_str)

    if not ips:
        raise SSRFBlockedError(
            DNS_RESOLUTION_FAILED,
            f"DNS returned no IPs for '{hostname}'.",
        )

    for ip_str in ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if not ip.is_global:
            raise SSRFBlockedError(
                BLOCKED_PRIVATE_HOST,
                f"Host '{hostname}' resolves to private/reserved IP '{ip_str}'.",
            )

    return tuple(sorted(ips))


def assert_safe_url(url: str, *, _redirect: bool = False) -> None:
    """Validate scheme + host + DNS resolution for a URL.

    When `_redirect=True`, a failure raises with `BLOCKED_REDIRECT_TARGET`
    instead of the underlying code so the caller can distinguish initial-target
    rejections from redirect-target rejections.
    """
    try:
        parsed = urlparse((url or "").strip())
    except Exception as exc:
        raise SSRFBlockedError(INVALID_URL, f"Could not parse URL: {exc}") from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise SSRFBlockedError(
            UNSUPPORTED_SCHEME,
            f"Unsupported URL scheme '{scheme}'. Only http/https allowed.",
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise SSRFBlockedError(INVALID_URL, "URL has no hostname.")

    try:
        resolve_and_validate_host(hostname)
    except SSRFBlockedError as exc:
        if _redirect:
            raise SSRFBlockedError(
                BLOCKED_REDIRECT_TARGET,
                f"Redirect target rejected: {exc.reason}",
            ) from exc
        raise


class _SSRFGuardRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-runs `assert_safe_url()` on every redirect and caps the chain length."""

    max_redirections = MAX_REDIRECTS

    def redirect_request(  # noqa: D401, ANN001 — match stdlib signature
        self, req, fp, code, msg, headers, newurl,
    ):
        assert_safe_url(newurl, _redirect=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPSConnection that connects to a pre-validated IP but keeps SNI/Host.

    Closes the DNS-rebinding window: even if DNS flips between the SSRF check
    and the socket open, we connect to the IP we already validated.
    """

    def __init__(self, host: str, *, pinned_ip: str, **kwargs) -> None:
        super().__init__(host, **kwargs)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        sock = socket.create_connection(
            (self._pinned_ip, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
        # `server_hostname` preserves SNI so cert validation still matches `host`.
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """Plain-HTTP equivalent of `_PinnedHTTPSConnection`."""

    def __init__(self, host: str, *, pinned_ip: str, **kwargs) -> None:
        super().__init__(host, **kwargs)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._pinned_ip, self.port),
            self.timeout,
            self.source_address,
        )


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, pinned_ip: str, *, context: ssl.SSLContext | None = None) -> None:
        super().__init__(context=context)
        self._pinned_ip = pinned_ip

    def https_open(self, req):  # noqa: D401, ANN001
        return self.do_open(self._build_conn, req, context=self._context)

    def _build_conn(self, host, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, context=None, **kw):  # noqa: ANN001
        return _PinnedHTTPSConnection(
            host,
            pinned_ip=self._pinned_ip,
            timeout=timeout,
            context=context,
            **kw,
        )


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, pinned_ip: str) -> None:
        super().__init__()
        self._pinned_ip = pinned_ip

    def http_open(self, req):  # noqa: D401, ANN001
        return self.do_open(self._build_conn, req)

    def _build_conn(self, host, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, **kw):  # noqa: ANN001
        return _PinnedHTTPConnection(
            host,
            pinned_ip=self._pinned_ip,
            timeout=timeout,
            **kw,
        )


def build_guarded_opener(pinned_ip: str | None = None) -> urllib.request.OpenerDirector:
    """Return a urllib opener that re-validates redirects.

    If `pinned_ip` is supplied, http/https connections route to that IP while
    preserving the URL hostname for SNI and the `Host:` header. This closes the
    DNS-rebinding window between `resolve_and_validate_host()` and `open()`.
    """
    handlers: list[urllib.request.BaseHandler] = [_SSRFGuardRedirectHandler()]
    if pinned_ip:
        handlers.append(_PinnedHTTPHandler(pinned_ip))
        handlers.append(_PinnedHTTPSHandler(pinned_ip))
    return urllib.request.build_opener(*handlers)


__all__ = [
    "BLOCKED_PRIVATE_HOST",
    "BLOCKED_REDIRECT_TARGET",
    "DNS_RESOLUTION_FAILED",
    "INVALID_URL",
    "MAX_REDIRECTS",
    "SSRFBlockedError",
    "UNSUPPORTED_SCHEME",
    "assert_safe_url",
    "build_guarded_opener",
    "resolve_and_validate_host",
]
