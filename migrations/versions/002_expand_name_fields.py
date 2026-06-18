"""Add the modern columns without changing the legacy schema."""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = depends_on = None


def upgrade():
    op.add_column("users", sa.Column("first_name", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.Text(), nullable=True))


def downgrade():
    raise RuntimeError("Forward-only demo. Use a fresh database to repeat the migration.")

