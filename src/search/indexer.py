"""Elasticsearch indexing helpers for event documents.

This module centralises the transformation of the rich event payloads
returned by :class:`src.services.events.EventService` into documents ready to
be indexed in Elasticsearch.  It focuses on exposing geo capabilities,
taxonomies (categories, tags) and localisation (translations/languages).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional

__all__ = ["EventIndexer", "EventDocument"]


@dataclass
class EventDocument:
    """Representation of an event ready for Elasticsearch indexing."""

    id: int
    title: str
    description: Optional[str]
    event_date: Optional[str]
    timezone: Optional[str]
    location: Optional[str]
    coordinates: Optional[Dict[str, float]]
    categories: List[str] = field(default_factory=list)
    category_ids: List[int] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    tag_ids: List[int] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    default_locale: Optional[str] = None
    fallback_locale: Optional[str] = None
    status: Optional[str] = None
    attendees: Optional[int] = None
    series: Optional[str] = None
    share_url: Optional[str] = None

    def asdict(self) -> Dict[str, Any]:
        payload = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "event_date": self.event_date,
            "timezone": self.timezone,
            "location": self.location,
            "coordinates": self.coordinates,
            "categories": self.categories,
            "category_ids": self.category_ids,
            "tags": self.tags,
            "tag_ids": self.tag_ids,
            "languages": self.languages,
            "default_locale": self.default_locale,
            "fallback_locale": self.fallback_locale,
            "status": self.status,
            "attendees": self.attendees,
            "series": self.series,
            "share_url": self.share_url,
            "indexed_at": datetime.utcnow().isoformat(),
        }
        return {key: value for key, value in payload.items() if value is not None}


class EventIndexer:
    """Helper wrapping Elasticsearch indexing operations for events."""

    def __init__(self, client: Any, index_name: str = "events") -> None:
        self.client = client
        self.index_name = index_name

    def build_document(self, event: Mapping[str, Any]) -> EventDocument:
        """Convert an event payload into an :class:`EventDocument`."""

        coordinates = self._extract_coordinates(event)
        categories, category_ids = self._extract_taxonomy(event.get("categories"))
        tags, tag_ids = self._extract_taxonomy(event.get("tags"))
        languages = self._extract_languages(event)
        series_name = None
        series = event.get("series")
        if isinstance(series, Mapping):
            series_name = series.get("name")

        share_url = None
        share = event.get("share") if isinstance(event.get("share"), Mapping) else None
        if share:
            share_url = share.get("url")

        return EventDocument(
            id=int(event.get("id")),
            title=str(event.get("title", "")),
            description=event.get("description"),
            event_date=event.get("date") or event.get("event_date"),
            timezone=event.get("timezone"),
            location=event.get("location"),
            coordinates=coordinates,
            categories=categories,
            category_ids=category_ids,
            tags=tags,
            tag_ids=tag_ids,
            languages=languages,
            default_locale=event.get("default_locale"),
            fallback_locale=event.get("fallback_locale"),
            status=event.get("status"),
            attendees=event.get("attendees"),
            series=series_name,
            share_url=share_url,
        )

    def index_event(self, event: Mapping[str, Any], *, refresh: bool = False) -> Dict[str, Any]:
        document = self.build_document(event)
        kwargs = {"index": self.index_name, "id": document.id, "document": document.asdict()}
        if refresh:
            kwargs["refresh"] = "wait_for" if refresh is True else refresh
        return self.client.index(**kwargs)

    def bulk_index_events(
        self, events: Iterable[Mapping[str, Any]], *, refresh: bool = False
    ) -> Dict[str, Any]:
        operations: List[Dict[str, Any]] = []
        for event in events:
            document = self.build_document(event)
            operations.append({"index": {"_index": self.index_name, "_id": document.id}})
            operations.append(document.asdict())
        kwargs: Dict[str, Any] = {"operations": operations}
        if refresh:
            kwargs["refresh"] = "wait_for" if refresh is True else refresh
        return self.client.bulk(**kwargs)

    def delete_event(self, event_id: int, *, refresh: bool = False) -> Dict[str, Any]:
        kwargs = {"index": self.index_name, "id": int(event_id)}
        if refresh:
            kwargs["refresh"] = "wait_for" if refresh is True else refresh
        return self.client.delete(**kwargs)

    @staticmethod
    def _extract_coordinates(event: Mapping[str, Any]) -> Optional[Dict[str, float]]:
        settings = event.get("settings")
        lat = event.get("latitude")
        lon = event.get("longitude")

        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            if isinstance(settings, Mapping):
                coordinates = settings.get("coordinates") or settings.get("geo")
                if isinstance(coordinates, Mapping):
                    lat = coordinates.get("lat")
                    lon = coordinates.get("lon")
                else:
                    location = settings.get("location")
                    if isinstance(location, Mapping):
                        lat = location.get("lat")
                        lon = location.get("lon")

        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return {"lat": float(lat), "lon": float(lon)}
        return None

    @staticmethod
    def _extract_taxonomy(items: Any) -> tuple[list[str], list[int]]:
        names: List[str] = []
        identifiers: List[int] = []
        if isinstance(items, Iterable):
            for item in items:
                if isinstance(item, Mapping):
                    name = item.get("name")
                    if isinstance(name, str):
                        names.append(name)
                    identifier = item.get("id")
                    if isinstance(identifier, int):
                        identifiers.append(identifier)
        return names, identifiers

    @staticmethod
    def _extract_languages(event: Mapping[str, Any]) -> List[str]:
        languages: List[str] = []
        default_locale = event.get("default_locale")
        if isinstance(default_locale, str):
            languages.append(default_locale)
        translations = event.get("translations")
        if isinstance(translations, Iterable):
            for translation in translations:
                if isinstance(translation, Mapping):
                    locale = translation.get("locale")
                    if isinstance(locale, str) and locale not in languages:
                        languages.append(locale)
        fallback = event.get("fallback_locale")
        if isinstance(fallback, str) and fallback not in languages:
            languages.append(fallback)
        return languages
