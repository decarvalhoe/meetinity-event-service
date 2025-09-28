from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.main import app, _reset_events_storage


@pytest.fixture
def client():
    _reset_events_storage()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


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


def test_create_event(client):
    response = client.post('/events', json={"title": "Test Event"})
    assert response.status_code == 201
    assert 'event_id' in response.json


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
    response = client.post('/events', json={"title": "Bool Event", "attendees": True})
    assert response.status_code == 422
    assert response.json["error"]["message"] == "Validation échouée."
    assert response.json["error"]["details"]["attendees"] == [
        "Doit être un entier >= 0 (valeur booléenne non autorisée)."
    ]
