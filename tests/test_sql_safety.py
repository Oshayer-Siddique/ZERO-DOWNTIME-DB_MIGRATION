import subprocess
import sys

import pytest

from scripts.check_migration_sql import compatibility_sql, violations


@pytest.mark.parametrize("sql", [
    "ALTER TABLE users ADD COLUMN first_name TEXT;",
    "-- DROP COLUMN full_name\nSELECT 1;",
    "/* DROP TABLE users; */ SELECT 1;",
    "SELECT 'DROP TABLE users';",
    'SELECT "DROP", "TABLE" FROM users;',
    "CREATE TRIGGER example BEFORE INSERT ON users FOR EACH ROW EXECUTE FUNCTION sync();",
])
def test_safe_sql(sql):
    assert violations(sql) == []


@pytest.mark.parametrize("sql", [
    "ALTER TABLE users DROP COLUMN full_name;",
    "alter table users drop full_name;",
    "DROP TABLE users;",
    "drop\n/* comment */ table users;",
    "ALTER TABLE users DROP /* nested /* inner */ outer */ COLUMN full_name;",
    "TRUNCATE users;",
    "TRUNCATE TABLE users;",
    "ALTER TABLE users RENAME COLUMN full_name TO name;",
    "ALTER TABLE users RENAME full_name TO name;",
    'ALTER TABLE "users" DROP "full_name";',
    "ALTER TABLE users ADD COLUMN extra text, DROP full_name;",
    "DO $$ BEGIN DROP TABLE users; END $$;",
    "DO $body$ BEGIN EXECUTE 'DROP ' || 'TABLE users'; END $body$;",
])
def test_unsafe_sql(sql):
    assert violations(sql)


def test_actual_compatibility_migrations_pass():
    sql = compatibility_sql()
    assert "ADD COLUMN first_name" in sql
    assert "CREATE TRIGGER" in sql
    assert "UPDATE users" in sql
    assert violations(sql) == []


def test_unsafe_cli_fails(tmp_path):
    path = tmp_path / "unsafe.sql"
    path.write_text("ALTER TABLE users DROP COLUMN full_name;")
    result = subprocess.run([sys.executable, "-m", "scripts.check_migration_sql", "--file", str(path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "Dangerous migration detected" in result.stderr

