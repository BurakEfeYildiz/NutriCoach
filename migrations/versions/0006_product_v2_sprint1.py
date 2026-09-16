"""Product V2 Sprint 1 personalization and nutrition plan snapshot."""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    columns = (
        sa.Column("goal_type", sa.String(20), nullable=True),
        sa.Column("training_frequency", sa.String(20), nullable=True),
        sa.Column("pace_percent_per_week", sa.Float(), nullable=True),
        sa.Column("pregnancy_or_breastfeeding", sa.Boolean(), nullable=True),
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bmr_kcal", sa.Integer(), nullable=True),
        sa.Column("estimated_expenditure_kcal", sa.Integer(), nullable=True),
        sa.Column("expenditure_source", sa.String(30), nullable=True),
        sa.Column("planned_rate_kg_per_week", sa.Float(), nullable=True),
        sa.Column("planned_eta_earliest", sa.Date(), nullable=True),
        sa.Column("planned_eta_latest", sa.Date(), nullable=True),
        sa.Column("eta_source", sa.String(30), nullable=True),
        sa.Column("plan_status", sa.String(40), nullable=True),
        sa.Column("plan_constraint_reason", sa.String(200), nullable=True),
        sa.Column("calculation_version", sa.String(30), nullable=True),
        sa.Column("targets_recalculated_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in columns:
        op.add_column("user_profiles", column)


def downgrade():
    with op.batch_alter_table("user_profiles") as batch:
        for name in (
            "targets_recalculated_at", "calculation_version", "plan_constraint_reason",
            "plan_status", "eta_source", "planned_eta_latest", "planned_eta_earliest",
            "planned_rate_kg_per_week", "expenditure_source", "estimated_expenditure_kcal",
            "bmr_kcal", "onboarding_completed_at", "pregnancy_or_breastfeeding",
            "pace_percent_per_week", "training_frequency", "goal_type",
        ):
            batch.drop_column(name)
