from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    parsed = make_url(url)
    if parsed.drivername in ("postgres", "postgresql"):
        parsed = parsed.set(drivername="postgresql+psycopg")
    sqlite = parsed.get_backend_name() == "sqlite"
    options = {"check_same_thread": False} if sqlite else {"connect_timeout": 10, "prepare_threshold": None}
    if not sqlite and (parsed.host or "").endswith((".supabase.co", ".supabase.com")):
        # Keep certificate verification if configured; never silently downgrade TLS.
        if parsed.query.get("sslmode") not in ("require", "verify-ca", "verify-full"):
            options["sslmode"] = "require"
    engine = create_engine(parsed, connect_args=options, pool_pre_ping=True, hide_parameters=True,
                           **({} if sqlite else {"pool_size": 3, "max_overflow": 2, "pool_recycle": 300}))
    if sqlite:
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
