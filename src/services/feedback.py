"""Service layer handling event feedback collection and moderation."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.repositories.events import EventRepository
from src.repositories.feedback import FeedbackRepository

__all__ = ["FeedbackService", "FeedbackValidationError", "FeedbackNotFoundError"]


class FeedbackValidationError(Exception):
    """Raised when feedback payload validation fails."""

    def __init__(self, errors: Dict[str, List[str]], message: str = "Validation échouée."):
        super().__init__(message)
        self.errors = errors
        self.message = message


class FeedbackNotFoundError(Exception):
    """Raised when a feedback entry is missing."""


class FeedbackService:
    """Collect attendee feedback and compute quality metrics."""

    ALLOWED_STATUSES = {"pending", "approved", "rejected"}

    def __init__(self, session: Session) -> None:
        self.session = session
        self.event_repository = EventRepository(session)
        self.repository = FeedbackRepository(session)

    def submit_feedback(self, event_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_event_exists(event_id)
        clean = self._validate_submission_payload(payload)
        feedback = self.repository.create(event_id=event_id, **clean)
        self.session.commit()
        return self._serialize_feedback(feedback)

    def list_feedback(self, event_id: int) -> Dict[str, Any]:
        self._ensure_event_exists(event_id)
        feedback_entries = self.repository.list_for_event(event_id)
        aggregates = self.repository.aggregates(event_id)
        return {
            "feedback": [self._serialize_feedback(entry) for entry in feedback_entries],
            "summary": {
                "total": aggregates["total"],
                "average_rating": round(aggregates["average"], 2) if aggregates["total"] else 0.0,
                "ratings_breakdown": aggregates["breakdown"],
                "pending": aggregates["pending"],
            },
        }

    def moderate_feedback(
        self, event_id: int, feedback_id: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        self._ensure_event_exists(event_id)
        feedback = self._get_feedback(event_id, feedback_id)
        status, moderator = self._validate_moderation_payload(payload)
        updated = self.repository.update_status(feedback, status=status, moderator=moderator)
        self.session.commit()
        return self._serialize_feedback(updated)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_event_exists(self, event_id: int) -> None:
        try:
            self.event_repository.get_event(event_id)
        except LookupError as exc:
            raise FeedbackNotFoundError(str(exc)) from exc

    def _get_feedback(self, event_id: int, feedback_id: int):
        try:
            return self.repository.get(event_id, feedback_id)
        except LookupError as exc:
            raise FeedbackNotFoundError(str(exc)) from exc

    def _validate_submission_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(data, dict):
            raise FeedbackValidationError(
                {"_schema": ["Payload JSON invalide: un objet est requis."]}
            )

        errors: Dict[str, List[str]] = {}
        clean: Dict[str, Any] = {}

        rating = data.get("rating")
        if isinstance(rating, int) and 1 <= rating <= 5:
            clean["rating"] = rating
        else:
            errors.setdefault("rating", []).append("Note comprise entre 1 et 5 requise.")

        comment = data.get("comment")
        if comment is None or isinstance(comment, str):
            clean["comment"] = comment.strip() if isinstance(comment, str) and comment.strip() else comment
        else:
            errors.setdefault("comment", []).append("Commentaire invalide.")

        if "email" in data:
            email = data.get("email")
            if email is None:
                clean["participant_email"] = None
            elif isinstance(email, str) and email.strip():
                clean["participant_email"] = email.strip().lower()
            else:
                errors.setdefault("email", []).append("Email invalide.")

        if "name" in data:
            name = data.get("name")
            if name is None:
                clean["participant_name"] = None
            elif isinstance(name, str) and name.strip():
                clean["participant_name"] = name.strip()
            else:
                errors.setdefault("name", []).append("Nom invalide.")

        if "sentiment" in data:
            sentiment = data.get("sentiment")
            if sentiment is None or isinstance(sentiment, str):
                clean["sentiment"] = sentiment.strip() if isinstance(sentiment, str) else sentiment
            else:
                errors.setdefault("sentiment", []).append("Champ sentiment invalide.")

        metadata = data.get("metadata")
        if metadata is not None:
            if isinstance(metadata, dict):
                clean["metadata"] = metadata
            else:
                errors.setdefault("metadata", []).append("Métadonnées invalides.")
        else:
            clean["metadata"] = None

        if errors:
            raise FeedbackValidationError(errors)

        return clean

    def _validate_moderation_payload(self, data: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        if not isinstance(data, dict):
            raise FeedbackValidationError(
                {"_schema": ["Payload JSON invalide: un objet est requis."]}
            )

        errors: Dict[str, List[str]] = {}
        status = data.get("status")
        if status not in self.ALLOWED_STATUSES:
            errors.setdefault("status", []).append("Statut de modération invalide.")

        moderator = data.get("moderator")
        if moderator is not None and (not isinstance(moderator, str) or not moderator.strip()):
            errors.setdefault("moderator", []).append("Nom du modérateur invalide.")
        clean_moderator = moderator.strip() if isinstance(moderator, str) and moderator.strip() else None

        if errors:
            raise FeedbackValidationError(errors)
        return status, clean_moderator

    def _serialize_feedback(self, feedback) -> Dict[str, Any]:
        return {
            "id": feedback.id,
            "event_id": feedback.event_id,
            "email": feedback.participant_email,
            "name": feedback.participant_name,
            "rating": feedback.rating,
            "comment": feedback.comment,
            "sentiment": feedback.sentiment,
            "status": feedback.status,
            "metadata": feedback.metadata or {},
            "moderated_by": feedback.moderated_by,
            "moderated_at": feedback.moderated_at.isoformat() if feedback.moderated_at else None,
            "created_at": feedback.created_at.isoformat(),
        }
