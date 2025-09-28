"""Utilities for accessing services within Flask request context."""
from __future__ import annotations

from typing import Any, Callable, Dict, Type, TypeVar

from flask import g

from src.database import get_session
from src.services.events import (
    CategoryService,
    EventService,
    SeriesService,
    TagService,
    TemplateService,
)

T = TypeVar("T")

SERVICE_FACTORIES: Dict[str, Callable[[Any], Any]] = {
    "event_service": EventService,
    "category_service": CategoryService,
    "tag_service": TagService,
    "series_service": SeriesService,
    "template_service": TemplateService,
}


def get_db_session():
    if "db_session" not in g:
        g.db_session = get_session()
    return g.db_session


def get_event_service() -> EventService:
    return _get_service("event_service", EventService)


def get_category_service() -> CategoryService:
    return _get_service("category_service", CategoryService)


def get_tag_service() -> TagService:
    return _get_service("tag_service", TagService)


def get_series_service() -> SeriesService:
    return _get_service("series_service", SeriesService)


def get_template_service() -> TemplateService:
    return _get_service("template_service", TemplateService)


def _get_service(key: str, factory: Type[T]) -> T:
    if key not in g:
        session = get_db_session()
        g[key] = factory(session)
    return g[key]


def cleanup_services(exception):
    session = g.pop("db_session", None)
    for key in list(SERVICE_FACTORIES.keys()):
        g.pop(key, None)
    if session is not None:
        try:
            if exception is not None:
                session.rollback()
        finally:
            session.close()
