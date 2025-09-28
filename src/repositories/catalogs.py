"""Repository helpers for taxonomies and templates."""
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session, joinedload

from src.models import (
    EventCategory,
    EventSeries,
    EventTag,
    EventTemplate,
    EventTemplateTranslation,
)

__all__ = [
    "CategoryRepository",
    "TagRepository",
    "SeriesRepository",
    "TemplateRepository",
]


class BaseRepository:
    """Base repository storing the SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self.session = session


class CategoryRepository(BaseRepository):
    """Repository for :class:`EventCategory`."""

    def list(self) -> Sequence[EventCategory]:
        query = select(EventCategory).order_by(EventCategory.name.asc())
        return self.session.scalars(query).all()

    def get(self, category_id: int) -> EventCategory:
        category = self.session.get(EventCategory, category_id)
        if category is None:
            raise LookupError(f"Category {category_id} not found")
        return category

    def create(self, *, name: str, description: Optional[str]) -> EventCategory:
        category = EventCategory(name=name, description=description)
        self.session.add(category)
        self.session.flush()
        self.session.refresh(category)
        return category

    def delete(self, category: EventCategory) -> None:
        self.session.delete(category)

    def update(self, category: EventCategory, *, name: Optional[str], description: Optional[str]) -> EventCategory:
        if name is not None:
            category.name = name
        if description is not None:
            category.description = description
        self.session.flush()
        self.session.refresh(category)
        return category


class TagRepository(BaseRepository):
    """Repository for :class:`EventTag`."""

    def list(self) -> Sequence[EventTag]:
        query = select(EventTag).order_by(EventTag.name.asc())
        return self.session.scalars(query).all()

    def get(self, tag_id: int) -> EventTag:
        tag = self.session.get(EventTag, tag_id)
        if tag is None:
            raise LookupError(f"Tag {tag_id} not found")
        return tag

    def create(self, *, name: str) -> EventTag:
        tag = EventTag(name=name)
        self.session.add(tag)
        self.session.flush()
        self.session.refresh(tag)
        return tag

    def delete(self, tag: EventTag) -> None:
        self.session.delete(tag)

    def update(self, tag: EventTag, *, name: Optional[str]) -> EventTag:
        if name is not None:
            tag.name = name
        self.session.flush()
        self.session.refresh(tag)
        return tag


class SeriesRepository(BaseRepository):
    """Repository for :class:`EventSeries`."""

    def list(self) -> Sequence[EventSeries]:
        query = select(EventSeries).order_by(EventSeries.name.asc())
        return self.session.scalars(query).all()

    def get(self, series_id: int) -> EventSeries:
        series = self.session.get(EventSeries, series_id)
        if series is None:
            raise LookupError(f"Series {series_id} not found")
        return series

    def get_by_name(self, name: str) -> Optional[EventSeries]:
        query = select(EventSeries).where(func.lower(EventSeries.name) == name.casefold())
        return self.session.scalars(query).first()

    def create(self, *, name: str, description: Optional[str]) -> EventSeries:
        series = EventSeries(name=name, description=description)
        self.session.add(series)
        self.session.flush()
        self.session.refresh(series)
        return series

    def update(self, series: EventSeries, *, name: Optional[str], description: Optional[str]) -> EventSeries:
        if name is not None:
            series.name = name
        if description is not None:
            series.description = description
        self.session.flush()
        self.session.refresh(series)
        return series

    def delete(self, series: EventSeries) -> None:
        self.session.delete(series)


class TemplateRepository(BaseRepository):
    """Repository for :class:`EventTemplate`."""

    def list(self) -> Sequence[EventTemplate]:
        query = (
            select(EventTemplate)
            .options(joinedload(EventTemplate.translations))
            .order_by(EventTemplate.name.asc())
        )
        return self.session.scalars(query).all()

    def get(self, template_id: int) -> EventTemplate:
        query = (
            select(EventTemplate)
            .options(joinedload(EventTemplate.translations))
            .where(EventTemplate.id == template_id)
        )
        try:
            return self.session.execute(query).scalar_one()
        except NoResultFound as exc:
            raise LookupError(f"Template {template_id} not found") from exc

    def get_by_name(self, name: str) -> Optional<EventTemplate]:
        query = select(EventTemplate).where(EventTemplate.name == name)
        return self.session.scalars(query).first()

    def create(
        self,
        *,
        name: str,
        description: Optional[str],
        default_duration_minutes: Optional[int],
        default_timezone: str,
        default_locale: str,
        fallback_locale: Optional[str],
        default_capacity_limit: Optional[int],
        default_metadata: Optional[dict],
    ) -> EventTemplate:
        template = EventTemplate(
            name=name,
            description=description,
            default_duration_minutes=default_duration_minutes,
            default_timezone=default_timezone,
            default_locale=default_locale,
            fallback_locale=fallback_locale,
            default_capacity_limit=default_capacity_limit,
            default_metadata=default_metadata,
        )
        self.session.add(template)
        self.session.flush()
        self.session.refresh(template)
        return template

    def update(
        self,
        template: EventTemplate,
        *,
        description: Optional[str],
        default_duration_minutes: Optional[int],
        default_timezone: Optional[str],
        default_locale: Optional[str],
        fallback_locale: Optional[str],
        default_capacity_limit: Optional[int],
        default_metadata: Optional[dict],
    ) -> EventTemplate:
        if description is not None:
            template.description = description
        if default_duration_minutes is not None:
            template.default_duration_minutes = default_duration_minutes
        if default_timezone is not None:
            template.default_timezone = default_timezone
        if default_locale is not None:
            template.default_locale = default_locale
        if fallback_locale is not None or fallback_locale == "":
            template.fallback_locale = fallback_locale or None
        if default_capacity_limit is not None or default_capacity_limit == 0:
            template.default_capacity_limit = default_capacity_limit
        if default_metadata is not None:
            template.default_metadata = default_metadata
        self.session.flush()
        self.session.refresh(template)
        return template

    def delete(self, template: EventTemplate) -> None:
        self.session.delete(template)

    def upsert_translation(
        self,
        template: EventTemplate,
        *,
        locale: str,
        title: str,
        description: Optional[str],
    ) -> EventTemplateTranslation:
        translation = next(
            (t for t in template.translations if t.locale == locale),
            None,
        )
        if translation is None:
            translation = EventTemplateTranslation(
                template=template,
                locale=locale,
                title=title,
                description=description,
            )
            self.session.add(translation)
        else:
            translation.title = title
            translation.description = description
        self.session.flush()
        self.session.refresh(translation)
        return translation

    def remove_translation(self, template: EventTemplate, locale: str) -> None:
        translation = next((t for t in template.translations if t.locale == locale), None)
        if translation is None:
            raise LookupError(f"Translation {locale} not found for template {template.id}")
        self.session.delete(translation)

