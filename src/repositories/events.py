"""Repository objects for managing event persistence."""
from __future__ import annotations

from datetime import date
from typing import Iterable, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session, joinedload, selectinload

from src.models import (
    Event,
    EventApprovalLog,
    EventCategory,
    EventNotification,
    EventSeries,
    EventSpeaker,
    EventSponsor,
    EventTag,
    EventTemplate,
    EventTranslation,
    NetworkingSuggestion,
    ParticipantProfile,
)


class EventRepository:
    """Persistence operations for events and related aggregates."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_events(
        self,
        *,
        event_type: Optional[str] = None,
        location: Optional[str] = None,
        before: Optional[date] = None,
        after: Optional[date] = None,
        status: Optional[str] = None,
    ) -> Sequence[Event]:
        query = (
            select(Event)
            .options(
                joinedload(Event.series),
                selectinload(Event.categories),
                selectinload(Event.tags),
                selectinload(Event.translations),
                selectinload(Event.participant_profiles),
                selectinload(Event.networking_suggestions)
                .joinedload(NetworkingSuggestion.suggested_participant),
                selectinload(Event.feedback_entries),
                selectinload(Event.speaker_profiles),
                selectinload(Event.sponsors),
            )
            .order_by(Event.event_date.asc(), Event.id.asc())
        )

        if event_type:
            query = query.where(func.lower(Event.event_type) == event_type.casefold())
        if location:
            query = query.where(func.lower(Event.location) == location.casefold())
        if before:
            query = query.where(Event.event_date <= before)
        if after:
            query = query.where(Event.event_date >= after)
        if status:
            query = query.where(Event.status == status)

        return self.session.scalars(query).all()

    def get_event(self, event_id: int) -> Event:
        query = (
            select(Event)
            .options(
                joinedload(Event.series),
                selectinload(Event.categories),
                selectinload(Event.tags),
                selectinload(Event.translations),
                selectinload(Event.participant_profiles),
                selectinload(Event.networking_suggestions)
                .joinedload(NetworkingSuggestion.suggested_participant),
                selectinload(Event.feedback_entries),
                selectinload(Event.speaker_profiles),
                selectinload(Event.sponsors),
            )
            .where(Event.id == event_id)
        )
        try:
            return self.session.execute(query).scalar_one()
        except NoResultFound as exc:
            raise LookupError(f"Event {event_id} not found") from exc

    def create_event(
        self,
        *,
        title: str,
        event_date: date,
        location: Optional[str],
        event_type: Optional[str],
        attendees: int,
        timezone: str,
        status: str,
        event_format: str,
        streaming_url: Optional[str],
        virtual_platform: Optional[str],
        virtual_access_instructions: Optional[str],
        secure_access_token: Optional[str],
        rtmp_ingest_url: Optional[str],
        rtmp_stream_key: Optional[str],
        capacity_limit: Optional[int],
        recurrence_rule: Optional[str],
        default_locale: str,
        fallback_locale: Optional[str],
        organizer_email: Optional[str],
        settings: Optional[dict],
        series: Optional[EventSeries] = None,
        template: Optional[EventTemplate] = None,
        categories: Optional[Iterable[EventCategory]] = None,
        tags: Optional[Iterable[EventTag]] = None,
    ) -> Event:
        event = Event(
            title=title,
            event_date=event_date,
            location=location,
            event_type=event_type,
            attendees=attendees,
            timezone=timezone,
            status=status,
            event_format=event_format,
            streaming_url=streaming_url,
            virtual_platform=virtual_platform,
            virtual_access_instructions=virtual_access_instructions,
            secure_access_token=secure_access_token,
            rtmp_ingest_url=rtmp_ingest_url,
            rtmp_stream_key=rtmp_stream_key,
            capacity_limit=capacity_limit,
            recurrence_rule=recurrence_rule,
            default_locale=default_locale,
            fallback_locale=fallback_locale,
            organizer_email=organizer_email,
            settings=settings,
        )
        if series:
            event.series = series
        if template:
            event.template = template
        if categories:
            event.categories = list(categories)
        if tags:
            event.tags = list(tags)

        self.session.add(event)
        self.session.flush()
        self.session.refresh(event)
        return event

    def update_event(self, event: Event, updates: dict) -> Event:
        for key, value in updates.items():
            setattr(event, key, value)
        self.session.flush()
        self.session.refresh(event)
        return event

    def assign_series(self, event: Event, series: Optional[EventSeries]) -> None:
        event.series = series
        self.session.flush()

    def assign_categories(
        self, event: Event, categories: Iterable[EventCategory]
    ) -> Event:
        event.categories = list(categories)
        self.session.flush()
        self.session.refresh(event)
        return event

    def assign_tags(self, event: Event, tags: Iterable[EventTag]) -> Event:
        event.tags = list(tags)
        self.session.flush()
        self.session.refresh(event)
        return event

    def upsert_translation(
        self,
        event: Event,
        *,
        locale: str,
        title: str,
        description: Optional[str],
        fallback: Optional[bool],
    ) -> EventTranslation:
        translation = next(
            (t for t in event.translations if t.locale == locale),
            None,
        )
        if translation is None:
            translation = EventTranslation(
                event=event,
                locale=locale,
                title=title,
                description=description,
            )
            self.session.add(translation)
        else:
            translation.title = title
            translation.description = description
        if fallback is True:
            event.fallback_locale = locale
        elif fallback is False and event.fallback_locale == locale:
            event.fallback_locale = None
        self.session.flush()
        self.session.refresh(translation)
        return translation

    def remove_translation(self, event: Event, locale: str) -> None:
        translation = next((t for t in event.translations if t.locale == locale), None)
        if translation is None:
            raise LookupError(f"Translation {locale} not found for event {event.id}")
        self.session.delete(translation)
        if event.fallback_locale == locale:
            event.fallback_locale = None

    def log_status_change(
        self,
        event: Event,
        *,
        previous_status: Optional[str],
        new_status: str,
        actor: Optional[str],
        notes: Optional[str],
    ) -> EventApprovalLog:
        log = EventApprovalLog(
            event=event,
            previous_status=previous_status,
            new_status=new_status,
            actor=actor,
            notes=notes,
        )
        self.session.add(log)
        event.status = new_status
        self.session.flush()
        self.session.refresh(log)
        return log

    def create_notification(
        self,
        event: Event,
        *,
        recipient: str,
        message: str,
        channel: str = "email",
    ) -> EventNotification:
        notification = EventNotification(
            event=event,
            recipient=recipient,
            message=message,
            channel=channel,
        )
        self.session.add(notification)
        self.session.flush()
        self.session.refresh(notification)
        return notification

    def remove_event(self, event: Event) -> None:
        self.session.delete(event)
