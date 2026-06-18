from alembic import context
from sqlalchemy import text

from api.database import database_url, make_engine
from api.stages import MIGRATION_LOCK

config = context.config


def run(connection):
    context.configure(connection=connection, target_metadata=None, transaction_per_migration=False)
    with context.begin_transaction():
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("SET LOCAL statement_timeout = '30s'"))
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK})
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=database_url(), target_metadata=None, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        run(supplied_connection)
    else:
        engine = make_engine()
        try:
            with engine.connect() as connection:
                run(connection)
        finally:
            engine.dispose()

