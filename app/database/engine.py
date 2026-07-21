"""SQLAlchemy engine and session factory for SQLite."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import String, Text, create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_config
from app.core.logging import get_logger
from app.database.models import Base

logger = get_logger(__name__)

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def init_engine(database_path: str | None = None) -> Engine:
    """Create the engine, enable WAL + foreign keys, and create tables."""
    global _engine, _session_factory
    if _engine is not None:
        return _engine

    db_path = Path(database_path or get_config().database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(_engine, "connect")
    def _set_pragmas(dbapi_conn, _record) -> None:  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(_engine)
    _apply_additive_migrations(_engine)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def _apply_additive_migrations(engine: Engine) -> None:
    """Add columns introduced after a database was first created.

    ``create_all`` never alters existing tables, so when the ORM gains a new
    column an older database is missing it. This adds any missing columns
    (safe for SQLite's additive ``ALTER TABLE ADD COLUMN``) so upgrades need no
    manual migration. Non-additive changes would still need a real migration.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.tables.values():
        if table.name not in existing_tables:
            continue
        present = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            col_type = column.type.compile(dialect=engine.dialect)
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}"
            if isinstance(column.type, (String, Text)):
                ddl += " DEFAULT ''"
            with engine.begin() as conn:
                conn.execute(text(ddl))
            logger.info("Schema migration: added column %s.%s", table.name, column.name)


def get_session_factory() -> sessionmaker[Session]:
    """Session factory accessor (initialises the engine on first use)."""
    if _session_factory is None:
        init_engine()
    assert _session_factory is not None
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope: commits on success, rolls back on error."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_engine() -> None:
    """Dispose the engine (tests / clean shutdown)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
