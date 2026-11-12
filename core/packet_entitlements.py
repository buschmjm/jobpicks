"""Application packet limits — lifetime for Free, monthly for Pro."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.entitlements import FREE_LIFETIME_PACKET_LIMIT, PRO_PACKETS_PER_MONTH, is_pro_active
from core.models import ApplicationPacket, ApplicationPacketStatus, User

COUNTABLE_PACKET_STATUSES = (
    ApplicationPacketStatus.GENERATING.value,
    ApplicationPacketStatus.READY.value,
    ApplicationPacketStatus.OPENED.value,
)


class PacketLimitExceeded(Exception):
    """Packet cap reached for the user's plan."""

    def __init__(self, used: int, limit: int, *, monthly: bool = False) -> None:
        self.used = used
        self.limit = limit
        self.monthly = monthly
        period = "month" if monthly else "lifetime"
        super().__init__(
            f"Your plan includes {limit} AI application packets per {period}. "
            f"You've used {used}."
        )


def lifetime_packet_limit_for_user(user: User) -> int | None:
    """Return lifetime cap for free users; monthly cap for Pro."""
    if is_pro_active(user):
        return PRO_PACKETS_PER_MONTH
    return FREE_LIFETIME_PACKET_LIMIT


def lifetime_packets_used(session: Session, user_id: uuid.UUID) -> int:
    count = session.scalar(
        select(func.count())
        .select_from(ApplicationPacket)
        .where(
            ApplicationPacket.user_id == user_id,
            ApplicationPacket.status.in_(COUNTABLE_PACKET_STATUSES),
        )
    )
    return int(count or 0)


def packets_used_this_month(
    session: Session,
    user_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> int:
    ref = now or datetime.now(tz=UTC)
    start = datetime(ref.year, ref.month, 1, tzinfo=UTC)
    count = session.scalar(
        select(func.count())
        .select_from(ApplicationPacket)
        .where(
            ApplicationPacket.user_id == user_id,
            ApplicationPacket.created_at >= start,
            ApplicationPacket.status.in_(COUNTABLE_PACKET_STATUSES),
        )
    )
    return int(count or 0)


def _has_packet_for_todo(session: Session, user_id: uuid.UUID, todo_item_id: uuid.UUID) -> bool:
    existing = session.scalar(
        select(ApplicationPacket.id)
        .where(
            ApplicationPacket.user_id == user_id,
            ApplicationPacket.todo_item_id == todo_item_id,
        )
        .limit(1)
    )
    return existing is not None


def packets_used_for_user(session: Session, user: User) -> int:
    if is_pro_active(user):
        return packets_used_this_month(session, user.id)
    return lifetime_packets_used(session, user.id)


def can_generate_packet(session: Session, user: User, todo_item_id: uuid.UUID) -> bool:
    """Whether packet generation is allowed (regenerate existing todo or under cap)."""
    if _has_packet_for_todo(session, user.id, todo_item_id):
        return True
    if is_pro_active(user):
        return packets_used_this_month(session, user.id) < PRO_PACKETS_PER_MONTH
    return lifetime_packets_used(session, user.id) < FREE_LIFETIME_PACKET_LIMIT


def ensure_can_generate_packet(session: Session, user: User, todo_item_id: uuid.UUID) -> None:
    if can_generate_packet(session, user, todo_item_id):
        return
    if is_pro_active(user):
        used = packets_used_this_month(session, user.id)
        raise PacketLimitExceeded(used=used, limit=PRO_PACKETS_PER_MONTH, monthly=True)
    raise PacketLimitExceeded(
        used=lifetime_packets_used(session, user.id),
        limit=FREE_LIFETIME_PACKET_LIMIT,
        monthly=False,
    )
