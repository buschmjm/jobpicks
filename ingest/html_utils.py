"""HTML helpers for job description ingest and display."""

from __future__ import annotations

import re
from html import unescape

_BLOCK_BREAK_RE = re.compile(
    r"</(?:p|div|section|article|header|footer|h[1-6]|li|tr|blockquote|pre|ul|ol|table)>|<br\s*/?>",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_HTML_TAG_RE = re.compile(r"<\/?[a-z][\s\S]*?>", re.IGNORECASE)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]+")


def contains_html(value: str) -> bool:
    return bool(_HTML_TAG_RE.search(value))


def html_to_plain_text(value: str) -> str:
    """Convert HTML to readable plain text while preserving block structure."""
    if not value:
        return ""

    text = _BLOCK_BREAK_RE.sub("\n", value)
    text = _TAG_RE.sub("", text)
    text = unescape(text)

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = _MULTI_SPACE_RE.sub(" ", raw_line).strip()
        if line:
            lines.append(line)

    normalized = "\n".join(lines)
    return _MULTI_BLANK_RE.sub("\n\n", normalized).strip()
