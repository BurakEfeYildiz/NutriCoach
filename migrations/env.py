from alembic import context
from app.core.config import Settings
from app.db.database import Base, create_database
from app.models import chat, nutrition, user  # noqa: F401

config = context.config


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Bu proje migration için canlı DB bağlantısı gerektirir.")
connection = config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    engine, _ = create_database(Settings().database_url)
    try:
        with engine.connect() as connection:
            run(connection)
    finally:
        engine.dispose()
