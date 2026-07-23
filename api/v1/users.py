from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Connection, text

from api.database import connection
from api.schemas import LegacyUser, LegacyUserInput
from api.stages import require_v1

router = APIRouter(prefix="/v1/users", tags=["Legacy API v1"])
Database = Annotated[Connection, Depends(connection, scope="function")]


@router.get("", response_model=list[LegacyUser])
def list_users(conn: Database):
    require_v1(conn)
    return conn.execute(text("SELECT full_name AS name FROM users ORDER BY id")).mappings().all()


@router.post("", response_model=LegacyUser, status_code=201)
def create_user(user: LegacyUserInput, conn: Database):
    require_v1(conn)
    return conn.execute(
        text("INSERT INTO users (full_name) VALUES (:name) RETURNING full_name AS name"),
        user.model_dump(),
    ).mappings().one()

