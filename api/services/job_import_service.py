"""Import jobs from user-supplied apply URLs."""

from __future__ import annotations

import uuid

from core.apply.job_from_url import JobFromUrlError, standard_job_from_url
from core.packet_entitlements import can_generate_packet
from ingest.runner import persist_job
from sqlalchemy.orm import Session
from workers.consumer import enqueue_job

from api.repositories.todo_repo import TodoRepository
from api.repositories.user_repo import UserRepository
from api.schemas import JobFromUrlRequest, JobFromUrlResponse
from api.services.todo_service import todo_item_from_orm


class JobImportService:
    def import_from_url(
        self,
        session: Session,
        user_id: uuid.UUID,
        body: JobFromUrlRequest,
    ) -> JobFromUrlResponse:
        try:
            std_job = standard_job_from_url(body.url)
        except JobFromUrlError:
            raise
        except Exception as exc:
            raise JobFromUrlError(f"Failed to import job: {exc}") from exc

        job_row, _created = persist_job(session, std_job)
        todo = TodoRepository(session).create(user_id, job_row.id)
        session.flush()

        packet_status = "skipped"
        if body.generate_packet:
            user = UserRepository(session).get_by_id(user_id)
            if user is not None and can_generate_packet(session, user, todo.id):
                enqueue_job(
                    session,
                    "packet_prefetch",
                    {"user_id": str(user_id), "todo_item_id": str(todo.id)},
                    priority=6,
                )
                packet_status = "queued"
            elif user is not None:
                packet_status = "skipped_limit"
            else:
                packet_status = "skipped"

        session.commit()
        session.refresh(job_row)
        session.refresh(todo)

        return JobFromUrlResponse(
            job_id=job_row.id,
            todo_item_id=todo.id,
            apply_url=job_row.apply_url or job_row.source_url,
            ats_type=job_row.ats_type,
            title=job_row.title,
            company=job_row.company_name,
            packet_status=packet_status,  # type: ignore[arg-type]
            todo_item=todo_item_from_orm(todo),
        )


job_import_service = JobImportService()
