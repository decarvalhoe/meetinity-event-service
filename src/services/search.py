"""Search service wrapping Elasticsearch queries with graceful fallbacks."""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

__all__ = ["EventSearchService", "SearchError"]


class SearchError(RuntimeError):
    """Raised when the search backend cannot satisfy a request."""


class EventSearchService:
    """High level helper orchestrating search queries for events."""

    def __init__(
        self,
        client: Any,
        *,
        index_name: str = "events",
        event_provider: Optional[Callable[[], Iterable[Dict[str, Any]]]] = None,
    ) -> None:
        self.client = client
        self.index_name = index_name
        self.event_provider = event_provider or (lambda: [])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def search_events(
        self,
        *,
        text: Optional[str] = None,
        categories: Optional[Iterable[str]] = None,
        tags: Optional[Iterable[str]] = None,
        languages: Optional[Iterable[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        radius_km: Optional[float] = None,
        page: int = 1,
        size: int = 20,
        sort: Optional[str] = None,
        include_suggestions: bool = True,
    ) -> Dict[str, Any]:
        """Execute a search query.

        When an Elasticsearch client is configured, the query is delegated to it.
        Otherwise a best-effort in-memory filtering strategy is applied on the
        dataset returned by ``event_provider``.
        """

        page = max(1, page)
        size = max(1, min(size, 100))
        categories_list = self._normalise_iterable(categories)
        tags_list = self._normalise_iterable(tags)
        languages_list = self._normalise_iterable(languages)

        if self.client and hasattr(self.client, "search"):
            body = self._build_elasticsearch_query(
                text=text,
                categories=categories_list,
                tags=tags_list,
                languages=languages_list,
                start_date=start_date,
                end_date=end_date,
                lat=lat,
                lon=lon,
                radius_km=radius_km,
                from_=(page - 1) * size,
                size=size,
                sort=sort,
                include_suggestions=include_suggestions,
            )
            response = self.client.search(index=self.index_name, **body)
            return self._format_es_response(response, page=page, size=size)

        # Fallback search strategy when no ES client is available.
        events = list(self.event_provider())
        results = self._filter_events(
            events,
            text=text,
            categories=categories_list,
            tags=tags_list,
            languages=languages_list,
            start_date=start_date,
            end_date=end_date,
            lat=lat,
            lon=lon,
            radius_km=radius_km,
        )
        sorted_results = self._sort_results(results, sort)
        total = len(sorted_results)
        start = (page - 1) * size
        end = start + size
        return {
            "results": sorted_results[start:end],
            "total": total,
            "page": page,
            "size": size,
            "suggestions": self._build_suggestions(text, sorted_results)
            if include_suggestions
            else [],
        }

    # ------------------------------------------------------------------
    # Elasticsearch helpers
    # ------------------------------------------------------------------
    def _build_elasticsearch_query(
        self,
        *,
        text: Optional[str],
        categories: List[str],
        tags: List[str],
        languages: List[str],
        start_date: Optional[str],
        end_date: Optional[str],
        lat: Optional[float],
        lon: Optional[float],
        radius_km: Optional[float],
        from_: int,
        size: int,
        sort: Optional[str],
        include_suggestions: bool,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {"bool": {"must": [], "filter": []}}

        if text:
            query["bool"]["must"].append(
                {
                    "multi_match": {
                        "query": text,
                        "fields": ["title^3", "description", "tags", "categories"],
                    }
                }
            )
        if categories:
            query["bool"]["filter"].append({"terms": {"categories.keyword": categories}})
        if tags:
            query["bool"]["filter"].append({"terms": {"tags.keyword": tags}})
        if languages:
            query["bool"]["filter"].append({"terms": {"languages": languages}})
        if start_date or end_date:
            range_filter: Dict[str, Any] = {}
            if start_date:
                range_filter["gte"] = start_date
            if end_date:
                range_filter["lte"] = end_date
            query["bool"]["filter"].append({"range": {"event_date": range_filter}})
        if lat is not None and lon is not None and radius_km:
            query["bool"]["filter"].append(
                {
                    "geo_distance": {
                        "distance": f"{radius_km}km",
                        "coordinates": {"lat": lat, "lon": lon},
                    }
                }
            )

        if not query["bool"]["must"] and not query["bool"]["filter"]:
            final_query: Dict[str, Any] = {"match_all": {}}
        else:
            final_query = query

        body: Dict[str, Any] = {"query": final_query, "from": from_, "size": size}

        if sort:
            body["sort"] = [self._translate_sort(sort)]
        if include_suggestions and text:
            body["suggest"] = {
                "event-suggest": {
                    "text": text,
                    "term": {"field": "title"},
                }
            }
        return body

    def _format_es_response(self, response: Mapping[str, Any], *, page: int, size: int) -> Dict[str, Any]:
        hits = response.get("hits", {}) if isinstance(response, Mapping) else {}
        total_value = hits.get("total", {}).get("value") if isinstance(hits, Mapping) else None
        results = []
        hit_items = hits.get("hits") if isinstance(hits, Mapping) else []
        if isinstance(hit_items, Iterable):
            for item in hit_items:
                if isinstance(item, Mapping):
                    source = item.get("_source")
                    if isinstance(source, Mapping):
                        results.append(dict(source))
        suggestions: List[str] = []
        suggest = response.get("suggest") if isinstance(response, Mapping) else None
        if isinstance(suggest, Mapping):
            for value in suggest.values():
                if isinstance(value, Iterable):
                    for entry in value:
                        options = entry.get("options") if isinstance(entry, Mapping) else None
                        if isinstance(options, Iterable):
                            for option in options:
                                text = option.get("text") if isinstance(option, Mapping) else None
                                if isinstance(text, str) and text not in suggestions:
                                    suggestions.append(text)
        return {
            "results": results,
            "total": total_value if isinstance(total_value, int) else len(results),
            "page": page,
            "size": size,
            "suggestions": suggestions,
        }

    @staticmethod
    def _translate_sort(sort: str) -> Dict[str, Any]:
        field = sort
        order = "asc"
        if sort.startswith("-"):
            field = sort[1:]
            order = "desc"
        mapping = {
            "date": "event_date",
            "attendees": "attendees",
        }
        es_field = mapping.get(field, field)
        return {es_field: {"order": order}}

    # ------------------------------------------------------------------
    # Fallback search helpers
    # ------------------------------------------------------------------
    def _filter_events(
        self,
        events: List[Dict[str, Any]],
        *,
        text: Optional[str],
        categories: List[str],
        tags: List[str],
        languages: List[str],
        start_date: Optional[str],
        end_date: Optional[str],
        lat: Optional[float],
        lon: Optional[float],
        radius_km: Optional[float],
    ) -> List[Dict[str, Any]]:
        filtered: List[Dict[str, Any]] = []
        for event in events:
            if not isinstance(event, Mapping):
                continue
            if text and not self._matches_text(event, text):
                continue
            if categories and not self._matches_taxonomy(event.get("categories"), categories):
                continue
            if tags and not self._matches_taxonomy(event.get("tags"), tags):
                continue
            if languages and not self._matches_languages(event, languages):
                continue
            if not self._matches_date_range(event, start_date, end_date):
                continue
            if radius_km and not self._matches_geo(event, lat, lon, radius_km):
                continue
            filtered.append(dict(event))
        return filtered

    def _sort_results(self, results: List[Dict[str, Any]], sort: Optional[str]) -> List[Dict[str, Any]]:
        if not sort:
            return sorted(results, key=lambda event: event.get("date") or "")
        reverse = sort.startswith("-")
        key = sort[1:] if reverse else sort

        def sort_key(event: Mapping[str, Any]) -> Any:
            if key == "date":
                return event.get("date") or event.get("event_date") or ""
            if key == "attendees":
                return event.get("attendees", 0)
            return event.get(key)

        return sorted(results, key=sort_key, reverse=reverse)

    @staticmethod
    def _build_suggestions(text: Optional[str], results: List[Dict[str, Any]]) -> List[str]:
        if not text:
            return []
        suggestions: List[str] = []
        lowered = text.casefold()
        for event in results:
            title = event.get("title")
            if isinstance(title, str) and lowered in title.casefold():
                if title not in suggestions:
                    suggestions.append(title)
        return suggestions[:5]

    # ------------------------------------------------------------------
    # Matching helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalise_iterable(values: Optional[Iterable[str]]) -> List[str]:
        if not values:
            return []
        return [str(value).strip() for value in values if str(value).strip()]

    @staticmethod
    def _matches_text(event: Mapping[str, Any], text: str) -> bool:
        lowered = text.casefold()
        for field in ("title", "description", "location", "type"):
            value = event.get(field)
            if isinstance(value, str) and lowered in value.casefold():
                return True
        tags = event.get("tags")
        if isinstance(tags, Iterable):
            for tag in tags:
                if isinstance(tag, Mapping):
                    name = tag.get("name")
                else:
                    name = tag
                if isinstance(name, str) and lowered in name.casefold():
                    return True
        categories = event.get("categories")
        if isinstance(categories, Iterable):
            for category in categories:
                if isinstance(category, Mapping):
                    name = category.get("name")
                else:
                    name = category
                if isinstance(name, str) and lowered in name.casefold():
                    return True
        return False

    @staticmethod
    def _matches_taxonomy(items: Any, expected: List[str]) -> bool:
        if not items:
            return False
        available: List[str] = []
        if isinstance(items, Iterable):
            for item in items:
                if isinstance(item, Mapping):
                    name = item.get("name")
                else:
                    name = item
                if isinstance(name, str):
                    available.append(name.casefold())
        expected_norm = [value.casefold() for value in expected]
        return any(value in available for value in expected_norm)

    @staticmethod
    def _matches_languages(event: Mapping[str, Any], expected: List[str]) -> bool:
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
        fallback = event.get("fallback_locale")
        if isinstance(fallback, str):
            locales.append(fallback.casefold())
        expected_norm = [value.casefold() for value in expected]
        return any(value in locales for value in expected_norm)

    @staticmethod
    def _matches_date_range(
        event: Mapping[str, Any], start_date: Optional[str], end_date: Optional[str]
    ) -> bool:
        event_date = event.get("date") or event.get("event_date")
        if not (start_date or end_date) or not isinstance(event_date, str):
            return True
        if start_date and event_date < start_date:
            return False
        if end_date and event_date > end_date:
            return False
        return True

    def _matches_geo(
        self,
        event: Mapping[str, Any],
        lat: Optional[float],
        lon: Optional[float],
        radius_km: float,
    ) -> bool:
        if lat is None or lon is None:
            return True
        coordinates = self._extract_coordinates(event)
        if not coordinates:
            return False
        distance = self._haversine_distance(lat, lon, coordinates["lat"], coordinates["lon"])
        return distance <= radius_km

    @staticmethod
    def _extract_coordinates(event: Mapping[str, Any]) -> Optional[Dict[str, float]]:
        settings = event.get("settings") if isinstance(event.get("settings"), Mapping) else None
        candidates: List[Mapping[str, Any]] = []
        if settings:
            for key in ("coordinates", "geo"):
                value = settings.get(key)
                if isinstance(value, Mapping):
                    candidates.append(value)
            location = settings.get("location")
            if isinstance(location, Mapping):
                candidates.append(location)
        lat = event.get("latitude")
        lon = event.get("longitude")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return {"lat": float(lat), "lon": float(lon)}
        for candidate in candidates:
            c_lat = candidate.get("lat")
            c_lon = candidate.get("lon") or candidate.get("lng")
            if isinstance(c_lat, (int, float)) and isinstance(c_lon, (int, float)):
                return {"lat": float(c_lat), "lon": float(c_lon)}
        return None

    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)
        a = (
            math.sin(d_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius * c
