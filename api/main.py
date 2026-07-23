import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from api.database import make_engine
from api.demo import router as demo_router
from api.v1.users import router as v1_router
from api.v2.users import router as v2_router

logger = logging.getLogger(__name__)


def create_app(engine: Engine | None = None, demo_controls_enabled: bool | None = None) -> FastAPI:
    owns_engine = engine is None
    engine = engine if engine is not None else make_engine()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        if owns_engine:
            app.state.engine.dispose()

    app = FastAPI(title="Zero-Downtime Migration Demo", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.demo_controls_enabled = (
        os.environ.get("DEMO_CONTROLS_ENABLED", "false").lower() == "true"
        if demo_controls_enabled is None else demo_controls_enabled
    )
    app.include_router(v1_router)
    app.include_router(v2_router)
    app.include_router(demo_router)

    @app.exception_handler(DBAPIError)
    async def database_error(request: Request, error: DBAPIError):
        code = getattr(error.orig, "sqlstate", None)
        if code in ("23514", "P0001"):
            diagnostic = getattr(error.orig, "diag", None)
            detail = getattr(diagnostic, "message_primary", None) or "Database validation failed."
            return JSONResponse(status_code=409, content={"detail": detail})
        if code in ("55P03", "57014"):
            return JSONResponse(status_code=409, content={"detail": "Database operation timed out. Refresh the stage and retry."})
        logger.error("Database request failed", exc_info=error)
        return JSONResponse(status_code=503, content={"detail": "Database operation failed. Check the API logs for the cause."})

    return app


app = create_app()

