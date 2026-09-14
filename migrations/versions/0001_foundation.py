"""Frozen Phase 1 schema. Existing databases are validated before adoption."""
from alembic import op
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = depends_on = None


def foundation_metadata():
    metadata = sa.MetaData()
    sa.Table("users", metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(320), unique=True),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    sa.Table("user_profiles", metadata,
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("birth_date", sa.Date),
        sa.Column("biological_sex", sa.String(20)),
        sa.Column("height_cm", sa.Float),
        sa.Column("goal_weight_kg", sa.Float),
        sa.Column("activity_level", sa.String(30)),
        sa.Column("calorie_target", sa.Integer),
        sa.Column("protein_target_g", sa.Float),
        sa.Column("carb_target_g", sa.Float),
        sa.Column("fat_target_g", sa.Float),
        sa.Column("preferred_weekly_weight_change_kg", sa.Float),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *(sa.CheckConstraint(f"{f} IS NULL OR {f} > 0", name=f"ck_profile_{f}")
          for f in ("height_cm", "goal_weight_kg", "calorie_target")),
        *(sa.CheckConstraint(f"{f} IS NULL OR {f} >= 0", name=f"ck_profile_{f}")
          for f in ("protein_target_g", "carb_target_g", "fat_target_g")))
    return metadata


def upgrade():
    connection = op.get_bind()
    metadata = foundation_metadata()
    inspector = sa.inspect(connection)
    existing = set(inspector.get_table_names()) - {"alembic_version"}
    if not existing:
        metadata.create_all(connection)
        return
    if existing != set(metadata.tables):
        raise RuntimeError("Bilinmeyen/kısmi şema; Aşama 1 olarak benimsenmedi.")
    differences = compare_metadata(MigrationContext.configure(connection), metadata)
    if differences:
        raise RuntimeError("Mevcut şema Aşama 1 ile eşleşmiyor; veriler değiştirilmedi.")
    # Autogenerate CHECK ve PK farklarını her durumda tespit etmez.
    for table in metadata.sorted_tables:
        if inspector.get_pk_constraint(table.name)["constrained_columns"] != [c.name for c in table.primary_key]:
            raise RuntimeError("Aşama 1 primary key eşleşmiyor.")
        expected = {str(c.sqltext).replace(" ", "").lower() for c in table.constraints if isinstance(c, sa.CheckConstraint)}
        actual = {c["sqltext"].replace(" ", "").lower() for c in inspector.get_check_constraints(table.name)}
        if expected != actual:
            raise RuntimeError("Aşama 1 CHECK kısıtları eşleşmiyor.")
    if connection.dialect.name == "sqlite" and connection.exec_driver_sql("PRAGMA foreign_key_check").first():
        raise RuntimeError("Mevcut veritabanında foreign key ihlali var.")
    # Validated existing tables are kept intact; Alembic records this revision.


def downgrade():
    raise RuntimeError("Temel kullanıcı verileri otomatik olarak silinmez. Yedekten geri yükleyin.")
