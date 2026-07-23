from threading import Lock
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Connection, text

from api.database import connection
from api.migration_runner import upgrade
from api.stages import (
    LEGACY_LOCK, MIGRATION_LOCK, NEXT_REVISION, DemoStatus, Stage, status,
)

router = APIRouter(prefix="/demo", tags=["Local demonstration"])
Database = Annotated[Connection, Depends(connection, scope="function")]
# Alembic uses process-global proxies: do not invoke it from concurrent threads.
_migration_mutex = Lock()


class AdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_stage: Stage


def require_controls(request: Request) -> None:
    if not request.app.state.demo_controls_enabled:
        raise HTTPException(403, "Migration controls are disabled. Enable them only for the local demo.")


def control_lock(conn: Connection) -> None:
    conn.execute(text("SET LOCAL lock_timeout = '5s'"))
    conn.execute(text("SET LOCAL statement_timeout = '30s'"))
    if not conn.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK}):
        raise HTTPException(409, "Another migration or retirement is in progress. Refresh the stage and retry.")


@router.get("/status", response_model=DemoStatus)
def get_status(request: Request, conn: Database):
    return status(conn, request.app.state.demo_controls_enabled)


@router.post("/migrations/next", response_model=DemoStatus, dependencies=[Depends(require_controls)])
def advance_migration(body: AdvanceRequest, conn: Database):
    if not _migration_mutex.acquire(blocking=False):
        raise HTTPException(409, "Another migration is in progress. Refresh the stage and retry.")
    try:
        control_lock(conn)
        before = status(conn, True)
        if body.expected_stage != before.stage:
            raise HTTPException(409, f"Stage changed: expected {body.expected_stage}, current {before.stage}.")
        if before.next_stage is None:
            raise HTTPException(409, "The migration is already complete.")
        if not before.can_migrate:
            raise HTTPException(409, "Retire API v1 before running the contract migration.")
        upgrade(conn, NEXT_REVISION[before.revision])
        return status(conn, True)
    finally:
        _migration_mutex.release()


@router.post("/v1/retire", response_model=DemoStatus, dependencies=[Depends(require_controls)])
def retire_v1(conn: Database):
    control_lock(conn)
    before = status(conn, True)
    if before.v1_retired:
        return before
    if before.revision != "003":
        raise HTTPException(409, "Synchronize and backfill the database before retiring API v1.")
    conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LEGACY_LOCK})
    conn.execute(text("UPDATE demo_state SET v1_retired = true WHERE id = 1"))
    return status(conn, True)

