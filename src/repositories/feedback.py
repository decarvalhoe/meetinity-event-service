"""Repository helpers for managing event feedback."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models import EventFeedback


class FeedbackRepository:
    """Persistence operations for event feedback entries."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        event_id: int,
        participant_email: Optional[str],
        participant_name: Optional[str],
        rating: int,
        comment: Optional[str],
        sentiment: Optional[str],
        metadata: Optional[dict],
    ) -> EventFeedback:
        feedback = EventFeedback(
            event_id=event_id,
            participant_email=participant_email,
            participant_name=participant_name,
            rating=rating,
            comment=comment,
            sentiment=sentiment,
            metadata=metadata,
        )
        self.session.add(feedback)
        self.session.flush()
        self.session.refresh(feedback)
        return feedback

    def list_for_event(self, event_id: int) -> Sequence[EventFeedback]:
        query = (
            select(EventFeedback)
            .where(EventFeedback.event_id == event_id)
            .order_by(EventFeedback.created_at.desc())
        )
        return self.session.scalars(query).all()

    def get(self, event_id: int, feedback_id: int) -> EventFeedback:
        feedback = self.session.get(EventFeedback, feedback_id)
        if feedback is None or feedback.event_id != event_id:
            raise LookupError(f"Feedback {feedback_id} introuvable pour l'événement {event_id}")
        return feedback

    def update_status(
        self,
        feedback: EventFeedback,
        *,
        status: str,
        moderator: Optional[str],
    ) -> EventFeedback:
        feedback.status = status
        feedback.moderated_by = moderator
        if moderator:
            feedback.moderated_at = datetime.now(timezone.utc)
        else:
            feedback.moderated_at = None
        self.session.flush()
        self.session.refresh(feedback)
        return feedback

    def aggregates(self, event_id: int) -> Dict[str, float]:
        base_query = select(
            func.count(EventFeedback.id),
            func.avg(EventFeedback.rating),
        ).where(EventFeedback.event_id == event_id)
        total, average = self.session.execute(base_query).one()

        breakdown_query = select(
            EventFeedback.rating,
            func.count(EventFeedback.id),
        ).where(EventFeedback.event_id == event_id)
        breakdown_query = breakdown_query.group_by(EventFeedback.rating)
        breakdown_rows = self.session.execute(breakdown_query).all()
        breakdown = {row[0]: row[1] for row in breakdown_rows}

        pending_query = select(func.count(EventFeedback.id)).where(
            EventFeedback.event_id == event_id,
            EventFeedback.status == "pending",
        )
        pending_total = self.session.execute(pending_query).scalar_one()

        return {
            "total": int(total or 0),
            "average": float(average or 0.0),
            "breakdown": {int(k): int(v) for k, v in breakdown.items()},
            "pending": int(pending_total or 0),
        }
