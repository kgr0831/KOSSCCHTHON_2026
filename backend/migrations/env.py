from alembic import context

from app.config import get_settings
from app.db import Base, make_engine
from app import models  # noqa: F401

settings = get_settings()
settings.storage_path.parent.mkdir(parents=True, exist_ok=True)

if context.is_offline_mode():
    context.configure(url=settings.database_url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with make_engine(settings.database_url).connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
