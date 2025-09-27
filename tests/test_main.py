import pathlib
import sys

import pytest

project_root = pathlib.Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.main import app


@pytest.fixture
def client():
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


def test_create_event_invalid_date(client):
    response = client.post(
        '/events', json={"title": "Test Event", "date": "2025/08/15"}
    )
    assert response.status_code == 422
    assert response.json['error']['code'] == 422
    assert 'date' in response.json['error']['details']
    assert any(
        "YYYY-MM-DD" in msg for msg in response.json['error']['details']['date']
    )


def test_create_event_valid_date(client):
    payload = {"title": "Valid Date Event", "date": "2025-08-15"}
    response = client.post('/events', json=payload)
    assert response.status_code == 201
    assert response.json['event']['date'] == payload['date']
