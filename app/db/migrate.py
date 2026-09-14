"""Run explicitly with: python -m app.db.migrate (stop the server first)."""
from pathlib import Path
import sqlite3
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine, make_url

from app.core.config import Settings
from app.db.database import create_database

ROOT = Path(__file__).resolve().parents[2]


def migration_config() -> Config:
    return Config(str(ROOT / "alembic.ini"))


def require_current_schema(engine: Engine) -> None:
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_heads()
    if set(current) != set(ScriptDirectory.from_config(migration_config()).get_heads()):
        raise RuntimeError("Veritabanı güncel değil. Önce: python -m app.db.migrate")


def upgrade_database(url: str) -> Path | None:
    parsed = make_url(url)
    backup = None
    if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, "", ":memory:"):
        path = Path(parsed.database).resolve()
        if path.exists() and path.stat().st_size:
            backup = path.with_name(f"{path.name}.backup-{uuid4().hex}")
            # sqlite backup API includes committed WAL content; never unlink/replace the source.
            with sqlite3.connect(str(path)) as source, sqlite3.connect(str(backup)) as target:
                source.backup(target)
            backup.chmod(0o600)
    engine, _ = create_database(url)
    try:
        with engine.begin() as connection:
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()
    return backup


if __name__ == "__main__":
    backup = upgrade_database(Settings().database_url)
    print("Migration tamamlandı." + (f" Yedek: {backup}" if backup else ""))
