"""Website fetching helpers."""
from __future__ import annotations

import html
import hashlib
import io
import re
import socket
import ssl
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from src.research.contracts import (
    DEFAULT_HOMEPAGE_FETCH_TIMEOUT_SECONDS,
    MAX_RAW_RESPONSE_BYTES,
    MAX_VISIBLE_TEXT_CHARS,
    WebsiteSnapshot,
)
from src.research.ssrf_guard import (
    SSRFBlockedError,
    assert_safe_url,
    build_guarded_opener,
    resolve_and_validate_host,
)

ALLOWED_CONTENT_TYPE_PREFIXES = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
)
BOT_PROTECTION_MARKERS = (
    "captcha",
    "cloudflare",
    "access denied",
    "bot protection",
    "unusual traffic",
)


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in {"script", "style", "noscript", "nav", "footer", "header", "form"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "nav", "footer", "header", "form"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        cleaned = " ".join(data.split())
        if cleaned:
            self._parts.append(cleaned)

    def get_text(self) -> str:
        return " ".join(self._parts)


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.description = ""
        self.og_title = ""
        self.og_description = ""
        self.h1: list[str] = []
        self.h2: list[str] = []
        self.about_url = ""
        self.imprint_url = ""
        self._heading_tag = ""

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        tag = tag.lower()
        normalized = {str(key).lower(): str(value or "") for key, value in attrs}
        if tag in {"h1", "h2"}:
            self._heading_tag = tag
            return
        if tag == "a":
            href = normalized.get("href", "")
            label = " ".join(normalized.get("aria-label", "").split()).lower()
            lowered = f"{href} {label}".lower()
            if not self.about_url and any(token in lowered for token in ("about", "ueber", "über")):
                self.about_url = href
            if not self.imprint_url and any(token in lowered for token in ("impressum", "imprint", "legal notice")):
                self.imprint_url = href
            return
        if tag != "meta":
            return
        meta_name = (
            normalized.get("name", "")
            or normalized.get("property", "")
            or normalized.get("http-equiv", "")
        ).lower()
        content = normalized.get("content", "")
        if not self.description and meta_name in {
            "description",
            "og:description",
            "twitter:description",
        }:
            self.description = html.unescape(" ".join(content.split()))
        if not self.og_title and meta_name in {"og:title", "twitter:title"}:
            self.og_title = html.unescape(" ".join(content.split()))
        if not self.og_description and meta_name in {"og:description", "twitter:description"}:
            self.og_description = html.unescape(" ".join(content.split()))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == self._heading_tag:
            self._heading_tag = ""

    def handle_data(self, data: str) -> None:
        if self._heading_tag not in {"h1", "h2"}:
            return
        text = html.unescape(" ".join(data.split()))
        if not text:
            return
        if self._heading_tag == "h1" and len(self.h1) < 5:
            self.h1.append(text[:180])
        if self._heading_tag == "h2" and len(self.h2) < 8:
            self.h2.append(text[:180])


def _snapshot(
    *,
    reachable: bool,
    url: str,
    title: str = "",
    meta_description: str = "",
    visible_text: str = "",
    content_type: str = "",
    is_pdf: bool = False,
    error_type: str = "",
    error_message: str = "",
    final_url: str = "",
    http_status: int = 0,
    content_length: int = 0,
    content_language: str = "",
    fetched_at: str = "",
    blocked_reason: str = "",
    redirect_chain: tuple[str, ...] = (),
) -> WebsiteSnapshot:
    """Build the snapshot dict consumed by `build_company_research()` and the
    Supervisor briefing fetch_audit (TODO 5.5).

    Extra fields are optional so legacy fixtures keep validating; they default
    to empty values when the caller does not supply them.
    """
    from datetime import UTC, datetime

    return WebsiteSnapshot(
        requested_url=url,
        final_url=final_url or url,
        reachable=reachable,
        http_status=int(http_status),
        content_type=content_type,
        title=title,
        meta_description=meta_description,
        visible_text=visible_text,
        language=content_language,
        redirect_chain=redirect_chain,
        fetch_error_type=error_type,
        fetch_error_message=error_message,
        retrieved_at=fetched_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        content_length=int(content_length),
        is_pdf=is_pdf,
        blocked_reason=blocked_reason,
        extraction_quality="unknown",
    )


def _content_language_from_html(html_text: str, headers_lang: str = "") -> str:
    """Cheap content-language detection (TODO 5.5).

    Priority: `<html lang="...">` → `<meta http-equiv="content-language">` →
    `Content-Language` header. Returns the first two characters lower-cased.
    """
    match = re.search(r'<html[^>]*\blang\s*=\s*["\']([a-zA-Z\-]+)', html_text, re.IGNORECASE)
    if match:
        return match.group(1).split("-", 1)[0].lower()[:2]
    match = re.search(
        r'<meta[^>]*http-equiv\s*=\s*["\']content-language["\'][^>]*content\s*=\s*["\']([a-zA-Z\-]+)',
        html_text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).split("-", 1)[0].lower()[:2]
    if headers_lang:
        return headers_lang.split(",", 1)[0].split("-", 1)[0].lower()[:2]
    return ""


def _meta_description(html_text: str) -> str:
    parser = _MetadataParser()
    parser.feed(html_text)
    return parser.description[:500]


def _metadata(html_text: str, base_url: str) -> _MetadataParser:
    parser = _MetadataParser()
    parser.feed(html_text)
    if parser.about_url:
        parser.about_url = urljoin(base_url, parser.about_url)
    if parser.imprint_url:
        parser.imprint_url = urljoin(base_url, parser.imprint_url)
    return parser


def _title(html_text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return html.unescape(" ".join(match.group(1).split()))


def _looks_like_pdf(url: str, content_type: str) -> bool:
    lowered_url = url.lower()
    lowered_type = content_type.lower()
    return lowered_url.endswith(".pdf") or "application/pdf" in lowered_type


def _allowed_content_type(content_type: str) -> bool:
    lowered = (content_type or "").split(";", 1)[0].strip().lower()
    return not lowered or any(lowered.startswith(prefix) for prefix in ALLOWED_CONTENT_TYPE_PREFIXES)


def _charset_from_content_type(content_type: str) -> str:
    match = re.search(r"charset=([^\s;]+)", content_type or "", re.IGNORECASE)
    return match.group(1).strip("\"'") if match else "utf-8"


def _decode_html(raw_bytes: bytes, content_type: str) -> str:
    charset = _charset_from_content_type(content_type)
    try:
        return raw_bytes.decode(charset, errors="ignore")
    except LookupError:
        return raw_bytes.decode("utf-8", errors="ignore")


def _extract_pdf_text(raw_bytes: bytes) -> tuple[str, str]:
    try:
        from pypdf import PdfReader
    except Exception:
        return "", ""


def _classify_error(exc: Exception) -> tuple[str, str]:
    text = str(exc)
    if isinstance(exc, TimeoutError) or isinstance(exc, socket.timeout):
        return "fetch_timeout", text[:300]
    if isinstance(exc, ssl.SSLError):
        return "tls_failed", text[:300]
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 429:
            return "fetch_rate_limited", text[:300]
        if exc.code in {401, 403}:
            return "fetch_access_denied", text[:300]
    return type(exc).__name__, text[:300]


def _detect_js_content(html_text: str, visible_text: str) -> bool:
    lowered = html_text[:20000].lower()
    has_app_marker = any(
        marker in lowered
        for marker in ("id=\"root\"", "id=\"app\"", "__next", "data-reactroot", "ng-version")
    )
    return has_app_marker and len(visible_text.split()) < 25


def _extraction_quality(visible_text: str, js_content_detected: bool) -> str:
    words = visible_text.split()
    if js_content_detected:
        return "js_limited"
    if len(words) < 8:
        return "empty"
    if len(words) < 35:
        return "weak"
    return "ok"

    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
        meta_title = ""
        if getattr(reader, "metadata", None):
            meta_title = str(getattr(reader.metadata, "title", "") or "").strip()
        text_parts: list[str] = []
        for page in reader.pages[:8]:
            text = page.extract_text() or ""
            text = " ".join(text.split())
            if text:
                text_parts.append(text)
        return " ".join(text_parts)[:12000], meta_title[:300]
    except Exception:
        return "", ""


def fetch_website_snapshot(
    url: str,
    *,
    timeout: int = DEFAULT_HOMEPAGE_FETCH_TIMEOUT_SECONDS,
    accept_language: str = "de,en;q=0.8",
) -> WebsiteSnapshot:
    cleaned_url = str(url or "").strip()
    if not cleaned_url or "://" not in cleaned_url:
        return _snapshot(
            reachable=False,
            url=cleaned_url,
            error_type="invalid_url",
            error_message="URL must include a scheme.",
        )

    # DNS-level SSRF guard: rejects URLs whose hostname resolves to private/
    # reserved IPs. Initial check + per-redirect re-check via guarded opener,
    # and the opener pins connections to the validated IP (IP pinning closes
    # the DNS-rebinding window between resolution and connect).
    try:
        assert_safe_url(cleaned_url)
        parsed = urlparse(cleaned_url)
        hostname = (parsed.hostname or "").lower()
        resolved_ips = resolve_and_validate_host(hostname) if hostname else ()
    except SSRFBlockedError as exc:
        return _snapshot(
            reachable=False,
            url=cleaned_url,
            error_type=exc.code,
            error_message=exc.reason[:300],
            blocked_reason=exc.code,
        )

    # Prefer the first resolved IP (sorted, deterministic). On redirect to a
    # different host the opener's redirect handler re-validates; if we encounter
    # a cross-host redirect we cannot keep IP-pinning, but the redirect handler
    # already enforces DNS-level SSRF on the new target.
    pinned_ip = resolved_ips[0] if resolved_ips else None

    final_url = cleaned_url
    http_status = 0
    headers_lang = ""
    try:
        request = urllib.request.Request(
            cleaned_url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; LiquistoBot/1.0)",
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
                "Accept-Language": accept_language,
            },
        )
        opener = build_guarded_opener(pinned_ip=pinned_ip)
        with opener.open(request, timeout=timeout) as response:  # nosec B310 - SSRF-guarded + IP-pinned opener
            # Capture audit fields (TODO 5.5): final URL after redirects,
            # HTTP status, and Content-Language header.
            final_url = getattr(response, "url", cleaned_url) or cleaned_url
            http_status = int(getattr(response, "status", 0) or 0)
            headers_lang = str(response.headers.get("Content-Language", "") or "")
            content_type = str(response.headers.get("Content-Type", "") or "")
            charset = getattr(response.headers, "get_content_charset", lambda: None)()
            if charset and "charset=" not in content_type.lower():
                content_type = f"{content_type}; charset={charset}" if content_type else f"charset={charset}"
            raw_bytes = response.read(MAX_RAW_RESPONSE_BYTES)
    except SSRFBlockedError as exc:
        return _snapshot(
            reachable=False,
            url=cleaned_url,
            error_type=exc.code,
            error_message=exc.reason[:300],
            blocked_reason=exc.code,
        )
    except Exception as exc:
        error_type, error_message = _classify_error(exc)
        return _snapshot(
            reachable=False,
            url=cleaned_url,
            error_type=error_type,
            error_message=error_message,
        )

    redirect_chain: tuple[str, ...] = (
        (cleaned_url, final_url) if final_url and final_url != cleaned_url else ()
    )

    if not _allowed_content_type(content_type):
        return _snapshot(
            reachable=False,
            url=cleaned_url,
            content_type=content_type,
            final_url=final_url,
            http_status=http_status,
            content_length=len(raw_bytes),
            redirect_chain=redirect_chain,
            error_type="unsupported_content_type",
            error_message=f"Unsupported homepage content type: {content_type}",
        )

    html_text = _decode_html(raw_bytes, content_type)
    content_language = _content_language_from_html(html_text, headers_lang)
    meta = _metadata(html_text, final_url)

    parser = _VisibleTextParser()
    parser.feed(html_text)
    visible_text = parser.get_text()[:MAX_VISIBLE_TEXT_CHARS]
    js_content_detected = _detect_js_content(html_text, visible_text)
    quality = _extraction_quality(visible_text, js_content_detected)
    title = _title(html_text)[:300] or meta.og_title[:300]
    snapshot = _snapshot(
        reachable=True,
        url=cleaned_url,
        title=title,
        meta_description=(meta.description or meta.og_description)[:500],
        visible_text=visible_text,
        content_type=content_type,
        is_pdf=False,
        final_url=final_url,
        http_status=http_status,
        content_length=len(raw_bytes),
        content_language=content_language,
        redirect_chain=redirect_chain,
    )
    object.__setattr__(snapshot, "og_title", meta.og_title[:300])
    object.__setattr__(snapshot, "og_description", meta.og_description[:500])
    object.__setattr__(snapshot, "h1", tuple(meta.h1))
    object.__setattr__(snapshot, "h2", tuple(meta.h2))
    object.__setattr__(snapshot, "about_url", meta.about_url)
    object.__setattr__(snapshot, "imprint_url", meta.imprint_url)
    object.__setattr__(snapshot, "js_content_detected", js_content_detected)
    object.__setattr__(snapshot, "extraction_quality", quality)
    object.__setattr__(
        snapshot,
        "content_hash",
        hashlib.sha256(raw_bytes).hexdigest(),
    )
    if http_status in {401, 403}:
        object.__setattr__(snapshot, "fetch_error_type", "fetch_access_denied")
    elif http_status == 429:
        object.__setattr__(snapshot, "fetch_error_type", "fetch_rate_limited")
    elif any(marker in html_text[:20000].lower() for marker in BOT_PROTECTION_MARKERS):
        object.__setattr__(snapshot, "fetch_error_type", "fetch_blocked_bot_protection")
    return snapshot
