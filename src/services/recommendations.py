"""Recommendation service combining user preferences with event metadata."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol

from .events import EventService
from .search import EventSearchService

__all__ = ["UserProfileClient", "RecommendationService", "UserProfile"]


class UserProfileClient(Protocol):
    """Protocol describing the minimal user profile client interface."""

    def get_user_profile(self, user_id: str) -> Mapping[str, Any]:
        ...


@dataclass
class UserProfile:
    """Structured representation of a user profile used for recommendations."""

    user_id: str
    preferred_categories: List[str]
    preferred_tags: List[str]
    preferred_languages: List[str]
    location: Optional[Dict[str, float]]
    radius_km: Optional[float]
    bookmarked_events: List[int]

    @classmethod
    def from_payload(cls, user_id: str, payload: Mapping[str, Any]) -> "UserProfile":
        def _ensure_list(values: Any) -> List[str]:
            if not values:
                return []
            if isinstance(values, str):
                return [values]
            if isinstance(values, Iterable):
                return [str(value) for value in values if str(value).strip()]
            return []

        def _ensure_float(mapping: Mapping[str, Any], key: str) -> Optional[float]:
            value = mapping.get(key)
            if isinstance(value, (int, float)):
                return float(value)
            return None

        location_payload = payload.get("location")
        location = None
        if isinstance(location_payload, Mapping):
            lat = _ensure_float(location_payload, "lat")
            lon = _ensure_float(location_payload, "lon")
            if lat is not None and lon is not None:
                location = {"lat": lat, "lon": lon}

        radius = payload.get("radius_km")
        if isinstance(radius, (int, float)):
            radius_km = float(radius)
        else:
            radius_km = None

        bookmarks: List[int] = []
        if isinstance(payload.get("bookmarked_events"), Iterable):
            for value in payload["bookmarked_events"]:
                try:
                    bookmarks.append(int(value))
                except (TypeError, ValueError):
                    continue

        return cls(
            user_id=user_id,
            preferred_categories=_ensure_list(payload.get("preferred_categories")),
            preferred_tags=_ensure_list(payload.get("preferred_tags")),
            preferred_languages=_ensure_list(payload.get("preferred_languages")),
            location=location,
            radius_km=radius_km,
            bookmarked_events=bookmarks,
        )


class RecommendationService:
    """Provide personalised event recommendations for users."""

    def __init__(
        self,
        event_service: EventService,
        user_client: UserProfileClient,
        *,
        search_service: Optional[EventSearchService] = None,
    ) -> None:
        self.event_service = event_service
        self.user_client = user_client
        self.search_service = search_service

    def get_recommendations(self, user_id: str, *, limit: int = 10) -> List[Dict[str, Any]]:
        profile_payload = self.user_client.get_user_profile(user_id)
        profile = UserProfile.from_payload(user_id, profile_payload)

        # Start from the full list of events.
        events = self.event_service.list_events()

        # Optionally refine using the search service (leveraging geo filters).
        if self.search_service and (profile.preferred_categories or profile.preferred_tags):
            try:
                search_results = self.search_service.search_events(
                    categories=profile.preferred_categories,
                    tags=profile.preferred_tags,
                    languages=profile.preferred_languages,
                    lat=profile.location["lat"] if profile.location else None,
                    lon=profile.location["lon"] if profile.location else None,
                    radius_km=profile.radius_km,
                    size=limit * 3,
                    include_suggestions=False,
                )
                if search_results.get("results"):
                    events = search_results["results"]
            except Exception:
                # Fallback silently to local heuristics if the search backend fails.
                pass

        ranked = self._rank_events(events, profile)
        filtered = [event for event in ranked if event["id"] not in profile.bookmarked_events]
        return filtered[:limit]

    # ------------------------------------------------------------------
    # Ranking helpers
    # ------------------------------------------------------------------
    def _rank_events(self, events: Iterable[Mapping[str, Any]], profile: UserProfile) -> List[Dict[str, Any]]:
        scored: List[tuple[float, Dict[str, Any]]] = []
        for event in events:
            if not isinstance(event, Mapping):
                continue
            event_id = event.get("id")
            if event_id is None:
                continue
            score = 0.0
            score += self._score_taxonomy(event.get("categories"), profile.preferred_categories, weight=3.0)
            score += self._score_taxonomy(event.get("tags"), profile.preferred_tags, weight=2.0)
            score += self._score_languages(event, profile.preferred_languages)
            score += self._score_geo(event, profile)
            if event.get("status") == "approved":
                score += 0.5
            bookmark_count = 0
            if isinstance(event.get("settings"), Mapping):
                bookmarks = event["settings"].get("bookmarks")
                if isinstance(bookmarks, list):
                    bookmark_count = len(bookmarks)
            score += min(bookmark_count, 10) * 0.05
            scored.append((score, dict(event)))
        scored.sort(key=lambda item: (-item[0], item[1].get("date") or item[1].get("event_date") or ""))
        return [item[1] for item in scored]

    @staticmethod
    def _score_taxonomy(items: Any, preferences: Iterable[str], *, weight: float) -> float:
        if not items or not preferences:
            return 0.0
        available: List[str] = []
        if isinstance(items, Iterable):
            for item in items:
                if isinstance(item, Mapping):
                    name = item.get("name")
                else:
                    name = item
                if isinstance(name, str):
                    available.append(name.casefold())
        preference_norm = [pref.casefold() for pref in preferences if isinstance(pref, str)]
        matches = len([pref for pref in preference_norm if pref in available])
        return matches * weight

    @staticmethod
    def _score_languages(event: Mapping[str, Any], preferences: Iterable[str]) -> float:
        if not preferences:
            return 0.0
        locales: List[str] = []
        default_locale = event.get("default_locale")
        if isinstance(default_locale, str):
            locales.append(default_locale.casefold())
        translations = event.get("translations")
        if isinstance(translations, Iterable):
            for translation in translations:
                if isinstance(translation, Mapping):
                    locale = translation.get("locale")
                    if isinstance(locale, str):
                        locales.append(locale.casefold())
        score = 0.0
        for preference in preferences:
            if isinstance(preference, str) and preference.casefold() in locales:
                score += 1.0
        return score

    @staticmethod
    def _score_geo(event: Mapping[str, Any], profile: UserProfile) -> float:
        if not profile.location or not profile.radius_km:
            return 0.0
        coordinates = RecommendationService._extract_coordinates(event)
        if not coordinates:
            return 0.0
        distance = RecommendationService._haversine_distance(
            profile.location["lat"],
            profile.location["lon"],
            coordinates["lat"],
            coordinates["lon"],
        )
        if distance > profile.radius_km:
            return 0.0
        return max(0.0, (profile.radius_km - distance) / profile.radius_km)

    @staticmethod
    def _extract_coordinates(event: Mapping[str, Any]) -> Optional[Dict[str, float]]:
        settings = event.get("settings") if isinstance(event.get("settings"), Mapping) else None
        if settings:
            for key in ("coordinates", "geo", "location"):
                candidate = settings.get(key)
                if isinstance(candidate, Mapping):
                    lat = candidate.get("lat")
                    lon = candidate.get("lon") or candidate.get("lng")
                    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                        return {"lat": float(lat), "lon": float(lon)}
        lat = event.get("latitude")
        lon = event.get("longitude")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return {"lat": float(lat), "lon": float(lon)}
        return None

    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        from math import atan2, cos, radians, sin, sqrt

        radius = 6371.0
        phi1, phi2 = radians(lat1), radians(lat2)
        d_phi = radians(lat2 - lat1)
        d_lambda = radians(lon2 - lon1)
        a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return radius * c
