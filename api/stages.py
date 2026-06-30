from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection, text

Stage = Literal["uninitialized", "initial", "expanded", "synchronized", "contracted"]
STAGES: dict[str | None, Stage] = {
    None: "uninitialized",
    "001": "initial",
    "002": "expanded",
    "003": "synchronized",
    "004": "contracted",
}
NEXT_REVISION = {None: "001", "001": "002", "002": "003", "003": "004"}
# Separate migration serialization from the lock used to drain legacy requests.
MIGRATION_LOCK = 74612001
LEGACY_LOCK = 74612002


class DemoStatus(BaseModel):
    stage: Stage
    revision: str | None
    v1_available: bool
    v2_available: bool
    v1_retired: bool
    next_stage: Stage | None
    can_migrate: bool
    can_retire_v1: bool
    controls_enabled: bool


def current_revision(conn: Connection) -> str | None:
    if conn.scalar(text("SELECT to_regclass('public.alembic_version')")) is None:
        return None
    revisions = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    if len(revisions) > 1 or (revisions and revisions[0] not in STAGES):
        raise HTTPException(409, "The database has an unsupported migration revision.")
    return revisions[0] if revisions else None


def status(conn: Connection, controls_enabled: bool) -> DemoStatus:
    revision = current_revision(conn)
    retired = bool(conn.scalar(text("SELECT v1_retired FROM demo_state WHERE id = 1"))) if revision else False
    next_revision = NEXT_REVISION.get(revision)
    return DemoStatus(
        stage=STAGES[revision],
        revision=revision,
        v1_available=revision in ("001", "002", "003") and not retired,
        v2_available=revision in ("003", "004"),
        v1_retired=retired,
        next_stage=STAGES[next_revision] if next_revision else None,
        can_migrate=controls_enabled and next_revision is not None and (revision != "003" or retired),
        can_retire_v1=controls_enabled and revision == "003" and not retired,
        controls_enabled=controls_enabled,
    )


def require_v1(conn: Connection) -> None:
    # Retirement takes the exclusive lock and waits for existing v1 requests.
    conn.execute(text("SELECT pg_advisory_xact_lock_shared(:key)"), {"key": LEGACY_LOCK})
    revision = current_revision(conn)
    if revision is None:
        raise HTTPException(409, "Initialize the database before using API v1.")
    if revision == "004" or conn.scalar(text("SELECT v1_retired FROM demo_state WHERE id = 1")):
        raise HTTPException(410, "API v1 has been retired. Use API v2.")


def require_v2(conn: Connection) -> None:
    if current_revision(conn) not in ("003", "004"):
        raise HTTPException(409, "Apply synchronization and backfill before using API v2.")

