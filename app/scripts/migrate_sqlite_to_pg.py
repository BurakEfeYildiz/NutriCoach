"""Manual utility to migrate data from local SQLite database to Cloud SQL PostgreSQL.

Usage:
    python -m app.scripts.migrate_sqlite_to_pg --sqlite sqlite:///./nutricoach.db --pg postgresql://user:pass@host:5432/dbname [--dry-run]
"""
import argparse
import sys
from sqlalchemy import MetaData, Table, select

from app.db.database import Base, create_database
from app.db.migrate import require_current_schema
from app.db.types import Amount, UTCDateTime
from app.models import activity, auth, chat, food, memory, nutrition, recipe, user  # noqa: F401 - register metadata

TABLE_ORDER = [
    "users",
    "user_profiles",
    "auth_sessions",
    "foods",
    "food_aliases",
    "food_portions",
    "favorite_foods",
    "meals",
    "meal_items",
    "weight_logs",
    "daily_steps",
    "workouts",
    "recipes",
    "recipe_ingredients",
    "conversations",
    "messages",
    "ai_requests",
    "memories",
]


def normalize_source_row(table_name: str, row: dict, source_dialect) -> dict:
    """Convert SQLite's scaled amounts and naive UTC timestamps before PG insert."""
    model_table = Base.metadata.tables[table_name]
    normalized = dict(row)
    for name, value in normalized.items():
        column_type = model_table.c[name].type
        if value is not None and isinstance(column_type, (Amount, UTCDateTime)):
            normalized[name] = column_type.process_result_value(value, source_dialect)
    return normalized


def migrate_data(sqlite_url: str, pg_url: str, dry_run: bool = False):
    print(f"Connecting to source SQLite: {sqlite_url}")
    src_engine, _ = create_database(sqlite_url)

    # A source on an older revision can silently omit Product V2 columns/tables.
    require_current_schema(src_engine)

    print(f"Connecting to target PostgreSQL: {pg_url.split('@')[-1] if '@' in pg_url else pg_url}")
    tgt_engine, _ = create_database(pg_url)

    # Verify target PostgreSQL schema is at head
    try:
        require_current_schema(tgt_engine)
        print("Target PostgreSQL schema verified at head revision.")
    except Exception as e:
        print(f"ERROR: Target database schema check failed: {e}")
        print("Please run migrations on target database first: python -m app.db.migrate")
        sys.exit(1)

    src_meta = MetaData()
    src_meta.reflect(bind=src_engine)

    tgt_meta = MetaData()
    tgt_meta.reflect(bind=tgt_engine)

    total_rows = 0
    table_counts = {}

    with tgt_engine.begin() as tgt_conn:
        for tbl_name in TABLE_ORDER:
            if tbl_name not in src_meta.tables:
                print(f"Table '{tbl_name}' not present in source database. Skipping.")
                continue

            src_table: Table = src_meta.tables[tbl_name]
            tgt_table: Table = tgt_meta.tables[tbl_name]

            with src_engine.connect() as src_conn:
                rows = src_conn.execute(select(src_table)).mappings().all()

            if not rows:
                print(f"[{tbl_name}] 0 rows found.")
                continue

            print(f"[{tbl_name}] Transferring {len(rows)} rows...")

            insert_records = [normalize_source_row(tbl_name, row, src_engine.dialect) for row in rows]

            if not dry_run:
                tgt_conn.execute(tgt_table.insert(), insert_records)

            table_counts[tbl_name] = len(insert_records)
            total_rows += len(insert_records)

        if dry_run:
            print(f"\n[DRY RUN] {total_rows} total rows inspected. No changes committed.")
            tgt_conn.rollback()
        else:
            print(f"\n[SUCCESS] {total_rows} total rows successfully migrated to PostgreSQL.")
            tgt_conn.commit()

        return table_counts


def main():
    parser = argparse.ArgumentParser(description="Migrate NutriCoach SQLite database to PostgreSQL")
    parser.add_argument("--sqlite", default="sqlite:///./nutricoach.db", help="SQLite database URL")
    parser.add_argument("--pg", required=True, help="Target PostgreSQL database URL")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without committing changes")

    args = parser.parse_args()
    migrate_data(args.sqlite, args.pg, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
