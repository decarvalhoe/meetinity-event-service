import pytest
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


def test_create_event_with_array_payload(client):
    response = client.post('/events', json=[{"title": "Invalid"}])
    assert response.status_code == 400
    assert response.json['error']['code'] == 400
    assert 'objet JSON' in response.json['error']['message']
