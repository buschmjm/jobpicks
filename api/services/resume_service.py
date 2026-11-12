"""Resume builder — master + job-tailored drafts."""

from __future__ import annotations

import uuid
from typing import Any

from core.models import Job, ResumeDraft
from core.resume.document import apply_tailor_selection, build_master_document
from core.resume.render import render_ats_html
from inference.resume_tailor import propose_resume_tailor
from sqlalchemy.orm import Session

from api.repositories.user_repo import UserRepository
from api.schemas import (
    ResumeDraftResponse,
    ResumeTailorRequest,
    ResumeTailorResponse,
)


def _draft_response(row: ResumeDraft) -> ResumeDraftResponse:
    return ResumeDraftResponse(
        id=row.id,
        job_id=row.job_id,
        status=row.status,  # type: ignore[arg-type]
        layout=row.layout,  # type: ignore[arg-type]
        document=row.document or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ResumeService:
    def build_master(self, session: Session, user_id: uuid.UUID) -> ResumeDraftResponse:
        user = UserRepository(session).get_by_id(user_id)
        email = user.email if user else None
        document = build_master_document(session, user_id, email=email)
        row = ResumeDraft(
            user_id=user_id,
            job_id=None,
            status="draft",
            layout="ats",
            document=document,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _draft_response(row)

    def tailor(self, session: Session, user_id: uuid.UUID, body: ResumeTailorRequest) -> ResumeTailorResponse:
        user = UserRepository(session).get_by_id(user_id)
        email = user.email if user else None
        master = build_master_document(session, user_id, email=email)

        job_payload = self._job_payload(session, body)
        target = {
            "job_id": str(job_payload.get("job_id") or "") or None,
            "title": job_payload.get("title") or "",
            "company": job_payload.get("company") or "",
            "source_url": job_payload.get("source_url") or "",
        }
        selection, source = propose_resume_tailor(catalog=master, job=job_payload)
        document = apply_tailor_selection(master, selection, target=target)

        job_uuid = None
        if body.job_id:
            job_uuid = body.job_id
        elif job_payload.get("job_id"):
            try:
                job_uuid = uuid.UUID(str(job_payload["job_id"]))
            except ValueError:
                job_uuid = None

        row = ResumeDraft(
            user_id=user_id,
            job_id=job_uuid,
            status="draft",
            layout="ats",
            document=document,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return ResumeTailorResponse(draft=_draft_response(row), source=source)  # type: ignore[arg-type]

    def get_draft(self, session: Session, user_id: uuid.UUID, draft_id: uuid.UUID) -> ResumeDraftResponse:
        row = self._get_owned(session, user_id, draft_id)
        return _draft_response(row)

    def update_draft(
        self,
        session: Session,
        user_id: uuid.UUID,
        draft_id: uuid.UUID,
        document: dict[str, Any],
        *,
        status: str | None = None,
    ) -> ResumeDraftResponse:
        row = self._get_owned(session, user_id, draft_id)
        row.document = document
        if status:
            row.status = status
        session.commit()
        session.refresh(row)
        return _draft_response(row)

    def accept_draft(self, session: Session, user_id: uuid.UUID, draft_id: uuid.UUID) -> ResumeDraftResponse:
        draft = self._get_owned(session, user_id, draft_id)
        return self.update_draft(session, user_id, draft_id, draft.document, status="accepted")

    def render_html(self, session: Session, user_id: uuid.UUID, draft_id: uuid.UUID) -> str:
        row = self._get_owned(session, user_id, draft_id)
        return render_ats_html(row.document or {})

    def _get_owned(self, session: Session, user_id: uuid.UUID, draft_id: uuid.UUID) -> ResumeDraft:
        row = session.get(ResumeDraft, draft_id)
        if row is None or row.user_id != user_id:
            raise LookupError("Resume draft not found")
        return row

    def _job_payload(self, session: Session, body: ResumeTailorRequest) -> dict[str, Any]:
        if body.job_id:
            job = session.get(Job, body.job_id)
            if job is not None:
                return {
                    "job_id": str(job.id),
                    "title": job.title,
                    "company": job.company_name,
                    "description": (job.description or "")[:4000],
                    "source_url": job.source_url or "",
                    "why": [],
                    "caution": [],
                }
        return {
            "job_id": str(body.job_id) if body.job_id else "",
            "title": body.title or "",
            "company": body.company or "",
            "description": (body.description or "")[:4000],
            "source_url": body.source_url or "",
            "why": list(body.why_bullets or []),
            "caution": list(body.caution_bullets or []),
        }


resume_service = ResumeService()
