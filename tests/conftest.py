import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from api.database import database_url, make_engine
from api.main import create_app
from api.migration_runner import upgrade


@pytest.fixture
def engine():
    # Never reset the configured application's database. Each test owns a newly
    # created database, and only that generated database is removed afterward.
    url = make_url(os.environ.get("TEST_DATABASE_URL", database_url()))
    name = "migration_test_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    test_engine = make_engine(url.set(database=name))
    try:
        yield test_engine
    finally:
        test_engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def client(engine):
    with TestClient(create_app(engine, demo_controls_enabled=True)) as client:
        yield client


@pytest.fixture
def migrate(engine):
    def apply(revision):
        with engine.begin() as conn:
            upgrade(conn, revision)
    return apply

