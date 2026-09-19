import importlib.util
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, func, select
from sqlalchemy.engine import make_url

from app.config import LOCAL_DATABASE_URL, Settings
from app.db import Base, make_engine
from app.migrate_sqlite import TransferError, copy_rows, counts, source_engine
from app.models import AuthSession, Job, PersonalSite, SiteVersion, User


def test_supabase_dotenv_driver_and_secret_safe_errors(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("DUDRI_DATABASE_URL=postgresql://postgres.example:fixture%40password@pool.supabase.com:5432/postgres\n")
    settings = Settings(_env_file=dotenv)
    assert make_url(settings.database_url).drivername == "postgresql+psycopg"
    assert make_url(settings.database_url).password == "fixture@password"
    assert "fixture" not in repr(settings)
    assert Settings(_env_file=None, database_url="").database_url == LOCAL_DATABASE_URL
    with pytest.raises(ValueError) as error:
        Settings(_env_file=None, database_url="invalid-fixture-secret")
    assert "invalid-fixture-secret" not in str(error.value)


@pytest.mark.parametrize("query, expected", [("", "require"), ("?sslmode=disable", "require"), ("?sslmode=verify-full", "verify-full")])
def test_supabase_tls_and_pooler_connection_options(query, expected):
    engine = make_engine("postgresql://postgres.example:fixture@pool.supabase.com:6543/postgres" + query)
    captured = {}

    @event.listens_for(engine, "do_connect")
    def capture(dialect, record, args, kwargs):
        captured.update(kwargs)
        raise RuntimeError("Prevent all network access in this test")

    with pytest.raises(RuntimeError):
        engine.connect()
    assert captured["sslmode"] == expected
    assert captured["prepare_threshold"] is None
    assert captured["connect_timeout"] == 10
    assert engine.hide_parameters
    engine.dispose()


def test_postgres_migrations_include_private_tables_and_circular_fk(monkeypatch):
    output = StringIO()
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(backend / "migrations"))
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(_env_file=None, database_url="postgresql://localhost/unused"))
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "ADD CONSTRAINT fk_personal_sites_published_version" in sql
    for table in [*Base.metadata.tables, "alembic_version"]:
        assert f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY' in sql
        assert f'REVOKE ALL ON TABLE public."{table}" FROM PUBLIC' in sql
        for role in ("anon", "authenticated", "service_role"):
            assert f'REVOKE ALL ON TABLE public."{table}" FROM {role}' in sql
    output.seek(0)
    output.truncate()
    command.downgrade(config, "head:base", sql=True)
    sql = output.getvalue()
    assert sql.index("DROP CONSTRAINT fk_personal_sites_published_version") < sql.index("DROP TABLE site_versions")


def add_saved_portfolio(world):
    world["auth"](0)  # Authentication rows must not be copied.
    with world["factory"].begin() as db:
        site = PersonalSite(user_id=world["users"][0], site_kind="portfolio", slug="fixture")
        db.add(site)
        db.flush()
        first = SiteVersion(site_id=site.id, version_number=1, edit_mode="ai", style_id="linear",
                            public_input_snapshot={"name": "Fixture", "active": True}, facts_revision=1,
                            code={"html": "<h1>Saved portfolio</h1>"})
        db.add(first)
        db.flush()
        second = SiteVersion(site_id=site.id, version_number=2, edit_mode="gui", style_id="linear",
                             public_input_snapshot={}, facts_revision=1, base_version_id=first.id)
        db.add(second)
        db.flush()
        site.published_version_id = second.id
        return site.id, first.id, second.id


def test_transfer_preserves_documents_links_and_refuses_overwrite(world, tmp_path):
    site_id, first_id, second_id = add_saved_portfolio(world)
    source = world["factory"].kw["bind"]
    target = make_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(target)
    try:
        with source.connect() as read, target.begin() as write:
            expected = copy_rows(read, write)
        with target.connect() as write, source.connect() as read:
            assert counts(write) == expected == counts(read)
            assert write.scalar(select(PersonalSite.published_version_id).where(PersonalSite.id == site_id)) == second_id
            assert write.scalar(select(SiteVersion.base_version_id).where(SiteVersion.id == second_id)) == first_id
            assert write.scalar(select(SiteVersion.public_input_snapshot).where(SiteVersion.id == first_id))["active"] is True
            assert write.scalar(select(func.count()).select_from(AuthSession)) == 0
        with pytest.raises(TransferError), source.connect() as read, target.begin() as write:
            copy_rows(read, write)
        with target.connect() as write:
            assert counts(write) == expected
    finally:
        target.dispose()


def test_transfer_failure_rolls_back_all_rows_and_source_is_read_only(world, tmp_path):
    add_saved_portfolio(world)
    source = source_engine(Path(world["factory"].kw["bind"].url.database))
    target = make_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(target)

    @event.listens_for(target, "before_cursor_execute")
    def reject(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO site_versions"):
            raise RuntimeError("Fixture failure after other tables were inserted")

    try:
        with pytest.raises(RuntimeError), source.connect() as read, target.begin() as write:
            copy_rows(read, write)
        with target.connect() as read:
            assert read.scalar(select(func.count()).select_from(User)) == 0
        with source.connect() as read:
            with pytest.raises(Exception, match="readonly"):
                read.execute(User.__table__.update().values(account_status="inactive"))
    finally:
        source.dispose()
        target.dispose()


def test_reclaimed_lease_is_rechecked_after_owner_lock(world, monkeypatch):
    from app import job_lease
    from app.job_lease import locked_lease
    with world["factory"].begin() as db:
        job = Job(user_id=world["users"][0], kind="site", target_id="fixture", status="running", lease_token="old-worker")
        db.add(job)
        db.flush()
        job_id = job.id
    original = job_lease.lock_user

    def reclaim_before_lock(db, user_id):
        with world["factory"].begin() as other:
            other.get(Job, job_id).lease_token = "new-worker"
        return original(db, user_id)

    monkeypatch.setattr(job_lease, "lock_user", reclaim_before_lock)
    with world["factory"].begin() as db:
        stale = db.get(Job, job_id)
        assert stale.lease_token == "old-worker"
        assert locked_lease(db, job_id, "old-worker") is None
        assert stale.lease_token == "new-worker"


def test_frontend_environment_excludes_backend_credentials_and_keeps_site_origin():
    path = Path(__file__).resolve().parents[2] / "scripts/run_local.py"
    spec = importlib.util.spec_from_file_location("dudri_launcher", path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    result = launcher.frontend_environment({"DUDRI_DATABASE_URL": "fixture", "DUDRI_AI_API_KEY": "fixture",
                                           "SUPABASE_KEY": "fixture", "DATABASE_URL": "fixture",
                                           "DUDRI_SITE_ORIGIN": "http://127.0.0.1:8003", "API_ORIGIN": "http://127.0.0.1:8002"})
    assert result == {"DUDRI_SITE_ORIGIN": "http://127.0.0.1:8003", "API_ORIGIN": "http://127.0.0.1:8002"}


def test_health_checks_database_and_hides_driver_details(world):
    from sqlalchemy.exc import OperationalError

    from app.db import get_db
    client = world["client"]
    assert client.get("/api/v1/health").json()["database"] == "ok"

    def unavailable():
        raise OperationalError("fixture-secret-sql", {}, RuntimeError("fixture-secret-connection"))
        yield

    client.app.dependency_overrides[get_db] = unavailable
    result = client.get("/api/v1/health")
    assert result.status_code == 503 and result.json()["code"] == "DATABASE_UNAVAILABLE"
    assert "fixture-secret" not in result.text


def test_production_origins_and_sites_need_no_mail_credentials():
    assert Settings(_env_file=None, app_origin="https://app.example:443/").app_origin == "https://app.example"
    with pytest.raises(ValueError, match="separate origin"):
        Settings(_env_file=None, app_origin="https://app.example", site_origin="https://app.example:443/")
    settings = Settings(_env_file=None, environment="production", service_role="sites",
                        database_url="postgresql://localhost/fixture", site_origin="https://sites.example")
    assert not settings.smtp_password and not settings.ai_api_key


def test_production_catalog_does_not_create_demo_users(world):
    from app.seed import catalog
    with world["factory"].begin() as db:
        before = db.scalar(select(func.count()).select_from(User))
        catalog(db)
        catalog(db)
        assert db.scalar(select(func.count()).select_from(User)) == before


def test_cloud_rejects_subscription_cli_before_execution(monkeypatch):
    from fastapi import HTTPException

    from app.ai import AIProvider
    monkeypatch.setattr("app.ai.get_settings", lambda: type("Config", (), {"environment": "production"})())
    with pytest.raises(HTTPException) as error:
        AIProvider("cli")._cli("fixture", {}, "hard")
    assert error.value.status_code == 403


def test_import_legacy_sqlite_without_supabase_identity_column(tmp_path, monkeypatch):
    legacy_url = f"sqlite:///{tmp_path / 'legacy.db'}"
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(_env_file=None, database_url=legacy_url))
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    command.upgrade(config, "c28170e1b9ad")
    source = make_engine(legacy_url)
    target = make_engine(f"sqlite:///{tmp_path / 'new.db'}")
    Base.metadata.create_all(target)
    try:
        with source.begin() as db:
            db.exec_driver_sql("INSERT INTO users (id, created_at, login_email, account_status, is_admin, facts_revision) "
                               "VALUES ('legacy-owner', '2026-01-01 00:00:00', 'legacy@example.com', 'active', 0, 1)")
        with source.connect() as read, target.begin() as write:
            copy_rows(read, write)
        with target.connect() as db:
            assert db.scalar(select(User.id)) == "legacy-owner"
            assert db.scalar(select(User.supabase_user_id)) is None
        command.upgrade(config, "head")
        command.downgrade(config, "c28170e1b9ad")
    finally:
        source.dispose()
        target.dispose()
