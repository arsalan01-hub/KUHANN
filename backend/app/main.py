"""KUHHAN FastAPI application entry point."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.api.routes import apis, auth, listings, search, sources, system, users
from app.core.config import settings
from app.db.session import get_db
from app.services.bootstrap import run_bootstrap

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger("kuhhan.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        summary = run_bootstrap()
        logger.info("Bootstrap summary: %s", summary)
    except Exception:  # noqa: BLE001 - the API must still start so /health can report the fault
        logger.exception("Bootstrap failed")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="KUHHAN API",
        description=(
            "Truck search, website discovery and listing monitoring platform. "
            "KUHHAN is not a marketplace: listings belong to the original external websites."
        ),
        version=__version__,
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        lifespan=lifespan,
    )

    origins = settings.cors_origin_list
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Accept"],
        )

    @app.middleware("http")
    async def security_and_logging(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Cache-Control"] = "no-store"
        if request.url.path.startswith(settings.api_prefix) and request.url.path not in (
            f"{settings.api_prefix}/health",
        ):
            logger.info(
                "%s %s %s %sms", request.method, request.url.path, response.status_code, duration_ms
            )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(str(p) for p in error.get("loc", [])[1:]), "message": error.get("msg")}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "Please check the submitted values", "errors": details},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred. The incident has been logged."},
        )

    prefix = settings.api_prefix
    for router in (
        auth.router,
        users.router,
        sources.router,
        sources.discovery_router,
        apis.router,
        listings.router,
        search.router,
        system.router,
    ):
        app.include_router(router, prefix=prefix)

    @app.get(f"{prefix}/health", tags=["System"])
    def health(db: Session = Depends(get_db)) -> dict:
        database_ok = True
        error = None
        try:
            db.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001
            database_ok = False
            error = exc.__class__.__name__
        return {
            "status": "ok" if database_ok else "degraded",
            "database": database_ok,
            "database_error": error,
            "version": __version__,
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "name": "KUHHAN API",
            "docs": f"{prefix}/docs",
            "health": f"{prefix}/health",
        }

    return app


app = create_app()
