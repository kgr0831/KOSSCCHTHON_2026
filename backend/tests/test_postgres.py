"""Runs only against the explicit disposable CI database, never a configured app DB."""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from test_database import add_saved_portfolio

from app.config import Settings
from app.db import Base, make_engine
from app.migrate_sqlite import copy_rows
from app.models import PersonalSite, SiteVersion

URL = os.environ.get("DUDRI_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="An isolated PostgreSQL CI database is required")


def test_postgres_upgrade_copy_private_roles_and_downgrade(world, monkeypatch):
    url = make_url(URL)
    assert url.host in ("127.0.0.1", "localhost") and url.database == "dudri_ci", "Only the disposable localhost CI database is allowed"
    settings = Settings(_env_file=None, environment="test", database_url=URL)
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    engine = make_engine(settings.database_url)
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    assert not set(inspect(engine).get_table_names()) & set(Base.metadata.tables), "CI target must initially be empty"
    with engine.begin() as db:
        for role in ("anon", "authenticated", "service_role"):
            if not db.scalar(text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}):
                db.exec_driver_sql(f"CREATE ROLE {role} NOLOGIN")
    try:
        command.upgrade(config, "head")
        assert "fk_personal_sites_published_version" in {x["name"] for x in inspect(engine).get_foreign_keys("personal_sites")}
        site_id, first_id, second_id = add_saved_portfolio(world)
        with world["factory"].kw["bind"].connect() as source, engine.begin() as target:
            copy_rows(source, target)
        with engine.connect() as db:
            assert db.scalar(select(PersonalSite.published_version_id).where(PersonalSite.id == site_id)) == second_id
            assert db.scalar(select(SiteVersion.base_version_id).where(SiteVersion.id == second_id)) == first_id
            for table in Base.metadata.tables:
                assert db.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass(:name)"), {"name": f"public.{table}"})
        with pytest.raises(DBAPIError), engine.begin() as db:
            db.execute(PersonalSite.__table__.update().where(PersonalSite.id == site_id).values(published_version_id="missing"))
        for role in ("anon", "authenticated", "service_role"):
            with pytest.raises(DBAPIError), engine.begin() as db:
                db.exec_driver_sql(f"SET LOCAL ROLE {role}")
                db.exec_driver_sql("SELECT * FROM public.source_materials")
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        assert "fk_personal_sites_published_version" in {x["name"] for x in inspect(engine).get_foreign_keys("personal_sites")}
    finally:
        # This target was asserted empty before this test created its schema.
        command.downgrade(config, "base")
        engine.dispose()
