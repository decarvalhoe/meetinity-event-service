# Meetinity Event Service

This service powers professional event management on the Meetinity platform. It is built with **Flask** and **SQLAlchemy**, and exposes a JSON REST API for creating, searching and updating events.

## Overview

- **Frameworks**: Flask 3, SQLAlchemy 2, Alembic
- **Database**: PostgreSQL by default (SQLite fallback for local development/testing)
- **Structure**: layered architecture with database, repository and service modules

## Features

- Persistent storage of events, categories, tags, templates and series
- CRUD operations exposed through REST endpoints
- Validation with rich error messages and consistent HTTP responses
- Automatic timestamps and status tracking for approvals
- Service layer encapsulating business logic, including series management

## Project Layout

```
src/
├── database/             # SQLAlchemy engine and session management
├── main.py               # Flask application and HTTP endpoints
├── models/               # SQLAlchemy ORM models
├── repositories/         # Data access abstractions
└── services/             # Domain services (validation + orchestration)
migrations/               # Alembic migration scripts
tests/                    # Pytest suite with database fixtures
```

## Getting Started

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure the database**
   Set a `DATABASE_URL` pointing to PostgreSQL or SQLite. Example for SQLite:
   ```bash
   export DATABASE_URL=sqlite:///./event_service.db
   ```
   PostgreSQL example:
   ```bash
   export DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/meetinity_events
   ```

3. **Run migrations**
   ```bash
   alembic upgrade head
   ```

4. **Start the service**
   ```bash
   python src/main.py
   ```
   The API listens on `http://localhost:5003` by default.

## Database Migrations

Alembic is configured under the `migrations/` directory.

- Create a new revision:
  ```bash
  alembic revision -m "short description"
  ```
- Apply migrations:
  ```bash
  alembic upgrade head
  ```
- Downgrade to a previous revision:
  ```bash
  alembic downgrade <revision_id>
  ```

The migration environment automatically uses the `DATABASE_URL` environment variable. When not provided, it falls back to the same defaults as the application (`sqlite:///./event_service.db`).

## Testing

Pytest is configured to run against a temporary SQLite database with fixtures defined in `tests/conftest.py`.

```bash
pytest
```

## Environment Variables

| Variable       | Description                                                      |
|----------------|------------------------------------------------------------------|
| `DATABASE_URL` | Full SQLAlchemy URL (e.g. `postgresql+psycopg2://...`). Optional. |
| `DB_USER`      | PostgreSQL user (used when `DATABASE_URL` is not provided).       |
| `DB_PASSWORD`  | PostgreSQL password.                                              |
| `DB_HOST`      | PostgreSQL host.                                                  |
| `DB_PORT`      | PostgreSQL port.                                                  |
| `DB_NAME`      | PostgreSQL database name.                                         |
| `DB_POOL_SIZE` | Optional pool size override (default: 5).                         |
| `DB_MAX_OVERFLOW` | Optional pool overflow override (default: 10).                 |

If `DATABASE_URL` is omitted, the application will assemble one from the `DB_*` variables. When none are set it uses a local SQLite database for convenience.

## Development Tips

- Use Alembic for all schema changes.
- Keep business rules in the service layer (`src/services/`).
- Repositories should stay focused on data access and querying.
- Tests rely on the fixtures in `tests/conftest.py` to prepare a clean database per test.
