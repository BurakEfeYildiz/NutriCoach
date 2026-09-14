from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def create_database(url: str):
    options = {}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if url in {"sqlite://", "sqlite:///:memory:"}:
            options["poolclass"] = StaticPool
    engine = create_engine(url, **options)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
