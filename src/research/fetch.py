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


def _meta_description(html_text: str) -> str:
    match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    return html.unescape(" ".join(match.group(1).split()))


def _title(html_text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return html.unescape(" ".join(match.group(1).split()))


def _looks_like_pdf(url: str, content_type: str) -> bool:
    lowered_url = url.lower()
    lowered_type = content_type.lower()
    return lowered_url.endswith(".pdf") or "application/pdf" in lowered_type


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
        return {
            "reachable": False,
            "url": cleaned_url,
            "title": "",
            "meta_description": "",
            "visible_text": "",
            "content_type": "",
            "is_pdf": False,
        }

    try:
        request = urllib.request.Request(
            cleaned_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; LiquistoBot/1.0)"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = str(response.headers.get("Content-Type", "") or "")
            raw_bytes = response.read(800000)
    except Exception:
        return {
            "reachable": False,
            "url": cleaned_url,
            "title": "",
            "meta_description": "",
            "visible_text": "",
            "content_type": "",
            "is_pdf": False,
        }

    if _looks_like_pdf(cleaned_url, content_type):
        visible_text, pdf_title = _extract_pdf_text(raw_bytes)
        fallback_title = urlparse(cleaned_url).path.rsplit("/", 1)[-1]
        return {
            "reachable": True,
            "url": cleaned_url,
            "title": (pdf_title or fallback_title)[:300],
            "meta_description": "",
            "visible_text": visible_text[:12000],
            "content_type": content_type,
            "is_pdf": True,
        }

    html_text = raw_bytes.decode("utf-8", errors="ignore")

    parser = _VisibleTextParser()
    parser.feed(html_text)
    visible_text = parser.get_text()[:4000]
    return {
        "reachable": True,
        "url": cleaned_url,
        "title": _title(html_text)[:300],
        "meta_description": _meta_description(html_text)[:500],
        "visible_text": visible_text,
        "content_type": content_type,
        "is_pdf": False,
    }
