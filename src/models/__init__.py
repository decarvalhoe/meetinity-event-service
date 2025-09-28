"""SQLAlchemy models for the event service domain."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class TimestampMixin:
    """Mixin providing automatic created/updated timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


event_categories_events = Table(
    "event_categories_events",
    Base.metadata,
    mapped_column("event_id", ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
    mapped_column(
        "category_id",
        ForeignKey("event_categories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


event_tags_events = Table(
    "event_tags_events",
    Base.metadata,
    mapped_column("event_id", ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
    mapped_column(
        "tag_id", ForeignKey("event_tags.id", ondelete="CASCADE"), primary_key=True
    ),
)


class EventCategory(TimestampMixin, Base):
    __tablename__ = "event_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)

    events: Mapped[List["Event"]] = relationship(
        "Event",
        secondary=event_categories_events,
        back_populates="categories",
    )


class EventTag(TimestampMixin, Base):
    __tablename__ = "event_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    events: Mapped[List["Event"]] = relationship(
        "Event", secondary=event_tags_events, back_populates="tags"
    )


class EventTemplate(TimestampMixin, Base):
    __tablename__ = "event_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    default_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)

    events: Mapped[List["Event"]] = relationship(
        "Event", back_populates="template", cascade="all, delete"
    )


class EventSeries(TimestampMixin, Base):
    __tablename__ = "event_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)

    events: Mapped[List["Event"]] = relationship(
        "Event", back_populates="series", cascade="all, delete"
    )


class Event(TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("attendees >= 0", name="ck_events_attendees_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255))
    event_type: Mapped[Optional[str]] = mapped_column(String(120))
    attendees: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    template_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("event_templates.id", ondelete="SET NULL")
    )
    series_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("event_series.id", ondelete="SET NULL")
    )

    template: Mapped[Optional[EventTemplate]] = relationship(
        "EventTemplate", back_populates="events"
    )
    series: Mapped[Optional[EventSeries]] = relationship(
        "EventSeries", back_populates="events"
    )
    categories: Mapped[List[EventCategory]] = relationship(
        "EventCategory",
        secondary=event_categories_events,
        back_populates="events",
    )
    tags: Mapped[List[EventTag]] = relationship(
        "EventTag", secondary=event_tags_events, back_populates="events"
    )
    translations: Mapped[List["EventTranslation"]] = relationship(
        "EventTranslation", back_populates="event", cascade="all, delete-orphan"
    )
    approvals: Mapped[List["EventApproval"]] = relationship(
        "EventApproval", back_populates="event", cascade="all, delete-orphan"
    )


class EventTranslation(TimestampMixin, Base):
    __tablename__ = "event_translations"
    __table_args__ = (
        UniqueConstraint("event_id", "locale", name="uq_event_translation_locale"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    locale: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    event: Mapped[Event] = relationship("Event", back_populates="translations")


class EventApproval(TimestampMixin, Base):
    __tablename__ = "event_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Enum("pending", "approved", "rejected", name="event_approval_status"),
        nullable=False,
        default="pending",
    )
    approved_by: Mapped[Optional[str]] = mapped_column(String(120))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    event: Mapped[Event] = relationship("Event", back_populates="approvals")


__all__ = [
    "Event",
    "EventApproval",
    "EventCategory",
    "EventSeries",
    "EventTag",
    "EventTemplate",
    "EventTranslation",
]
