from datetime import date, timedelta


def create_event(client, **overrides):
    payload = {
        "title": "Capacity Test",
        "date": (date.today() + timedelta(days=7)).isoformat(),
        "location": "Paris",
        "type": "workshop",
        "attendees": 2,
    }
    payload.update(overrides)
    response = client.post("/events", json=payload)
    assert response.status_code == 201
    return response.json["event_id"]


def register(client, event_id, email, name):
    response = client.post(
        f"/events/{event_id}/registrations",
        json={"email": email, "name": name},
    )
    return response


def test_registration_waitlist_flow(client):
    event_id = create_event(client, attendees=2)

    first = register(client, event_id, "alice@example.com", "Alice")
    assert first.status_code == 201
    assert first.json["status"] == "confirmed"
    assert first.json["registration"]["status"] == "confirmed"

    second = register(client, event_id, "bob@example.com", "Bob")
    assert second.status_code == 201

    third = register(client, event_id, "carol@example.com", "Carol")
    assert third.status_code == 202
    assert third.json["status"] == "waitlisted"

    waitlist = client.get(f"/events/{event_id}/waitlist")
    assert waitlist.status_code == 200
    emails = [entry["email"] for entry in waitlist.json["waitlist"]]
    assert "carol@example.com" in emails


def test_waitlist_promotion_on_cancellation(client):
    event_id = create_event(client, attendees=1)
    first = register(client, event_id, "first@example.com", "First")
    second = register(client, event_id, "second@example.com", "Second")
    assert second.status_code == 202

    registration_id = first.json["registration"]["id"]
    cancel = client.delete(f"/events/{event_id}/registrations/{registration_id}")
    assert cancel.status_code == 200
    promoted = cancel.json.get("promoted", [])
    assert any(item["email"] == "second@example.com" for item in promoted)

    registrations = client.get(f"/events/{event_id}/registrations")
    assert registrations.status_code == 200
    statuses = {item["email"]: item["status"] for item in registrations.json["registrations"]}
    assert statuses.get("second@example.com") == "confirmed"


def test_check_in_endpoint_creates_attendance(client):
    event_id = create_event(client, attendees=1)
    response = register(client, event_id, "check@example.com", "Check In")
    token = response.json["registration"]["token"]

    check_in = client.post(
        f"/check-in/{token}",
        json={"method": "qr", "metadata": {"gate": "north"}},
    )
    assert check_in.status_code == 200
    attendance = check_in.json["attendance"]
    assert attendance["status"] == "checked_in"
    assert attendance["method"] == "qr"

    attendance_list = client.get(f"/events/{event_id}/attendance")
    assert attendance_list.status_code == 200
    record = attendance_list.json["attendance"][0]
    assert record["status"] == "checked_in"
    assert record["checked_in_at"] is not None


def test_no_show_detection_applies_penalty(client):
    past_date = (date.today() - timedelta(days=10)).isoformat()
    event_id = create_event(client, date=past_date, attendees=1)
    response = register(client, event_id, "ghost@example.com", "Ghost")
    assert response.status_code == 201

    detection = client.post(f"/events/{event_id}/attendance")
    assert detection.status_code == 200
    penalized = detection.json["penalized"]
    assert penalized
    assert penalized[0]["email"] == "ghost@example.com"

    registrations = client.get(f"/events/{event_id}/registrations")
    assert registrations.status_code == 200
    statuses = {item["email"]: item["status"] for item in registrations.json["registrations"]}
    assert statuses["ghost@example.com"] == "no_show"
