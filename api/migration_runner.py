from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection

ROOT = Path(__file__).resolve().parent.parent


def alembic_config() -> Config:
    return Config(str(ROOT / "alembic.ini"))


def upgrade(conn: Connection, revision: str) -> None:
    config = alembic_config()
    config.attributes["connection"] = conn
    command.upgrade(config, revision)

