from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def sqlite_constraints(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=10000")
    return engine


_factory = None


def session_factory():
    global _factory
    if _factory is None:
        settings = get_settings()
        settings.storage_path.parent.mkdir(parents=True, exist_ok=True)
        _factory = sessionmaker(make_engine(settings.database_url), expire_on_commit=False)
    return _factory


def get_db() -> Generator[Session, None, None]:
    with session_factory()() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
