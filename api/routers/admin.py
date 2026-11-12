"""Admin dashboard — server-rendered Jinja2 pages (plan §11, E2.12)."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.entitlements import PlanTier, SubscriptionStatus
from core.metrics import (
    DashboardMetrics,
    EventRow,
    QuotaSnapshot,
    SourceHealthRow,
    build_dashboard_metrics,
    source_health_from_fetches,
)
from core.models import (
    Digest,
    Event,
    JobSource,
    LlmCallLog,
    QueueState,
    ReferralRedemption,
    ScoringConfig,
    User,
    UserJobQueue,
)
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from ingest.quota_store import load_quota_tracker
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from workers.jobs.source_health import SOURCE_HEALTH_KEY

from api.deps import get_db

router = APIRouter(prefix="/admin", tags=["admin"])

_templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def require_admin_secret(x_admin_secret: str | None = Header(default=None)) -> None:
    expected = os.environ.get("ADMIN_SECRET")
    if not expected:
        if os.environ.get("APP_ENV", "development") == "development":
            expected = "dev-admin-secret"
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ADMIN_SECRET not configured",
            )
    if x_admin_secret != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin secret")


def _load_recent_events(session: Session, *, days: int = 7) -> list[EventRow]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = session.scalars(select(Event).where(Event.created_at >= cutoff).order_by(Event.created_at)).all()
    return [
        EventRow(
            user_id=row.user_id,
            type=row.type.value if hasattr(row.type, "value") else str(row.type),
            created_at=row.created_at,
            payload=row.payload,
        )
        for row in rows
    ]


def _load_queue_depth(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(UserJobQueue).where(UserJobQueue.state == QueueState.QUEUED.value)
        )
        or 0
    )


def _load_source_rows(session: Session) -> list[tuple[str, datetime]]:
    rows = session.execute(select(JobSource.source_name, JobSource.fetched_at)).all()
    return [(str(source), fetched_at) for source, fetched_at in rows]


def _load_quota_snapshots(session: Session) -> list[QuotaSnapshot]:
    tracker = load_quota_tracker(session)
    today = datetime.now(UTC).date()
    return [
        QuotaSnapshot(source=source, used=tracker.used(source), limit=budget.daily_limit, day=today)
        for source, budget in tracker.budgets.items()
    ]


def _load_probe_health(session: Session) -> dict[str, dict[str, Any]]:
    row = session.get(ScoringConfig, SOURCE_HEALTH_KEY)
    if row is None:
        return {}
    value = row.value or {}
    sources = value.get("sources") or {}
    return {str(k): v for k, v in sources.items()}


def _merge_source_health(
    fetch_rows: list[tuple[str, datetime]],
    probes: dict[str, dict[str, Any]],
) -> list[SourceHealthRow]:
    merged = {row.source_name: row for row in source_health_from_fetches(fetch_rows)}
    for source, probe in probes.items():
        existing = merged.get(source)
        status = str(probe.get("status", "unknown"))
        error = probe.get("error")
        merged[source] = SourceHealthRow(
            source_name=source,
            jobs_last_24h=existing.jobs_last_24h if existing else 0,
            last_fetched_at=existing.last_fetched_at if existing else None,
            status=status,
            error=str(error) if error else None,
        )
    return sorted(merged.values(), key=lambda row: row.source_name)


def _load_business_metrics(session: Session) -> dict[str, int | float]:
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    total_users = int(session.scalar(select(func.count()).select_from(User)) or 0)
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
    digests_sent = int(
        session.scalar(
            select(func.count()).select_from(Digest).where(Digest.sent_at >= cutoff)
        )
        or 0
    )
    digests_opened = int(
        session.scalar(
            select(func.count()).select_from(Digest).where(Digest.opened_at >= cutoff)
        )
        or 0
    )
    open_rate = round(digests_opened / digests_sent, 4) if digests_sent else 0.0
    referrals_total = int(session.scalar(select(func.count()).select_from(ReferralRedemption)) or 0)
    llm_calls = int(
        session.scalar(
            select(func.count()).select_from(LlmCallLog).where(LlmCallLog.created_at >= cutoff)
        )
        or 0
    )
    return {
        "pro_users": pro_users,
        "free_users": max(0, total_users - pro_users),
        "referrals_total": referrals_total,
        "digests_sent_24h": digests_sent,
        "digest_open_rate_24h": open_rate,
        "llm_calls_24h": llm_calls,
    }


def compute_dashboard(session: Session) -> DashboardMetrics:
    business = _load_business_metrics(session)
    return build_dashboard_metrics(
        events=_load_recent_events(session),
        queue_depth=_load_queue_depth(session),
        source_health=_merge_source_health(_load_source_rows(session), _load_probe_health(session)),
        quota=_load_quota_snapshots(session),
        pro_users=int(business["pro_users"]),
        free_users=int(business["free_users"]),
        referrals_total=int(business["referrals_total"]),
        digests_sent_24h=int(business["digests_sent_24h"]),
        digest_open_rate_24h=float(business["digest_open_rate_24h"]),
        llm_calls_24h=int(business["llm_calls_24h"]),
    )


@router.get("/api/summary")
def admin_summary_json(
    session: Session = Depends(get_db),
    _: None = Depends(require_admin_secret),
) -> dict[str, object]:
    """JSON admin metrics for automation (Workstream E)."""
    metrics = compute_dashboard(session)
    return {
        "dau": metrics.dau,
        "wau": metrics.wau,
        "queue_depth": metrics.queue_depth,
        "pro_users": metrics.pro_users,
        "free_users": metrics.free_users,
        "referrals_total": metrics.referrals_total,
        "digests_sent_24h": metrics.digests_sent_24h,
        "digest_open_rate_24h": metrics.digest_open_rate_24h,
        "llm_calls_24h": metrics.llm_calls_24h,
        "right_swipe_rate": metrics.right_swipe_rate,
        "event_counts": metrics.event_counts,
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    session: Session = Depends(get_db),
    _: None = Depends(require_admin_secret),
) -> HTMLResponse:
    metrics = compute_dashboard(session)
    return _templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        {"metrics": metrics},
    )
