"""Repository objects for managing event persistence."""
from __future__ import annotations

from datetime import date
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session, joinedload

from src.models import Event, EventSeries


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
    ) -> Sequence[Event]:
        query = (
            select(Event)
            .options(joinedload(Event.series))
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

        return self.session.scalars(query).all()

    def get_event(self, event_id: int) -> Event:
        query = (
            select(Event)
            .options(joinedload(Event.series))
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
        series: Optional[EventSeries] = None,
    ) -> Event:
        event = Event(
            title=title,
            event_date=event_date,
            location=location,
            event_type=event_type,
            attendees=attendees,
        )
        if series:
            event.series = series

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

    def get_or_create_series(self, name: str) -> EventSeries:
        query = select(EventSeries).where(func.lower(EventSeries.name) == name.casefold())
        result = self.session.scalars(query).first()
        if result:
            return result

        series = EventSeries(name=name.strip())
        self.session.add(series)
        self.session.flush()
        self.session.refresh(series)
        return series

    def get_series_by_id(self, series_id: int) -> Optional[EventSeries]:
        return self.session.get(EventSeries, series_id)

    def assign_series(self, event: Event, series: Optional[EventSeries]) -> None:
        event.series = series
        self.session.flush()

    def remove_event(self, event: Event) -> None:
        self.session.delete(event)
