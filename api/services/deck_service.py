"""Deck / queue service — DB-backed user_job_queue."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

from core.deck_bootstrap import (
    has_pending_backfill,
    has_pending_corpus_ingest,
    open_job_count,
    queued_count,
    schedule_backfill_if_needed,
)
from core.entitlements import (
    UserEntitlements,
    apply_explanation_entitlements,
    default_entitlements,
    entitlements_for_user,
)
from core.geo.routing import estimate_drive_minutes
from core.models import (
    EventType,
    FeedbackAction,
    Job,
    Profile,
    QueueSlotType,
    QueueState,
    SwipeReason,
    User,
    UserJobQueue,
)
from core.packet_entitlements import can_generate_packet
from core.preference import apply_feedback, reverse_feedback
from core.preference_store import preference_state_from_stored, serialize_preference_state
from core.profile_loader import user_profile_from_orm
from core.queue_builder import job_features_from_orm
from core.scoring_config_loader import load_scoring_config
from core.types import (
    FeedbackAction as CoreFeedbackAction,
)
from core.types import (
    FeedbackEvent as CoreFeedbackEvent,
)
from core.types import (
    RejectionReason,
    RemoteMode,
    UserProfile,
)
from sqlalchemy import select
from sqlalchemy.orm import Session
from workers.consumer import enqueue_job

from api.repositories.deck_repo import DeckRepository
from api.repositories.events_repo import EventsRepository
from api.repositories.profile_repo import ProfileRepository
from api.schemas import (
    ChangeDecisionResponse,
    DeckNextResponse,
    DeckStatusResponse,
    DwellResponse,
    LeftSwipeReason,
    MatchCard,
    SwipeAction,
    SwipeResponse,
    WorkMode,
)
from api.services.todo_service import TodoService

_LEFT_REASON_TO_MODEL: dict[LeftSwipeReason, SwipeReason] = {
    LeftSwipeReason.not_qualified: SwipeReason.NOT_QUALIFIED,
    LeftSwipeReason.overqualified: SwipeReason.OVERQUALIFIED,
    LeftSwipeReason.comp_too_low: SwipeReason.COMP_TOO_LOW,
    LeftSwipeReason.location_remote: SwipeReason.LOCATION_REMOTE,
    LeftSwipeReason.dont_want_work: SwipeReason.DONT_WANT_WORK,
    LeftSwipeReason.company: SwipeReason.COMPANY,
}

_LEFT_REASON_TO_CORE: dict[LeftSwipeReason, RejectionReason] = {
    LeftSwipeReason.not_qualified: RejectionReason.NOT_QUALIFIED,
    LeftSwipeReason.overqualified: RejectionReason.OVERQUALIFIED,
    LeftSwipeReason.comp_too_low: RejectionReason.COMP_TOO_LOW,
    LeftSwipeReason.location_remote: RejectionReason.LOCATION_REMOTE,
    LeftSwipeReason.dont_want_work: RejectionReason.DONT_WANT_THIS_WORK,
    LeftSwipeReason.company: RejectionReason.COMPANY,
}

_ACTION_TO_FEEDBACK: dict[SwipeAction, FeedbackAction] = {
    SwipeAction.right: FeedbackAction.SWIPE_RIGHT,
    SwipeAction.left: FeedbackAction.SWIPE_LEFT,
    SwipeAction.skip: FeedbackAction.SKIP,
}

_ACTION_TO_STATE: dict[SwipeAction, QueueState] = {
    SwipeAction.right: QueueState.SWIPED_RIGHT,
    SwipeAction.left: QueueState.SWIPED_LEFT,
    SwipeAction.skip: QueueState.SKIPPED,
}

_ACTION_TO_EVENT: dict[SwipeAction, EventType] = {
    SwipeAction.right: EventType.SWIPE_RIGHT,
    SwipeAction.left: EventType.SWIPE_LEFT,
    SwipeAction.skip: EventType.SKIP,
}

_ACTION_TO_CORE: dict[SwipeAction, CoreFeedbackAction] = {
    SwipeAction.right: CoreFeedbackAction.SWIPE_RIGHT,
    SwipeAction.left: CoreFeedbackAction.SWIPE_LEFT,
    SwipeAction.skip: CoreFeedbackAction.SKIP,
}

_STATE_TO_SWIPE: dict[str, SwipeAction] = {
    QueueState.SWIPED_RIGHT.value: SwipeAction.right,
    QueueState.SWIPED_LEFT.value: SwipeAction.left,
    QueueState.SKIPPED.value: SwipeAction.skip,
}

_MODEL_TO_LEFT: dict[SwipeReason, LeftSwipeReason] = {
    v: k for k, v in _LEFT_REASON_TO_MODEL.items()
}

_CHANGEABLE_STATES = frozenset(
    {
        QueueState.SWIPED_RIGHT.value,
        QueueState.SWIPED_LEFT.value,
        QueueState.SKIPPED.value,
    }
)


def _format_salary(job: Job) -> str:
    if job.salary_min is None and job.salary_max is None:
        return "salary not listed"
    if job.salary_min is not None and job.salary_max is not None:
        return f"${job.salary_min // 1000}–{job.salary_max // 1000}k"
    if job.salary_min is not None:
        return f"${job.salary_min // 1000}k+"
    assert job.salary_max is not None
    return f"up to ${job.salary_max // 1000}k"


def _posted_ago(first_seen: datetime | None) -> str:
    if first_seen is None:
        return "recently"
    now = datetime.now(UTC)
    if first_seen.tzinfo is None:
        first_seen = first_seen.replace(tzinfo=UTC)
    days = max(0, (now - first_seen).days)
    if days == 0:
        return "today"
    if days == 1:
        return "1d ago"
    return f"{days}d ago"


def _work_mode(remote_mode: str | object) -> WorkMode:
    value = remote_mode.value if hasattr(remote_mode, "value") else str(remote_mode)
    try:
        return WorkMode(value)
    except ValueError:
        return WorkMode.unknown


def _commute_display(session: Session, user_id: UUID, job: Job) -> str | None:
    repo = ProfileRepository(session)
    constraints = repo.get_or_create_hard_constraints(user_id)
    if not constraints.locations:
        return None
    first = constraints.locations[0]
    if not isinstance(first, dict):
        return None
    home_lat, home_lon = first.get("lat"), first.get("lon")
    if home_lat is None or home_lon is None or job.latitude is None or job.longitude is None:
        return None
    remote = job.remote_mode.value if hasattr(job.remote_mode, "value") else str(job.remote_mode)
    if remote == RemoteMode.REMOTE.value:
        return None
    minutes = estimate_drive_minutes(float(home_lat), float(home_lon), job.latitude, job.longitude)
    return f"~{minutes} min drive (est.)"


def _left_reason_from_model(reason: SwipeReason | str | None) -> LeftSwipeReason | None:
    if reason is None:
        return None
    if isinstance(reason, SwipeReason):
        return _MODEL_TO_LEFT.get(reason)
    try:
        return _MODEL_TO_LEFT.get(SwipeReason(reason))
    except ValueError:
        return None


def _load_entitlements(session: Session, user_id: UUID) -> UserEntitlements:
    user = session.get(User, user_id)
    if user is None:
        return default_entitlements()
    return entitlements_for_user(user)


def match_card_from_queue_item(
    item: UserJobQueue,
    *,
    session: Session | None = None,
    user_id: UUID | None = None,
    include_queue_meta: bool = False,
    entitlements: UserEntitlements | None = None,
) -> MatchCard:
    job = item.job
    if job is None:
        raise ValueError("Queue item missing job")
    explain = item.explain or {}
    components = item.score_components or {}
    ent = entitlements or default_entitlements()
    why_bullets, caution_bullets, score_breakdown = apply_explanation_entitlements(
        explain,
        components,
        ent,
    )
    match_raw = float(components.get("match_score", item.score or 0.0))
    slot = item.slot_type.value if hasattr(item.slot_type, "value") else item.slot_type
    state_value = item.state.value if hasattr(item.state, "value") else str(item.state)
    model_reason = item.reason
    if model_reason is not None and not isinstance(model_reason, SwipeReason):
        try:
            model_reason = SwipeReason(model_reason)
        except ValueError:
            model_reason = None
    match_state: Literal["queued", "swiped_right", "swiped_left", "skipped", "expired"] | None = None
    if include_queue_meta:
        match_state = cast(
            Literal["queued", "swiped_right", "swiped_left", "skipped", "expired"],
            state_value,
        )
    return MatchCard(
        queue_item_id=item.id,
        job_id=job.id,
        match_score=max(0, min(100, int(round(match_raw * 100)))),
        title=job.title,
        company=job.company_name,
        salary_display=_format_salary(job),
        work_mode=_work_mode(job.remote_mode),
        location_display=job.location_text or "—",
        posted_ago=_posted_ago(job.first_seen),
        source=job.primary_source or "unknown",
        source_url=job.source_url or "https://example.com",
        why_bullets=why_bullets,
        caution_bullets=caution_bullets,
        score_breakdown=score_breakdown,
        description=job.description or "",
        commute_display=_commute_display(session, user_id, job)
        if session is not None and user_id is not None
        else None,
        is_explore=slot == QueueSlotType.EXPLORE.value,
        stretch=bool(item.is_stretch),
        state=match_state,
        swiped_at=item.swiped_at if include_queue_meta else None,
        reason=_left_reason_from_model(model_reason) if include_queue_meta else None,
    )


def _serialize_user_profile_state(profile: UserProfile) -> dict[str, Any]:
    return {
        "learned_facet_weights": profile.learned_facet_weights,
        "stated_facet_weights": profile.stated_facet_weights,
        "qualification_gap_penalties": profile.qualification_gap_penalties,
        "blocked_companies": list(profile.blocked_companies),
        "facet_exposure_counts": profile.facet_exposure_counts,
        "effective_salary_floor": profile.effective_salary_floor,
        "seniority_floor": profile.seniority_floor,
        "geo_weight_multiplier": profile.geo_weight_multiplier,
        "daily_weight_delta_used": profile.daily_weight_delta_used,
        "daily_weight_delta_date": profile.daily_weight_delta_date,
        "profile_prior_embedding": list(profile.profile_prior_embedding)
        if profile.profile_prior_embedding
        else None,
    }


class DeckService:
    def __init__(self) -> None:
        self._todo = TodoService()

    def _deck_building(
        self,
        session: Session,
        user_id: UUID,
        *,
        remaining: int,
    ) -> tuple[bool, str | None]:
        if remaining > 0:
            return False, None

        profile = session.scalar(select(Profile).where(Profile.user_id == user_id))
        awaiting = bool(profile and profile.awaiting_deck_backfill)
        corpus = open_job_count(session)
        pending_backfill = has_pending_backfill(session, user_id)
        pending_ingest = has_pending_corpus_ingest(session)

        if awaiting and corpus == 0:
            return True, "Fetching jobs from our sources — this may take a minute."
        if awaiting and corpus > 0:
            if pending_backfill:
                return True, "Ranking matches for your profile…"
            scheduled = schedule_backfill_if_needed(session, user_id, enqueue=enqueue_job)
            if scheduled:
                session.commit()
                return True, "Ranking matches for your profile…"
        if pending_backfill or pending_ingest:
            return True, "Building your deck from matching jobs…"
        if corpus == 0:
            return True, "Fetching jobs from our sources — this may take a minute."
        scheduled = schedule_backfill_if_needed(session, user_id, enqueue=enqueue_job)
        if scheduled:
            session.commit()
            return True, "Ranking jobs for your profile…"
        return False, "Queue empty — check back tomorrow for new matches."

    def get_status(self, session: Session, user_id: UUID) -> DeckStatusResponse:
        remaining = queued_count(session, user_id)
        corpus = open_job_count(session)
        building, message = self._deck_building(session, user_id, remaining=remaining)
        return DeckStatusResponse(
            queue_remaining=remaining,
            building=building,
            open_jobs=corpus,
            message=message,
        )

    def get_next(self, session: Session, user_id: UUID) -> DeckNextResponse:
        repo = DeckRepository(session)
        remaining = repo.count_queued(user_id)
        building, building_message = self._deck_building(session, user_id, remaining=remaining)
        item = repo.get_next_queued(user_id)
        if item is None:
            return DeckNextResponse(
                card=None,
                queue_remaining=0,
                building=building,
                message=building_message
                or "Queue empty — check back tomorrow for new matches.",
            )
        entitlements = _load_entitlements(session, user_id)
        return DeckNextResponse(
            card=match_card_from_queue_item(
                item,
                session=session,
                user_id=user_id,
                entitlements=entitlements,
            ),
            queue_remaining=remaining,
            building=False,
        )

    def swipe(
        self,
        session: Session,
        user_id: UUID,
        queue_item_id: UUID,
        action: SwipeAction,
        reason: LeftSwipeReason | None,
        dwell_ms: int | None,
    ) -> SwipeResponse:
        deck = DeckRepository(session)
        events = EventsRepository(session)
        profiles = ProfileRepository(session)

        item = deck.get_queue_item(user_id, queue_item_id)
        if item is None or item.state != QueueState.QUEUED.value:
            return SwipeResponse(
                success=False,
                action=action,
                next_available=False,
                message="Card not found",
            )

        job = item.job
        if job is None:
            return SwipeResponse(
                success=False,
                action=action,
                next_available=False,
                message="Card not found",
            )

        model_reason = _LEFT_REASON_TO_MODEL.get(reason) if reason else None
        dwell_seconds = dwell_ms / 1000.0 if dwell_ms is not None else None

        deck.update_swipe_state(item, state=_ACTION_TO_STATE[action], reason=model_reason)
        deck.record_feedback(
            user_id=user_id,
            job_id=job.id,
            action=_ACTION_TO_FEEDBACK[action],
            reason=model_reason,
            dwell_seconds=dwell_seconds,
            payload={"queue_item_id": str(queue_item_id)},
        )
        events.append(
            _ACTION_TO_EVENT[action],
            user_id=user_id,
            entity_id=item.id,
            payload={"job_id": str(job.id), "reason": reason.value if reason else None},
        )

        self._apply_preference_update(
            session,
            profiles,
            user_id,
            job,
            action,
            reason,
            dwell_seconds,
        )

        todo_item_id = None
        entitlements = _load_entitlements(session, user_id)
        card = match_card_from_queue_item(
            item,
            session=session,
            user_id=user_id,
            entitlements=entitlements,
        )
        if action == SwipeAction.right:
            todo = self._todo.add_from_swipe(session, user_id, card)
            todo_item_id = todo.id
            user = session.get(User, user_id)
            if user is not None and can_generate_packet(session, user, todo_item_id):
                enqueue_job(
                    session,
                    "packet_prefetch",
                    {"user_id": str(user_id), "todo_item_id": str(todo_item_id)},
                    priority=4,
                )

        session.commit()

        next_resp = self.get_next(session, user_id)
        return SwipeResponse(
            action=action,
            todo_item_id=todo_item_id,
            next_available=next_resp.card is not None,
        )

    def change_decision(
        self,
        session: Session,
        user_id: UUID,
        queue_item_id: UUID,
        action: SwipeAction,
        reason: LeftSwipeReason | None,
    ) -> ChangeDecisionResponse:
        deck = DeckRepository(session)
        events = EventsRepository(session)
        profiles = ProfileRepository(session)

        item = deck.get_queue_item(user_id, queue_item_id)
        if item is None:
            return ChangeDecisionResponse(success=False, action=action, message="Card not found")

        current_state = item.state.value if hasattr(item.state, "value") else str(item.state)
        if current_state not in _CHANGEABLE_STATES:
            return ChangeDecisionResponse(
                success=False,
                action=action,
                message="Only past swipes can be changed",
            )

        job = item.job
        if job is None:
            return ChangeDecisionResponse(success=False, action=action, message="Card not found")

        previous_state = current_state
        was_right = previous_state == QueueState.SWIPED_RIGHT.value
        will_be_right = action == SwipeAction.right

        if was_right and not will_be_right:
            self._todo.archive_for_job(session, user_id, job.id)
        elif will_be_right and not was_right:
            entitlements = _load_entitlements(session, user_id)
            card = match_card_from_queue_item(
                item,
                session=session,
                user_id=user_id,
                entitlements=entitlements,
            )
            todo = self._todo.ensure_apply_for_job(session, user_id, card)
        else:
            todo = None

        model_reason = _LEFT_REASON_TO_MODEL.get(reason) if reason else None
        deck.update_swipe_state(item, state=_ACTION_TO_STATE[action], reason=model_reason)
        deck.record_feedback(
            user_id=user_id,
            job_id=job.id,
            action=_ACTION_TO_FEEDBACK[action],
            reason=model_reason,
            payload={
                "queue_item_id": str(queue_item_id),
                "change_decision": True,
                "previous_state": previous_state,
            },
        )
        events.append(
            _ACTION_TO_EVENT[action],
            user_id=user_id,
            entity_id=item.id,
            payload={
                "job_id": str(job.id),
                "reason": reason.value if reason else None,
                "change_decision": True,
                "previous_state": previous_state,
            },
        )

        prior_swipe = _STATE_TO_SWIPE.get(previous_state)
        if prior_swipe is not None and prior_swipe != action:
            self._reverse_preference_update(session, profiles, user_id, job, prior_swipe)
        if prior_swipe != action:
            self._apply_preference_update(
                session,
                profiles,
                user_id,
                job,
                action,
                reason,
                None,
            )

        todo_item_id = todo.id if will_be_right and not was_right and todo is not None else None
        session.commit()
        return ChangeDecisionResponse(action=action, todo_item_id=todo_item_id)

    def record_dwell(
        self, session: Session, user_id: UUID, queue_item_id: UUID, dwell_ms: int
    ) -> DwellResponse:
        deck = DeckRepository(session)
        events = EventsRepository(session)
        item = deck.get_queue_item(user_id, queue_item_id)
        if item is None:
            return DwellResponse(recorded=False)
        events.append(
            EventType.CARD_VIEWED,
            user_id=user_id,
            entity_id=item.id,
            payload={"dwell_ms": dwell_ms, "job_id": str(item.job_id)},
        )
        session.commit()
        return DwellResponse()

    def record_todo_applied(self, session: Session, user_id: UUID, job_id: UUID) -> None:
        deck = DeckRepository(session)
        job = deck.get_job(job_id)
        if job is None:
            return
        profiles = ProfileRepository(session)
        self._apply_core_feedback(session, profiles, user_id, job, CoreFeedbackAction.TODO_APPLIED)

    def record_todo_archived(self, session: Session, user_id: UUID, job_id: UUID) -> None:
        deck = DeckRepository(session)
        job = deck.get_job(job_id)
        if job is None:
            return
        profiles = ProfileRepository(session)
        self._apply_core_feedback(session, profiles, user_id, job, CoreFeedbackAction.TODO_ARCHIVED)

    def _reverse_preference_update(
        self,
        session: Session,
        profiles: ProfileRepository,
        user_id: UUID,
        job: Job,
        prior_action: SwipeAction,
    ) -> None:
        profile_row = profiles.get_or_create_profile(user_id)
        weights_row = profiles.get_or_create_preference_weights(user_id)
        stored = dict(weights_row.weights or {})
        constraints_row = profiles.get_or_create_hard_constraints(user_id)
        user_profile = user_profile_from_orm(
            profile_row, weights_row, hard_constraints=constraints_row
        )
        job_features = job_features_from_orm(job)
        event = CoreFeedbackEvent(
            user_id=str(user_id),
            job_id=str(job.id),
            action=_ACTION_TO_CORE[prior_action],
            timestamp=datetime.now(UTC),
            job=job_features,
        )
        state = preference_state_from_stored(user_profile, stored)
        config = load_scoring_config(session)
        updated = reverse_feedback(state, event, _ACTION_TO_CORE[prior_action], config)
        merged_weights = {
            **stored,
            **_serialize_user_profile_state(updated.profile),
            **serialize_preference_state(updated),
        }
        profiles.save_preference_state(
            user_id,
            weights=merged_weights,
            facet_boosts=weights_row.facet_boosts,
            taste_embedding=list(updated.profile.taste_embedding)
            if updated.profile.taste_embedding
            else None,
            right_swipe_count=updated.profile.right_swipe_count,
        )

    def _apply_core_feedback(
        self,
        session: Session,
        profiles: ProfileRepository,
        user_id: UUID,
        job: Job,
        action: CoreFeedbackAction,
    ) -> None:
        profile_row = profiles.get_or_create_profile(user_id)
        weights_row = profiles.get_or_create_preference_weights(user_id)
        stored = dict(weights_row.weights or {})
        constraints_row = profiles.get_or_create_hard_constraints(user_id)
        user_profile = user_profile_from_orm(
            profile_row, weights_row, hard_constraints=constraints_row
        )
        job_features = job_features_from_orm(job)
        event = CoreFeedbackEvent(
            user_id=str(user_id),
            job_id=str(job.id),
            action=action,
            timestamp=datetime.now(UTC),
            job=job_features,
        )
        state = preference_state_from_stored(user_profile, stored)
        config = load_scoring_config(session)
        updated = apply_feedback(state, event, config)
        merged_weights = {
            **stored,
            **_serialize_user_profile_state(updated.profile),
            **serialize_preference_state(updated),
        }
        profiles.save_preference_state(
            user_id,
            weights=merged_weights,
            facet_boosts=weights_row.facet_boosts,
            taste_embedding=list(updated.profile.taste_embedding)
            if updated.profile.taste_embedding
            else None,
            right_swipe_count=updated.profile.right_swipe_count,
        )

    def _apply_preference_update(
        self,
        session: Session,
        profiles: ProfileRepository,
        user_id: UUID,
        job: Job,
        action: SwipeAction,
        reason: LeftSwipeReason | None,
        dwell_seconds: float | None,
    ) -> None:
        profile_row = profiles.get_or_create_profile(user_id)
        weights_row = profiles.get_or_create_preference_weights(user_id)
        stored = dict(weights_row.weights or {})
        constraints_row = profiles.get_or_create_hard_constraints(user_id)
        user_profile = user_profile_from_orm(
            profile_row, weights_row, hard_constraints=constraints_row
        )
        job_features = job_features_from_orm(job)
        core_reason = _LEFT_REASON_TO_CORE.get(reason) if reason else None
        event = CoreFeedbackEvent(
            user_id=str(user_id),
            job_id=str(job.id),
            action=_ACTION_TO_CORE[action],
            timestamp=datetime.now(UTC),
            job=job_features,
            reason=core_reason,
            dwell_seconds=dwell_seconds,
        )
        state = preference_state_from_stored(user_profile, stored)
        config = load_scoring_config(session)
        updated = apply_feedback(state, event, config)
        merged_weights = {
            **stored,
            **_serialize_user_profile_state(updated.profile),
            **serialize_preference_state(updated),
        }
        profiles.save_preference_state(
            user_id,
            weights=merged_weights,
            facet_boosts=weights_row.facet_boosts,
            taste_embedding=list(updated.profile.taste_embedding)
            if updated.profile.taste_embedding
            else None,
            right_swipe_count=updated.profile.right_swipe_count,
        )


deck_service = DeckService()
