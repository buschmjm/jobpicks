"""Unit tests for bulk-fill field matching."""

from __future__ import annotations

from core.apply.bulk_fill import FormField, build_fill_actions, normalize_label, resolve_field_value


def _field(**kwargs: object) -> FormField:
    defaults = {
        "selector": "#email",
        "tag": "input",
        "input_type": "email",
        "name": "email",
        "field_id": "email",
        "label": "Email",
        "placeholder": "",
        "aria_label": "",
        "required": True,
    }
    defaults.update(kwargs)
    return FormField(**defaults)  # type: ignore[arg-type]


def test_normalize_label_strips_punctuation() -> None:
    assert normalize_label("Work Authorization?") == "work authorization"


def test_resolve_email_from_identity() -> None:
    value, source = resolve_field_value(
        _field(label="Email address", name="email"),
        answers={},
        identity={"email": "alex@example.com"},
        cover_letter=None,
    )
    assert value == "alex@example.com"
    assert source == "identity"


def test_resolve_work_authorization_from_packet() -> None:
    field = _field(
        selector="#question",
        tag="textarea",
        input_type="text",
        name="",
        field_id="",
        label="Are you authorized to work in the United States?",
    )
    value, source = resolve_field_value(
        field,
        answers={"work_authorization": "Yes, I am a US citizen."},
        identity={},
        cover_letter=None,
    )
    assert "citizen" in (value or "")
    assert source == "packet"


def test_build_fill_actions_skips_pending_answers() -> None:
    actions, gaps = build_fill_actions(
        [
            _field(
                selector="#auth",
                label="Work authorization",
                tag="textarea",
                input_type="text",
                name="work_auth",
                field_id="auth",
            ),
            _field(selector="#email", label="Email"),
        ],
        packet_answers=[
            {
                "key": "work_authorization",
                "question_text": "Work auth?",
                "suggested_answer": "Yes",
                "status": "pending",
            }
        ],
        identity={"email": "a@b.com"},
        cover_letter=None,
    )
    assert len(actions) == 1
    assert actions[0].selector == "#email"
    assert any(g.reason == "required_unmatched" for g in gaps)


def test_greenhouse_first_name_ats_match() -> None:
    field = _field(
        selector="#first_name",
        name="job_application[first_name]",
        field_id="first_name",
        label="",
        input_type="text",
    )
    value, source = resolve_field_value(
        field,
        answers={},
        identity={"first_name": "Alex", "preferred_name": "Alex Example"},
        cover_letter=None,
        ats_type="greenhouse",
    )
    assert value == "Alex"
    assert source == "identity"


def test_ashby_systemfield_email_match() -> None:
    field = _field(
        selector="#ashby-email",
        name="_systemfield_email",
        field_id="_systemfield_email",
        label="",
        input_type="email",
    )
    value, source = resolve_field_value(
        field,
        answers={},
        identity={"email": "ashby@example.com"},
        cover_letter=None,
        ats_type="ashby",
    )
    assert value == "ashby@example.com"
    assert source == "identity"
