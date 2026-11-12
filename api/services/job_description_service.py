"""Job description resolution for deck views."""

from __future__ import annotations

import uuid

from core.competitiveness import competitiveness_percentile, format_competitiveness_lines
from core.job_description import description_looks_truncated
from core.job_description_enrich import enrich_job_description
from core.models import Job, PreferenceWeights, Profile
from core.profile_loader import user_profile_from_orm
from core.queue_builder import job_features_from_orm
from core.scoring_config_loader import load_scoring_config
from sqlalchemy import select
from sqlalchemy.orm import Session


def get_job_description(
    session: Session,
    job_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None = None,
) -> tuple[str, bool, int | None, int | None]:
    """Return description, truncated flag, and optional competitiveness display percents."""
    job = session.get(Job, job_id)
    if job is None:
        msg = "Job not found"
        raise LookupError(msg)

    description = (job.description or "").strip()
    if description_looks_truncated(description):
        enriched = enrich_job_description(session, job)
        if enriched and enriched != description and not description_looks_truncated(enriched):
            job.description = enriched
            session.commit()
            session.refresh(job)
            description = enriched

    top_percent: int | None = None
    p_top_percent: int | None = None
    if user_id is not None:
        profile_row = session.scalar(select(Profile).where(Profile.user_id == user_id))
        if profile_row is not None and profile_row.onboarding_completed_at is not None:
            weights = session.scalar(
                select(PreferenceWeights)
                .where(PreferenceWeights.user_id == user_id)
                .where(PreferenceWeights.is_current.is_(True))
            )
            user_profile = user_profile_from_orm(profile_row, weights)
            features = job_features_from_orm(job)
            config = load_scoring_config(session)
            from core.scoring import score_job

            scored = score_job(user_profile, features, config)
            if scored is not None:
                estimate = competitiveness_percentile(
                    user_profile,
                    features,
                    float(scored.components.get("match_score", scored.score)),
                    config=config,
                )
                _, _ = format_competitiveness_lines(estimate)
                top_percent = estimate.top_percent_display
                p_top_percent = estimate.p_top_percent_display

    return description, description_looks_truncated(description), top_percent, p_top_percent
