"""
AuraScript — FastAPI application entry point.

Responsibilities:
- Lifespan: startup (dirs, Vertex AI init, orphan cleanup, periodic cleanup task)
         and shutdown (graceful task cancellation).
- Middleware stack: TrustedHost → CORS → Request ID injection.
- Exception handlers: validation errors, audio errors, generic 500s.
- Router inclusion: transcription, websocket, health.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from aurascript.config import settings
from aurascript.core.job_store import job_store
from aurascript.core.storage import SafeFileStorage
from aurascript.routers import health, transcription, websocket
from aurascript.services.audio_processor import AudioProcessingError

logger = structlog.get_logger(__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────────


async def _periodic_job_cleanup() -> None:
    """Background task: remove expired jobs every 5 minutes."""
    while True:
        await asyncio.sleep(300)
        try:
            deleted = await job_store.cleanup_expired_jobs()
            if deleted:
                logger.info("periodic_cleanup", jobs_deleted=deleted)
        except Exception as exc:
            logger.warning("periodic_cleanup_error", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # ── STARTUP ───────────────────────────────────────────────────────────────
    logger.info(
        "aurascript_starting",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )

    # Ensure temporary directories exist.
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    # Initialise Vertex AI (lazy — agents still init individually, but this
    # validates the credentials path at startup rather than at first request).
    try:
        import vertexai
        vertexai.init(
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        )
        logger.info("vertex_ai_initialized", project=settings.GOOGLE_CLOUD_PROJECT)
    except Exception as exc:
        logger.warning("vertex_ai_init_failed", error=str(exc))

    # Scan for orphaned temp files from a previous crash.
    storage = SafeFileStorage()
    orphans = await storage.scan_orphaned_files()
    if orphans:
        logger.warning(
            "startup_orphaned_files",
            count=len(orphans),
            paths=[str(p) for p in orphans],
        )

    cleanup_task = asyncio.create_task(_periodic_job_cleanup())

    yield

    # ── SHUTDOWN ──────────────────────────────────────────────────────────────
    cleanup_task.cancel()
    with suppress(asyncio.CancelledError):
        await cleanup_task
    logger.info("aurascript_stopped")


# ── Application ────────────────────────────────────────────────────────────────


app = FastAPI(
    title="AuraScript API",
    description=(
        "High-accuracy Manglish transcription powered by Gemini AI.\n\n"
        '"Your voice, every language, perfectly captured."'
    ),
    version=settings.APP_VERSION,
    # Disable interactive docs in production to reduce attack surface.
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)


# ── Middleware ─────────────────────────────────────────────────────────────────

# 1. TrustedHostMiddleware — reject requests with unexpected Host headers.
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "api.aurascript.au",        # primary API domain (config.PRIMARY_DOMAIN)
        "www.aurascript.au",
        "www.aurascript.store",
        "aurascript.au",
        "aurascript.store",
        "localhost",
        "127.0.0.1",
        "testclient",  # httpx TestClient host
    ],
)

# 2. CORSMiddleware — allow approved origins (Lovable + own domains).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-Job-ID", "Retry-After"],
    max_age=600,
)


# 3. Request ID Middleware — inject a unique X-Request-ID on every request.
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        # Bind to structlog context for this request.
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        structlog.contextvars.unbind_contextvars("request_id")
        return response


app.add_middleware(RequestIDMiddleware)


# ── Exception handlers ─────────────────────────────────────────────────────────


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return 422 with field-level error messages, never internal paths."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Request validation failed.",
            "details": [
                {
                    "field": ".".join(str(loc) for loc in err["loc"]),
                    "message": err["msg"],
                }
                for err in exc.errors()
            ],
        },
    )


@app.exception_handler(AudioProcessingError)
async def audio_processing_exception_handler(
    request: Request, exc: AudioProcessingError
) -> JSONResponse:
    """Map AudioProcessingError to 422 with a safe user-facing message."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": exc.message},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Catch-all: return 500 with request_id but NEVER expose internal details,
    stack traces, or file paths.
    """
    request_id = request.headers.get("X-Request-ID", "unknown")
    logger.error(
        "unhandled_exception",
        request_id=request_id,
        path=request.url.path,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "An unexpected error occurred.",
            "request_id": request_id,
        },
    )


# ── Routers ────────────────────────────────────────────────────────────────────


app.include_router(health.router)
app.include_router(transcription.router)
app.include_router(websocket.router)
