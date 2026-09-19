"""One-time, non-destructive copy into an empty PostgreSQL application schema."""
import argparse
import sqlite3
from datetime import UTC
from pathlib import Path

from sqlalchemy import DateTime, create_engine, func, inspect, select

from . import models  # noqa: F401 - register tables
from .config import ROOT, get_settings
from .db import Base, make_engine

SOURCE = ROOT / "backend/.data/dudri.db"
# Authentication/session-like rows must not cross environments.  Realtime
# tickets are one-time credentials and event rows are disposable invalidation
# hints, so neither belongs in a durable user-data transfer.
SKIPPED = {"auth_sessions", "auth_challenges", "external_accounts", "idempotency_records", "realtime_tickets", "realtime_events"}


class TransferError(Exception):
    """Messages are fixed strings, never driver errors or row values."""


def source_engine(path: Path):
    path = path.resolve(strict=True)
    if not path.is_file():
        raise TransferError("SQLite source must be an existing file.")
    return create_engine("sqlite://", creator=lambda: sqlite3.connect(path.as_uri() + "?mode=ro", uri=True),
                         hide_parameters=True)


def counts(connection):
    available = set(inspect(connection).get_table_names())
    # A historical SQLite export can predate a later feature table.  It is an
    # empty table for transfer purposes, rather than a reason to abandon a
    # non-destructive import of the rest of the user's data.
    return {table.name: connection.scalar(select(func.count()).select_from(table)) if table.name in available else 0
            for table in Base.metadata.sorted_tables if table.name not in SKIPPED}


def copy_rows(source, target):
    """Caller owns both transactions. Never overwrite any existing target data."""
    tables = Base.metadata.sorted_tables
    if target.dialect.name == "postgresql":
        target.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
        names = ", ".join('public."' + table.name + '"' for table in tables)
        target.exec_driver_sql(f"LOCK TABLE {names} IN ACCESS EXCLUSIVE MODE")
    if any(target.scalar(select(func.count()).select_from(table)) for table in tables):
        raise TransferError("Target already contains application data; nothing was copied. Use a new empty database.")
    expected = counts(source)
    source_schema = inspect(source)
    source_tables = set(source_schema.get_table_names())
    deferred = []
    for table in tables:
        if table.name in SKIPPED:
            continue
        if table.name not in source_tables:
            continue
        # Do not even read worker lease tokens or external credential records.
        available = {column["name"] for column in source_schema.get_columns(table.name)}
        missing = [column for column in table.c if column.name not in available]
        if any(not column.nullable and column.default is None and column.server_default is None for column in missing):
            raise TransferError("Source schema is missing required fields; nothing was copied.")
        columns = [column for column in table.c if column.name in available
                   and not (table.name == "jobs" and column.name == "lease_token")]
        result = source.execute(select(*columns)).mappings()
        while batch := result.fetchmany(100):
            rows = []
            for original in batch:
                row = dict(original)
                for column in columns:
                    if isinstance(column.type, DateTime) and row[column.name] is not None and row[column.name].tzinfo is None:
                        row[column.name] = row[column.name].replace(tzinfo=UTC)
                reference = {"personal_sites": "published_version_id", "site_versions": "base_version_id"}.get(table.name)
                if reference and row[reference]:
                    deferred.append((table, row["id"], reference, row[reference]))
                    row[reference] = None
                if table.name == "source_materials":
                    row["external_account_id"] = None
                if table.name == "jobs":
                    row["lease_token"], row["lease_until"] = None, None
                    if row["status"] == "running":
                        row["status"] = "queued"
                rows.append(row)
            target.execute(table.insert(), rows)
    for table, row_id, column, value in deferred:
        target.execute(table.update().where(table.c.id == row_id).values({column: value}))
    if counts(target) != expected:
        raise TransferError("Row-count verification failed; the copy was rolled back.")
    return expected


def transfer(path=SOURCE):
    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        raise TransferError("Set the Supabase PostgreSQL URI in DUDRI_DATABASE_URL first.")
    source = source_engine(path)
    target = make_engine(settings.database_url)
    try:
        with source.connect() as read:
            # Explicit BEGIN gives all tables the same snapshot on Python's SQLite driver.
            read.exec_driver_sql("BEGIN")
            with target.begin() as write:
                result = copy_rows(read, write)
        print(f"[database] Copied {sum(result.values())} records across {len(result)} tables; SQLite preserved.", flush=True)
        print("[database] Log in again and reconnect external accounts. Credentials and sessions were not copied.", flush=True)
    finally:
        source.dispose()
        target.dispose()


def local_data_exists():
    if not SOURCE.is_file():
        return False
    source = source_engine(SOURCE)
    try:
        with source.connect() as connection:
            return bool(connection.scalar(select(func.count()).select_from(Base.metadata.tables["users"])))
    finally:
        source.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Migrate the schema and copy into an empty PostgreSQL DB")
    args = parser.parse_args()
    try:
        if args.apply:
            from .prepare_database import upgrade
            if not get_settings().database_url.startswith("postgresql"):
                raise TransferError("Set DUDRI_DATABASE_URL to PostgreSQL first.")
            upgrade()
            transfer()
        else:
            source = source_engine(SOURCE)
            try:
                with source.connect() as connection:
                    result = counts(connection)
                print(f"[database] SQLite contains {sum(result.values())} transferable records. No data was written.")
                print("[database] Stop the app, set the root .env DB URI, then add --apply to copy into an empty PostgreSQL DB.")
            finally:
                source.dispose()
    except TransferError as exc:
        raise SystemExit(f"[database] {exc}") from None
    except Exception:
        raise SystemExit("[database] Transfer failed; no partial copy was committed. Check DB configuration, schema version and connectivity.") from None


if __name__ == "__main__":
    main()
