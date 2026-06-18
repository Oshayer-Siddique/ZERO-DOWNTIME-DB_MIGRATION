"""Create the legacy users schema and the local demo's retirement marker."""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("full_name ~ '[^[:space:]]'", name="users_full_name_not_blank"),
    )
    op.create_table(
        "demo_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("v1_retired", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("id = 1", name="demo_state_singleton"),
    )
    op.execute("INSERT INTO demo_state (id, v1_retired) VALUES (1, false)")


def downgrade():
    raise RuntimeError("Forward-only demo. Use a fresh database to repeat the migration.")

