"""Application packet orchestration — generate, review, apply assist."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from core.apply.vault import AUTO_VAULT_KEYS
from core.career.profile_snapshot import build_profile_snapshot
from core.models import ApplicationPacket, ApplicationPacketStatus, Job, QueueJob, QueueJobStatus
from core.packet_entitlements import ensure_can_generate_packet
from core.profile_identity import resolve_identity
from inference.application_packet import propose_application_packet
from inference.apply_assist import apply_assist_stream
from inference.cover_letter import draft_cover_letter
from sqlalchemy import select
from sqlalchemy.orm import Session
from workers.consumer import enqueue_job

from api.repositories.application_packet_repo import ApplicationPacketRepository
from api.repositories.profile_repo import ProfileRepository
from api.repositories.saved_application_answer_repo import SavedApplicationAnswerRepository
from api.repositories.todo_repo import TodoRepository
from api.repositories.user_repo import UserRepository
from api.schemas import (
    ApplicationPacketOpenResponse,
    ApplicationPacketPatchRequest,
    ApplicationPacketResponse,
    PacketAnswerItem,
    PacketAnswerSource,
    PacketAnswerStatus,
    PreparedPacketListResponse,
    PreparedPacketSummary,
    ResumeTailorRequest,
    TodoStatus,
)
from api.services.resume_service import resume_service

logger = logging.getLogger(__name__)

PACKET_PREFETCH_JOB_TYPE = "packet_prefetch"
STALE_GENERATING_MINUTES = 5


def _job_title_company(packet: ApplicationPacket, job: Job | None = None) -> tuple[str, str]:
    resolved = job if job is not None else packet.job
    title = (resolved.title if resolved else "") or "Job"
    company = (resolved.company_name if resolved else "") or "Unknown"
    return title, company


def _packet_label(packet: ApplicationPacket, job: Job | None = None) -> str:
    label = (getattr(packet, "label", None) or "").strip()
    if label:
        return label
    title, _ = _job_title_company(packet, job)
    return title


def _default_label(job: Job) -> str:
    title = (job.title or "").strip()
    return title[:256] if title else "Untitled application"


def _packet_response(
    packet: ApplicationPacket, job: Job | None = None
) -> ApplicationPacketResponse:
    answers: list[PacketAnswerItem] = []
    for raw in packet.answers or []:
        if not isinstance(raw, dict):
            continue
        try:
            source = PacketAnswerSource(str(raw.get("source") or "llm"))
        except ValueError:
            source = PacketAnswerSource.llm
        try:
            status = PacketAnswerStatus(str(raw.get("status") or "pending"))
        except ValueError:
            status = PacketAnswerStatus.pending
        answers.append(
            PacketAnswerItem(
                key=str(raw.get("key") or ""),
                question_text=str(raw.get("question_text") or ""),
                suggested_answer=str(raw.get("suggested_answer") or ""),
                source=source,
                status=status,
                final_answer=raw.get("final_answer"),
                save_to_vault=bool(raw.get("save_to_vault")),
            )
        )

    status_value = (
        packet.status.value if hasattr(packet.status, "value") else str(packet.status)
    )
    fit_verdict = packet.fit_verdict
    if fit_verdict not in {"apply", "lean_apply", "lean_skip", "skip"}:
        fit_verdict = None

    title, company = _job_title_company(packet, job)
    return ApplicationPacketResponse(
        id=packet.id,
        todo_item_id=packet.todo_item_id,
        job_id=packet.job_id,
        status=status_value,  # type: ignore[arg-type]
        apply_url=packet.apply_url,
        ats_type=packet.ats_type,
        label=_packet_label(packet, job),
        title=title,
        company=company,
        fit_verdict=fit_verdict,  # type: ignore[arg-type]
        fit_rationale=list(packet.fit_rationale or []),
        identity=dict(packet.identity or {}),
        resume_draft_id=packet.resume_draft_id,
        cover_letter=packet.cover_letter,
        answers=answers,
        generation_error=packet.generation_error,
        created_at=packet.created_at,
        updated_at=packet.updated_at,
    )


def _job_payload(job: Job) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "title": job.title,
        "company": job.company_name,
        "description": (job.description or "")[:6000],
        "source_url": job.source_url or "",
        "location": job.location_text,
    }


class ApplicationPacketService:
    def request_generate(
        self, session: Session, user_id: uuid.UUID, todo_item_id: uuid.UUID
    ) -> ApplicationPacketResponse:
        """Queue packet generation and return immediately with status=generating."""
        user = UserRepository(session).get_by_id(user_id)
        if user is None:
            raise LookupError("User not found")
        ensure_can_generate_packet(session, user, todo_item_id)

        todo = TodoRepository(session).get_item(user_id, todo_item_id)
        if todo is None or todo.job is None:
            raise LookupError("Todo item not found")

        job = todo.job
        apply_url = (job.apply_url or job.source_url or "").strip()
        if not apply_url:
            raise ValueError("Job has no apply URL")

        repo = ApplicationPacketRepository(session)
        packet = repo.upsert_for_todo(
            user_id=user_id,
            todo_item_id=todo_item_id,
            job_id=job.id,
            apply_url=apply_url,
            status=ApplicationPacketStatus.GENERATING,
            ats_type=job.ats_type,
            fit_verdict=None,
            fit_rationale=[],
            identity={},
            resume_draft_id=None,
            resume_pdf_path=None,
            cover_letter=None,
            answers=[],
            generation_error=None,
        )
        if not (packet.label or "").strip():
            packet = repo.update(packet, label=_default_label(job))
        session.commit()
        session.refresh(packet)

        if not self._has_active_prefetch(session, todo_item_id):
            enqueue_job(
                session,
                PACKET_PREFETCH_JOB_TYPE,
                {"user_id": str(user_id), "todo_item_id": str(todo_item_id)},
                priority=6,
            )
            session.commit()

        return _packet_response(packet)

    def execute_generate(
        self, session: Session, user_id: uuid.UUID, todo_item_id: uuid.UUID
    ) -> ApplicationPacketResponse:
        user = UserRepository(session).get_by_id(user_id)
        if user is None:
            raise LookupError("User not found")
        ensure_can_generate_packet(session, user, todo_item_id)

        todo = TodoRepository(session).get_item(user_id, todo_item_id)
        if todo is None or todo.job is None:
            raise LookupError("Todo item not found")

        job = todo.job
        apply_url = (job.apply_url or job.source_url or "").strip()
        if not apply_url:
            raise ValueError("Job has no apply URL")

        ats_type = job.ats_type

        repo = ApplicationPacketRepository(session)
        packet = repo.upsert_for_todo(
            user_id=user_id,
            todo_item_id=todo_item_id,
            job_id=job.id,
            apply_url=apply_url,
            status=ApplicationPacketStatus.GENERATING,
            ats_type=ats_type,
            fit_verdict=None,
            fit_rationale=[],
            identity={},
            resume_draft_id=None,
            resume_pdf_path=None,
            cover_letter=None,
            answers=[],
            generation_error=None,
        )
        session.commit()

        try:
            profile_row = ProfileRepository(session).get_profile(user_id)
            user = UserRepository(session).get_by_id(user_id)
            email = user.email if user else None
            identity = resolve_identity(profile_row, account_email=email)
            profile = build_profile_snapshot(session, user_id)

            tailor_result = resume_service.tailor(
                session,
                user_id,
                ResumeTailorRequest(job_id=job.id),
            )
            job_payload = _job_payload(job)
            proposal = propose_application_packet(
                profile=profile,
                identity=identity,
                job=job_payload,
            )
            cover_letter = draft_cover_letter(
                profile=profile,
                identity=identity,
                job=job_payload,
                fit_rationale=list(proposal.get("fit_rationale") or []),
            )

            ready_fields: dict[str, Any] = {
                "status": ApplicationPacketStatus.READY,
                "identity": identity,
                "fit_verdict": proposal.get("fit_verdict"),
                "fit_rationale": proposal.get("fit_rationale") or [],
                "cover_letter": cover_letter,
                "answers": [],
                "resume_draft_id": tailor_result.draft.id,
                "generation_error": None,
            }
            if not (packet.label or "").strip():
                ready_fields["label"] = _default_label(job)
            packet = repo.update(packet, **ready_fields)
            session.commit()
            session.refresh(packet)
            return _packet_response(packet)
        except Exception as exc:
            logger.exception("application packet generation failed todo=%s", todo_item_id)
            packet = repo.update(
                packet,
                status=ApplicationPacketStatus.FAILED,
                generation_error=str(exc)[:500],
            )
            session.commit()
            session.refresh(packet)
            return _packet_response(packet)

    def generate(
        self, session: Session, user_id: uuid.UUID, todo_item_id: uuid.UUID
    ) -> ApplicationPacketResponse:
        """Run packet generation synchronously (worker/tests)."""
        return self.execute_generate(session, user_id, todo_item_id)

    def recover_stale_generating(
        self, session: Session, *, older_than_minutes: int = STALE_GENERATING_MINUTES
    ) -> int:
        """Re-queue packet generation for rows stuck in generating."""
        cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
        stale_packets = session.scalars(
            select(ApplicationPacket).where(
                ApplicationPacket.status == ApplicationPacketStatus.GENERATING.value,
                ApplicationPacket.updated_at < cutoff,
            )
        ).all()

        recovered = 0
        for packet in stale_packets:
            if packet.todo_item_id is None:
                continue
            if self._has_active_prefetch(session, packet.todo_item_id):
                continue
            enqueue_job(
                session,
                PACKET_PREFETCH_JOB_TYPE,
                {
                    "user_id": str(packet.user_id),
                    "todo_item_id": str(packet.todo_item_id),
                },
                priority=6,
            )
            recovered += 1
        if recovered:
            session.commit()
        return recovered

    def _has_active_prefetch(self, session: Session, todo_item_id: uuid.UUID) -> bool:
        todo_id = str(todo_item_id)
        jobs = session.scalars(
            select(QueueJob).where(
                QueueJob.job_type == PACKET_PREFETCH_JOB_TYPE,
                QueueJob.status.in_(
                    [QueueJobStatus.PENDING.value, QueueJobStatus.RUNNING.value]
                ),
            )
        ).all()
        for job in jobs:
            payload = job.payload or {}
            if str(payload.get("todo_item_id") or "") == todo_id:
                if job.status == QueueJobStatus.RUNNING.value and job.started_at is not None:
                    stale_cutoff = datetime.now(UTC) - timedelta(minutes=STALE_GENERATING_MINUTES)
                    if job.started_at < stale_cutoff:
                        continue
                return True
        return False

    def get(
        self, session: Session, user_id: uuid.UUID, todo_item_id: uuid.UUID
    ) -> ApplicationPacketResponse | None:
        packet = ApplicationPacketRepository(session).get_by_todo(user_id, todo_item_id)
        return _packet_response(packet) if packet else None

    def get_by_id(
        self, session: Session, user_id: uuid.UUID, packet_id: uuid.UUID
    ) -> ApplicationPacketResponse | None:
        packet = ApplicationPacketRepository(session).get_by_id(user_id, packet_id)
        return _packet_response(packet) if packet else None

    def patch(
        self,
        session: Session,
        user_id: uuid.UUID,
        todo_item_id: uuid.UUID,
        body: ApplicationPacketPatchRequest,
    ) -> ApplicationPacketResponse | None:
        repo = ApplicationPacketRepository(session)
        packet = repo.get_by_todo(user_id, todo_item_id)
        if packet is None:
            return None
        return self._apply_patch(session, user_id, packet, body)

    def patch_by_id(
        self,
        session: Session,
        user_id: uuid.UUID,
        packet_id: uuid.UUID,
        body: ApplicationPacketPatchRequest,
    ) -> ApplicationPacketResponse | None:
        repo = ApplicationPacketRepository(session)
        packet = repo.get_by_id(user_id, packet_id)
        if packet is None:
            return None
        return self._apply_patch(session, user_id, packet, body)

    def reuse_from(
        self,
        session: Session,
        user_id: uuid.UUID,
        todo_item_id: uuid.UUID,
        source_packet_id: uuid.UUID,
    ) -> ApplicationPacketResponse:
        repo = ApplicationPacketRepository(session)
        source = repo.get_by_id(user_id, source_packet_id)
        if source is None:
            raise LookupError("Source application not found")

        todo = TodoRepository(session).get_item(user_id, todo_item_id)
        if todo is None or todo.job is None:
            raise LookupError("Todo item not found")

        job = todo.job
        apply_url = (job.apply_url or job.source_url or "").strip()
        if not apply_url:
            raise ValueError("Job has no apply URL")

        target = repo.get_by_todo(user_id, todo_item_id)
        if target is None:
            target = repo.create(
                user_id=user_id,
                todo_item_id=todo_item_id,
                job_id=job.id,
                apply_url=apply_url,
                status=ApplicationPacketStatus.READY,
                ats_type=job.ats_type,
                fit_verdict=None,
                fit_rationale=[],
                identity=dict(source.identity or {}),
                cover_letter=source.cover_letter,
                answers=[],
                generation_error=None,
            )
        else:
            target = repo.update(
                target,
                apply_url=apply_url,
                job_id=job.id,
                status=ApplicationPacketStatus.READY,
                cover_letter=source.cover_letter,
                answers=[],
                generation_error=None,
            )

        if not (target.label or "").strip() and (source.label or "").strip():
            target = repo.update(target, label=source.label)
        elif not (target.label or "").strip():
            target = repo.update(target, label=_default_label(job))

        session.commit()
        session.refresh(target)
        return _packet_response(target, job)

    def _apply_patch(
        self,
        session: Session,
        user_id: uuid.UUID,
        packet: ApplicationPacket,
        body: ApplicationPacketPatchRequest,
    ) -> ApplicationPacketResponse:
        repo = ApplicationPacketRepository(session)
        updates: dict[str, Any] = {}
        if body.cover_letter is not None:
            updates["cover_letter"] = body.cover_letter
        if body.fit_verdict is not None:
            updates["fit_verdict"] = body.fit_verdict
        if body.label is not None:
            updates["label"] = body.label.strip()

        if body.answers:
            by_key = {
                str(item.get("key")): dict(item)
                for item in (packet.answers or [])
                if isinstance(item, dict) and item.get("key")
            }
            vault_repo = SavedApplicationAnswerRepository(session)
            for patch_item in body.answers:
                existing = by_key.get(patch_item.key, {"key": patch_item.key})
                existing["status"] = patch_item.status.value
                if patch_item.final_answer is not None:
                    existing["final_answer"] = patch_item.final_answer
                    if patch_item.status.value == "edited":
                        existing["suggested_answer"] = patch_item.final_answer
                existing["save_to_vault"] = patch_item.save_to_vault
                if "question_text" not in existing:
                    existing["question_text"] = patch_item.key.replace("_", " ").title()
                if "suggested_answer" not in existing:
                    existing["suggested_answer"] = patch_item.final_answer or ""
                if "source" not in existing:
                    existing["source"] = "user"
                by_key[patch_item.key] = existing

                should_save = patch_item.save_to_vault or (
                    patch_item.key in AUTO_VAULT_KEYS
                    and patch_item.status.value in {"confirmed", "edited"}
                )
                answer_text = (patch_item.final_answer or existing.get("suggested_answer") or "").strip()
                if should_save and answer_text:
                    vault_repo.upsert(
                        user_id,
                        question_key=patch_item.key,
                        question_text=str(existing.get("question_text") or patch_item.key),
                        answer=answer_text,
                        touch_used=True,
                    )
            updates["answers"] = list(by_key.values())

        if updates:
            packet = repo.update(packet, **updates)
            session.commit()
            session.refresh(packet)
        return _packet_response(packet)

    def open(
        self, session: Session, user_id: uuid.UUID, todo_item_id: uuid.UUID
    ) -> ApplicationPacketOpenResponse:
        repo = ApplicationPacketRepository(session)
        packet = repo.get_by_todo(user_id, todo_item_id)
        if packet is None:
            raise LookupError("Application packet not found")
        if packet.status == ApplicationPacketStatus.FAILED.value:
            raise ValueError("Packet generation failed; regenerate before opening")

        apply_url = (packet.apply_url or "").strip()
        if not apply_url:
            raise ValueError("Packet has no apply URL")

        packet = repo.update(packet, status=ApplicationPacketStatus.OPENED)
        session.commit()

        return ApplicationPacketOpenResponse(
            packet_id=packet.id,
            todo_item_id=todo_item_id,
            job_id=packet.job_id,
            apply_url=apply_url,
        )

    def iter_assist_sse(
        self,
        session: Session,
        user_id: uuid.UUID,
        todo_item_id: uuid.UUID,
        *,
        question: str,
    ) -> Iterator[str]:
        repo = ApplicationPacketRepository(session)
        packet = repo.get_by_todo(user_id, todo_item_id)
        if packet is None:
            yield f"data: {json.dumps({'type': 'error', 'detail': 'Application packet not found'})}\n\n"
            return

        todo = TodoRepository(session).get_item(user_id, todo_item_id)
        job = todo.job if todo is not None else None
        if job is None and packet.job_id is not None:
            job = session.get(Job, packet.job_id)

        snapshot = build_profile_snapshot(session, user_id)
        profile_row = ProfileRepository(session).get_profile(user_id)
        user = UserRepository(session).get_by_id(user_id)
        email = user.email if user else None
        identity = resolve_identity(profile_row, account_email=email)
        job_payload = _job_payload(job) if job is not None else None
        apply_url = (packet.apply_url or "").strip()
        page_title = f"{job.title} at {job.company_name}" if job is not None else "Application"

        parts: list[str] = []
        try:
            for chunk in apply_assist_stream(
                profile=snapshot,
                identity=identity,
                page_url=apply_url,
                page_title=page_title,
                selection_text="",
                selection_tag="",
                is_editable=True,
                question=question,
                job=job_payload,
            ):
                parts.append(chunk)
                yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"
            reply = "".join(parts).strip()
            yield f"data: {json.dumps({'type': 'done', 'reply': reply})}\n\n"
        except Exception as exc:
            logger.exception("packet assist failed todo=%s", todo_item_id)
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)[:240]})}\n\n"

    def list_prepared(
        self, session: Session, user_id: uuid.UUID
    ) -> PreparedPacketListResponse:
        repo = ApplicationPacketRepository(session)
        packets = repo.list_for_user(user_id, prepared_only=True)
        todo_repo = TodoRepository(session)
        items: list[PreparedPacketSummary] = []
        for packet in packets:
            job = session.get(Job, packet.job_id)
            title = job.title if job else "Job"
            company = job.company_name if job else "Unknown"
            todo_status = None
            if packet.todo_item_id is not None:
                todo = todo_repo.get_item(user_id, packet.todo_item_id)
                if todo is not None:
                    status_value = (
                        todo.status.value if hasattr(todo.status, "value") else str(todo.status)
                    )
                    try:
                        todo_status = TodoStatus(status_value)
                    except ValueError:
                        todo_status = None
            fit_verdict = packet.fit_verdict
            if fit_verdict not in {"apply", "lean_apply", "lean_skip", "skip"}:
                fit_verdict = None
            status_value = (
                packet.status.value if hasattr(packet.status, "value") else str(packet.status)
            )
            items.append(
                PreparedPacketSummary(
                    id=packet.id,
                    todo_item_id=packet.todo_item_id,
                    job_id=packet.job_id,
                    label=_packet_label(packet, job),
                    title=title,
                    company=company,
                    status=status_value,  # type: ignore[arg-type]
                    fit_verdict=fit_verdict,
                    answers_count=len(packet.answers or []),
                    has_cover_letter=bool((packet.cover_letter or "").strip()),
                    todo_status=todo_status,
                    updated_at=packet.updated_at,
                )
            )
        return PreparedPacketListResponse(items=items, total=len(items))


application_packet_service = ApplicationPacketService()
