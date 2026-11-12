#!/usr/bin/env python3
"""Re-run the initial training deck backfill for a user account."""

from __future__ import annotations

import argparse
import uuid

from core.database import SessionLocal
from core.deck_bootstrap import queued_count
from core.models import Profile, QueueState, User, UserJobQueue
from sqlalchemy import delete, select
from workers.consumer import enqueue_job


def _resolve_user_id(session, *, email: str | None, user_id: str | None) -> uuid.UUID:
    if user_id:
        return uuid.UUID(user_id)
    if not email:
        profile = session.scalar(
            select(Profile)
            .where(Profile.onboarding_completed_at.is_not(None))
            .order_by(Profile.onboarding_completed_at.desc())
        )
        if profile is None:
            raise SystemExit("No onboarded users found; pass --email or --user-id")
        print(f"Using most recently onboarded user: {profile.user_id}")
        return profile.user_id

    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        raise SystemExit(f"No user found for email {email!r}")
    return user.id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", help="User email address")
    parser.add_argument("--user-id", help="User UUID")
    parser.add_argument(
        "--clear-queued",
        action="store_true",
        help="Remove queued (unswiped) deck rows before backfill",
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        uid = _resolve_user_id(session, email=args.email, user_id=args.user_id)
        profile = session.scalar(select(Profile).where(Profile.user_id == uid))
        if profile is None or profile.onboarding_completed_at is None:
            raise SystemExit(f"User {uid} has not completed onboarding")

        before = queued_count(session, uid)
        if args.clear_queued and before:
            session.execute(
                delete(UserJobQueue)
                .where(UserJobQueue.user_id == uid)
                .where(UserJobQueue.state == QueueState.QUEUED.value)
            )
            session.commit()
            print(f"Cleared {before} queued deck rows")

        profile.last_backfill_at = None
        profile.awaiting_deck_backfill = False
        enqueue_job(session, "queue_backfill", {"user_id": str(uid)}, priority=5)
        session.commit()
        print(f"Enqueued queue_backfill for user {uid}")


if __name__ == "__main__":
    main()
