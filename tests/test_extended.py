import pytest


def test_category_crud(client):
    create_resp = client.post(
        "/event-categories",
        json={"name": "Workshops", "description": "Hands-on"},
    )
    assert create_resp.status_code == 201
    category_id = create_resp.json["category"]["id"]

    list_resp = client.get("/event-categories")
    assert list_resp.status_code == 200
    assert any(cat["id"] == category_id for cat in list_resp.json["categories"])

    get_resp = client.get(f"/event-categories/{category_id}")
    assert get_resp.status_code == 200
    assert get_resp.json["category"]["name"] == "Workshops"

    update_resp = client.patch(
        f"/event-categories/{category_id}",
        json={"description": "Workshops and labs"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json["category"]["description"] == "Workshops and labs"

    delete_resp = client.delete(f"/event-categories/{category_id}")
    assert delete_resp.status_code == 204

    missing_resp = client.get(f"/event-categories/{category_id}")
    assert missing_resp.status_code == 404


def test_tag_crud(client):
    create_resp = client.post("/event-tags", json={"name": "hybrid"})
    assert create_resp.status_code == 201
    tag_id = create_resp.json["tag"]["id"]

    get_resp = client.get(f"/event-tags/{tag_id}")
    assert get_resp.status_code == 200

    update_resp = client.put(f"/event-tags/{tag_id}", json={"name": "remote"})
    assert update_resp.status_code == 200
    assert update_resp.json["tag"]["name"] == "remote"

    delete_resp = client.delete(f"/event-tags/{tag_id}")
    assert delete_resp.status_code == 204


def test_template_instantiation_and_translations(client):
    template_payload = {
        "name": "Meetup template",
        "description": "Default meetup",
        "default_duration_minutes": 90,
        "default_timezone": "Europe/Paris",
        "default_locale": "fr-FR",
        "fallback_locale": "en-US",
        "default_capacity_limit": 200,
        "default_metadata": {"visibility": "public"},
    }
    template_resp = client.post("/event-templates", json=template_payload)
    assert template_resp.status_code == 201
    template_id = template_resp.json["template"]["id"]

    translation_resp = client.post(
        f"/event-templates/{template_id}/translations",
        json={"locale": "en-US", "title": "Meetup", "description": "Default"},
    )
    assert translation_resp.status_code == 201

    instantiate_payload = {
        "template_id": template_id,
        "overrides": {
            "title": "Paris Developers", "date": "2026-01-10", "attendees": 25
        },
    }
    create_event = client.post("/events/from-template", json=instantiate_payload)
    assert create_event.status_code == 201
    event = create_event.json["event"]
    assert event["timezone"] == "Europe/Paris"
    assert event["default_locale"] == "fr-FR"
    assert any(t["locale"] == "en-US" for t in event["translations"])
    assert event["settings"]["visibility"] == "public"


def test_event_translation_workflow(client):
    create_resp = client.post(
        "/events",
        json={"title": "Localised", "date": "2026-05-05"},
    )
    event_id = create_resp.json["event_id"]

    add_resp = client.post(
        f"/events/{event_id}/translations",
        json={"locale": "en-GB", "title": "Localized", "fallback": True},
    )
    assert add_resp.status_code == 201
    assert add_resp.json["translation"]["fallback"] is True

    update_resp = client.put(
        f"/events/{event_id}/translations/en-GB",
        json={"title": "Localized event"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json["translation"]["title"] == "Localized event"

    get_resp = client.get(f"/events/{event_id}")
    translations = get_resp.json["event"]["translations"]
    assert any(t["locale"] == "en-GB" and t["fallback"] for t in translations)

    delete_resp = client.delete(f"/events/{event_id}/translations/en-GB")
    assert delete_resp.status_code == 204


def test_approval_workflow(client):
    create_resp = client.post(
        "/events",
        json={"title": "Approval", "organizer_email": "orga@example.com"},
    )
    event_id = create_resp.json["event_id"]

    submit = client.post(
        f"/events/{event_id}/submit",
        json={"actor": "alice", "notes": "Ready"},
    )
    assert submit.status_code == 200
    assert submit.json["event"]["status"] == "pending"

    approve = client.post(
        f"/events/{event_id}/approve",
        json={"actor": "bob", "notes": "Looks good"},
    )
    assert approve.status_code == 200
    assert approve.json["event"]["status"] == "approved"

    invalid = client.post(f"/events/{event_id}/approve")
    assert invalid.status_code == 409


@pytest.mark.parametrize(
    "payload, field",
    [
        ({"title": "Bad TZ", "timezone": "Mars/Crater"}, "timezone"),
        ({"title": "Bad recurrence", "recurrence_rule": "DAILY"}, "recurrence_rule"),
    ],
)
def test_event_validation_errors(client, payload, field):
    resp = client.post("/events", json=payload)
    assert resp.status_code == 422
    assert field in resp.json["error"]["details"]


def test_virtual_networking_feedback_and_partners_flow(client):
    create_resp = client.post(
        "/events",
        json={
            "title": "Hybrid Innovation Summit",
            "date": "2026-09-10",
            "format": "hybrid",
            "streaming_url": "https://stream.example.com/hybrid",
            "virtual_platform": "Meetinity Live",
            "virtual_access_instructions": "Use the secure token provided",
            "secure_access_token": "secret-token",
            "rtmp_ingest_url": "rtmp://live.example.com/app",
            "rtmp_stream_key": "hybrid-key",
            "location": "Paris HQ",
        },
    )
    assert create_resp.status_code == 201
    event_id = create_resp.json["event_id"]
    event_payload = create_resp.json["event"]
    assert event_payload["format"] == "hybrid"
    assert event_payload["streaming_url"] == "https://stream.example.com/hybrid"
    assert event_payload["rtmp_stream_key"] == "hybrid-key"

    profile_1 = {
        "email": "alice@example.com",
        "name": "Alice",
        "company": "Innotech",
        "interests": ["AI", "Data"],
        "goals": ["Partnerships"],
        "availability": ["day1-morning", "day2-afternoon"],
    }
    profile_2 = {
        "email": "bob@example.com",
        "name": "Bob",
        "company": "CloudCorp",
        "interests": ["AI", "Cloud"],
        "goals": ["Networking", "Partnerships"],
        "availability": ["day1-morning"],
    }

    resp_profile_1 = client.post(
        f"/events/{event_id}/networking/profiles", json=profile_1
    )
    assert resp_profile_1.status_code == 201
    resp_profile_2 = client.post(
        f"/events/{event_id}/networking/profiles", json=profile_2
    )
    assert resp_profile_2.status_code == 201

    suggestions_resp = client.post(
        f"/events/{event_id}/networking/suggestions", json={"limit": 1}
    )
    assert suggestions_resp.status_code == 200
    suggestions = suggestions_resp.json["suggestions"]
    assert len(suggestions) == 2  # mutual suggestion
    assert all(s["rationale"] for s in suggestions)

    alice_suggestions = client.get(
        f"/events/{event_id}/networking/suggestions", query_string={"email": "alice@example.com"}
    )
    assert alice_suggestions.status_code == 200
    assert alice_suggestions.json["total"] == 1
    assert alice_suggestions.json["suggestions"][0]["suggested_email"] == "bob@example.com"

    feedback_1 = client.post(
        f"/events/{event_id}/feedback",
        json={
            "email": "alice@example.com",
            "name": "Alice",
            "rating": 5,
            "comment": "Excellent sessions",
        },
    )
    assert feedback_1.status_code == 201

    feedback_2 = client.post(
        f"/events/{event_id}/feedback",
        json={
            "email": "bob@example.com",
            "name": "Bob",
            "rating": 3,
            "comment": "Bon contenu",
        },
    )
    assert feedback_2.status_code == 201

    list_feedback = client.get(f"/events/{event_id}/feedback")
    assert list_feedback.status_code == 200
    assert list_feedback.json["summary"]["total"] == 2

    moderate = client.patch(
        f"/events/{event_id}/feedback/{feedback_1.json['feedback']['id']}",
        json={"status": "approved", "moderator": "moderator"},
    )
    assert moderate.status_code == 200
    assert moderate.json["feedback"]["status"] == "approved"

    speakers_resp = client.post(
        f"/events/{event_id}/speakers",
        json={
            "name": "Alice",
            "role": "speaker",
            "title": "CTO",
            "company": "Innotech",
            "topics": {"main": "AI"},
        },
    )
    assert speakers_resp.status_code == 201
    speaker_id = speakers_resp.json["speaker"]["id"]

    organizer_resp = client.post(
        f"/events/{event_id}/speakers",
        json={
            "name": "Claire",
            "role": "organizer",
            "company": "Meetinity",
        },
    )
    assert organizer_resp.status_code == 201

    speaker_update = client.patch(
        f"/events/{event_id}/speakers/{speaker_id}",
        json={"company": "Innotech Labs"},
    )
    assert speaker_update.status_code == 200
    assert speaker_update.json["speaker"]["company"] == "Innotech Labs"

    speakers_list = client.get(f"/events/{event_id}/speakers")
    assert speakers_list.status_code == 200
    assert speakers_list.json["total"] == 2

    sponsor_resp = client.post(
        f"/events/{event_id}/sponsors",
        json={
            "name": "CloudCorp",
            "level": "Gold",
            "website": "https://cloudcorp.example.com",
        },
    )
    assert sponsor_resp.status_code == 201
    sponsor_id = sponsor_resp.json["sponsor"]["id"]

    sponsor_update = client.patch(
        f"/events/{event_id}/sponsors/{sponsor_id}",
        json={"description": "Premier partenaire"},
    )
    assert sponsor_update.status_code == 200
    assert sponsor_update.json["sponsor"]["description"] == "Premier partenaire"

    sponsors_list = client.get(f"/events/{event_id}/sponsors")
    assert sponsors_list.status_code == 200
    assert sponsors_list.json["total"] == 1

    delete_sponsor = client.delete(
        f"/events/{event_id}/sponsors/{sponsor_id}"
    )
    assert delete_sponsor.status_code == 204

    final_sponsors = client.get(f"/events/{event_id}/sponsors")
    assert final_sponsors.json["total"] == 0
