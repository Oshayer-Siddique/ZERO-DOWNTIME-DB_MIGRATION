"""Remove the old name only after the legacy API has been retired."""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = depends_on = None


def upgrade():
    op.execute("SELECT pg_advisory_xact_lock(74612002)")
    op.execute("""
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM demo_state WHERE id = 1 AND v1_retired) THEN
            RAISE EXCEPTION 'Retire API v1 before running the contract migration.';
        END IF;
        IF EXISTS (SELECT 1 FROM users WHERE first_name IS NULL OR last_name IS NULL
                   OR normalize_user_name(first_name) = ''
                   OR normalize_user_name(full_name) IS DISTINCT FROM
                      concat_ws(' ', normalize_user_name(first_name), nullif(normalize_user_name(last_name), ''))) THEN
            RAISE EXCEPTION 'Name backfill is incomplete or inconsistent. Contract refused.';
        END IF;
    END $$
    """)
    op.execute("DROP TRIGGER users_synchronize_names ON users")
    op.execute("DROP FUNCTION synchronize_user_names()")
    op.execute("DROP FUNCTION normalize_user_name(text)")
    op.drop_column("users", "full_name")
    op.alter_column("users", "first_name", existing_type=sa.Text(), nullable=False)
    op.alter_column("users", "last_name", existing_type=sa.Text(), nullable=False)
    op.create_check_constraint("users_first_name_not_blank", "users", "first_name ~ '[^[:space:]]'")


def downgrade():
    raise RuntimeError("Contract is forward-only. The legacy representation has been removed.")
