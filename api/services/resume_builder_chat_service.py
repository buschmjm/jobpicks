"""Resume builder chat service."""

from __future__ import annotations

import json
import logging
import queue
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal, cast

from core.career.profile_snapshot import build_profile_snapshot
from core.database import get_session_factory
from core.daily_usage import (
    DailyLimitExceeded,
    UsageFeature,
    ensure_can_use_feature,
    increment_feature_usage,
)
from core.monthly_usage import MonthlyLimitExceeded
from core.models import ResumeBuilderMessage as ResumeBuilderMessageRow
from core.models import ResumeVariant, User
from fastapi import HTTPException, status
from inference.config import advisor_reply_max_chars
from inference.load_control import check_builder_rate_limit, interactive_llm_lock
from inference.resume_builder import (
    extract_proposal_from_reply,
    normalize_builder_text,
    resume_builder_stream,
    resume_builder_sync,
)
from sqlalchemy.orm import Session

from api.repositories.resume_message_repo import ResumeMessageRepository
from api.repositories.user_repo import UserRepository
from api.schemas import (
    CareerMessageStatus,
    ResumeBuilderMessage,
    ResumeBuilderMessageCreate,
    ResumeBuilderMessageRole,
    ResumeBuilderThreadResponse,
)
from api.services.resume_proposal_service import create_from_builder_payload
from api.services.resume_variant_service import get_or_create_default_variant, variant_context

logger = logging.getLogger(__name__)

_DONE = object()


def _message_schema(row: ResumeBuilderMessageRow) -> ResumeBuilderMessage:
    source: Literal["llm", "template"] | None = None
    if row.source in {"llm", "template"}:
        source = cast(Literal["llm", "template"], row.source)
    status: CareerMessageStatus | None = None
    if row.status in {"pending", "complete", "failed"}:
        status = CareerMessageStatus(row.status)
    return ResumeBuilderMessage(
        id=row.id,
        variant_id=row.variant_id,
        role=ResumeBuilderMessageRole(row.role),
        content=row.content,
        proposal_id=row.proposal_id,
        source=source,
        status=status,
        created_at=row.created_at,
    )


def _resolve_variant(
    session: Session, user_id: uuid.UUID, variant_id: uuid.UUID | None
) -> ResumeVariant:
    if variant_id is not None:
        from api.repositories.resume_variant_repo import ResumeVariantRepository

        row = ResumeVariantRepository(session).get_variant(user_id, variant_id)
        if row is None:
            raise LookupError("Variant not found")
        return row
    return get_or_create_default_variant(session, user_id)


def get_thread(
    session: Session,
    user_id: uuid.UUID,
    *,
    variant_id: uuid.UUID | None = None,
) -> ResumeBuilderThreadResponse:
    variant = _resolve_variant(session, user_id, variant_id)
    rows = ResumeMessageRepository(session).list_messages(user_id, variant.id)
    return ResumeBuilderThreadResponse(messages=[_message_schema(row) for row in rows])


def clear_thread(
    session: Session,
    user_id: uuid.UUID,
    *,
    variant_id: uuid.UUID | None = None,
) -> ResumeBuilderThreadResponse:
    variant = _resolve_variant(session, user_id, variant_id)
    ResumeMessageRepository(session).clear_messages(user_id, variant.id)
    session.commit()
    return ResumeBuilderThreadResponse(messages=[])


def send_message(
    session: Session,
    user_id: uuid.UUID,
    body: ResumeBuilderMessageCreate,
) -> ResumeBuilderThreadResponse:
    if not check_builder_rate_limit(user_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Resume builder rate limit exceeded",
        )
    user = UserRepository(session).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        ensure_can_use_feature(session, user, UsageFeature.RESUME_BUILDER_MESSAGE)
    except (DailyLimitExceeded, MonthlyLimitExceeded) as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(exc),
        ) from exc
    variant = _resolve_variant(session, user_id, body.variant_id)
    repo = ResumeMessageRepository(session)
    prior = repo.list_messages(user_id, variant.id)
    history = [{"role": row.role, "content": row.content} for row in prior]
    text = body.content.strip()

    repo.add_message(user_id, role="user", content=text, variant_id=variant.id)
    increment_feature_usage(session, user, UsageFeature.RESUME_BUILDER_MESSAGE)
    snapshot = build_profile_snapshot(session, user_id)
    with interactive_llm_lock(session) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Resume builder is busy; try again shortly",
            )
        reply = resume_builder_sync(
            snapshot=snapshot,
            history=history,
            user_message=text,
            variant=variant_context(variant),
        )
    assistant_row = repo.add_message(
        user_id,
        role="assistant",
        content=reply.reply,
        variant_id=variant.id,
        source=reply.source,
        status="complete",
    )
    if reply.proposal:
        create_from_builder_payload(
            session,
            user_id,
            variant.id,
            reply.proposal,
            assistant_row.id,
        )
    else:
        session.commit()
    return get_thread(session, user_id, variant_id=variant.id)


@dataclass(frozen=True)
class StreamPreparation:
    user_id: uuid.UUID
    variant_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    history: list[dict[str, str]]
    user_message: str


def prepare_stream(
    session: Session,
    user_id: uuid.UUID,
    body: ResumeBuilderMessageCreate,
) -> StreamPreparation:
    variant = _resolve_variant(session, user_id, body.variant_id)
    repo = ResumeMessageRepository(session)
    prior = repo.list_messages(user_id, variant.id)
    history = [{"role": row.role, "content": row.content} for row in prior]
    text = body.content.strip()
    user_row = repo.add_message(user_id, role="user", content=text, variant_id=variant.id)
    assistant_row = repo.add_message(
        user_id,
        role="assistant",
        content="",
        variant_id=variant.id,
        status="pending",
    )
    session.commit()
    return StreamPreparation(
        user_id=user_id,
        variant_id=variant.id,
        user_message_id=user_row.id,
        assistant_message_id=assistant_row.id,
        history=history,
        user_message=text,
    )


def iter_builder_sse(prep: StreamPreparation) -> Iterator[str]:
    """SSE event stream that tails a background generation task."""
    event_queue: queue.Queue[Any] = queue.Queue()
    thread = threading.Thread(
        target=_run_builder_generation,
        args=(prep, event_queue),
        name=f"resume-builder-{prep.assistant_message_id}",
        daemon=True,
    )
    thread.start()

    yield _sse(
        {
            "type": "user",
            "id": str(prep.user_message_id),
            "content": prep.user_message,
            "assistant_id": str(prep.assistant_message_id),
            "variant_id": str(prep.variant_id),
        }
    )

    while True:
        try:
            event = event_queue.get(timeout=0.5)
        except queue.Empty:
            if not thread.is_alive():
                break
            continue
        if event is _DONE:
            break
        yield _sse(event)

    thread.join(timeout=300)


def _run_builder_generation(prep: StreamPreparation, event_queue: queue.Queue[Any]) -> None:
    factory = get_session_factory()
    proposal_payload: dict[str, Any] | None = None
    try:
        if not check_builder_rate_limit(prep.user_id):
            event_queue.put(
                {
                    "type": "error",
                    "detail": "Resume builder rate limit exceeded. Please wait a moment.",
                }
            )
            return

        assistant: ResumeBuilderMessageRow | None = None
        source = "llm"
        with factory() as session:
            snapshot = build_profile_snapshot(session, prep.user_id)
            variant = _resolve_variant(session, prep.user_id, prep.variant_id)
            variant_ctx = variant_context(variant)
            with interactive_llm_lock(session) as acquired:
                if not acquired:
                    event_queue.put(
                        {
                            "type": "error",
                            "detail": "Resume builder is busy; try again shortly.",
                        }
                    )
                    return

                parts: list[str] = []
                emitted = 0
                max_chars = advisor_reply_max_chars()
                for chunk, chunk_source in resume_builder_stream(
                    snapshot=snapshot,
                    history=prep.history,
                    user_message=prep.user_message,
                    variant=variant_ctx,
                ):
                    source = chunk_source
                    parts.append(chunk)
                    text, emitted = _stream_token_chunk(chunk, emitted, max_chars=max_chars)
                    if text:
                        event_queue.put({"type": "token", "text": text})

                raw_reply = "".join(parts)
                chat_text, extracted = extract_proposal_from_reply(raw_reply)
                reply = _finalize_builder_reply(
                    chat_text if extracted else raw_reply, max_chars=max_chars
                )
                if extracted:
                    proposal_payload = extracted

                assistant = _complete_assistant(prep.assistant_message_id, reply, source)

        if assistant is None:
            return

        if proposal_payload:
            with factory() as session:
                proposal_response = create_from_builder_payload(
                    session,
                    prep.user_id,
                    prep.variant_id,
                    proposal_payload,
                    prep.assistant_message_id,
                )
            event_queue.put(
                {
                    "type": "proposal",
                    "proposal": proposal_response.model_dump(mode="json"),
                }
            )

        done_message: dict[str, Any] = {
            "id": str(assistant.id),
            "role": "assistant",
            "content": assistant.content,
            "source": source,
            "status": "complete",
            "created_at": assistant.created_at.isoformat(),
        }
        event_queue.put(
            {
                "type": "done",
                "source": source,
                "message": done_message,
            }
        )
    except Exception as exc:
        logger.warning("resume builder stream failed mid-flight: %s", exc)
        _fail_assistant(prep.assistant_message_id)
        event_queue.put({"type": "error", "detail": "Resume builder failed to respond. Try again."})
    finally:
        event_queue.put(_DONE)


def _finalize_builder_reply(parts_or_text: str | list[str], *, max_chars: int) -> str:
    raw_reply = parts_or_text if isinstance(parts_or_text, str) else "".join(parts_or_text)
    reply = normalize_builder_text(raw_reply)[:max_chars]
    if len(reply) < 10 and len(raw_reply.strip()) >= 10:
        reply = raw_reply.strip()[:max_chars]
    if len(reply) < 10:
        raise ValueError("Builder reply too short")
    return reply


def _stream_token_chunk(chunk: str, emitted: int, *, max_chars: int) -> tuple[str, int]:
    if emitted >= max_chars:
        return "", emitted
    text = chunk if emitted + len(chunk) <= max_chars else chunk[: max_chars - emitted]
    if not text:
        return "", emitted
    return text, emitted + len(text)


def _complete_assistant(
    message_id: uuid.UUID,
    content: str,
    source: str,
) -> ResumeBuilderMessageRow:
    factory = get_session_factory()
    with factory() as session:
        row = ResumeMessageRepository(session).update_message(
            message_id,
            content=content,
            source=source,
            status="complete",
        )
        if row is None:
            raise ValueError(f"assistant message {message_id} not found")
        session.commit()
        session.refresh(row)
        return row


def _fail_assistant(message_id: uuid.UUID) -> None:
    factory = get_session_factory()
    with factory() as session:
        ResumeMessageRepository(session).update_message(
            message_id,
            content="Resume builder failed to respond. Try again.",
            status="failed",
        )
        session.commit()


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
