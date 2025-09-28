"""Repositories for networking and participant collaboration features."""
from __future__ import annotations

from typing import Iterable, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import NetworkingSuggestion, ParticipantProfile


class ParticipantProfileRepository:
    """Persistence utilities for participant networking profiles."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        *,
        event_id: int,
        attendee_email: str,
        attendee_name: Optional[str],
        company: Optional[str],
        bio: Optional[str],
        headline: Optional[str],
        interests: Optional[dict],
        goals: Optional[dict],
        availability: Optional[dict],
        metadata: Optional[dict],
    ) -> ParticipantProfile:
        profile = self.get_by_event_and_email(event_id, attendee_email)
        if profile is None:
            profile = ParticipantProfile(
                event_id=event_id,
                attendee_email=attendee_email,
            )
            self.session.add(profile)

        profile.attendee_name = attendee_name
        profile.company = company
        profile.bio = bio
        profile.headline = headline
        profile.interests = interests
        profile.goals = goals
        profile.availability = availability
        profile.metadata = metadata
        self.session.flush()
        self.session.refresh(profile)
        return profile

    def list_for_event(self, event_id: int) -> Sequence[ParticipantProfile]:
        query = (
            select(ParticipantProfile)
            .where(ParticipantProfile.event_id == event_id)
            .order_by(ParticipantProfile.attendee_name.asc())
        )
        return self.session.scalars(query).all()

    def get_by_event_and_email(
        self, event_id: int, attendee_email: str
    ) -> Optional[ParticipantProfile]:
        query = (
            select(ParticipantProfile)
            .where(ParticipantProfile.event_id == event_id)
            .where(ParticipantProfile.attendee_email == attendee_email)
        )
        return self.session.scalars(query).first()

    def get(self, profile_id: int) -> ParticipantProfile:
        profile = self.session.get(ParticipantProfile, profile_id)
        if profile is None:
            raise LookupError(f"Participant profile {profile_id} not found")
        return profile


class NetworkingSuggestionRepository:
    """Persistence helper for networking suggestions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        *,
        event_id: int,
        participant_id: int,
        suggested_participant_id: int,
        score: float,
        rationale: Optional[str],
        metadata: Optional[dict],
        status: Optional[str] = None,
    ) -> NetworkingSuggestion:
        query = (
            select(NetworkingSuggestion)
            .where(NetworkingSuggestion.participant_id == participant_id)
            .where(
                NetworkingSuggestion.suggested_participant_id
                == suggested_participant_id
            )
        )
        suggestion = self.session.scalars(query).first()
        if suggestion is None:
            suggestion = NetworkingSuggestion(
                event_id=event_id,
                participant_id=participant_id,
                suggested_participant_id=suggested_participant_id,
            )
            self.session.add(suggestion)

        suggestion.score = score
        suggestion.rationale = rationale
        suggestion.metadata = metadata
        if status is not None:
            suggestion.status = status
        self.session.flush()
        self.session.refresh(suggestion)
        return suggestion

    def list_for_participant(
        self, participant_id: int, *, statuses: Optional[Iterable[str]] = None
    ) -> Sequence[NetworkingSuggestion]:
        query = select(NetworkingSuggestion).where(
            NetworkingSuggestion.participant_id == participant_id
        )
        if statuses is not None:
            query = query.where(NetworkingSuggestion.status.in_(list(statuses)))
        query = query.order_by(NetworkingSuggestion.score.desc())
        return self.session.scalars(query).all()

    def list_for_event(self, event_id: int) -> Sequence[NetworkingSuggestion]:
        query = (
            select(NetworkingSuggestion)
            .where(NetworkingSuggestion.event_id == event_id)
            .order_by(NetworkingSuggestion.score.desc())
        )
        return self.session.scalars(query).all()

    def get(self, suggestion_id: int) -> NetworkingSuggestion:
        suggestion = self.session.get(NetworkingSuggestion, suggestion_id)
        if suggestion is None:
            raise LookupError(f"Networking suggestion {suggestion_id} not found")
        return suggestion
