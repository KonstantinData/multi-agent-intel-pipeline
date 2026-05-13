"""Normalization helpers for intake domain validation."""
from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

import idna as idna2008  # IDNA 2008
import tldextract

# tldextract ships its own snapshot of the public suffix list; disable network
# fetch so the module is offline-deterministic and CI-safe.
_TLD_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


class IntakeErrorCode(StrEnum):
    # Generic / domain-level codes (used by normalize_domain_result + IntakeRequest)
    EMPTY_INPUT = "empty_input"
    PLACEHOLDER_VALUE = "placeholder_value"
    DOMAIN_TOO_LONG = "domain_too_long"
    CONTROL_CHARACTERS = "control_characters"
    UNSUPPORTED_SCHEME = "unsupported_scheme"
    USERINFO_NOT_ALLOWED = "userinfo_not_allowed"
    INVALID_HOSTNAME = "invalid_hostname"
    BLOCKED_PRIVATE_HOST = "blocked_private_host"
    NO_REGISTRABLE_DOMAIN = "no_registrable_domain"
    DNS_RESOLUTION_FAILED = "dns_resolution_failed"
    HOMOGRAPH_RISK = "homograph_risk"
    # Field-specific codes raised by IntakeRequest (see src/domain/intake.py)
    COMPANY_NAME_REQUIRED = "company_name_required"
    COMPANY_NAME_PLACEHOLDER = "company_name_placeholder"
    COMPANY_NAME_TOO_LONG = "company_name_too_long"
    WEB_DOMAIN_REQUIRED = "web_domain_required"
    WEB_DOMAIN_TOO_LONG = "web_domain_too_long"


_PLACEHOLDER_LOWER: frozenset[str] = frozenset({
    "n/v", "n/a", "unknown", "none", "null", "test", "example",
    "na", "n.a.", "tbd", "-", "--", ".",
})

_MAX_HOSTNAME_LENGTH = 253  # RFC 1035

# 1–63 chars per label; alphanumeric + hyphens; no leading/trailing hyphen
_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


@dataclass(frozen=True, slots=True)
class NormalizedDomainResult:
    """Typed, auditable result of a domain normalization attempt."""

    original_input: str
    canonical_domain: str
    canonical_url: str
    hostname: str
    scheme: str
    is_valid: bool
    rejection_code: str = ""
    rejection_reason: str = ""
    normalization_steps: tuple[str, ...] = ()
    # Public-suffix / registrable-domain (filled when is_valid and not bare IP)
    public_suffix: str = ""
    registrable_domain: str = ""
    # IDN audit trail: input before IDNA encoding (mirrors hostname when ASCII)
    original_hostname: str = ""
    # Unicode / homograph risk flags surfaced for the calling UI.
    # Empty tuple for plain ASCII inputs. Examples: "mixed_script:<label>".
    unicode_risk_flags: tuple[str, ...] = ()


def _is_blocked_host(hostname: str) -> bool:
    """Return True for loopback, private, link-local, and reserved IP ranges."""
    candidate = hostname.strip("[]")
    if ":" in candidate:
        try:
            return not ipaddress.ip_address(candidate).is_global
        except ValueError:
            candidate = candidate.rsplit(":", 1)[0]
    if candidate.lower() == "localhost":
        return True
    try:
        return not ipaddress.ip_address(candidate).is_global
    except ValueError:
        return False  # regular hostname — allow


def _is_ip_literal(hostname: str) -> bool:
    """True if hostname is an IPv4 or IPv6 literal (no brackets)."""
    try:
        ipaddress.ip_address(hostname.strip("[]"))
        return True
    except ValueError:
        return False


def _detect_unicode_risks(labels: list[str]) -> tuple[str, ...]:
    """Flag labels that mix ASCII Latin and non-ASCII characters.

    Mixed-script labels are the cheapest signal for homograph attacks
    (e.g. `googlе.com` where `е` is the Cyrillic small letter ie). We do
    not block such labels yet — we only surface a `mixed_script:<label>`
    warning so the UI / Supervisor can flag them for human review.
    Full Unicode-confusables analysis (per UTS-39) is Phase-2 work.
    """
    flags: list[str] = []
    for label in labels:
        has_ascii_letter = any(c.isascii() and c.isalpha() for c in label)
        has_non_ascii_letter = any((not c.isascii()) and c.isalpha() for c in label)
        if has_ascii_letter and has_non_ascii_letter:
            flags.append(f"mixed_script:{label}")
    return tuple(flags)


def _invalid_result(
    original: str,
    *,
    code: IntakeErrorCode,
    reason: str,
    hostname: str = "",
    scheme: str = "",
    steps: tuple[str, ...] = (),
) -> NormalizedDomainResult:
    return NormalizedDomainResult(
        original_input=original,
        canonical_domain="",
        canonical_url="",
        hostname=hostname,
        scheme=scheme,
        is_valid=False,
        rejection_code=code,
        rejection_reason=reason,
        normalization_steps=steps,
    )


def _idna_encode_label(label: str) -> str:
    """Encode a label per IDNA 2008 (preferred) with IDNA 2003 fallback.

    Raises UnicodeError if neither codec accepts the label. IDNA 2008 rejects
    a few characters that 2003 accepted (e.g. ß becomes 'xn--' rather than 'ss');
    the fallback preserves backward compatibility for legacy domains.
    """
    if label.isascii():
        # Pure ASCII labels skip the IDNA encode step entirely.
        return label
    try:
        return idna2008.encode(label, uts46=True).decode("ascii")
    except idna2008.IDNAError:
        # Some labels (e.g. underscored or transitional) only validate under IDNA 2003.
        return label.encode("idna").decode("ascii")


def normalize_domain_result(domain: str) -> NormalizedDomainResult:
    """Validate, normalize, and canonicalize a domain/URL input.

    Returns a NormalizedDomainResult with is_valid=True on success,
    or is_valid=False with rejection_code and rejection_reason on failure.
    Never raises.

    Normalization steps applied (in order):
    1.  Control-character rejection
    2.  Empty / placeholder rejection
    3.  Length guard (> 2048 chars)
    4.  Scheme addition (https) + bare-IPv6 bracketing for correct urlparse
    5.  URL parsing
    6.  Scheme validation (only http / https)
    7.  Userinfo rejection (user:pass@host)
    8.  Hostname extraction; netloc colon-check catches bare IPv6 with scheme
    9.  www. prefix removal
    10. SSRF guard (private / loopback / reserved hosts)
    11. Empty-label rejection (e.g. foo..bar, .com)
    12. IDN normalization via idna pkg (IDNA 2008, UTS-46) with IDNA 2003 fallback
    13. Hostname label syntax validation (RFC 952 / 1123)
    14. Max hostname length (RFC 1035, 253 chars)
    15. Public-suffix / registrable-domain check (tldextract, offline snapshot)
    """
    raw = str(domain or "").strip()
    steps: list[str] = []

    # 1. Control characters
    if any(unicodedata.category(c) in ("Cc", "Cf", "Cs") for c in raw):
        return _invalid_result(
            domain,
            code=IntakeErrorCode.CONTROL_CHARACTERS,
            reason="Input contains control or invisible Unicode characters.",
        )

    # 2. Empty / placeholder
    lower_raw = raw.lower()
    if not raw or lower_raw in _PLACEHOLDER_LOWER:
        code = IntakeErrorCode.EMPTY_INPUT if not raw else IntakeErrorCode.PLACEHOLDER_VALUE
        return _invalid_result(domain, code=code, reason=f"'{raw}' is not a valid domain input.")

    # 3. Max length guard
    if len(raw) > 2048:
        return _invalid_result(
            domain,
            code=IntakeErrorCode.DOMAIN_TOO_LONG,
            reason="Input exceeds 2048 characters.",
        )

    # 4. Add scheme and bracket bare IPv6 so urlparse handles it correctly.
    working = raw
    if "://" not in working:
        # Detect bare IPv6 first — otherwise urlparse misreads "fd00::1" as scheme "fd00".
        _is_bare_ipv6 = False
        try:
            addr = ipaddress.ip_address(working)
            if isinstance(addr, ipaddress.IPv6Address):
                working = f"[{working}]"
                _is_bare_ipv6 = True
        except ValueError:
            pass

        if not _is_bare_ipv6:
            # Catch scheme-like prefixes without // (e.g. "mailto:a@b.com", "ftp:abc")
            pre_scheme = urlparse(working).scheme
            if pre_scheme and pre_scheme not in ("http", "https"):
                return _invalid_result(
                    domain,
                    code=IntakeErrorCode.UNSUPPORTED_SCHEME,
                    reason=(
                        f"Unsupported URL scheme '{pre_scheme}'. "
                        "Only http and https are allowed."
                    ),
                    scheme=pre_scheme,
                )

        working = f"https://{working}"
        steps.append("scheme_added:https")

    # 5. Parse URL
    try:
        parsed = urlparse(working)
    except Exception:
        return _invalid_result(
            domain, code=IntakeErrorCode.INVALID_HOSTNAME, reason="Failed to parse URL."
        )

    # 6. Scheme: only http / https
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return _invalid_result(
            domain,
            code=IntakeErrorCode.UNSUPPORTED_SCHEME,
            reason=f"Unsupported URL scheme '{scheme}'. Only http and https are allowed.",
            scheme=scheme,
            steps=tuple(steps),
        )

    # 7. No userinfo (user:pass@host)
    if parsed.username or parsed.password:
        return _invalid_result(
            domain,
            code=IntakeErrorCode.USERINFO_NOT_ALLOWED,
            reason="URL must not contain credentials (user:pass@host).",
            scheme=scheme,
            steps=tuple(steps),
        )

    # Audit URL components that are intentionally dropped before normalization.
    # These do not change validity but make the normalization step list complete.
    if parsed.path and parsed.path not in ("", "/"):
        steps.append("path_dropped")
    if parsed.query:
        steps.append("query_dropped")
    if parsed.fragment:
        steps.append("fragment_dropped")
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port is not None and port not in (80, 443):
        steps.append(f"port_ignored:{port}")

    # 8. Extract hostname; handle bare IPv6 with scheme that urlparse misparses.
    hostname = (parsed.hostname or "").lower()
    netloc = parsed.netloc or ""
    if ":" in netloc and hostname:
        netloc_candidate = netloc.strip("[]").lower()
        try:
            ip = ipaddress.ip_address(netloc_candidate)
            if not ip.is_global:
                return _invalid_result(
                    domain,
                    code=IntakeErrorCode.BLOCKED_PRIVATE_HOST,
                    reason=f"'{netloc_candidate}' is a private or reserved IP address.",
                    steps=tuple(steps),
                )
            hostname = netloc_candidate  # global IPv6; continue (label check will reject it)
        except ValueError:
            pass  # not an IP — proceed with parsed.hostname

    if not hostname:
        return _invalid_result(
            domain,
            code=IntakeErrorCode.INVALID_HOSTNAME,
            reason="Could not extract a hostname from the input.",
            scheme=scheme,
            steps=tuple(steps),
        )

    # 9. Strip www. prefix
    if hostname.startswith("www."):
        hostname = hostname[4:]
        steps.append("www_stripped")

    original_hostname = hostname  # snapshot Unicode form before IDNA conversion

    # Unicode risk audit on the pre-IDNA form (post-IDNA labels are pure ASCII).
    risk_flags = _detect_unicode_risks(original_hostname.split("."))
    if risk_flags:
        steps.append("unicode_risk_flagged")

    # 10. SSRF guard — private / loopback / reserved hosts
    if _is_blocked_host(hostname):
        return _invalid_result(
            domain,
            code=IntakeErrorCode.BLOCKED_PRIVATE_HOST,
            reason=f"Host '{hostname}' is a private, loopback, or reserved address.",
            hostname=hostname,
            scheme=scheme,
            steps=tuple(steps),
        )

    # 11. Reject empty labels (e.g. "foo..bar", ".com")
    raw_labels = hostname.split(".")
    if not all(raw_labels):
        return _invalid_result(
            domain,
            code=IntakeErrorCode.INVALID_HOSTNAME,
            reason=f"Hostname '{hostname}' contains empty labels.",
            hostname=hostname,
            scheme=scheme,
            steps=tuple(steps),
        )

    # 12. IDN normalization via idna package (IDNA 2008 + UTS-46 mapping)
    try:
        ascii_labels = [_idna_encode_label(label) for label in raw_labels]
        hostname_ascii = ".".join(ascii_labels)
        if hostname_ascii != hostname:
            steps.append("idna_normalized")
        hostname = hostname_ascii
    except (UnicodeError, UnicodeDecodeError, idna2008.IDNAError):
        return _invalid_result(
            domain,
            code=IntakeErrorCode.INVALID_HOSTNAME,
            reason="Hostname contains characters invalid for IDNA encoding.",
            hostname=hostname,
            scheme=scheme,
            steps=tuple(steps),
        )

    # 13. Hostname label syntax (RFC 952 / 1123)
    for label in hostname.split("."):
        if not _LABEL_RE.match(label):
            return _invalid_result(
                domain,
                code=IntakeErrorCode.INVALID_HOSTNAME,
                reason=f"Invalid hostname label '{label}'.",
                hostname=hostname,
                scheme=scheme,
                steps=tuple(steps),
            )

    # 14. Max hostname length (RFC 1035)
    if len(hostname) > _MAX_HOSTNAME_LENGTH:
        return _invalid_result(
            domain,
            code=IntakeErrorCode.DOMAIN_TOO_LONG,
            reason=f"Hostname exceeds {_MAX_HOSTNAME_LENGTH} characters.",
            hostname=hostname,
            scheme=scheme,
            steps=tuple(steps),
        )

    # 15. Public-suffix / registrable-domain check via tldextract.
    #     IP literals are exempt (no PSL match makes sense for "8.8.8.8").
    public_suffix = ""
    registrable_domain = ""
    if not _is_ip_literal(hostname):
        extracted = _TLD_EXTRACTOR(hostname)
        public_suffix = extracted.suffix or ""
        if extracted.domain and extracted.suffix:
            registrable_domain = f"{extracted.domain}.{extracted.suffix}"
        if not registrable_domain:
            return _invalid_result(
                domain,
                code=IntakeErrorCode.NO_REGISTRABLE_DOMAIN,
                reason=(
                    f"Hostname '{hostname}' has no registrable domain "
                    "(missing public suffix or single-label input)."
                ),
                hostname=hostname,
                scheme=scheme,
                steps=tuple(steps),
            )
        steps.append("registrable_domain_resolved")

    steps.append("canonical:https")
    return NormalizedDomainResult(
        original_input=domain,
        canonical_domain=hostname,
        canonical_url=f"https://{hostname}",
        hostname=hostname,
        scheme="https",
        is_valid=True,
        normalization_steps=tuple(steps),
        public_suffix=public_suffix,
        registrable_domain=registrable_domain,
        original_hostname=original_hostname,
        unicode_risk_flags=risk_flags,
    )


def normalize_domain(domain: str) -> str:
    """Return the canonical hostname string, or '' for invalid inputs.

    Backward-compatible wrapper around normalize_domain_result().
    """
    return normalize_domain_result(domain).canonical_domain


def homepage_url(domain: str) -> str:
    """Build a canonical homepage URL from arbitrary user input.

    Runs the full validation pipeline; returns '' for invalid input. In-pipeline
    callers should use `RunContext.intake['canonical_url']` instead to avoid
    re-running normalization (see Section 0.0 of the Step-1 TODO).
    """
    result = normalize_domain_result(domain)
    return result.canonical_url if result.is_valid else ""
