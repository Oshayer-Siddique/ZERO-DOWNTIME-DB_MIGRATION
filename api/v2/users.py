from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Connection, text

from api.database import connection
from api.schemas import ModernUser, ModernUserInput
from api.stages import require_v2

router = APIRouter(prefix="/v2/users", tags=["Modern API v2"])
Database = Annotated[Connection, Depends(connection, scope="function")]


@router.get("", response_model=list[ModernUser])
def list_users(conn: Database):
    require_v2(conn)
    return conn.execute(text("SELECT first_name, last_name FROM users ORDER BY id")).mappings().all()


@router.post("", response_model=ModernUser, status_code=201)
def create_user(user: ModernUserInput, conn: Database):
    require_v2(conn)
    return conn.execute(
        text("""INSERT INTO users (first_name, last_name)
                VALUES (:first_name, :last_name) RETURNING first_name, last_name"""),
        user.model_dump(),
    ).mappings().one()

