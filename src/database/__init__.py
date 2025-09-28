"""Database configuration and session management utilities."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

__all__ = [
    "Base",
    "get_engine",
    "init_engine",
    "get_session",
    "session_scope",
]

Base = declarative_base()

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def _build_database_url() -> str:
    """Build a database URL from environment variables."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    name = os.getenv("DB_NAME")

    if all([user, password, host, port, name]):
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"

    # Default to a local SQLite database when nothing else is configured.
    return "sqlite:///./event_service.db"


def init_engine(database_url: Optional[str] = None, **engine_kwargs) -> Engine:
    """Initialise the SQLAlchemy engine and session factory."""
    global _engine, _SessionLocal

    if database_url is None:
        database_url = _build_database_url()

    if _engine is not None:
        _engine.dispose()

    kwargs = {"future": True, "pool_pre_ping": True}
    kwargs.update(engine_kwargs)

    if database_url.startswith("sqlite"):
        kwargs.setdefault("connect_args", {"check_same_thread": False})
    else:
        pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
        max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
        kwargs.setdefault("pool_size", pool_size)
        kwargs.setdefault("max_overflow", max_overflow)

    _engine = create_engine(database_url, **kwargs)
    _SessionLocal = sessionmaker(
        bind=_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        future=True,
        class_=Session,
    )
    return _engine


def get_engine() -> Engine:
    """Return the configured SQLAlchemy engine, initialising if necessary."""
    global _engine
    if _engine is None:
        _engine = init_engine()
    return _engine


def get_session() -> Session:
    """Create a new SQLAlchemy session."""
    global _SessionLocal
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None  # For mypy
    return _SessionLocal()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope for database operations."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
