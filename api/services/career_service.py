"""Career assistant API: title suggestions and future counselor features."""

from __future__ import annotations

import uuid

from core.career.profile_snapshot import build_profile_snapshot
from inference.career import suggest_job_titles
from sqlalchemy.orm import Session

from api.schemas import TitleSuggestion, TitleSuggestionsResponse


def get_title_suggestions(
    session: Session,
    user_id: uuid.UUID,
    *,
    goals: str | None = None,
) -> TitleSuggestionsResponse:
    snapshot = build_profile_snapshot(session, user_id, goals=goals)
    output = suggest_job_titles(snapshot)
    return TitleSuggestionsResponse(
        suggestions=[
            TitleSuggestion(title=item.title, tier=item.tier, reason=item.reason)
            for item in output.suggestions
        ],
        source=output.source,
    )
