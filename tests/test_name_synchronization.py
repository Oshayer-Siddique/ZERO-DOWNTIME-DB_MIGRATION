import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError


@pytest.mark.parametrize("sql,expected", [
    ("INSERT INTO users (full_name) VALUES ('  John  Smith  ')", ("John Smith", "John", "Smith")),
    ("INSERT INTO users (full_name) VALUES ('Alice')", ("Alice", "Alice", "")),
    ("INSERT INTO users (first_name, last_name) VALUES (' Mary Jane ', ' Watson ')", ("Mary Jane Watson", "Mary Jane", "Watson")),
    ("INSERT INTO users (first_name, last_name) VALUES ('Alice', '')", ("Alice", "Alice", "")),
    ("INSERT INTO users (full_name, first_name, last_name) VALUES ('John Smith', 'John', 'Smith')", ("John Smith", "John", "Smith")),
])
def test_insert_synchronization(engine, migrate, sql, expected):
    migrate("003")
    with engine.begin() as conn:
        conn.execute(text(sql))
        assert tuple(conn.execute(text("SELECT full_name, first_name, last_name FROM users")).one()) == expected


def test_update_synchronization(engine, migrate):
    migrate("003")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (full_name) VALUES ('John Smith')"))
        conn.execute(text("UPDATE users SET full_name = 'Mary Jane Watson'"))
        assert tuple(conn.execute(text("SELECT first_name, last_name FROM users")).one()) == ("Mary", "Jane Watson")
        conn.execute(text("UPDATE users SET first_name = 'Ada', last_name = 'Lovelace'"))
        assert conn.scalar(text("SELECT full_name FROM users")) == "Ada Lovelace"
        conn.execute(text("UPDATE users SET last_name = ''"))
        assert conn.scalar(text("SELECT full_name FROM users")) == "Ada"
        conn.execute(text("UPDATE users SET full_name = 'Alan Turing', first_name = 'Alan', last_name = 'Turing'"))
        assert conn.scalar(text("SELECT full_name FROM users")) == "Alan Turing"


@pytest.mark.parametrize("sql", [
    "INSERT INTO users (full_name, first_name, last_name) VALUES ('John Smith', 'Alice', 'Brown')",
    "INSERT INTO users (first_name) VALUES ('John')",
    "INSERT INTO users (first_name, last_name) VALUES ('  ', 'Smith')",
    "UPDATE users SET full_name = 'Alice Brown', first_name = 'Other'",
    "UPDATE users SET first_name = NULL",
    "UPDATE users SET last_name = NULL",
    "UPDATE users SET full_name = '  '",
])
def test_conflicting_or_incomplete_writes_roll_back(engine, migrate, sql):
    migrate("003")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (full_name) VALUES ('John Smith')"))
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(text(sql))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT full_name, first_name, last_name FROM users")).all() == [("John Smith", "John", "Smith")]


@pytest.mark.parametrize("first,last", [(None, None), ("John", None), (None, "Smith")])
def test_backfill_preserves_legacy_source(engine, migrate, first, last):
    migrate("002")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (full_name, first_name, last_name) VALUES ('  John\t Smith  ', :first, :last)"), {"first": first, "last": last})
        before = conn.execute(text("SELECT id, full_name, created_at FROM users")).one()
    migrate("003")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT id, full_name, created_at FROM users")).one() == before
        assert conn.execute(text("SELECT first_name, last_name FROM users")).one() == ("John", "Smith")


def test_contract_refuses_inconsistent_data_atomically(client, engine, migrate):
    migrate("003")
    with engine.begin() as conn:
        # Simulate corruption outside the API to test the contract precondition.
        conn.execute(text("ALTER TABLE users DISABLE TRIGGER users_synchronize_names"))
        conn.execute(text("INSERT INTO users (full_name, first_name, last_name) VALUES ('John Smith', 'Wrong', 'Name')"))
        conn.execute(text("ALTER TABLE users ENABLE TRIGGER users_synchronize_names"))
    assert client.post("/demo/v1/retire").status_code == 200
    response = client.post("/demo/migrations/next", json={"expected_stage": "synchronized"})
    assert response.status_code == 409
    assert "incomplete or inconsistent" in response.json()["detail"]
    assert client.get("/demo/status").json()["stage"] == "synchronized"
    assert "full_name" in {c["name"] for c in inspect(engine).get_columns("users")}



def test_inconsistent_expanded_data_prevents_enabling_v2(client, engine, migrate):
    migrate("002")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (full_name, first_name, last_name) VALUES ('John Smith', 'Wrong', 'Name')"))
    with pytest.raises(DBAPIError, match="incomplete or inconsistent"):
        migrate("003")
    assert client.get("/demo/status").json()["stage"] == "expanded"
    assert client.get("/v1/users").status_code == 200
    assert client.get("/v2/users").status_code == 409
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT to_regprocedure('synchronize_user_names()')")) is None
