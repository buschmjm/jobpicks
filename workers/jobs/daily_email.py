"""Daily digest email (E2.11) with per-timezone send window (Workstream C3)."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from api.digest_cards import card_to_template_context, queue_item_to_digest_card
from api.email import LoggingEmailSender, SmtpConfig, SmtpEmailSender
from api.repositories.events_repo import log_event
from api.services.revenue_service import email_preferences_service
from core.database import SessionLocal
from core.digest_schedule import is_digest_send_window
from core.models import Digest, EventType, Profile, QueueState, User, UserJobQueue
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "api" / "templates"
_jinja = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _get_sender() -> SmtpEmailSender | LoggingEmailSender:
    if os.environ.get("EMAIL_BACKEND", "").lower() == "log":
        return LoggingEmailSender(sent=[])
    return SmtpEmailSender(SmtpConfig.from_env())


def _last_digest_sent_at(session: Session, user_id: UUID) -> datetime | None:
    row = session.scalar(
        select(Digest.sent_at)
        .where(Digest.user_id == user_id, Digest.sent_at.is_not(None))
        .order_by(Digest.sent_at.desc())
        .limit(1)
    )
    return row


def _new_queue_items(session: Session, user_id: UUID, since: datetime | None) -> list[UserJobQueue]:
    stmt = (
        select(UserJobQueue)
        .options(joinedload(UserJobQueue.job))
        .where(
            UserJobQueue.user_id == user_id,
            UserJobQueue.state == QueueState.QUEUED.value,
        )
    )
    if since is not None:
        stmt = stmt.where(UserJobQueue.enqueued_at > since)
    items = list(session.scalars(stmt).unique().all())
    items.sort(key=lambda item: float(item.score or 0), reverse=True)
    return items


def _eligible_users(session: Session) -> list[User]:
    return list(
        session.scalars(
            select(User)
            .join(Profile, Profile.user_id == User.id)
            .where(
                User.is_active.is_(True),
                User.unsubscribed_at.is_(None),
                Profile.onboarding_completed_at.is_not(None),
            )
        ).all()
    )


def render_digest_html(
    *,
    new_jobs_count: int,
    cards: list[dict[str, Any]],
    deck_url: str,
    unsubscribe_url: str,
    dev_note: str | None = None,
    applied_this_week: int | None = None,
    streak_days: int | None = None,
) -> str:
    template = _jinja.get_template("digest_email.html")
    return template.render(
        new_jobs_count=new_jobs_count,
        cards=cards,
        deck_url=deck_url,
        unsubscribe_url=unsubscribe_url,
        dev_note=dev_note,
        applied_this_week=applied_this_week,
        streak_days=streak_days,
    )


def send_user_digest(session: Session, user: User, sender: SmtpEmailSender | LoggingEmailSender) -> bool:
    now = datetime.now(UTC)
    if not is_digest_send_window(timezone=user.timezone, now=now):
        return False

    since = _last_digest_sent_at(session, user.id)
    new_items = _new_queue_items(session, user.id, since)
    if not new_items:
        return False

    config = SmtpConfig.from_env()
    tracking_token = secrets.token_urlsafe(24)
    deck_url = f"{config.app_base_url}/api/events/digest/open/{tracking_token}"
    unsubscribe_url = email_preferences_service.unsubscribe_url(user)

    top_items = new_items[:3]
    cards = [
        card_to_template_context(queue_item_to_digest_card(item, item.job, now=now))
        for item in top_items
        if item.job is not None
    ]
    dev_note = None
    if os.environ.get("APP_ENV", "development") == "development":
        dev_note = (
            "Dev note: open the deck at /deck while signed in (session cookie). "
            "The link above tracks digest opens and redirects to /deck."
        )

    from core.engagement import engagement_stats

    stats = engagement_stats(session, user.id)

    html = render_digest_html(
        new_jobs_count=len(new_items),
        cards=cards,
        deck_url=deck_url,
        unsubscribe_url=unsubscribe_url,
        dev_note=dev_note,
        applied_this_week=stats["applied_this_week"],
        streak_days=stats["streak_days"],
    )
    subject = f"{len(new_items)} new job{'s' if len(new_items) != 1 else ''} in your queue"
    sender.send_html(user.email, subject, html, list_unsubscribe_url=unsubscribe_url)

    digest = Digest(
        user_id=user.id,
        sent_at=now,
        new_jobs_count=len(new_items),
        top_job_ids=[str(item.job_id) for item in top_items],
        email_subject=subject,
        tracking_token=tracking_token,
        payload={"cards": cards},
    )
    session.add(digest)
    log_event(
        session,
        event_type=EventType.DIGEST_SENT,
        user_id=user.id,
        entity_id=digest.id,
        payload={"new_jobs_count": len(new_items), "tracking_token": tracking_token},
    )
    return True


def run_daily_email(session: Session | None = None) -> int:
    """Send digests; returns count of emails sent."""
    owns_session = session is None
    db = session or SessionLocal()
    sender = _get_sender()
    sent = 0
    try:
        for user in _eligible_users(db):
            try:
                if send_user_digest(db, user, sender):
                    sent += 1
            except Exception:
                logger.exception("Failed digest for user %s", user.id)
                db.rollback()
                continue
        db.commit()
    finally:
        if owns_session:
            db.close()
    logger.info("daily_email complete: sent=%d", sent)
    return sent


def main() -> None:
    run_daily_email()
