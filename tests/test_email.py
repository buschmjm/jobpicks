"""Tests for digest email rendering and SMTP sender."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from api.digest_cards import format_salary, queue_item_to_digest_card
from api.email import LoggingEmailSender, SmtpConfig, email_backend_status, html_to_plain
from core.models import RemoteMode
from workers.jobs.daily_email import render_digest_html


class _JobStub:
    def __init__(self) -> None:
        self.salary_min = 140_000
        self.salary_max = 170_000
        self.remote_mode = RemoteMode.REMOTE
        self.location_text = "Remote"
        self.country = "US"
        self.date_posted = date(2026, 8, 26)
        self.first_seen = datetime(2026, 8, 26, tzinfo=UTC)
        self.primary_source = "Adzuna"
        self.source_url = "https://example.com/job/1"
        self.title = "Senior Platform Engineer"
        self.company_name = "Acme Corp"


class _ItemStub:
    def __init__(self) -> None:
        self.score = 0.87
        self.explain = {
            "why_bullets": ["Strong Kubernetes overlap"],
            "caution_bullets": ["Wants Go experience"],
        }
        self.job = _JobStub()


def test_format_salary_range() -> None:
    job = _JobStub()
    assert format_salary(job) == "$140–170k"


def test_queue_item_to_digest_card() -> None:
    card = queue_item_to_digest_card(_ItemStub(), _ItemStub().job)
    assert card.match_score == 87
    assert card.title == "Senior Platform Engineer"
    assert card.why_bullets == ["Strong Kubernetes overlap"]


def test_render_digest_html_includes_count_and_cards() -> None:
    html = render_digest_html(
        new_jobs_count=5,
        cards=[
            {
                "match_score": 87,
                "title": "Senior Platform Engineer",
                "company": "Acme Corp",
                "salary_display": "$140–170k",
                "work_mode_display": "Remote (US)",
                "posted_ago": "1d ago",
                "source": "Adzuna",
                "why_bullets": ["Strong Kubernetes overlap"],
                "caution_bullets": [],
                "source_url": "https://example.com/job/1",
            }
        ],
        deck_url="http://localhost:8000/deck",
        unsubscribe_url="http://localhost:8000/api/email/unsubscribe/test-token",
        dev_note="Dev note",
    )
    assert "5 new jobs" in html
    assert "Senior Platform Engineer" in html
    assert "Dev note" in html


def test_logging_email_sender_records_messages() -> None:
    sender = LoggingEmailSender(sent=[])
    sender.send_html("user@example.com", "Subject", "<p>hi</p>")
    assert sender.sent == [("user@example.com", "Subject", "<p>hi</p>")]


def test_smtp_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USER", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "pass")
    monkeypatch.setenv("EMAIL_FROM", "jobs@test.local")
    monkeypatch.setenv("APP_BASE_URL", "https://jobs.test/")
    cfg = SmtpConfig.from_env()
    assert cfg.host == "smtp.test"
    assert cfg.port == 2525
    assert cfg.app_base_url == "https://jobs.test"
    assert cfg.is_configured() is True


def test_smtp_config_not_configured_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    cfg = SmtpConfig.from_env()
    assert cfg.is_configured() is False


def test_email_backend_status_log_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_BACKEND", "log")
    status = email_backend_status()
    assert status["backend"] == "log"
    assert status["ready"] is True


def test_html_to_plain_strips_tags() -> None:
    plain = html_to_plain("<p>Hello <strong>world</strong></p>")
    assert "Hello" in plain
    assert "world" in plain
    assert "<" not in plain
