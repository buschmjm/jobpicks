"""User persistence."""

from __future__ import annotations

import uuid

from core.models import User
from sqlalchemy import select
from sqlalchemy.orm import Session


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self._session.scalar(select(User).where(User.email == email))

    def get_or_create_by_email(self, email: str) -> User:
        normalized = email.lower().strip()
        existing = self.get_by_email(normalized)
        if existing is not None:
            return existing
        user = User(email=normalized)
        from core.referrals import ensure_email_unsubscribe_token, ensure_referral_code

        self._session.add(user)
        self._session.flush()
        ensure_referral_code(self._session, user)
        ensure_email_unsubscribe_token(user)
        return user
