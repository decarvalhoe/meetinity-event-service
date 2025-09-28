import os
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.database import Base, get_engine, get_session, init_engine
from src.main import app
from src.services.events import EventService


class StubUserProfileClient:
    def __init__(self):
        self.profiles = {
            "user-geo": {
                "preferred_categories": ["Tech"],
                "preferred_tags": ["python"],
                "preferred_languages": ["fr-FR", "en-US"],
                "location": {"lat": 48.8566, "lon": 2.3522},
                "radius_km": 500,
                "bookmarked_events": [],
            }
        }

    def get_user_profile(self, user_id: str):
        return self.profiles.get(user_id, {})


DEFAULT_EVENTS = [
    {
        "title": "Networking Night Paris",
        "date": "2025-08-15",
        "location": "Paris",
        "type": "networking",
        "attendees": 45,
    },
    {
        "title": "Tech Meetup Lyon",
        "date": "2025-08-20",
        "location": "Lyon",
        "type": "tech",
        "attendees": 32,
    },
]


@pytest.fixture(scope="session")
def database_url(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("db") / "test.db"
    return f"sqlite:///{db_file}"


@pytest.fixture(scope="session", autouse=True)
def setup_database(database_url):
    os.environ["DATABASE_URL"] = database_url
    engine = init_engine(database_url)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_database():
    engine = get_engine()
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    yield


@pytest.fixture
def seed_default_events():
    session = get_session()
    service = EventService(session)
    try:
        for payload in DEFAULT_EVENTS:
            service.create_event(payload)
    finally:
        session.close()


@pytest.fixture
def client(seed_default_events):
    app.config["TESTING"] = True
    app.config["EVENTS_INDEX"] = "events-test"
    app.config["SEARCH_CLIENT"] = None
    app.config["USER_PROFILE_CLIENT"] = StubUserProfileClient()
    with app.test_client() as client:
        yield client
