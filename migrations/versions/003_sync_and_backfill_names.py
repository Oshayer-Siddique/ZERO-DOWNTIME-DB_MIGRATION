"""Synchronize writes in both directions and backfill the legacy rows."""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = depends_on = None


def upgrade():
    op.execute(r"""
    CREATE FUNCTION normalize_user_name(value text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT AS $$
        SELECT btrim(regexp_replace(value, '[[:space:]]+', ' ', 'g'))
    $$
    """)
    op.execute(r"""
    CREATE FUNCTION synchronize_user_names() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE
        legacy_changed boolean;
        modern_changed boolean;
        legacy text;
        first_part text;
        last_part text;
        joined text;
    BEGIN
        legacy := normalize_user_name(NEW.full_name);
        first_part := normalize_user_name(NEW.first_name);
        last_part := normalize_user_name(NEW.last_name);
        joined := concat_ws(' ', first_part, nullif(last_part, ''));

        IF TG_OP = 'INSERT' THEN
            legacy_changed := NEW.full_name IS NOT NULL;
            modern_changed := NEW.first_name IS NOT NULL OR NEW.last_name IS NOT NULL;
        ELSE
            legacy_changed := NEW.full_name IS DISTINCT FROM OLD.full_name;
            modern_changed := NEW.first_name IS DISTINCT FROM OLD.first_name
                              OR NEW.last_name IS DISTINCT FROM OLD.last_name;

            -- Backfill derives fields from the unchanged legacy name. Preserve
            -- its original whitespace instead of rewriting the source column.
            IF NOT legacy_changed AND (OLD.first_name IS NULL OR OLD.last_name IS NULL)
               AND first_part IS NOT DISTINCT FROM split_part(legacy, ' ', 1)
               AND last_part IS NOT DISTINCT FROM
                   substr(legacy, length(split_part(legacy, ' ', 1)) + 2)
            THEN
                NEW.first_name := first_part;
                NEW.last_name := last_part;
                RETURN NEW;
            END IF;
        END IF;

        IF legacy_changed AND modern_changed THEN
            IF legacy IS NULL OR legacy = '' OR first_part IS NULL OR first_part = ''
               OR last_part IS NULL OR legacy IS DISTINCT FROM joined THEN
                RAISE EXCEPTION 'Conflicting or incomplete legacy and modern name fields.' USING ERRCODE = '23514';
            END IF;
            NEW.full_name := legacy;
            NEW.first_name := first_part;
            NEW.last_name := last_part;
        ELSIF legacy_changed THEN
            IF legacy IS NULL OR legacy = '' THEN
                RAISE EXCEPTION 'Full name must not be blank.' USING ERRCODE = '23514';
            END IF;
            NEW.full_name := legacy;
            NEW.first_name := split_part(legacy, ' ', 1);
            NEW.last_name := substr(legacy, length(NEW.first_name) + 2);
        ELSIF modern_changed THEN
            IF first_part IS NULL OR first_part = '' OR last_part IS NULL THEN
                RAISE EXCEPTION 'First name is required; last name must be a string.' USING ERRCODE = '23514';
            END IF;
            NEW.first_name := first_part;
            NEW.last_name := last_part;
            NEW.full_name := joined;
        ELSIF TG_OP = 'INSERT' THEN
            RAISE EXCEPTION 'Provide a legacy name or modern name fields.' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END;
    $$
    """)
    op.execute("""
    CREATE TRIGGER users_synchronize_names
    BEFORE INSERT OR UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION synchronize_user_names()
    """)
    op.execute("""
    UPDATE users SET
        first_name = split_part(normalize_user_name(full_name), ' ', 1),
        last_name = substr(normalize_user_name(full_name),
                           length(split_part(normalize_user_name(full_name), ' ', 1)) + 2)
    WHERE first_name IS NULL OR last_name IS NULL
    """)
    op.execute("""
    DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM users WHERE first_name IS NULL OR last_name IS NULL
                   OR normalize_user_name(first_name) = ''
                   OR normalize_user_name(full_name) IS DISTINCT FROM
                      concat_ws(' ', normalize_user_name(first_name), nullif(normalize_user_name(last_name), ''))) THEN
            RAISE EXCEPTION 'Name backfill is incomplete or inconsistent.';
        END IF;
    END $$
    """)


def downgrade():
    raise RuntimeError("Forward-only demo. Use a fresh database to repeat the migration.")

