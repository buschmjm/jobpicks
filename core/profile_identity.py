"""Preferred resume identity (name, contact, links) stored on profile.parsed_resume."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from core.models import Profile

PRONOUN_PRESETS = (
    "he/him/his",
    "she/her/hers",
    "they/them/theirs",
)

_PHONE_DIGITS_RE = re.compile(r"\D+")


def normalize_us_phone(value: str) -> str:
    """Return national XXX-XXX-XXXX or '' if empty. Raises ValueError if incomplete."""
    raw = (value or "").strip()
    if not raw:
        return ""
    digits = _PHONE_DIGITS_RE.sub("", raw)
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError("Enter a complete 10-digit US phone number")
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"


def format_phone_display(phone: str) -> str:
    try:
        national = normalize_us_phone(phone)
    except ValueError:
        national = (phone or "").strip()
    if not national:
        return ""
    if national.startswith("+"):
        return national
    return f"+1 {national}"


def normalize_web_url(value: str) -> str:
    """Return a normalized http(s) URL or '' if empty. Raises ValueError if invalid."""
    raw = (value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Links must use http:// or https://")
    host = (parsed.netloc or "").strip().lower()
    host_check = host[4:] if host.startswith("www.") else host
    if not host_check or "." not in host_check:
        raise ValueError("Enter a valid website URL (e.g. https://linkedin.com/in/you)")
    if " " in raw:
        raise ValueError("Enter a valid website URL without spaces")
    return raw


def normalize_pronouns(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower().replace(" ", "")
    aliases = {
        "he/him": "he/him/his",
        "he/him/his": "he/him/his",
        "she/her": "she/her/hers",
        "she/her/hers": "she/her/hers",
        "they/them": "they/them/theirs",
        "they/them/theirs": "they/them/theirs",
    }
    if lowered in aliases:
        return aliases[lowered]
    return raw[:64]


def get_identity_dict(profile: Profile | None) -> dict[str, Any]:
    if profile is None:
        return _empty_identity()
    parsed = profile.parsed_resume if isinstance(profile.parsed_resume, dict) else {}
    raw = parsed.get("identity")
    if not isinstance(raw, dict):
        raw = {}
    links_raw = raw.get("links")
    links_in: list[Any] = links_raw if isinstance(links_raw, list) else []
    links: list[dict[str, str]] = []
    for item in links_in[:12]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()[:128]
        url = str(item.get("url") or "").strip()[:2048]
        if title or url:
            links.append({"title": title, "url": url})
    show_pronouns = raw.get("show_pronouns")
    if show_pronouns is None:
        show_pronouns = True
    phone_raw = str(raw.get("phone") or "").strip()
    try:
        phone = normalize_us_phone(phone_raw) if phone_raw else ""
    except ValueError:
        phone = phone_raw[:64]
    return {
        "preferred_name": str(raw.get("preferred_name") or "").strip()[:256],
        "email": str(raw.get("email") or "").strip()[:320],
        "phone": phone,
        "pronouns": normalize_pronouns(str(raw.get("pronouns") or "")),
        "show_pronouns": bool(show_pronouns),
        "links": links,
    }


def set_identity_dict(profile: Profile, identity: dict[str, Any]) -> None:
    parsed = dict(profile.parsed_resume) if isinstance(profile.parsed_resume, dict) else {}
    links_raw = identity.get("links")
    links_in: list[Any] = links_raw if isinstance(links_raw, list) else []
    links: list[dict[str, str]] = []
    for item in links_in[:12]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()[:128]
        url_raw = str(item.get("url") or "").strip()[:2048]
        if not title and not url_raw:
            continue
        url = normalize_web_url(url_raw) if url_raw else ""
        if title or url:
            links.append({"title": title or _title_from_url(url), "url": url})
    phone_raw = str(identity.get("phone") or "").strip()
    phone = normalize_us_phone(phone_raw) if phone_raw else ""
    show_pronouns = identity.get("show_pronouns")
    if show_pronouns is None:
        show_pronouns = True
    parsed["identity"] = {
        "preferred_name": str(identity.get("preferred_name") or "").strip()[:256],
        "email": str(identity.get("email") or "").strip()[:320],
        "phone": phone,
        "pronouns": normalize_pronouns(str(identity.get("pronouns") or "")),
        "show_pronouns": bool(show_pronouns),
        "links": links,
    }
    profile.parsed_resume = parsed


def merge_scraped_identity(profile: Profile, scraped: dict[str, Any]) -> None:
    """Fill empty identity fields from a resume scrape; merge new links by URL."""
    current = get_identity_dict(profile)
    parsed = profile.parsed_resume if isinstance(profile.parsed_resume, dict) else {}
    identity_raw = parsed.get("identity")
    existing_raw: dict[str, Any] = identity_raw if isinstance(identity_raw, dict) else {}
    merged = dict(current)
    for key in ("preferred_name", "email", "phone", "pronouns"):
        if not str(merged.get(key) or "").strip() and scraped.get(key):
            merged[key] = scraped[key]
    if "show_pronouns" in existing_raw:
        merged["show_pronouns"] = bool(existing_raw["show_pronouns"])
    else:
        merged["show_pronouns"] = True

    existing_urls = {_url_key(str(link.get("url") or "")) for link in merged.get("links") or []}
    links = list(merged.get("links") or [])
    for item in scraped.get("links") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url_raw = str(item.get("url") or "").strip()
        if not url_raw:
            continue
        try:
            url = normalize_web_url(url_raw)
        except ValueError:
            continue
        key = _url_key(url)
        if key in existing_urls:
            continue
        existing_urls.add(key)
        links.append({"title": title or _title_from_url(url), "url": url})
    merged["links"] = links[:12]
    set_identity_dict(profile, merged)


def fact_value(profile: Profile | None, *keys: str) -> str:
    if profile is None:
        return ""
    parsed = profile.parsed_resume if isinstance(profile.parsed_resume, dict) else {}
    wanted = {k.lower() for k in keys}
    for fact in parsed.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        if str(fact.get("key") or "").lower() in wanted:
            value = str(fact.get("value") or "").strip()
            if value:
                return value
    return ""


def resolve_identity(profile: Profile | None, *, account_email: str | None = None) -> dict[str, Any]:
    """Merge stored identity with parsed resume facts / account email defaults."""
    identity = get_identity_dict(profile)
    if not identity["preferred_name"]:
        identity["preferred_name"] = fact_value(profile, "full_name", "name")
    if not identity["email"]:
        identity["email"] = fact_value(profile, "email") or (account_email or "").strip()
    if not identity["phone"]:
        phone_fact = fact_value(profile, "phone")
        if phone_fact:
            try:
                identity["phone"] = normalize_us_phone(phone_fact)
            except ValueError:
                identity["phone"] = phone_fact
    if not identity["pronouns"]:
        identity["pronouns"] = normalize_pronouns(fact_value(profile, "pronouns"))
    return identity


def identity_contacts(identity: dict[str, Any]) -> list[dict[str, Any]]:
    contacts: list[dict[str, Any]] = []
    email = str(identity.get("email") or "").strip()
    phone = str(identity.get("phone") or "").strip()
    pronouns = str(identity.get("pronouns") or "").strip()
    show_pronouns = identity.get("show_pronouns")
    if show_pronouns is None:
        show_pronouns = True
    if email:
        contacts.append({"label": "Email", "value": email, "href": f"mailto:{email}"})
    if phone:
        try:
            national = normalize_us_phone(phone)
            digits = _PHONE_DIGITS_RE.sub("", national)
            contacts.append(
                {
                    "label": "Phone",
                    "value": format_phone_display(national),
                    "href": f"tel:+1{digits}" if digits else None,
                }
            )
        except ValueError:
            contacts.append({"label": "Phone", "value": phone, "href": None})
    if pronouns and show_pronouns:
        contacts.append({"label": "Pronouns", "value": pronouns, "href": None})
    for link in identity.get("links") or []:
        if not isinstance(link, dict):
            continue
        title = str(link.get("title") or "").strip() or "Link"
        url = str(link.get("url") or "").strip()
        if not url:
            continue
        try:
            href = normalize_web_url(url)
        except ValueError:
            href = url if "://" in url else f"https://{url}"
        display = href
        if display.startswith("https://"):
            display = display[len("https://") :]
        elif display.startswith("http://"):
            display = display[len("http://") :]
        contacts.append({"label": title, "value": display or title, "href": href})
    return contacts


def display_pronouns(identity: dict[str, Any]) -> str:
    if identity.get("show_pronouns") is False:
        return ""
    return str(identity.get("pronouns") or "").strip()


def _empty_identity() -> dict[str, Any]:
    return {
        "preferred_name": "",
        "email": "",
        "phone": "",
        "pronouns": "",
        "show_pronouns": True,
        "links": [],
    }


def _url_key(url: str) -> str:
    try:
        normalized = normalize_web_url(url)
    except ValueError:
        normalized = (url or "").strip().lower()
    parsed = urlparse(normalized)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parsed.path or "").rstrip("/").lower()
    return f"{host}{path}"


def _title_from_url(url: str) -> str:
    try:
        host = urlparse(normalize_web_url(url)).netloc.lower()
    except ValueError:
        return "Link"
    if host.startswith("www."):
        host = host[4:]
    if "linkedin.com" in host:
        return "LinkedIn"
    if "github.com" in host:
        return "GitHub"
    return host.split(".")[0].title() if host else "Link"
