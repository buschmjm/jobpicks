"""Prometheus metrics route (Workstream D)."""

from __future__ import annotations

from core.prometheus_metrics import render_prometheus_metrics
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from api.access_control import verify_metrics_token
from api.deps import get_db

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def prometheus_metrics(
    db: Session = Depends(get_db),
    _: None = Depends(verify_metrics_token),
) -> PlainTextResponse:
    return PlainTextResponse(content=render_prometheus_metrics(db), media_type="text/plain; version=0.0.4")
