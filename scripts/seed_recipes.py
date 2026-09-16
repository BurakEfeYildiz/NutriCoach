"""Idempotently seed curated recipes from already imported structured USDA foods."""
from app.core.config import Settings
from app.db.database import create_database
from app.models import activity, auth, chat, food, memory, nutrition, recipe, user  # noqa: F401
from app.services.recipes import seed_curated


if __name__ == "__main__":
    engine, factory = create_database(Settings().database_url)
    try:
        with factory() as session:
            print(f"{seed_curated(session)} kaynak yiyeceklerden tarif eklendi.")
    finally:
        engine.dispose()
