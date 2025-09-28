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
