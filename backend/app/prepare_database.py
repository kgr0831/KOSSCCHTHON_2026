"""Prepare the configured database without printing connection errors or row values."""
import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from .config import get_settings
from .db import session_factory
from .migrate_sqlite import TransferError
from .models import User
from .seed import catalog, seed


def upgrade():
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    command.upgrade(config, "head")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-sqlite", action="store_true")
    args = parser.parse_args()
    try:
        settings = get_settings()
        if args.import_sqlite and not settings.database_url.startswith("postgresql"):
            raise SystemExit("[database] Set DUDRI_DATABASE_URL to Supabase before using --import-sqlite.")
        upgrade()
        if args.import_sqlite:
            from .migrate_sqlite import transfer
            transfer()
        elif settings.database_url.startswith("postgresql"):
            from .migrate_sqlite import local_data_exists
            with session_factory()() as db:
                if not db.scalar(select(User.id).limit(1)) and local_data_exists():
                    raise SystemExit("[database] Existing SQLite data found. Close the app and run start-local.bat --import-sqlite once to preserve it in the empty PostgreSQL database.")
        with session_factory().begin() as db:
            if settings.environment == "development" and settings.local_demo_enabled:
                seed(db)
            else:
                catalog(db)
        print("[database] Migrations complete. Existing records preserved.", flush=True)
    except TransferError as exc:
        raise SystemExit(f"[database] {exc}") from None
    except Exception:
        # Driver exceptions can contain connection details or data. Do not print them.
        raise SystemExit("[database] Preparation failed. Check DUDRI_DATABASE_URL in the root .env, DB password, connectivity and schema permissions.") from None


if __name__ == "__main__":
    main()
