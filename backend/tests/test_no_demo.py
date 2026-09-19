import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import prepare_database
from app.config import Settings
from app.db import Base, make_engine
from app.main import create_app
from app.models import Tag, University, UniversityDomain, User


def test_repeated_startup_with_legacy_demo_flag_keeps_users_empty(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    monkeypatch.setenv("DUDRI_LOCAL_DEMO_ENABLED", "true")
    monkeypatch.setattr(sys, "argv", ["prepare_database"])
    monkeypatch.setattr(prepare_database, "upgrade", lambda: None)
    monkeypatch.setattr(prepare_database, "session_factory", lambda: factory)
    monkeypatch.setattr(prepare_database, "get_settings", lambda: Settings(_env_file=None))
    try:
        prepare_database.main()
        prepare_database.main()
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(User)) == 0
            assert db.scalar(select(func.count()).select_from(University)) == 3
            assert db.scalar(select(func.count()).select_from(UniversityDomain)) == 3
            assert db.scalar(select(func.count()).select_from(Tag)) == 15
    finally:
        engine.dispose()


@pytest.mark.parametrize("environment", ["development", "production"])
def test_demo_login_removed_and_local_instance_guarded(monkeypatch, environment):
    monkeypatch.setattr("app.dev.get_settings", lambda: type("Config", (), {"environment": environment})())
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/dev/accounts").status_code == 404
        assert client.post("/api/v1/dev/login", json={"user_id": "fixture"}).status_code == 404
        assert client.get("/api/v1/dev/instance").status_code == (200 if environment == "development" else 404)
    with TestClient(create_app(), client=("203.0.113.1", 12345)) as client:
        assert client.get("/api/v1/dev/instance").status_code in (403, 404)
