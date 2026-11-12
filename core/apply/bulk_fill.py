"""Bulk-fill field matching — pure logic, testable without Playwright."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_FILL_STATUSES = frozenset({"confirmed", "edited"})

_ANSWER_KEY_PHRASES: dict[str, tuple[str, ...]] = {
    "work_authorization": (
        "authorized to work",
        "work authorization",
        "legally authorized",
        "eligible to work",
        "right to work",
    ),
    "sponsorship": (
        "visa sponsorship",
        "require sponsorship",
        "immigration sponsorship",
        "work authorization sponsorship",
    ),
    "salary_expectation": (
        "salary",
        "compensation",
        "pay expectation",
        "desired salary",
        "expected salary",
    ),
    "start_date": (
        "start date",
        "available to start",
        "earliest start",
        "when can you start",
    ),
    "why_this_role": (
        "why are you interested",
        "why do you want",
        "why this role",
        "why this position",
    ),
    "relevant_experience": (
        "relevant experience",
        "describe your experience",
        "why are you qualified",
        "summary of qualifications",
    ),
}

_IDENTITY_HINTS: dict[str, tuple[str, ...]] = {
    "email": ("email", "e-mail"),
    "phone": ("phone", "mobile", "telephone", "cell"),
    "first_name": ("first name", "given name", "fname", "firstname"),
    "last_name": ("last name", "family name", "surname", "lname", "lastname"),
    "full_name": ("full name", "your name", "legal name", "name"),
    "linkedin": ("linkedin",),
    "website": ("website", "portfolio", "personal site"),
}

_GREENHOUSE_NAMES: dict[str, tuple[str, ...]] = {
    "first_name": ("job_application[first_name]", "first_name"),
    "last_name": ("job_application[last_name]", "last_name"),
    "email": ("job_application[email]", "email"),
    "phone": ("job_application[phone]", "phone"),
}

_LEVER_NAMES: dict[str, tuple[str, ...]] = {
    "full_name": ("name",),
    "email": ("email",),
    "phone": ("phone",),
    "linkedin": ("urls[LinkedIn]", "urls[linkedIn]"),
}

_ASHBY_NAMES: dict[str, tuple[str, ...]] = {
    "first_name": ("_systemfield_name", "first_name", "firstname"),
    "last_name": ("last_name", "lastname", "surname"),
    "email": ("_systemfield_email", "email"),
    "phone": ("phone", "phone_number"),
    "linkedin": ("linkedin", "linked_in"),
}


@dataclass
class BulkFillGap:
    label: str
    selector: str | None = None
    reason: str = "no_match"


@dataclass
class BulkFillReport:
    filled: int = 0
    skipped: int = 0
    gaps: list[BulkFillGap] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "filled": self.filled,
            "skipped": self.skipped,
            "gaps": [
                {"label": g.label, "selector": g.selector, "reason": g.reason} for g in self.gaps
            ],
            "errors": list(self.errors),
        }


@dataclass
class FormField:
    selector: str
    tag: str
    input_type: str
    name: str
    field_id: str
    label: str
    placeholder: str
    aria_label: str
    required: bool


@dataclass
class FillAction:
    selector: str
    value: str
    tag: str
    input_type: str
    label: str
    source: str


def normalize_label(text: str) -> str:
    lowered = (text or "").lower().strip()
    lowered = re.sub(r"[^\w\s]", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _split_name(full: str) -> tuple[str, str]:
    parts = (full or "").strip().split(None, 1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _confirmed_answers(answers: list[Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in answers or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "")
        if status not in _FILL_STATUSES:
            continue
        value = str(item.get("final_answer") or item.get("suggested_answer") or "").strip()
        if not value:
            continue
        key = str(item.get("key") or "").strip()
        if key:
            out[key] = value
    return out


def _identity_values(identity: dict[str, Any]) -> dict[str, str]:
    preferred = str(identity.get("preferred_name") or identity.get("full_name") or "").strip()
    first, last = _split_name(preferred)
    return {
        "email": str(identity.get("email") or "").strip(),
        "phone": str(identity.get("phone") or "").strip(),
        "first_name": first,
        "last_name": last,
        "full_name": preferred,
    }


def _label_blob(field: FormField) -> str:
    return normalize_label(
        " ".join(
            part
            for part in (field.label, field.placeholder, field.aria_label, field.name, field.field_id)
            if part
        )
    )


def _match_answer_key(blob: str) -> str | None:
    for key, phrases in _ANSWER_KEY_PHRASES.items():
        for phrase in phrases:
            if phrase in blob:
                return key
    return None


def _match_identity_key(blob: str, name: str, field_id: str) -> str | None:
    combined = normalize_label(f"{blob} {name} {field_id}")
    for key, hints in _IDENTITY_HINTS.items():
        for hint in hints:
            if hint in combined:
                return key
    return None


def _ats_name_match(name: str, field_id: str, ats_type: str | None) -> str | None:
    target = f"{name} {field_id}".lower()
    if ats_type == "greenhouse":
        patterns = _GREENHOUSE_NAMES
    elif ats_type == "lever":
        patterns = _LEVER_NAMES
    elif ats_type == "ashby":
        patterns = _ASHBY_NAMES
    else:
        patterns = {}
    for key, variants in patterns.items():
        for variant in variants:
            if variant.lower() in target:
                return key
    return None


def resolve_field_value(
    field: FormField,
    *,
    answers: dict[str, str],
    identity: dict[str, str],
    cover_letter: str | None,
    ats_type: str | None = None,
) -> tuple[str | None, str]:
    """Return (value, source) or (None, '') if no match."""
    blob = _label_blob(field)
    name = field.name or field.field_id

    ats_key = _ats_name_match(field.name, field.field_id, ats_type)
    if ats_key:
        if ats_key in identity and identity[ats_key]:
            return identity[ats_key], "identity"
        if ats_key in answers:
            return answers[ats_key], "packet"

    identity_key = _match_identity_key(blob, name, field.field_id)
    if identity_key and identity.get(identity_key):
        return identity[identity_key], "identity"

    answer_key = _match_answer_key(blob)
    if answer_key and answer_key in answers:
        return answers[answer_key], "packet"

    if field.tag == "textarea" and cover_letter and any(
        phrase in blob
        for phrase in ("cover letter", "additional information", "anything else", "message")
    ):
        return cover_letter, "cover_letter"

    return None, ""


def build_fill_actions(
    fields: list[FormField],
    *,
    packet_answers: list[Any],
    identity: dict[str, Any],
    cover_letter: str | None,
    ats_type: str | None = None,
) -> tuple[list[FillAction], list[BulkFillGap]]:
    answers = _confirmed_answers(packet_answers)
    id_values = _identity_values(identity)
    actions: list[FillAction] = []
    gaps: list[BulkFillGap] = []
    seen_selectors: set[str] = set()

    for form_field in fields:
        if form_field.selector in seen_selectors:
            continue
        if form_field.tag == "input" and form_field.input_type in {"hidden", "submit", "button", "file"}:
            continue

        value, source = resolve_field_value(
            form_field,
            answers=answers,
            identity=id_values,
            cover_letter=cover_letter,
            ats_type=ats_type,
        )
        label = form_field.label or form_field.placeholder or form_field.name or form_field.selector

        if value is None:
            if form_field.required:
                gaps.append(
                    BulkFillGap(
                        label=label,
                        selector=form_field.selector,
                        reason="required_unmatched",
                    )
                )
            continue

        seen_selectors.add(form_field.selector)
        actions.append(
            FillAction(
                selector=form_field.selector,
                value=value,
                tag=form_field.tag,
                input_type=form_field.input_type,
                label=label,
                source=source,
            )
        )

    return actions, gaps
