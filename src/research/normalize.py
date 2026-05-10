"""Normalization helpers."""
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


def _is_blocked_host(hostname: str) -> bool:
    """Return True for loopback, private, link-local, and reserved IP ranges."""
    candidate = hostname.strip("[]")  # remove IPv6 brackets: [::1] → ::1
    if ":" in candidate:
        # Try parsing as bare IPv6 address first (e.g. ::1, fd00::1)
        try:
            return not ipaddress.ip_address(candidate).is_global
        except ValueError:
            # Not valid IPv6 — must be hostname:port, strip the port
            candidate = candidate.rsplit(":", 1)[0]
    if candidate.lower() == "localhost":
        return True
    try:
        return not ipaddress.ip_address(candidate).is_global
    except ValueError:
        return False  # regular hostname — allow


def normalize_domain(domain: str) -> str:
    raw = (domain or "").strip().lower()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    hostname = parsed.netloc or parsed.path
    hostname = hostname.removeprefix("www.")
    hostname = hostname.strip("/")
    if _is_blocked_host(hostname):
        return ""
    return hostname


def homepage_url(domain: str) -> str:
    normalized = normalize_domain(domain)
    return f"https://{normalized}" if normalized else ""

