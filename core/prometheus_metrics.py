"""Prometheus metrics exposition (Workstream D)."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.entitlements import PlanTier, SubscriptionStatus
from core.models import Digest, Event, LlmCallLog, ReferralRedemption, User


def render_prometheus_metrics(session: Session) -> str:
    now = datetime.now(tz=UTC)
    cutoff_24h = now - timedelta(hours=24)

    event_rows = session.execute(
        select(Event.type, func.count())
        .where(Event.created_at >= cutoff_24h)
        .group_by(Event.type)
    ).all()
    event_counts: dict[str, int] = defaultdict(int)
    for event_type, count in event_rows:
        key = event_type.value if hasattr(event_type, "value") else str(event_type)
        event_counts[key] = int(count)

    pro_users = int(
        session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.plan_tier == PlanTier.PRO.value,
                User.subscription_status.in_(
                    [SubscriptionStatus.ACTIVE.value, SubscriptionStatus.TRIALING.value]
                ),
            )
        )
        or 0
    )
    free_users = int(session.scalar(select(func.count()).select_from(User)) or 0) - pro_users

    digests_sent = int(
        session.scalar(
            select(func.count()).select_from(Digest).where(Digest.sent_at >= cutoff_24h)
        )
        or 0
    )
    digests_opened = int(
        session.scalar(
            select(func.count()).select_from(Digest).where(Digest.opened_at >= cutoff_24h)
        )
        or 0
    )
    referrals = int(
        session.scalar(
            select(func.count())
            .select_from(ReferralRedemption)
            .where(ReferralRedemption.redeemed_at >= cutoff_24h)
        )
        or 0
    )
    llm_calls = int(
        session.scalar(
            select(func.count()).select_from(LlmCallLog).where(LlmCallLog.created_at >= cutoff_24h)
        )
        or 0
    )

    lines = [
        "# HELP jobdeck_users_total Active users by plan tier",
        "# TYPE jobdeck_users_total gauge",
        f'jobdeck_users_total{{tier="pro"}} {pro_users}',
        f'jobdeck_users_total{{tier="free"}} {free_users}',
        "",
        "# HELP jobdeck_events_24h Product events in the last 24 hours",
        "# TYPE jobdeck_events_24h counter",
    ]
    for event_type, count in sorted(event_counts.items()):
        lines.append(f'jobdeck_events_24h{{type="{event_type}"}} {count}')

    lines.extend(
        [
            "",
            "# HELP jobdeck_digests_24h Digest emails sent in the last 24 hours",
            "# TYPE jobdeck_digests_24h counter",
            f"jobdeck_digests_24h {digests_sent}",
            "",
            "# HELP jobdeck_digest_opens_24h Digest opens in the last 24 hours",
            "# TYPE jobdeck_digest_opens_24h counter",
            f"jobdeck_digest_opens_24h {digests_opened}",
            "",
            "# HELP jobdeck_referrals_24h Referral redemptions in the last 24 hours",
            "# TYPE jobdeck_referrals_24h counter",
            f"jobdeck_referrals_24h {referrals}",
            "",
            "# HELP jobdeck_llm_calls_24h LLM calls logged in the last 24 hours",
            "# TYPE jobdeck_llm_calls_24h counter",
            f"jobdeck_llm_calls_24h {llm_calls}",
            "",
        ]
    )
    return "\n".join(lines) + "\n"
