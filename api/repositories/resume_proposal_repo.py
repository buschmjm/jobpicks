"""Resume builder proposal persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from core.models import ResumeProposal
from sqlalchemy import select
from sqlalchemy.orm import Session


class ResumeProposalRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_proposal(self, user_id: uuid.UUID, proposal_id: uuid.UUID) -> ResumeProposal | None:
        return self._session.scalar(
            select(ResumeProposal)
            .where(ResumeProposal.id == proposal_id)
            .where(ResumeProposal.user_id == user_id)
        )

    def list_by_status(
        self,
        user_id: uuid.UUID,
        status: str,
        *,
        limit: int = 50,
    ) -> list[ResumeProposal]:
        return list(
            self._session.scalars(
                select(ResumeProposal)
                .where(ResumeProposal.user_id == user_id)
                .where(ResumeProposal.status == status)
                .order_by(ResumeProposal.created_at.desc())
                .limit(limit)
            )
        )

    def create(
        self,
        user_id: uuid.UUID,
        *,
        proposal_type: str,
        operations: list[dict[str, Any]],
        preview_summary: str,
        variant_id: uuid.UUID | None = None,
        message_id: uuid.UUID | None = None,
        status: str = "pending",
    ) -> ResumeProposal:
        row = ResumeProposal(
            user_id=user_id,
            variant_id=variant_id,
            message_id=message_id,
            status=status,
            proposal_type=proposal_type,
            operations=list(operations),
            preview_summary=preview_summary,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def mark_applied(self, proposal: ResumeProposal) -> ResumeProposal:
        proposal.status = "applied"
        proposal.applied_at = datetime.now(UTC)
        self._session.flush()
        return proposal

    def mark_rejected(self, proposal: ResumeProposal) -> ResumeProposal:
        proposal.status = "rejected"
        self._session.flush()
        return proposal

    def set_preview_summary(self, proposal: ResumeProposal, summary: str) -> ResumeProposal:
        proposal.preview_summary = summary
        self._session.flush()
        return proposal
