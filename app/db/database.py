from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def normalize_database_url(url: str) -> str:
    normalized = url
    if normalized.startswith("postgres://"):
        return normalized.replace("postgres://", "postgresql+psycopg2://", 1)
    if normalized.startswith("postgresql://") and "+" not in normalized.split("://")[0]:
        return normalized.replace("postgresql://", "postgresql+psycopg2://", 1)
    return normalized


def get_engine_options(url: str) -> dict:
    options = {}
    normalized_url = normalize_database_url(url)
    if normalized_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if normalized_url in {"sqlite://", "sqlite:///:memory:"}:
            options["poolclass"] = StaticPool
    else:
        # Production PostgreSQL connection pool parameters
        options["pool_pre_ping"] = True
        options["pool_recycle"] = 1800
        options["pool_size"] = 5
        options["max_overflow"] = 10
    return options


def create_database(url: str):
    normalized_url = normalize_database_url(url)
    options = get_engine_options(normalized_url)

    engine = create_engine(normalized_url, **options)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
