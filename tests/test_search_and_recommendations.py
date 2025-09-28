from __future__ import annotations

from typing import Any, Dict, List

from src.database import get_session
from src.search.indexer import EventIndexer
from src.services.events import EventService
from src.services.search import EventSearchService


class StubElasticsearchClient:
    def __init__(self) -> None:
        self.index_calls: List[Dict[str, Any]] = []
        self.bulk_calls: List[Dict[str, Any]] = []
        self.delete_calls: List[Dict[str, Any]] = []

    def index(self, **kwargs):
        self.index_calls.append(kwargs)
        return {"result": "created"}

    def bulk(self, **kwargs):
        self.bulk_calls.append(kwargs)
        return {"errors": False}

    def delete(self, **kwargs):
        self.delete_calls.append(kwargs)
        return {"result": "deleted"}


def test_event_indexer_builds_document():
    client = StubElasticsearchClient()
    indexer = EventIndexer(client, index_name="events-test")
    event = {
        "id": 99,
        "title": "Global Tech Summit",
        "description": "Conférence internationale",
        "date": "2025-10-10",
        "timezone": "Europe/Paris",
        "location": "Paris",
        "default_locale": "fr-FR",
        "fallback_locale": "en-US",
        "categories": [{"id": 1, "name": "Tech"}],
        "tags": [{"id": 1, "name": "innovation"}],
        "translations": [
            {"locale": "fr-FR", "title": "Sommet Tech"},
            {"locale": "en-US", "title": "Tech Summit"},
        ],
        "settings": {"coordinates": {"lat": 48.8566, "lon": 2.3522}},
        "share": {"url": "https://example.com/events/99"},
    }

    document = indexer.build_document(event)
    assert document.coordinates == {"lat": 48.8566, "lon": 2.3522}
    assert sorted(document.languages) == ["en-US", "fr-FR"]
    indexer.index_event(event, refresh=True)
    assert client.index_calls
    stored_document = client.index_calls[0]["document"]
    assert stored_document["coordinates"] == {"lat": 48.8566, "lon": 2.3522}
    assert "indexed_at" in stored_document

    indexer.bulk_index_events([event])
    assert client.bulk_calls


def test_search_service_combined_filters():
    events = [
        {
            "id": 1,
            "title": "Geo Python Paris",
            "description": "Meetup python",
            "date": "2025-09-10",
            "categories": [{"name": "Tech"}],
            "tags": [{"name": "python"}],
            "translations": [{"locale": "fr-FR"}],
            "settings": {"coordinates": {"lat": 48.8566, "lon": 2.3522}},
        },
        {
            "id": 2,
            "title": "Remote Marketing Webinar",
            "description": "Webinar",
            "date": "2025-09-12",
            "categories": [{"name": "Marketing"}],
            "tags": [{"name": "digital"}],
            "translations": [{"locale": "en-US"}],
            "settings": {"coordinates": {"lat": 45.764, "lon": 4.8357}},
        },
    ]

    service = EventSearchService(client=None, event_provider=lambda: events)
    results = service.search_events(
        text="python",
        categories=["Tech"],
        tags=["python"],
        languages=["fr-FR"],
        lat=48.8566,
        lon=2.3522,
        radius_km=100,
        page=1,
        size=10,
    )

    assert results["total"] == 1
    assert results["results"][0]["id"] == 1
    assert any("Geo" in suggestion for suggestion in results["suggestions"])


def test_bookmark_recommendations_and_map(client):
    session = get_session()
    service = EventService(session)
    try:
        event = service.create_event(
            {
                "title": "Geo Python Paris",
                "date": "2025-09-10",
                "location": "Paris",
                "default_locale": "fr-FR",
                "settings": {"coordinates": {"lat": 48.8566, "lon": 2.3522}},
                "translations": [
                    {
                        "locale": "fr-FR",
                        "title": "Geo Python Paris",
                        "description": "Rencontre autour de Python",
                    }
                ],
            }
        )
        event_id = event["id"]
    finally:
        session.close()

    search_resp = client.get(
        "/search/events",
        query_string={
            "q": "Python",
            "language": "fr-FR",
            "lat": "48.8566",
            "lon": "2.3522",
            "radius": "50",
        },
    )
    assert search_resp.status_code == 200
    search_ids = [item["id"] for item in search_resp.json["results"]]
    assert event_id in search_ids

    map_resp = client.get("/events/map")
    assert map_resp.status_code == 200
    feature_ids = [feature["properties"]["id"] for feature in map_resp.json["features"]]
    assert event_id in feature_ids

    calendar_resp = client.get("/events/calendar")
    assert calendar_resp.status_code == 200
    assert calendar_resp.mimetype == "text/calendar"
    assert "Geo Python Paris" in calendar_resp.data.decode()

    recommendations_resp = client.get("/users/user-geo/recommendations")
    assert recommendations_resp.status_code == 200
    recommended_ids = [item["id"] for item in recommendations_resp.json["recommendations"]]
    assert event_id in recommended_ids

    bookmark_resp = client.post(f"/events/{event_id}/bookmark", json={"user_id": "user-geo"})
    assert bookmark_resp.status_code == 201
    assert bookmark_resp.json["bookmark"]["bookmarked"] is True

    list_resp = client.get(f"/events/{event_id}/bookmark")
    assert list_resp.status_code == 200
    assert list_resp.json["total"] == 1

    recommendations_after = client.get("/users/user-geo/recommendations")
    ids_after = [item["id"] for item in recommendations_after.json["recommendations"]]
    assert event_id not in ids_after
