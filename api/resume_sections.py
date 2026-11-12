"""Parse work history and education sections from resume text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from api.resume_struct import (
    _CITY_STATE_RE,
    _RANGE_RE,
    _TITLE_HINT_RE,
    _YEAR_RE,
    _clean_title,
    _extract_location,
    _looks_like_title,
    _year_from,
)

_BULLET_LINE_RE = re.compile(
    r"^(?:"
    r"[-–—•*●◦▪▸►○◆]"
    r"|\u2022|\u2023|\u25e6|\u2043|\u2219"
    r"|\d{1,2}[.)]"
    r")\s+(.+)$",
    re.IGNORECASE,
)
_COMPANY_SUFFIX_RE = re.compile(
    r"\b("
    r"Inc\.?|Incorporated|LLC|L\.L\.C\.|Corp\.?|Corporation|Company|Co\.?|Ltd\.?|Limited|"
    r"LP|LLP|PLC|GmbH|Group|Holdings|Technologies|Technology|Tech|Labs|Systems|"
    r"Solutions|Services|Consulting|Partners|Enterprises|Industries|International|"
    r"Worldwide|Global|Digital|Software|Networks|Communications|Healthcare|Financial|"
    r"Bank|Capital|Ventures|Media|Studios|Games|Interactive|Automotive|Motors|"
    r"Airlines|University|College"
    r")\b",
    re.IGNORECASE,
)
_AT_SEP_RE = re.compile(r"\s+(?:at|@)\s+", re.IGNORECASE)
_PIPE_SEP_RE = re.compile(r"\s*\|\s*")
_EM_DASH_SEP_RE = re.compile(r"\s*[—–]\s+")
_COMMA_SEP_RE = re.compile(r"\s*,\s*")
_DEGREE_RE = re.compile(
    r"\b("
    r"B\.?\s?S\.?|B\.?\s?A\.?|M\.?\s?S\.?|M\.?\s?Eng|M\.?\s?B\.?\s?A\.?|Ph\.?\s?D\.?|"
    r"Associate(?:'?s)?|Bachelor(?:'?s)?|Master(?:'?s)?|Doctor(?:ate)?"
    r")\b",
    re.IGNORECASE,
)
_INSTITUTION_RE = re.compile(
    r"\b(University|College|Institute|School|Academy|Polytechnic)\b",
    re.IGNORECASE,
)
_MONTH_NAMES = {
    "jan": "01",
    "january": "01",
    "feb": "02",
    "february": "02",
    "mar": "03",
    "march": "03",
    "apr": "04",
    "april": "04",
    "may": "05",
    "jun": "06",
    "june": "06",
    "jul": "07",
    "july": "07",
    "aug": "08",
    "august": "08",
    "sep": "09",
    "sept": "09",
    "september": "09",
    "oct": "10",
    "october": "10",
    "nov": "11",
    "november": "11",
    "dec": "12",
    "december": "12",
}


@dataclass
class ExperienceEntry:
    title: str = ""
    company_name: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    is_current: bool = False
    highlights: list[str] = field(default_factory=list)


@dataclass
class EducationEntry:
    institution: str = ""
    degree: str = ""
    field: str = ""
    end_date: str = ""


def parse_experience_section(text: str) -> list[ExperienceEntry]:
    if not text.strip():
        return []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    entries: list[ExperienceEntry] = []
    index = 0
    while index < len(lines):
        range_index = _find_range_line(lines, index, max_lookahead=8)
        if range_index is None:
            break
        range_line = lines[range_index]
        match = _RANGE_RE.search(range_line)
        if not match:
            index = range_index + 1
            continue
        header_lines = list(lines[index:range_index])
        prefix = range_line[: match.start()].strip(" ,|–—-")
        if prefix:
            header_lines.append(prefix)
        entry = _entry_from_header_lines(header_lines)
        entry.start_date = _normalize_date_token(match.group(1))
        end_raw = match.group(2)
        entry.is_current = bool(re.search(r"present|current|now", end_raw, re.I))
        entry.end_date = "present" if entry.is_current else _normalize_date_token(end_raw)
        index = range_index + 1
        body_lines: list[str] = []
        while index < len(lines):
            line = lines[index]
            if _RANGE_RE.search(line) or _looks_like_new_role(line, lines, index):
                break
            body_lines.append(line)
            index += 1
        entry.highlights = _extract_highlights(body_lines)
        if entry.title or entry.company_name:
            entries.append(entry)
    return entries[:12]


def parse_education_section(text: str) -> list[EducationEntry]:
    if not text.strip():
        return []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    entries: list[EducationEntry] = []
    block: list[str] = []
    for line in lines:
        if _looks_like_education_block_start(line) and block:
            entry = _education_from_lines(block)
            if entry.institution or entry.degree:
                entries.append(entry)
            block = [line]
        else:
            block.append(line)
    if block:
        entry = _education_from_lines(block)
        if entry.institution or entry.degree:
            entries.append(entry)
    return entries[:8]


def _find_range_line(lines: list[str], start: int, *, max_lookahead: int) -> int | None:
    for offset in range(max_lookahead):
        idx = start + offset
        if idx >= len(lines):
            break
        if _RANGE_RE.search(lines[idx]):
            return idx
    return None


def _looks_like_new_role(line: str, lines: list[str], index: int) -> bool:
    if _is_bullet_line(line):
        return False
    if _RANGE_RE.search(line):
        return False
    if not (_looks_like_title(line) or _looks_like_company(line)):
        return False
    if index + 1 < len(lines) and _RANGE_RE.search(lines[index + 1]):
        return True
    if index + 2 < len(lines) and _RANGE_RE.search(lines[index + 2]):
        return True
    if index + 1 < len(lines):
        nxt = lines[index + 1]
        if _looks_like_company(nxt) or _COMPANY_SUFFIX_RE.search(nxt):
            for ahead in (2, 3):
                if index + ahead < len(lines) and _RANGE_RE.search(lines[index + ahead]):
                    return True
    return False


def _entry_from_header_lines(lines: list[str]) -> ExperienceEntry:
    entry = ExperienceEntry()
    if not lines:
        return entry

    pending: list[str] = []
    for line in lines:
        parsed = _parse_header_line(line)
        if parsed["title"] and not entry.title:
            entry.title = parsed["title"]
        if parsed["company"] and not entry.company_name:
            entry.company_name = parsed["company"]
        elif parsed["company"]:
            pending.append(parsed["company"])
        if parsed["location"] and not entry.location:
            entry.location = parsed["location"]
        if parsed["title"] and parsed["company"]:
            continue
        if not parsed["title"] and not parsed["company"]:
            if _extract_location(line) or _CITY_STATE_RE.search(line):
                entry.location = entry.location or _extract_location(line) or line
            elif _looks_like_company(line) and not entry.company_name:
                entry.company_name = _clean_company(line)
            elif _looks_like_title(line) and not entry.title:
                entry.title = _clean_title(line)
            elif not entry.company_name and not _looks_like_title(line):
                entry.company_name = _clean_company(line)

    if not entry.company_name and pending:
        entry.company_name = pending[0]
    if not entry.company_name and len(lines) >= 2:
        entry = _assign_title_company_from_block(lines, entry)
    return entry


def _assign_title_company_from_block(lines: list[str], entry: ExperienceEntry) -> ExperienceEntry:
    """Fallback when title/company weren't resolved line-by-line."""
    for line in lines:
        title, company, location = _split_title_company(line)
        if title and not entry.title:
            entry.title = title
        if company and not entry.company_name:
            entry.company_name = company
        if location and not entry.location:
            entry.location = location

    if entry.title and entry.company_name:
        return entry

    candidates = [line for line in lines if not _extract_location(line) or line.strip() != entry.location]
    title_lines = [line for line in candidates if _looks_like_title(line)]
    company_lines = [line for line in candidates if _looks_like_company(line) and line not in title_lines]

    if not entry.title and title_lines:
        entry.title = _clean_title(title_lines[0])
    if not entry.company_name:
        for line in candidates:
            if line in title_lines:
                continue
            loc = _extract_location(line)
            company_part = line
            if loc:
                entry.location = entry.location or loc
                company_part = line.replace(loc, "").strip(" ,|–—-")
            if company_part and (_looks_like_company(company_part) or not _looks_like_title(company_part)):
                entry.company_name = _clean_company(company_part)
                break
        if not entry.company_name and company_lines:
            entry.company_name = _clean_company(company_lines[0])
    return entry


def _parse_header_line(line: str) -> dict[str, str]:
    location = _extract_location(line) or ""
    working = line
    if location:
        working = working.replace(location, "").strip(" ,|–—-")

    title, company, _ = _split_title_company(working)
    if title or company:
        return {"title": title, "company": company, "location": location}

    if _looks_like_title(working):
        return {"title": _clean_title(working), "company": "", "location": location}
    if _looks_like_company(working):
        return {"title": "", "company": _clean_company(working), "location": location}
    return {"title": "", "company": "", "location": location}


def _split_title_company(line: str) -> tuple[str, str, str]:
    line = line.strip()
    if not line:
        return "", "", ""

    location = _extract_location(line) or ""
    if location:
        line = line.replace(location, "").strip(" ,|–—-")

    for pattern in (_AT_SEP_RE, _PIPE_SEP_RE, _EM_DASH_SEP_RE, _COMMA_SEP_RE):
        if not pattern.search(line):
            continue
        parts = pattern.split(line)
        if len(parts) < 2:
            continue
        left, right = parts[0].strip(), parts[1].strip()
        right = _strip_trailing_dates(right)
        left = _strip_trailing_dates(left)
        if _looks_like_title(left) and (_looks_like_company(right) or not _looks_like_title(right)):
            return _clean_title(left), _clean_company(right), location
        if _looks_like_company(left) and _looks_like_title(right):
            return _clean_title(right), _clean_company(left), location
        if _looks_like_title(left) and right:
            return _clean_title(left), _clean_company(right), location

    if _looks_like_title(line):
        return _clean_title(line), "", location
    if _looks_like_company(line):
        return "", _clean_company(line), location
    return "", _clean_company(line), location


def _strip_trailing_dates(text: str) -> str:
    return _RANGE_RE.sub("", text).strip(" ,|–—-")


def _looks_like_company(value: str) -> bool:
    value = value.strip()
    if not value or len(value) > 120:
        return False
    if _RANGE_RE.search(value):
        return False
    if _COMPANY_SUFFIX_RE.search(value):
        return True
    if _looks_like_title(value):
        return False
    words = value.split()
    if 1 <= len(words) <= 5 and value[0].isupper():
        if any(w.lower() in {"the", "and", "of"} for w in words[1:]):
            return True
        if not _TITLE_HINT_RE.search(value):
            return True
    return False


def _clean_company(value: str) -> str:
    value = value.strip(" ,;|–—-")
    value = _strip_trailing_dates(value)
    value = re.sub(r"\s+", " ", value)
    return value[:512]


def _parse_company_location(line: str) -> tuple[str, str]:
    location = _extract_location(line) or ""
    company_part = line.replace(location, "").strip(" ,|–—-") if location else line.strip()
    parts = _COMMA_SEP_RE.split(company_part)
    if len(parts) >= 2 and (_extract_location(parts[-1]) or _CITY_STATE_RE.search(parts[-1])):
        loc = _extract_location(parts[-1]) or parts[-1].strip()
        company = ", ".join(parts[:-1]).strip()
        return _clean_company(company), loc
    parts = _EM_DASH_SEP_RE.split(line, maxsplit=1)
    if len(parts) == 2:
        company, loc = parts[0].strip(), parts[1].strip()
        if _extract_location(loc) or _CITY_STATE_RE.search(loc) or loc.lower() == "remote":
            return _clean_company(company), loc
    return _clean_company(company_part), location


def _extract_highlights(lines: list[str]) -> list[str]:
    if not lines:
        return []

    cleaned = [line.strip() for line in lines if line.strip()]
    if not cleaned:
        return []

    has_bullets = any(_is_bullet_line(line) for line in cleaned)
    if has_bullets:
        highlights: list[str] = []
        current: list[str] = []

        def flush() -> None:
            if not current:
                return
            text = re.sub(r"\s+", " ", " ".join(current)).strip()
            if text:
                highlights.extend(split_accomplishment_text(text))
            current.clear()

        for line in cleaned:
            bullet_match = _BULLET_LINE_RE.match(line)
            if bullet_match:
                flush()
                current = [bullet_match.group(1).strip()]
                continue
            if current and _is_bullet_continuation(line):
                current.append(line.strip())
                continue
            if current:
                flush()
            current = [line.strip()]

        flush()
        return _dedupe_highlights(highlights)[:12]

    # PDFs often drop bullet glyphs — treat each accomplishment-like line separately.
    per_line: list[str] = []
    for line in cleaned:
        per_line.extend(split_accomplishment_text(line))
    if len(per_line) >= 2:
        return _dedupe_highlights(per_line)[:12]

    # Single line / short block: still try sentence splits on the joined text.
    paragraph = re.sub(r"\s+", " ", " ".join(cleaned)).strip()
    return _dedupe_highlights(split_accomplishment_text(paragraph))[:12]


_ACTION_VERB_RE = re.compile(
    r"^(?:"
    r"Built|Rebuild|Reworked|Rebuilt|Designed|Developed|Implemented|Created|Led|Lead|"
    r"Managed|Owned|Reduced|Improved|Increased|Decreased|Deployed|Automated|Maintained|"
    r"Supported|Configured|Migrated|Operated|Ran|Delivered|Launched|Established|Drove|"
    r"Coordinated|Architected|Engineered|Wrote|Integrated|Troubleshot|Served|Worked|"
    r"Helped|Partnered|Collaborated|Directed|Oversaw|Executed|Streamlined|Optimized|"
    r"Scaled|Provisioned|Monitored|Documented|Introduced|Refactored|Modernized|"
    r"Stand(?:ardized|ing)|Enabled|Facilitated|Negotiated|Analyzed|Resolved|"
    r"Administered|Installed|Upgraded|Secured|Tuned|Debugged"
    r")\b",
    re.IGNORECASE,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def split_accomplishment_text(text: str) -> list[str]:
    """Split a glued accomplishment blob into discrete bullets.

    Handles newline-separated lines and sentence boundaries that start with
    common resume action verbs (common when PDF extraction drops bullets).
    """
    raw = (text or "").strip()
    if not raw:
        return []

    chunks: list[str] = []
    for part in re.split(r"[\n\r]+", raw):
        part = part.strip()
        if not part:
            continue
        bullet = _BULLET_LINE_RE.match(part)
        if bullet:
            part = bullet.group(1).strip()
        chunks.append(re.sub(r"\s+", " ", part).strip())

    out: list[str] = []
    for chunk in chunks:
        pieces = _SENTENCE_SPLIT_RE.split(chunk)
        if len(pieces) == 1:
            if len(chunk) >= 8:
                out.append(chunk.rstrip(" ."))
            continue
        buf = pieces[0].strip()
        for piece in pieces[1:]:
            piece = piece.strip()
            if _ACTION_VERB_RE.match(piece) and len(buf) >= 20:
                out.append(buf.rstrip(" .") + ("." if not buf.endswith((".", "!", "?")) else ""))
                buf = piece
            else:
                buf = f"{buf} {piece}".strip()
        if buf and len(buf) >= 8:
            out.append(buf.rstrip(" .") + ("." if not buf.endswith((".", "!", "?")) else ""))
    return _dedupe_highlights(out)


def normalize_highlights(items: list[str] | None) -> list[str]:
    """Expand and clean highlight lists (import + save path)."""
    if not items:
        return []
    out: list[str] = []
    for item in items:
        out.extend(split_accomplishment_text(str(item)))
    return _dedupe_highlights(out)[:12]


def _dedupe_highlights(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        clean = re.sub(r"\s+", " ", (item or "").strip())
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return out


def _is_bullet_line(line: str) -> bool:
    return bool(_BULLET_LINE_RE.match(line.strip()))


def _is_bullet_continuation(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _is_bullet_line(stripped):
        return False
    if _RANGE_RE.search(stripped):
        return False
    if _looks_like_new_role_simple(stripped):
        return False
    if stripped[0].islower():
        return True
    if stripped.startswith(("and ", "with ", "for ", "to ", "by ", "using ", "including ")):
        return True
    return bool(len(stripped) < 80 and not stripped.endswith("."))


def _looks_like_new_role_simple(line: str) -> bool:
    return _looks_like_title(line) and not _is_bullet_line(line)


def _normalize_date_token(token: str) -> str:
    token = token.strip()
    year = _year_from(token)
    if year is None:
        return token
    month_match = re.search(
        r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)",
        token,
        re.I,
    )
    if month_match:
        month_key = month_match.group(1).lower()
        month = _MONTH_NAMES.get(month_key) or _MONTH_NAMES.get(month_key[:3], "01")
        return f"{year}-{month}"
    return str(year)


def _looks_like_education_block_start(line: str) -> bool:
    return bool(_DEGREE_RE.search(line) or _INSTITUTION_RE.search(line))


def _education_from_lines(lines: list[str]) -> EducationEntry:
    if len(lines) == 1:
        return _education_from_single_line(lines[0])
    entry = EducationEntry()
    for line in lines:
        year = _YEAR_RE.search(line)
        if year and not entry.end_date:
            entry.end_date = year.group(1)
            continue
        if _DEGREE_RE.search(line) and not entry.degree:
            entry.degree, entry.field = _split_degree_field(line)
            continue
        if _INSTITUTION_RE.search(line) and not entry.institution:
            entry.institution = line.strip(" ,")
    if not entry.degree:
        entry.degree, entry.field = _split_degree_field(lines[0])
    if not entry.institution:
        for line in lines:
            if not _DEGREE_RE.search(line) and not _YEAR_RE.search(line):
                entry.institution = line.strip(" ,")
                break
    return entry


def _education_from_single_line(line: str) -> EducationEntry:
    entry = EducationEntry()
    parts = [part.strip() for part in line.split(",") if part.strip()]
    if not parts:
        return entry
    if parts and _YEAR_RE.fullmatch(parts[-1]):
        entry.end_date = parts[-1]
        parts = parts[:-1]
    if len(parts) >= 2 and _INSTITUTION_RE.search(parts[-1]):
        entry.institution = parts[-1]
        entry.degree, entry.field = _split_degree_field(", ".join(parts[:-1]))
        return entry
    entry.degree, entry.field = _split_degree_field(parts[0])
    if len(parts) > 1:
        entry.institution = parts[1]
    return entry


def _split_degree_field(text: str) -> tuple[str, str]:
    text = text.strip(" ,")
    match = _DEGREE_RE.search(text)
    if not match:
        return "", text
    degree = match.group(1).strip()
    remainder = text[match.end() :].strip(" ,-–—")
    remainder = re.sub(r"^(in|of)\s+", "", remainder, flags=re.I)
    return degree, remainder
