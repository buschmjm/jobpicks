"""Career advisor chat service."""

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
from core.models import CareerMessage as CareerMessageRow, User
from fastapi import HTTPException, status
from inference.career_advisor import (
    career_advisor_reply,
    career_advisor_stream,
    normalize_advisor_text,
)
from inference.config import advisor_reply_max_chars, advisor_research_enabled
from inference.faq_router import try_faq_answer
from inference.load_control import (
    BUSY_ADVISOR_REPLY,
    begin_advisor_fifo,
    check_advisor_rate_limit,
    end_advisor_fifo,
    interactive_llm_lock,
)
from inference.research.planner import plan_research
from inference.research.tools import ResearchBundle, execute_research_plan
from sqlalchemy.orm import Session

from api.repositories.career_message_repo import CareerMessageRepository
from api.repositories.user_repo import UserRepository
from api.schemas import (
    CareerMessage,
    CareerMessageCreate,
    CareerMessageRole,
    CareerMessageSource,
    CareerMessageStatus,
    CareerThreadResponse,
)

logger = logging.getLogger(__name__)

_DONE = object()
_CANCELLED_REPLY = "Response stopped."
_cancel_lock = threading.Lock()
_cancel_events: dict[uuid.UUID, threading.Event] = {}
_RATE_LIMIT_REPLY = (
    "You've reached the advisor message limit for this minute. "
    "Please wait a moment before sending another message."
)


def _message_schema(row: CareerMessageRow) -> CareerMessage:
    source: Literal["llm", "template"] | None = None
    if row.source in {"llm", "template"}:
        source = cast(Literal["llm", "template"], row.source)
    status: CareerMessageStatus | None = None
    if row.status in {"pending", "complete", "failed", "cancelled"}:
        status = CareerMessageStatus(row.status)
    sources: list[CareerMessageSource] | None = None
    if row.sources:
        sources = [CareerMessageSource.model_validate(item) for item in row.sources]
    return CareerMessage(
        id=row.id,
        role=CareerMessageRole(row.role),
        content=row.content,
        source=source,
        status=status,
        sources=sources,
        created_at=row.created_at,
    )


def get_thread(session: Session, user_id: uuid.UUID) -> CareerThreadResponse:
    rows = CareerMessageRepository(session).list_messages(user_id)
    return CareerThreadResponse(messages=[_message_schema(row) for row in rows])


def clear_thread(session: Session, user_id: uuid.UUID) -> CareerThreadResponse:
    CareerMessageRepository(session).clear_messages(user_id)
    session.commit()
    return CareerThreadResponse(messages=[])


def _register_cancel_token(message_id: uuid.UUID) -> threading.Event:
    event = threading.Event()
    with _cancel_lock:
        _cancel_events[message_id] = event
    return event


def _clear_cancel_token(message_id: uuid.UUID) -> None:
    with _cancel_lock:
        _cancel_events.pop(message_id, None)


def _is_cancelled(message_id: uuid.UUID) -> bool:
    with _cancel_lock:
        event = _cancel_events.get(message_id)
    return event is not None and event.is_set()


def request_cancel(
    session: Session,
    user_id: uuid.UUID,
    assistant_message_id: uuid.UUID,
) -> CareerMessage:
    """Stop an in-flight advisor reply for the authenticated user."""
    repo = CareerMessageRepository(session)
    row = session.get(CareerMessageRow, assistant_message_id)
    if row is None or row.user_id != user_id or row.role != "assistant":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if row.status != "pending":
        return _message_schema(row)

    with _cancel_lock:
        event = _cancel_events.get(assistant_message_id)
    if event is not None:
        event.set()
        session.refresh(row)
        return _message_schema(row)

    content = row.content.strip() or _CANCELLED_REPLY
    updated = repo.update_message(
        assistant_message_id,
        content=content,
        status="cancelled",
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    session.commit()
    session.refresh(updated)
    return _message_schema(updated)


def _location_hint(snapshot: dict[str, Any]) -> str | None:
    prefs = snapshot.get("preferences") if isinstance(snapshot, dict) else None
    if not isinstance(prefs, dict):
        return None
    for loc in prefs.get("locations") or []:
        if isinstance(loc, dict):
            name = loc.get("name") or loc.get("formatted_name")
            if name:
                return str(name)[:120]
        elif loc:
            return str(loc)[:120]
    return None


def _run_research(snapshot: dict[str, Any], user_message: str) -> ResearchBundle | None:
    if not advisor_research_enabled():
        return None
    plan = plan_research(snapshot=snapshot, user_message=user_message)
    if not plan.get("need_research"):
        return None
    factory = get_session_factory()
    with factory() as session:
        return execute_research_plan(
            plan,
            session=session,
            location_hint=_location_hint(snapshot),
        )


def _assert_advisor_rate_limit(user_id: uuid.UUID) -> None:
    if not check_advisor_rate_limit(user_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Advisor rate limit exceeded",
        )


def _assert_advisor_daily_limit(session: Session, user: User) -> None:
    try:
        ensure_can_use_feature(session, user, UsageFeature.ADVISOR_MESSAGE)
    except (DailyLimitExceeded, MonthlyLimitExceeded) as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(exc),
        ) from exc


def send_message(
    session: Session,
    user_id: uuid.UUID,
    body: CareerMessageCreate,
) -> CareerThreadResponse:
    _assert_advisor_rate_limit(user_id)
    user = UserRepository(session).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    _assert_advisor_daily_limit(session, user)
    repo = CareerMessageRepository(session)
    snapshot = build_profile_snapshot(session, user_id)
    prior = repo.list_messages(user_id)
    history = [{"role": row.role, "content": row.content} for row in prior]
    text = body.content.strip()

    repo.add_message(user_id, role="user", content=text)
    increment_feature_usage(session, user, UsageFeature.ADVISOR_MESSAGE)

    faq = try_faq_answer(text)
    if faq is not None:
        repo.add_message(
            user_id,
            role="assistant",
            content=faq.reply,
            source="template",
            status="complete",
        )
        session.commit()
        return get_thread(session, user_id)

    fifo = begin_advisor_fifo()
    try:
        if fifo == "busy":
            repo.add_message(
                user_id,
                role="assistant",
                content=BUSY_ADVISOR_REPLY,
                source="template",
                status="complete",
            )
            session.commit()
            return get_thread(session, user_id)

        with interactive_llm_lock(session) as acquired:
            if not acquired:
                repo.add_message(
                    user_id,
                    role="assistant",
                    content=BUSY_ADVISOR_REPLY,
                    source="template",
                    status="complete",
                )
                session.commit()
                return get_thread(session, user_id)

            research = _run_research(snapshot, text)
            research_payload = research.to_prompt_dict() if research is not None else None
            reply = career_advisor_reply(
                snapshot=snapshot,
                history=history,
                user_message=text,
                research=research_payload,
            )
            sources = research.sources_payload() if research is not None else None
            repo.add_message(
                user_id,
                role="assistant",
                content=reply.reply,
                source=reply.source,
                status="complete",
                sources=sources,
            )
            session.commit()
            return get_thread(session, user_id)
    finally:
        end_advisor_fifo()


@dataclass(frozen=True)
class StreamPreparation:
    user_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    history: list[dict[str, str]]
    user_message: str


def prepare_stream(
    session: Session,
    user_id: uuid.UUID,
    body: CareerMessageCreate,
) -> StreamPreparation:
    """Persist the user turn and a pending assistant placeholder before streaming."""
    _assert_advisor_rate_limit(user_id)
    user = UserRepository(session).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    _assert_advisor_daily_limit(session, user)
    repo = CareerMessageRepository(session)
    prior = repo.list_messages(user_id)
    history = [{"role": row.role, "content": row.content} for row in prior]
    text = body.content.strip()
    user_row = repo.add_message(user_id, role="user", content=text)
    increment_feature_usage(session, user, UsageFeature.ADVISOR_MESSAGE)
    assistant_row = repo.add_message(
        user_id,
        role="assistant",
        content="",
        status="pending",
    )
    session.commit()
    return StreamPreparation(
        user_id=user_id,
        user_message_id=user_row.id,
        assistant_message_id=assistant_row.id,
        history=history,
        user_message=text,
    )


def iter_advisor_sse(prep: StreamPreparation) -> Iterator[str]:
    """SSE event stream that tails a background generation task."""
    event_queue: queue.Queue[Any] = queue.Queue()
    thread = threading.Thread(
        target=_run_advisor_generation,
        args=(prep, event_queue),
        name=f"career-advisor-{prep.assistant_message_id}",
        daemon=True,
    )
    thread.start()

    yield _sse(
        {
            "type": "user",
            "id": str(prep.user_message_id),
            "content": prep.user_message,
            "assistant_id": str(prep.assistant_message_id),
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


def _complete_template_stream(
    prep: StreamPreparation,
    event_queue: queue.Queue[Any],
    *,
    reply: str,
    source: str = "template",
    sources: list[dict[str, str]] | None = None,
) -> None:
    event_queue.put({"type": "token", "text": reply})
    assistant = _complete_assistant(
        prep.assistant_message_id,
        reply,
        source,
        sources=sources,
    )
    done_message: dict[str, Any] = {
        "id": str(assistant.id),
        "role": "assistant",
        "content": assistant.content,
        "source": source,
        "status": "complete",
        "created_at": assistant.created_at.isoformat(),
    }
    if sources:
        done_message["sources"] = sources
    event_queue.put({"type": "done", "source": source, "message": done_message})


def _run_advisor_generation(prep: StreamPreparation, event_queue: queue.Queue[Any]) -> None:
    """Generate advisor reply in a background thread; survives SSE disconnect."""
    factory = get_session_factory()
    fifo_started = False
    _register_cancel_token(prep.assistant_message_id)
    try:
        if _is_cancelled(prep.assistant_message_id):
            assistant = _cancel_assistant(prep.assistant_message_id, partial_content="")
            _emit_cancelled(event_queue, assistant)
            return

        if not check_advisor_rate_limit(prep.user_id):
            _complete_template_stream(prep, event_queue, reply=_RATE_LIMIT_REPLY)
            return

        faq = try_faq_answer(prep.user_message)
        if faq is not None:
            _complete_template_stream(prep, event_queue, reply=faq.reply)
            return

        fifo = begin_advisor_fifo()
        if fifo == "busy":
            _complete_template_stream(prep, event_queue, reply=BUSY_ADVISOR_REPLY)
            return
        fifo_started = True

        with factory() as session:
            snapshot = build_profile_snapshot(session, prep.user_id)
            with interactive_llm_lock(session) as acquired:
                if not acquired:
                    _complete_template_stream(prep, event_queue, reply=BUSY_ADVISOR_REPLY)
                    return

                research: ResearchBundle | None = None
                research_payload: dict[str, Any] | None = None
                sources: list[dict[str, str]] = []

                if advisor_research_enabled():
                    event_queue.put(
                        {
                            "type": "status",
                            "phase": "researching",
                            "detail": "Checking local market…",
                        }
                    )
                    if _is_cancelled(prep.assistant_message_id):
                        assistant = _cancel_assistant(prep.assistant_message_id, partial_content="")
                        _emit_cancelled(event_queue, assistant)
                        return
                    try:
                        plan = plan_research(snapshot=snapshot, user_message=prep.user_message)
                        if plan.get("need_research"):
                            research = execute_research_plan(
                                plan,
                                session=session,
                                location_hint=_location_hint(snapshot),
                            )
                        else:
                            research = None
                    except Exception as exc:
                        logger.warning("advisor research failed: %s", exc)
                        research = ResearchBundle(failed=True, detail=str(exc)[:240])

                    if research is not None:
                        research_payload = research.to_prompt_dict()
                        sources = research.sources_payload()
                        if research.failed:
                            event_queue.put(
                                {
                                    "type": "status",
                                    "phase": "research_failed",
                                    "detail": research.detail or "I couldn’t verify live market data.",
                                }
                            )
                        else:
                            event_queue.put(
                                {
                                    "type": "status",
                                    "phase": "research_done",
                                    "detail": "Research ready",
                                }
                            )
                        if sources:
                            event_queue.put({"type": "sources", "items": sources})
                    else:
                        event_queue.put(
                            {
                                "type": "status",
                                "phase": "research_skipped",
                                "detail": "Answering from your profile",
                            }
                        )

                parts: list[str] = []
                source: str = "llm"
                emitted = 0
                max_chars = advisor_reply_max_chars()
                for chunk, chunk_source in career_advisor_stream(
                    snapshot=snapshot,
                    history=prep.history,
                    user_message=prep.user_message,
                    research=research_payload,
                ):
                    if _is_cancelled(prep.assistant_message_id):
                        raw_partial = "".join(parts).strip()
                        partial = (
                            normalize_advisor_text(raw_partial)[:max_chars] if raw_partial else ""
                        )
                        assistant = _cancel_assistant(
                            prep.assistant_message_id,
                            partial_content=partial,
                        )
                        _emit_cancelled(event_queue, assistant)
                        return
                    source = chunk_source
                    parts.append(chunk)
                    text, emitted = _stream_token_chunk(chunk, emitted, max_chars=max_chars)
                    if text:
                        event_queue.put({"type": "token", "text": text})
                reply = _finalize_advisor_reply(parts, max_chars=max_chars)
                assistant = _complete_assistant(
                    prep.assistant_message_id,
                    reply,
                    source,
                    sources=sources or None,
                )
                done_message: dict[str, Any] = {
                    "id": str(assistant.id),
                    "role": "assistant",
                    "content": assistant.content,
                    "source": source,
                    "status": "complete",
                    "created_at": assistant.created_at.isoformat(),
                }
                if sources:
                    done_message["sources"] = sources
                event_queue.put(
                    {
                        "type": "done",
                        "source": source,
                        "message": done_message,
                    }
                )
    except Exception as exc:
        logger.warning("advisor stream failed mid-flight: %s", exc)
        _fail_assistant(prep.assistant_message_id)
        event_queue.put({"type": "error", "detail": "Advisor failed to respond. Try again."})
    finally:
        if fifo_started:
            end_advisor_fifo()
        _clear_cancel_token(prep.assistant_message_id)
        event_queue.put(_DONE)


def _finalize_advisor_reply(parts: list[str], *, max_chars: int) -> str:
    """Join streamed chunks, normalize, and keep a readable fallback if normalization strips too much."""
    raw_reply = "".join(parts)
    reply = normalize_advisor_text(raw_reply)[:max_chars]
    if len(reply) < 20 and len(raw_reply.strip()) >= 20:
        reply = raw_reply.strip()[:max_chars]
    if len(reply) < 20:
        raise ValueError("Advisor reply too short")
    return reply


def _stream_token_chunk(chunk: str, emitted: int, *, max_chars: int) -> tuple[str, int]:
    """Return the next SSE token slice and updated emitted length."""
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
    *,
    sources: list[dict[str, str]] | None,
) -> CareerMessageRow:
    factory = get_session_factory()
    with factory() as session:
        row = CareerMessageRepository(session).update_message(
            message_id,
            content=content,
            source=source,
            status="complete",
            sources=sources,
        )
        if row is None:
            raise ValueError(f"assistant message {message_id} not found")
        session.commit()
        session.refresh(row)
        return row


def _fail_assistant(message_id: uuid.UUID) -> None:
    factory = get_session_factory()
    with factory() as session:
        CareerMessageRepository(session).update_message(
            message_id,
            content="Advisor failed to respond. Try again.",
            status="failed",
        )
        session.commit()


def _cancel_assistant(message_id: uuid.UUID, *, partial_content: str) -> CareerMessageRow:
    content = partial_content.strip() or _CANCELLED_REPLY
    factory = get_session_factory()
    with factory() as session:
        row = CareerMessageRepository(session).update_message(
            message_id,
            content=content,
            status="cancelled",
        )
        if row is None:
            raise ValueError(f"assistant message {message_id} not found")
        session.commit()
        session.refresh(row)
        return row


def _emit_cancelled(event_queue: queue.Queue[Any], assistant: CareerMessageRow) -> None:
    event_queue.put(
        {
            "type": "done",
            "source": assistant.source or "llm",
            "message": {
                "id": str(assistant.id),
                "role": "assistant",
                "content": assistant.content,
                "source": assistant.source,
                "status": "cancelled",
                "created_at": assistant.created_at.isoformat(),
            },
        }
    )


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
