"""ATS-style resume field extraction: sections + regex + skill ontology.

This is the Greenhouse/Lever-style path used by open-source parsers (pyresume,
peregrine, SkillNER-style EntityRuler): split the document into labeled sections,
pull contact with regex, match skills against a known list, and keep summary to
the actual summary/objective — not the whole file. No LLM on this path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from api.resume_skills import AMBIGUOUS_ALIASES, skill_patterns

_SKILL_PAIRS = skill_patterns()

_EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.IGNORECASE)
_PHONE_RE = re.compile(
    r"(?:(?:\+?1[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?)\d{3}[\s.\-]?\d{4})"
)
_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-/%]+", re.I)
_GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w.-]+/?", re.I)
_URL_RE = re.compile(r"https?://[^\s<>\[\]()\"']+", re.I)
_PRONOUNS_RE = re.compile(
    r"\b((?:he/him(?:/his)?)|(?:she/her(?:/hers)?)|(?:they/them(?:/theirs)?))\b",
    re.I,
)
_REMOTE_RE = re.compile(r"\b(remote|hybrid|on-?site)\b", re.I)

_US_STATES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DC": "District of Columbia",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}
_STATE_NAMES = {name.lower(): abbr for abbr, name in _US_STATES.items()}
_CITY_STATE_RE = re.compile(
    r"\b([A-Z][a-zA-Z .'-]{1,40}),\s*([A-Z]{2}|[A-Z][a-z]{2,20})\b"
)

_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_DATE_TOKEN = rf"(?:{_MONTH}\s+)?(?:19|20)\d{{2}}"
_RANGE_RE = re.compile(
    rf"({_DATE_TOKEN})\s*(?:[-–—]|to)\s*(present|current|now|{_DATE_TOKEN})",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

_TITLE_HINT_RE = re.compile(
    r"\b(engineer|developer|programmer|sre|devops|architect|manager|director|"
    r"scientist|analyst|designer|consultant|specialist|administrator|admin|"
    r"lead|principal|staff|intern|founder|cto|vp|head of|officer|researcher|"
    r"product manager|program manager|site reliability)\b",
    re.IGNORECASE,
)

_SECTION_HEADER_RE = re.compile(
    r"^\s*(?:"
    r"(?P<summary>summary|objective|profile|about(?:\s+me)?|professional summary|"
    r"career summary|career objective|personal statement|overview)|"
    r"(?P<experience>experience|work experience|employment|work history|"
    r"professional experience|career history|relevant experience|"
    r"professional history|employment history|positions?\s+held)|"
    r"(?P<education>education|academic(?:\s+background)?|qualifications|degrees?|"
    r"educational background)|"
    r"(?P<skills>skills?|technical skills?|core competencies|competencies|"
    r"expertise|areas?\s+of\s+expertise|key skills?|proficiencies|"
    r"tools?\s*(?:&|and)\s*technologies|tech(?:nical)?\s+stack)|"
    r"(?P<certs>certifications?|licenses?|certificates)|"
    r"(?P<projects>projects?|selected projects)|"
    r"(?P<other>achievements?|accomplishments?|awards?|honors?|publications?|"
    r"volunteer(?:ing)?|interests)"
    r")\s*:?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)

_NAME_STOP = re.compile(
    r"^(resume|curriculum|vitae|cv|contact|phone|email|linkedin|github|portfolio)$",
    re.IGNORECASE,
)
_SKILL_SPLIT_RE = re.compile(r"[,;|/•·\n]+")
_SKILL_STOP = {
    "and",
    "or",
    "the",
    "with",
    "using",
    "including",
    "skills",
    "proficient",
    "experienced",
    "familiar",
    "tools",
    "technologies",
}


@dataclass
class StructuredResume:
    full_name: str = ""
    title: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    skills: list[str] = field(default_factory=list)
    summary: str = ""
    years_experience: str = ""
    linkedin: str = ""
    pronouns: str = ""
    links: list[dict[str, str]] = field(default_factory=list)
    experiences: list[Any] = field(default_factory=list)
    education: list[Any] = field(default_factory=list)


def parse_structured_resume(text: str) -> StructuredResume:
    from api.resume_sections import parse_education_section, parse_experience_section

    cleaned = _normalize_lines(text)
    if not cleaned:
        return StructuredResume()

    sections = split_sections(cleaned)
    header = sections.get("header", "")
    result = StructuredResume()

    result.email = _first(_EMAIL_RE.findall(cleaned))
    phones = [p.strip() for p in _PHONE_RE.findall(cleaned) if _looks_like_phone(p)]
    result.phone = phones[0] if phones else ""
    result.linkedin = _first(_LINKEDIN_RE.findall(cleaned))
    result.pronouns = _extract_pronouns(header) or _extract_pronouns("\n".join(cleaned.splitlines()[:12]))
    result.links = _extract_links(header, cleaned, linkedin=result.linkedin)
    result.location = _extract_location(header) or _extract_location(cleaned)
    result.full_name = _extract_name(header, cleaned)
    result.title = _extract_title(header, sections.get("experience", ""))
    result.skills = _extract_skills(sections.get("skills", ""), cleaned)
    result.summary = _extract_summary(sections.get("summary", ""), result)
    experience_text = sections.get("experience", "")
    result.experiences = parse_experience_section(experience_text)
    result.education = parse_education_section(sections.get("education", ""))
    if result.experiences and not result.title:
        result.title = result.experiences[0].title
    return result


def split_sections(text: str) -> dict[str, str]:
    lines = text.splitlines()
    buckets: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in lines:
        match = _SECTION_HEADER_RE.match(line.strip())
        if match:
            current = next(name for name, value in match.groupdict().items() if value and name != "rest")
            buckets.setdefault(current, [])
            rest = (match.group("rest") or "").strip()
            if rest:
                buckets[current].append(rest)
            continue
        buckets.setdefault(current, []).append(line)
    return {name: "\n".join(body).strip() for name, body in buckets.items() if "".join(body).strip()}


def _normalize_lines(text: str) -> str:
    text = text.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _first(values: list[str]) -> str:
    return values[0].strip() if values else ""


def _looks_like_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    return 10 <= len(digits) <= 11


def _ensure_https(url: str) -> str:
    raw = (url or "").strip().rstrip(".,);]")
    if not raw:
        return ""
    if "://" not in raw:
        return f"https://{raw}"
    return raw


def _extract_pronouns(text: str) -> str:
    match = _PRONOUNS_RE.search(text or "")
    if not match:
        return ""
    from core.profile_identity import normalize_pronouns

    return normalize_pronouns(match.group(1))


def _extract_links(header: str, cleaned: str, *, linkedin: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(title: str, url: str) -> None:
        href = _ensure_https(url)
        if not href:
            return
        key = href.lower().rstrip("/")
        if key in seen:
            return
        seen.add(key)
        links.append({"title": title, "url": href})

    if linkedin:
        add("LinkedIn", linkedin)
    github = _first(_GITHUB_RE.findall(cleaned))
    if github:
        add("GitHub", github)

    # Other absolute URLs from the header / top of the resume only.
    scan = "\n".join((header or "").splitlines()[:20] or cleaned.splitlines()[:12])
    for match in _URL_RE.findall(scan):
        href = _ensure_https(match)
        lower = href.lower()
        if "linkedin.com" in lower or "github.com" in lower:
            continue
        if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg")):
            continue
        title = "Website"
        host = re.sub(r"^https?://(www\.)?", "", lower).split("/")[0]
        if host:
            title = host.split(".")[0].title()
        add(title, href)
    return links[:8]


def _header_tokens(header: str) -> list[str]:
    if not header:
        return []
    first_block = header.split("\n\n", 1)[0]
    chunks: list[str] = []
    for raw in first_block.splitlines()[:8]:
        for part in re.split(r"\s*[|•·]\s*", raw):
            part = part.strip(" ,;-")
            if part:
                chunks.append(part)
    return chunks


def _extract_name(header: str, full_text: str) -> str:
    for token in _header_tokens(header) or full_text.splitlines()[:5]:
        cleaned = _PRONOUNS_RE.sub("", token)
        cleaned = re.sub(r"[()]", " ", cleaned)
        cleaned = " ".join(cleaned.split()).strip(" ,;-")
        if _looks_like_name(cleaned):
            return _title_case_name(cleaned)
    return ""


def _looks_like_name(value: str) -> bool:
    if _EMAIL_RE.search(value) or _PHONE_RE.search(value) or "http" in value.lower():
        return False
    if _NAME_STOP.match(value.strip()):
        return False
    if _TITLE_HINT_RE.search(value) or _SECTION_HEADER_RE.match(value):
        return False
    words = [w for w in re.split(r"\s+", value.strip()) if w]
    if not 2 <= len(words) <= 5:
        return False
    if len(value) > 60:
        return False
    letters = [w for w in words if re.fullmatch(r"[A-Za-z][A-Za-z.'\-]*", w)]
    return len(letters) == len(words)


def _title_case_name(value: str) -> str:
    if value.isupper() or value.islower():
        return " ".join(part.capitalize() for part in value.split())
    return value.strip()


def _extract_title(header: str, experience: str) -> str:
    for token in _header_tokens(header):
        if _looks_like_title(token):
            return _clean_title(token)
    for line in experience.splitlines()[:12]:
        if _looks_like_title(line):
            return _clean_title(line)
    return ""


def _looks_like_title(value: str) -> bool:
    if not value or len(value) > 80:
        return False
    if _EMAIL_RE.search(value) or _PHONE_RE.search(value):
        return False
    if _looks_like_name(value):
        return False
    if _YEAR_RE.search(value) and not _TITLE_HINT_RE.search(value):
        return False
    return bool(_TITLE_HINT_RE.search(value))


def _clean_title(value: str) -> str:
    value = re.split(r"\s+[|@–—-]\s+", value, maxsplit=1)[0]
    return value.strip(" ,;-")


def _extract_location(text: str) -> str:
    if not text:
        return ""
    for match in _CITY_STATE_RE.finditer(text):
        city, region = match.group(1).strip(), match.group(2).strip()
        if len(region) == 2 and region.upper() in _US_STATES:
            return f"{city}, {region.upper()}"
        abbr = _STATE_NAMES.get(region.lower())
        if abbr:
            return f"{city}, {abbr}"
    remote = _REMOTE_RE.search(text)
    if remote and remote.group(1).lower() == "remote":
        return "Remote"
    return ""


def _extract_skills(skills_section: str, full_text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def add(canonical: str) -> None:
        if canonical not in seen:
            seen.add(canonical)
            found.append(canonical)

    section_l = skills_section.lower()
    body_l = full_text.lower()
    for canonical, alias in _SKILL_PAIRS:
        pattern = _alias_re(alias)
        in_section = bool(section_l and pattern.search(section_l))
        in_body = bool(pattern.search(body_l))
        if alias in AMBIGUOUS_ALIASES:
            if in_section:
                add(canonical)
            continue
        if in_section or in_body:
            add(canonical)

    for token in _SKILL_SPLIT_RE.split(skills_section):
        token = token.strip().lower()
        if not 2 < len(token) <= 32:
            continue
        if token in _SKILL_STOP or " " in token and len(token.split()) > 4:
            continue
        if re.fullmatch(r"[a-z0-9][a-z0-9.+#\- ]*[a-z0-9.+#]", token) and token not in seen:
            add(token)

    return found[:24]


def _alias_re(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias)
    if re.search(r"[^\w]", alias):
        return re.compile(escaped, re.IGNORECASE)
    return re.compile(rf"(?<![\w]){escaped}(?![\w])", re.IGNORECASE)


def _extract_summary(summary_section: str, parsed: StructuredResume) -> str:
    if summary_section:
        compact = " ".join(summary_section.split())
        return _truncate_sentences(compact, max_chars=420)
    if parsed.title:
        return parsed.title
    return ""


def _truncate_sentences(text: str, *, max_chars: int) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text)
    out: list[str] = []
    for part in parts:
        candidate = (" ".join(out + [part])).strip()
        if len(candidate) > max_chars and out:
            break
        out.append(part)
        if len(out) >= 3:
            break
    summary = " ".join(out).strip()
    return summary[:max_chars].rstrip()


def _extract_years(experience_text: str) -> str:
    spans: list[tuple[int, int]] = []
    now = datetime.now(UTC).year
    for match in _RANGE_RE.finditer(experience_text):
        start_raw, end_raw = match.group(1), match.group(2)
        start_year = _year_from(start_raw)
        if start_year is None or not end_raw:
            continue
        end_year = now if re.search(r"present|current|now", end_raw, re.I) else _year_from(end_raw) or now
        if end_year < start_year:
            continue
        spans.append((start_year, end_year))
    if not spans:
        years = [int(y) for y in _YEAR_RE.findall(experience_text)]
        years = [y for y in years if 1980 <= y <= now]
        if len(years) >= 2:
            spans.append((min(years), max(years)))
    if not spans:
        return ""
    earliest = min(start for start, _ in spans)
    latest = max(end for _, end in spans)
    total_years = max(1, latest - earliest)
    return str(total_years)


def _year_from(token: str) -> int | None:
    match = _YEAR_RE.search(token)
    if not match:
        return None
    year = int(match.group(1))
    now = datetime.now(UTC).year
    if 1980 <= year <= now + 1:
        return year
    return None
