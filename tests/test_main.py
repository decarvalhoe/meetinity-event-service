from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))


def test_health(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json['status'] == 'ok'
    assert response.json['service'] == 'event-service'


def test_get_events(client):
    response = client.get('/events')
    assert response.status_code == 200
    assert 'events' in response.json
    assert len(response.json['events']) >= 0


def test_get_events_with_filters(client):
    # Ensure filtering by type narrows the results
    response = client.get('/events?type=networking')
    assert response.status_code == 200
    events = response.json['events']
    assert all(event['type'] == 'networking' for event in events)

    # Invalid filter values should trigger validation errors
    invalid_filter = client.get('/events?after=2025/08/01')
    assert invalid_filter.status_code == 422
    error = invalid_filter.json['error']
    assert error['message'] == 'Validation échouée.'
    assert 'after' in error['details']


def test_create_event(client):
    response = client.post('/events', json={"title": "Test Event"})
    assert response.status_code == 201
    assert 'event_id' in response.json


def test_create_event_with_invalid_date(client):
    response = client.post(
        '/events',
        json={"title": "Date Invalide", "date": "2025/09/01"},
    )
    assert response.status_code == 422
    error = response.json["error"]
    assert error["message"] == "Validation échouée."
    assert "date" in error["details"]
    assert any(
        "YYYY-MM-DD" in message for message in error["details"]["date"]
    )


def test_create_event_with_valid_date(client):
    payload = {"title": "Date Valide", "date": "2025-10-05"}
    response = client.post('/events', json=payload)
    assert response.status_code == 201
    created_event = response.json["event"]
    assert created_event["date"] == payload["date"]


def test_create_and_get_event(client):
    payload = {
        "title": "Evenement Test",
        "date": "2025-09-01",
        "location": "Marseille",
        "type": "networking",
        "attendees": 10,
    }

    create_response = client.post('/events', json=payload)
    assert create_response.status_code == 201
    event_id = create_response.json['event_id']

    get_response = client.get(f'/events/{event_id}')
    assert get_response.status_code == 200
    event = get_response.json['event']
    assert event['id'] == event_id
    assert event['title'] == payload['title']
    assert event['date'] == payload['date']
    assert event['location'] == payload['location']
    assert event['type'] == payload['type']
    assert event['attendees'] == payload['attendees']


def test_update_event(client):
    payload = {
        "title": "Evenement Update",
        "date": "2025-09-15",
        "location": "Nice",
        "type": "conference",
        "attendees": 50,
    }

    create_response = client.post('/events', json=payload)
    event_id = create_response.json['event_id']

    update_payload = {"location": "Nice Centre", "attendees": 75}
    update_response = client.patch(f'/events/{event_id}', json=update_payload)
    assert update_response.status_code == 200
    updated_event = update_response.json['event']
    assert updated_event['location'] == "Nice Centre"
    assert updated_event['attendees'] == 75

    # Fetch to confirm persistence
    fetch_response = client.get(f'/events/{event_id}')
    assert fetch_response.status_code == 200
    assert fetch_response.json['event']['attendees'] == 75


def test_update_event_validation_errors(client):
    create_response = client.post(
        '/events',
        json={"title": "Validation Target"},
    )
    event_id = create_response.json['event_id']

    invalid_update = client.patch(
        f'/events/{event_id}',
        json={"date": "2025/11/01", "attendees": True},
    )

    assert invalid_update.status_code == 422
    error = invalid_update.json['error']
    assert error['message'] == 'Validation échouée.'
    assert 'date' in error['details']
    assert 'attendees' in error['details']


def test_update_event_not_found(client):
    response = client.patch('/events/9999', json={"title": "Missing"})
    assert response.status_code == 404
    error = response.json['error']
    assert error['code'] == 404
    assert error['message'] == 'Événement introuvable.'


def test_get_event_not_found(client):
    response = client.get('/events/9999')
    assert response.status_code == 404
    error = response.json['error']
    assert error['code'] == 404
    assert error['message'] == 'Événement introuvable.'


def test_create_event_with_array_payload(client):
    response = client.post('/events', json=[])
    assert response.status_code == 400
    error = response.json['error']
    assert error['code'] == 400
    assert (
        error['message']
        == "Payload JSON invalide: un objet JSON (type dict) est requis."
    )


def test_create_event_rejects_boolean_attendees(client):
    response = client.post(
        '/events',
        json={"title": "Bool Event", "attendees": True},
    )
    assert response.status_code == 422
    assert response.json["error"]["message"] == "Validation échouée."
    assert response.json["error"]["details"]["attendees"] == [
        "Doit être un entier >= 0 (valeur booléenne non autorisée)."
    ]
