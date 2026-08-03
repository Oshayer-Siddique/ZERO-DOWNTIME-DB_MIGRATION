from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import DBAPIError

from api.main import create_app
from api.stages import current_revision


def advance(client, stage):
    response = client.post("/demo/migrations/next", json={"expected_stage": stage})
    assert response.status_code == 200, response.text
    return response.json()


def test_complete_lifecycle(client, engine):
    before = client.get("/demo/status").json()
    assert before["stage"] == "uninitialized"
    assert not before["v1_available"] and not before["v2_available"]
    assert client.get("/v1/users").status_code == 409
    assert client.get("/v2/users").status_code == 409

    assert advance(client, "uninitialized")["stage"] == "initial"
    for name in ("John Smith", "Alice", "Mary Jane Watson"):
        response = client.post("/v1/users", json={"name": name})
        assert response.status_code == 201
        assert response.json() == {"name": name}
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (full_name) VALUES ('  Alan   Mathison  Turing  ')"))
        original = conn.execute(text("SELECT id, full_name, created_at FROM users ORDER BY id")).all()
    assert advance(client, "initial")["stage"] == "expanded"
    assert client.post("/v1/users", json={"name": "Grace Hopper"}).status_code == 201
    assert client.get("/v2/users").status_code == 409
    assert advance(client, "expanded")["stage"] == "synchronized"
    assert client.get("/v1/users").json()[:4] == [{"name": row.full_name} for row in original]
    assert client.get("/v2/users").json() == [
        {"first_name": "John", "last_name": "Smith"},
        {"first_name": "Alice", "last_name": ""},
        {"first_name": "Mary", "last_name": "Jane Watson"},
        {"first_name": "Alan", "last_name": "Mathison Turing"},
        {"first_name": "Grace", "last_name": "Hopper"},
    ]
    assert client.post("/v1/users", json={"name": "Katherine Johnson"}).status_code == 201
    assert client.get("/v2/users").json()[-1] == {"first_name": "Katherine", "last_name": "Johnson"}
    assert client.post("/v2/users", json={"first_name": "Ada", "last_name": "Lovelace"}).status_code == 201
    assert client.get("/v1/users").json()[-1] == {"name": "Ada Lovelace"}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT id, full_name, created_at FROM users ORDER BY id LIMIT 4")).all() == original
        preserved = conn.execute(text("SELECT id, first_name, last_name, created_at FROM users ORDER BY id")).all()

    refused = client.post("/demo/migrations/next", json={"expected_stage": "synchronized"})
    assert refused.status_code == 409
    assert "Retire" in refused.json()["detail"]
    assert client.post("/demo/v1/retire").json()["v1_retired"] is True
    assert client.get("/v1/users").status_code == 410
    assert client.post("/v1/users", json={"name": "Too Late"}).status_code == 410
    assert advance(client, "synchronized")["stage"] == "contracted"
    assert {c["name"] for c in inspect(engine).get_columns("users")} == {"id", "first_name", "last_name", "created_at"}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT id, first_name, last_name, created_at FROM users ORDER BY id")).all() == preserved
        assert conn.scalar(text("SELECT count(*) FROM pg_trigger WHERE tgname = 'users_synchronize_names'")) == 0
        assert conn.scalar(text("SELECT to_regprocedure('synchronize_user_names()')")) is None
        assert conn.scalar(text("SELECT to_regprocedure('normalize_user_name(text)')")) is None
    assert client.post("/v2/users", json={"first_name": "New", "last_name": "User"}).status_code == 201
    assert len(client.get("/v2/users").json()) == 8
    assert client.post("/demo/migrations/next", json={"expected_stage": "contracted"}).status_code == 409
    # Restarting the API does not reactivate retired routes.
    with TestClient(create_app(engine, demo_controls_enabled=True)) as restarted:
        assert restarted.get("/demo/status").json()["v1_retired"] is True
        assert restarted.get("/v1/users").status_code == 410
        assert restarted.get("/v2/users").status_code == 200


def test_direct_contract_is_gated_and_atomic(client, engine, migrate):
    migrate("003")
    assert client.post("/v1/users", json={"name": "John Smith"}).status_code == 201
    with pytest.raises(DBAPIError, match="Retire API v1"):
        migrate("004")
    with engine.connect() as conn:
        assert current_revision(conn) == "003"
    assert client.get("/v1/users").status_code == 200
    assert "full_name" in {c["name"] for c in inspect(engine).get_columns("users")}


def test_stage_controls_and_disabled_mode(client, engine):
    assert client.post("/demo/v1/retire").status_code == 409
    assert client.post("/demo/migrations/next", json={"expected_stage": "initial"}).status_code == 409
    assert client.post("/demo/migrations/next", json={"expected_stage": "anything"}).status_code == 422
    advance(client, "uninitialized")
    assert client.post("/demo/migrations/next", json={"expected_stage": "uninitialized"}).status_code == 409
    with TestClient(create_app(engine, demo_controls_enabled=False)) as disabled:
        assert disabled.get("/demo/status").json()["controls_enabled"] is False
        assert disabled.post("/demo/migrations/next", json={"expected_stage": "initial"}).status_code == 403
        assert disabled.post("/demo/v1/retire").status_code == 403
        assert disabled.get("/v1/users").status_code == 200


@pytest.mark.parametrize("version,payload", [
    ("v1", {"name": "  \t "}),
    ("v1", {"name": None}),
    ("v1", {"name": 123}),
    ("v1", {"name": "John", "first_name": "Other"}),
    ("v2", {"first_name": " ", "last_name": "Smith"}),
    ("v2", {"first_name": "John", "last_name": None}),
    ("v2", {"first_name": "John"}),
])
def test_invalid_requests_do_not_insert(client, engine, migrate, version, payload):
    migrate("003")
    assert client.post(f"/{version}/users", json=payload).status_code == 422
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM users")) == 0


def test_names_are_normalized_and_sql_is_parameterized(client, migrate):
    migrate("003")
    assert client.post("/v1/users", json={"name": "  John\t Smith  "}).json() == {"name": "John Smith"}
    assert client.post("/v2/users", json={"first_name": "  Mary Jane ", "last_name": "  Watson  "}).json() == {
        "first_name": "Mary Jane", "last_name": "Watson",
    }
    name = "Robert'); DROP TABLE users; --"
    assert client.post("/v1/users", json={"name": name}).json() == {"name": name}
    assert len(client.get("/v1/users").json()) == 3


@pytest.mark.parametrize("source,target,version,ddl", [
    ("001", "002", "v1", "ALTER TABLE users ADD COLUMN first_name"),
    ("002", "003", "v1", "CREATE TRIGGER users_synchronize_names"),
    ("003", "004", "v2", "ALTER TABLE users DROP COLUMN full_name"),
])
def test_requests_overlap_migration(client, engine, migrate, source, target, version, ddl):
    migrate(source)
    if target == "004":
        assert client.post("/demo/v1/retire").status_code == 200
    migration_locked = Event()
    release_migration = Event()

    def hold_after_ddl(conn, cursor, statement, parameters, context, executemany):
        if ddl in statement:
            migration_locked.set()
            if not release_migration.wait(8):
                raise AssertionError("Timed out coordinating the migration test")

    event.listen(engine, "after_cursor_execute", hold_after_ddl)
    payload = {"name": "During Migration"} if version == "v1" else {"first_name": "During", "last_name": "Migration"}
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            migration = pool.submit(migrate, target)
            try:
                assert migration_locked.wait(5)
                read = pool.submit(client.get, f"/{version}/users")
                write = pool.submit(client.post, f"/{version}/users", json=payload)
                # Observe an actual blocked API query in PostgreSQL while the DDL
                # transaction holds its lock. No sleep-based overlap assumption.
                deadline = monotonic() + 5
                with engine.connect() as monitor:
                    while monotonic() < deadline:
                        blocked = monitor.scalar(text("""
                            SELECT count(*) FROM pg_stat_activity
                            WHERE datname = current_database()
                            AND pid <> pg_backend_pid() AND wait_event_type = 'Lock'
                            AND (query LIKE 'SELECT %FROM users%' OR query LIKE 'INSERT INTO users%')
                        """))
                        monitor.commit()
                        if blocked:
                            break
                    else:
                        pytest.fail("No API request overlapped the migration lock")
            finally:
                release_migration.set()
            migration.result(timeout=10)
            assert read.result(timeout=10).status_code == 200
            assert write.result(timeout=10).status_code == 201
    finally:
        release_migration.set()
        event.remove(engine, "after_cursor_execute", hold_after_ddl)
    assert client.get(f"/{version}/users").json() == [payload]



def test_control_lock_rejects_competing_changes(client, engine, migrate):
    from api.stages import MIGRATION_LOCK

    migrate("003")
    with engine.begin() as blocker:
        blocker.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK})
        response = client.post("/demo/v1/retire")
        assert response.status_code == 409
        assert "in progress" in response.json()["detail"]
        response = client.post("/demo/migrations/next", json={"expected_stage": "synchronized"})
        assert response.status_code == 409
        assert "in progress" in response.json()["detail"]
        assert client.get("/v1/users").status_code == 200
    assert client.post("/demo/v1/retire").status_code == 200
    assert advance(client, "synchronized")["stage"] == "contracted"


def test_retirement_drains_inflight_legacy_write(client, engine, migrate):
    migrate("003")
    write_inflight = Event()
    release_write = Event()

    def hold_write(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO users (full_name)"):
            write_inflight.set()
            if not release_write.wait(8):
                raise AssertionError("Timed out coordinating legacy retirement")

    event.listen(engine, "after_cursor_execute", hold_write)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            write = pool.submit(client.post, "/v1/users", json={"name": "Last Legacy"})
            try:
                assert write_inflight.wait(5)
                retirement = pool.submit(client.post, "/demo/v1/retire")
                deadline = monotonic() + 5
                with engine.connect() as monitor:
                    while monotonic() < deadline:
                        waiting = monitor.scalar(text("""
                            SELECT count(*) FROM pg_stat_activity
                            WHERE datname = current_database() AND pid <> pg_backend_pid()
                            AND wait_event = 'advisory'
                        """))
                        monitor.commit()
                        if waiting:
                            break
                    else:
                        pytest.fail("Retirement did not wait for the active v1 request")
                assert client.get("/demo/status").json()["v1_retired"] is False
            finally:
                release_write.set()
            assert write.result(timeout=10).status_code == 201
            assert retirement.result(timeout=10).status_code == 200
    finally:
        release_write.set()
        event.remove(engine, "after_cursor_execute", hold_write)
    assert client.post("/v1/users", json={"name": "Rejected User"}).status_code == 410
    assert client.get("/v2/users").json() == [{"first_name": "Last", "last_name": "Legacy"}]


def test_alembic_cli_uses_configured_database(client, engine):
    import os
    import subprocess
    import sys

    env = {**os.environ, "DATABASE_URL": engine.url.render_as_string(hide_password=False)}

    def cli(target):
        return subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", target],
            env=env, capture_output=True, text=True, timeout=30,
        )

    for revision, stage in (("001", "initial"), ("002", "expanded"), ("003", "synchronized")):
        result = cli(revision)
        assert result.returncode == 0, result.stderr
        assert client.get("/demo/status").json()["stage"] == stage
    refused = cli("004")
    assert refused.returncode != 0
    assert "Retire API v1" in refused.stderr
    assert client.post("/demo/v1/retire").status_code == 200
    result = cli("004")
    assert result.returncode == 0, result.stderr
    assert client.get("/demo/status").json()["stage"] == "contracted"
