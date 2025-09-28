"""Utilities for accessing services within Flask request context."""
from __future__ import annotations

from typing import Any, Callable, Dict, Type, TypeVar

from flask import current_app, g

from src.database import get_session
from src.services.events import (
    CategoryService,
    EventService,
    SeriesService,
    TagService,
    TemplateService,
)
from src.services.recommendations import RecommendationService
from src.services.search import EventSearchService

T = TypeVar("T")

SERVICE_FACTORIES: Dict[str, Callable[[Any], Any]] = {
    "event_service": EventService,
    "category_service": CategoryService,
    "tag_service": TagService,
    "series_service": SeriesService,
    "template_service": TemplateService,
}

EXTRA_SERVICE_KEYS = {"search_service", "recommendation_service"}


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


def get_search_service() -> EventSearchService:
    if "search_service" not in g:
        client = _get_search_client()
        index_name = current_app.config.get("EVENTS_INDEX", "events")
        event_service = get_event_service()
        event_provider = lambda: event_service.list_events()
        g["search_service"] = EventSearchService(
            client,
            index_name=index_name,
            event_provider=event_provider,
        )
    return g["search_service"]


def get_recommendation_service() -> RecommendationService:
    if "recommendation_service" not in g:
        event_service = get_event_service()
        search_service = get_search_service()
        user_client = _get_user_profile_client()
        g["recommendation_service"] = RecommendationService(
            event_service,
            user_client,
            search_service=search_service,
        )
    return g["recommendation_service"]


def _get_service(key: str, factory: Type[T]) -> T:
    if key not in g:
        session = get_db_session()
        g[key] = factory(session)
    return g[key]


def cleanup_services(exception):
    session = g.pop("db_session", None)
    for key in list(SERVICE_FACTORIES.keys()):
        g.pop(key, None)
    for key in EXTRA_SERVICE_KEYS:
        g.pop(key, None)
    if session is not None:
        try:
            if exception is not None:
                session.rollback()
        finally:
            session.close()


def _get_search_client():
    factory = current_app.config.get("SEARCH_CLIENT_FACTORY")
    if callable(factory):
        return factory()
    return current_app.config.get("SEARCH_CLIENT")


def _get_user_profile_client():
    client = current_app.config.get("USER_PROFILE_CLIENT")
    if callable(client):
        client = client()
    if client is None:
        client = _FallbackUserClient()
    return client


class _FallbackUserClient:
    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        return {
            "user_id": user_id,
            "preferred_categories": [],
            "preferred_tags": [],
            "preferred_languages": [],
            "bookmarked_events": [],
        }
