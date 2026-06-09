import os
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Connection, create_engine
from sqlalchemy.engine import Engine


def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://migration_demo:local_demo_only@localhost:5432/migration_demo",
    )


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True)


def connection(request: Request) -> Iterator[Connection]:
    # Commit before the endpoint responds, and roll back any failed request.
    with request.app.state.engine.begin() as conn:
        yield conn

