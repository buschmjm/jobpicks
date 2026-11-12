"""Auth service — DB-backed users with signed session tokens."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from core.models import EventType
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import EmailStr
from sqlalchemy.orm import Session

from api.auth import create_magic_link_token, create_session_token
from api.email import SmtpConfig, get_email_sender
from api.repositories.events_repo import EventsRepository
from api.repositories.user_repo import UserRepository

_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
_jinja = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _magic_link_email_html(verify_url: str) -> str:
    return _jinja.get_template("magic_link_email.html").render(verify_url=verify_url)


class AuthService:
    def request_magic_link(self, session: Session, email: EmailStr) -> tuple[str, UUID]:
        users = UserRepository(session)
        user = users.get_or_create_by_email(str(email))
        token = create_magic_link_token(email)
        session.commit()

        config = SmtpConfig.from_env()
        verify_url = f"{config.app_base_url}/auth/verify?token={token}"
        if os.environ.get("APP_ENV", "development") != "development" or os.environ.get(
            "SEND_MAGIC_LINK_IN_DEV", ""
        ).lower() in {"1", "true", "yes"}:
            sender = get_email_sender()
            sender.send_html(
                str(email),
                "Sign in to Job Platform",
                _magic_link_email_html(verify_url),
            )
        return token, user.id

    def verify_and_create_session(self, session: Session, email: str) -> tuple[str, UUID]:
        users = UserRepository(session)
        events = EventsRepository(session)
        user = users.get_or_create_by_email(email)
        events.append(EventType.LOGIN, user_id=user.id, payload={"email": email})
        session_token = create_session_token(user.id, email)
        session.commit()
        return session_token, user.id


auth_service = AuthService()
