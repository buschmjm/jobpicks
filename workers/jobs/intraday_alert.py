"""Pro intraday alert emails when new jobs are topped up (Workstream C3)."""

from __future__ import annotations

import logging

from api.email import SmtpConfig, get_email_sender
from api.repositories.events_repo import log_event
from api.services.revenue_service import email_preferences_service
from core.entitlements import entitlements_for_user
from core.models import EventType, User
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def send_intraday_alert(session: Session, user: User, *, new_jobs_count: int) -> bool:
    if new_jobs_count <= 0 or user.unsubscribed_at is not None:
        return False
    entitlements = entitlements_for_user(user)
    if not entitlements.intraday_alerts:
        return False

    config = SmtpConfig.from_env()
    deck_url = f"{config.app_base_url}/deck"
    unsubscribe_url = email_preferences_service.unsubscribe_url(user)
    subject = f"{new_jobs_count} new match{'es' if new_jobs_count != 1 else ''} just landed"
    html = (
        "<!DOCTYPE html><html><body style='font-family:system-ui;max-width:520px;margin:24px auto;'>"
        f"<h2>{subject}</h2>"
        "<p>Your Pro alert: fresh jobs were added to your swipe deck.</p>"
        f"<p><a href='{deck_url}'>Open your deck</a></p>"
        f"<p style='font-size:12px;color:#666;'><a href='{unsubscribe_url}'>Unsubscribe from emails</a></p>"
        "</body></html>"
    )
    sender = get_email_sender()
    sender.send_html(user.email, subject, html, list_unsubscribe_url=unsubscribe_url)

    log_event(
        session,
        event_type=EventType.INTRADAY_ALERT_SENT.value,
        user_id=user.id,
        payload={"new_jobs_count": new_jobs_count},
    )
    return True
