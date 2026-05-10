"""Website fetching helpers."""
from __future__ import annotations

import html
import io
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlparse


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
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

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag.lower() != "meta":
            return
        normalized = {str(key).lower(): str(value or "") for key, value in attrs}
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
) -> dict[str, str | bool]:
    return {
        "reachable": reachable,
        "url": url,
        "title": title,
        "meta_description": meta_description,
        "visible_text": visible_text,
        "content_type": content_type,
        "is_pdf": is_pdf,
        "error_type": error_type,
        "error_message": error_message,
    }


def _meta_description(html_text: str) -> str:
    parser = _MetadataParser()
    parser.feed(html_text)
    return parser.description[:500]


def _title(html_text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return html.unescape(" ".join(match.group(1).split()))


def _looks_like_pdf(url: str, content_type: str) -> bool:
    lowered_url = url.lower()
    lowered_type = content_type.lower()
    return lowered_url.endswith(".pdf") or "application/pdf" in lowered_type


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


def fetch_website_snapshot(url: str, *, timeout: int = 8) -> dict[str, str | bool]:
    cleaned_url = str(url or "").strip()
    if not cleaned_url or "://" not in cleaned_url:
        return _snapshot(
            reachable=False,
            url=cleaned_url,
            error_type="invalid_url",
            error_message="URL must include a scheme.",
        )

    try:
        request = urllib.request.Request(
            cleaned_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; LiquistoBot/1.0)"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - scheme is required and intended for web/PDF fetch
            content_type = str(response.headers.get("Content-Type", "") or "")
            charset = getattr(response.headers, "get_content_charset", lambda: None)()
            if charset and "charset=" not in content_type.lower():
                content_type = f"{content_type}; charset={charset}" if content_type else f"charset={charset}"
            raw_bytes = response.read(800000)
    except Exception as exc:
        return _snapshot(
            reachable=False,
            url=cleaned_url,
            error_type=type(exc).__name__,
            error_message=str(exc)[:300],
        )

    if _looks_like_pdf(cleaned_url, content_type):
        visible_text, pdf_title = _extract_pdf_text(raw_bytes)
        fallback_title = urlparse(cleaned_url).path.rsplit("/", 1)[-1]
        return _snapshot(
            reachable=True,
            url=cleaned_url,
            title=(pdf_title or fallback_title)[:300],
            visible_text=visible_text[:12000],
            content_type=content_type,
            is_pdf=True,
        )

    html_text = _decode_html(raw_bytes, content_type)

    parser = _VisibleTextParser()
    parser.feed(html_text)
    visible_text = parser.get_text()[:4000]
    return _snapshot(
        reachable=True,
        url=cleaned_url,
        title=_title(html_text)[:300],
        meta_description=_meta_description(html_text)[:500],
        visible_text=visible_text,
        content_type=content_type,
        is_pdf=False,
    )
