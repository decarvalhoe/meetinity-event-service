"""Repositories handling speakers, organisers and sponsors."""
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import EventSpeaker, EventSponsor


class EventSpeakerRepository:
    """Manage event speakers and organisers."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        event_id: int,
        full_name: str,
        role: str,
        title: Optional[str],
        company: Optional[str],
        bio: Optional[str],
        topics: Optional[dict],
        contact_email: Optional[str],
        photo_url: Optional[str],
        metadata: Optional[dict],
        display_order: int,
    ) -> EventSpeaker:
        speaker = EventSpeaker(
            event_id=event_id,
            full_name=full_name,
            role=role,
            title=title,
            company=company,
            bio=bio,
            topics=topics,
            contact_email=contact_email,
            photo_url=photo_url,
            metadata=metadata,
            display_order=display_order,
        )
        self.session.add(speaker)
        self.session.flush()
        self.session.refresh(speaker)
        return speaker

    def list_for_event(self, event_id: int, *, role: Optional[str] = None) -> Sequence[EventSpeaker]:
        query = select(EventSpeaker).where(EventSpeaker.event_id == event_id)
        if role:
            query = query.where(EventSpeaker.role == role)
        query = query.order_by(EventSpeaker.display_order.asc(), EventSpeaker.full_name.asc())
        return self.session.scalars(query).all()

    def get(self, event_id: int, speaker_id: int) -> EventSpeaker:
        speaker = self.session.get(EventSpeaker, speaker_id)
        if speaker is None or speaker.event_id != event_id:
            raise LookupError(f"Speaker {speaker_id} introuvable pour l'événement {event_id}")
        return speaker

    def update(self, speaker: EventSpeaker, updates: dict) -> EventSpeaker:
        for key, value in updates.items():
            setattr(speaker, key, value)
        self.session.flush()
        self.session.refresh(speaker)
        return speaker

    def delete(self, speaker: EventSpeaker) -> None:
        self.session.delete(speaker)


class EventSponsorRepository:
    """Persistence layer for event sponsors."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        event_id: int,
        name: str,
        level: Optional[str],
        description: Optional[str],
        website: Optional[str],
        logo_url: Optional[str],
        contact_email: Optional[str],
        metadata: Optional[dict],
        display_order: int,
    ) -> EventSponsor:
        sponsor = EventSponsor(
            event_id=event_id,
            name=name,
            level=level,
            description=description,
            website=website,
            logo_url=logo_url,
            contact_email=contact_email,
            metadata=metadata,
            display_order=display_order,
        )
        self.session.add(sponsor)
        self.session.flush()
        self.session.refresh(sponsor)
        return sponsor

    def list_for_event(self, event_id: int) -> Sequence[EventSponsor]:
        query = (
            select(EventSponsor)
            .where(EventSponsor.event_id == event_id)
            .order_by(EventSponsor.display_order.asc(), EventSponsor.name.asc())
        )
        return self.session.scalars(query).all()

    def get(self, event_id: int, sponsor_id: int) -> EventSponsor:
        sponsor = self.session.get(EventSponsor, sponsor_id)
        if sponsor is None or sponsor.event_id != event_id:
            raise LookupError(f"Sponsor {sponsor_id} introuvable pour l'événement {event_id}")
        return sponsor

    def update(self, sponsor: EventSponsor, updates: dict) -> EventSponsor:
        for key, value in updates.items():
            setattr(sponsor, key, value)
        self.session.flush()
        self.session.refresh(sponsor)
        return sponsor

    def delete(self, sponsor: EventSponsor) -> None:
        self.session.delete(sponsor)
