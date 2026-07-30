"""SQLite engine + session helpers (SQLModel)."""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import inspect, text
from sqlmodel import SQLModel, Session, create_engine

from . import models  # noqa: F401  (register models on the metadata)
from .config import settings


def get_engine(url: str | None = None):
    """Create a SQLModel engine. Defaults to the configured SQLite database."""
    database_url = url or settings.database_url
    connect_args = {}
    if database_url.startswith("sqlite"):
        # Allow the engine to be used across Streamlit reruns / threads.
        connect_args = {"check_same_thread": False}
    return create_engine(database_url, connect_args=connect_args, echo=False)


# Additive, local-only schema migration. SQLModel's create_all only creates
# missing *tables*, never missing *columns* on an existing table, so newly
# added nullable Lead columns are added here without dropping any data.
_LEAD_NEW_COLUMNS = {
    "phone": "TEXT",
    "address": "TEXT",
    "city": "TEXT",
}


def migrate_schema(engine) -> None:
    """Add any missing nullable columns to the existing local SQLite file."""
    if not engine.url.drivername.startswith("sqlite"):
        return
    inspector = inspect(engine)
    try:
        existing = {col["name"] for col in inspector.get_columns("lead")}
    except Exception:
        # Table may not exist yet (fresh DB); create_all will handle it.
        return
    with engine.begin() as conn:
        for col, sql_type in _LEAD_NEW_COLUMNS.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE lead ADD COLUMN {col} {sql_type}"))


def init_db(engine) -> None:
    """Create all tables if they do not exist yet, then run additive migration."""
    SQLModel.metadata.create_all(engine)
    migrate_schema(engine)


@contextmanager
def get_session(engine):
    with Session(engine) as session:
        yield session
