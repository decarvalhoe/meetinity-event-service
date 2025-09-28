"""SQLAlchemy models for the event service domain."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
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
    default_timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    default_locale: Mapped[str] = mapped_column(String(10), nullable=False, default="fr")
    fallback_locale: Mapped[Optional[str]] = mapped_column(String(10))
    default_capacity_limit: Mapped[Optional[int]] = mapped_column(Integer)
    default_metadata: Mapped[Optional[dict]] = mapped_column(JSON)

    events: Mapped[List["Event"]] = relationship(
        "Event", back_populates="template", cascade="all, delete"
    )
    translations: Mapped[List["EventTemplateTranslation"]] = relationship(
        "EventTemplateTranslation",
        back_populates="template",
        cascade="all, delete-orphan",
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
        CheckConstraint(
            "capacity_limit IS NULL OR capacity_limit >= attendees",
            name="ck_events_capacity_above_attendees",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255))
    event_type: Mapped[Optional[str]] = mapped_column(String(120))
    attendees: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    registration_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    registration_deadline: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    status: Mapped[str] = mapped_column(
        Enum("draft", "pending", "approved", "rejected", name="event_status"),
        nullable=False,
        default="draft",
    )
    capacity_limit: Mapped[Optional[int]] = mapped_column(Integer)
    recurrence_rule: Mapped[Optional[str]] = mapped_column(String(255))
    default_locale: Mapped[str] = mapped_column(String(10), nullable=False, default="fr")
    fallback_locale: Mapped[Optional[str]] = mapped_column(String(10))
    organizer_email: Mapped[Optional[str]] = mapped_column(String(255))
    settings: Mapped[Optional[dict]] = mapped_column(JSON)
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
    approval_logs: Mapped[List["EventApprovalLog"]] = relationship(
        "EventApprovalLog", back_populates="event", cascade="all, delete-orphan"
    )
    notifications: Mapped[List["EventNotification"]] = relationship(
        "EventNotification", back_populates="event", cascade="all, delete-orphan"
    )
    registrations: Mapped[List["Registration"]] = relationship(
        "Registration",
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="Registration.created_at",
    )
    waitlist_entries: Mapped[List["WaitlistEntry"]] = relationship(
        "WaitlistEntry",
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="WaitlistEntry.created_at",
    )
    penalties: Mapped[List["NoShowPenalty"]] = relationship(
        "NoShowPenalty", back_populates="event", cascade="all, delete-orphan"
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


class EventApprovalLog(TimestampMixin, Base):
    __tablename__ = "event_approval_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    previous_status: Mapped[Optional[str]] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    actor: Mapped[Optional[str]] = mapped_column(String(120))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    event: Mapped[Event] = relationship("Event", back_populates="approval_logs")


class EventNotification(TimestampMixin, Base):
    __tablename__ = "event_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False, default="email")

    event: Mapped[Event] = relationship("Event", back_populates="notifications")


class EventTemplateTranslation(TimestampMixin, Base):
    __tablename__ = "event_template_translations"
    __table_args__ = (
        UniqueConstraint(
            "template_id",
            "locale",
            name="uq_event_template_translation_locale",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("event_templates.id", ondelete="CASCADE"), nullable=False
    )
    locale: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    template: Mapped[EventTemplate] = relationship(
        "EventTemplate", back_populates="translations"
    )


class Registration(TimestampMixin, Base):
    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "attendee_email", name="uq_registration_event_email"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    attendee_email: Mapped[str] = mapped_column(String(255), nullable=False)
    attendee_name: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        Enum(
            "confirmed",
            "checked_in",
            "cancelled",
            "no_show",
            name="registration_status",
        ),
        nullable=False,
        default="confirmed",
    )
    check_in_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    qr_code_data: Mapped[Optional[str]] = mapped_column(Text)
    metadata: Mapped[Optional[str]] = mapped_column(Text)

    event: Mapped[Event] = relationship("Event", back_populates="registrations")
    attendance_record: Mapped[Optional["AttendanceRecord"]] = relationship(
        "AttendanceRecord",
        back_populates="registration",
        cascade="all, delete-orphan",
        uselist=False,
    )


class WaitlistEntry(TimestampMixin, Base):
    __tablename__ = "waitlist_entries"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "attendee_email", name="uq_waitlist_event_email"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    attendee_email: Mapped[str] = mapped_column(String(255), nullable=False)
    attendee_name: Mapped[Optional[str]] = mapped_column(String(255))
    notified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    event: Mapped[Event] = relationship("Event", back_populates="waitlist_entries")


class AttendanceRecord(TimestampMixin, Base):
    __tablename__ = "attendance_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_id: Mapped[int] = mapped_column(
        ForeignKey("registrations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    check_in_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    check_in_method: Mapped[Optional[str]] = mapped_column(String(50))
    scan_payload: Mapped[Optional[str]] = mapped_column(Text)

    registration: Mapped[Registration] = relationship(
        "Registration", back_populates="attendance_record"
    )


class NoShowPenalty(TimestampMixin, Base):
    __tablename__ = "no_show_penalties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attendee_email: Mapped[str] = mapped_column(String(255), nullable=False)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[Optional[str]] = mapped_column(Text)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    event: Mapped[Event] = relationship("Event", back_populates="penalties")


__all__ = [
    "Event",
    "EventApproval",
    "EventApprovalLog",
    "EventCategory",
    "EventNotification",
    "EventSeries",
    "EventTag",
    "EventTemplate",
    "EventTemplateTranslation",
    "EventTranslation",
    "Registration",
    "WaitlistEntry",
    "AttendanceRecord",
    "NoShowPenalty",
]
