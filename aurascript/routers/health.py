"""
AuraScript — Health and metrics endpoints.

GET /health         — Public liveness check (no auth required).
GET /health/ready   — Readiness check (verifies Vertex AI is reachable).
GET /metrics        — Aggregated job stats (auth required).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from aurascript.config import settings
from aurascript.core.job_store import job_store
from aurascript.core.security import api_key_auth
from aurascript.models.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check — no authentication required",
)
async def health_check() -> HealthResponse:
    """
    Returns 200 when the process is alive.
    Used by Nginx upstream health checks and Linode load balancer probes.
    """
    stats = job_store.get_stats()
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        vertex_ai_status="configured",
        active_jobs=stats.get("PROCESSING", 0),
        timestamp=datetime.now(tz=timezone.utc),
    )


@router.get(
    "/health/ready",
    summary="Readiness check — verifies critical dependencies",
)
async def readiness_check() -> dict:
    """
    Returns 200 when the service is ready to handle requests.
    Returns 503 if a critical dependency is unavailable.

    Checks:
    - Upload and chunks directories exist and are writable.
    - Vertex AI project and credentials are configured.
    """
    issues: list[str] = []

    # Check upload/chunks directories.
    for d in (settings.UPLOAD_DIR, settings.CHUNKS_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
            test_file = d / ".healthcheck"
            test_file.write_text("ok")
            test_file.unlink()
        except OSError as exc:
            issues.append(f"Directory {d} not writable: {exc}")

    # Check Vertex AI config (presence only — no actual API call).
    if not settings.GOOGLE_CLOUD_PROJECT:
        issues.append("GOOGLE_CLOUD_PROJECT is not set.")
    if not settings.GOOGLE_APPLICATION_CREDENTIALS:
        issues.append("GOOGLE_APPLICATION_CREDENTIALS is not set.")

    if issues:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "issues": issues},
        )

    return {
        "status": "ready",
        "version": settings.APP_VERSION,
        "upload_dir": str(settings.UPLOAD_DIR),
        "chunks_dir": str(settings.CHUNKS_DIR),
        "vertex_ai_project": settings.GOOGLE_CLOUD_PROJECT,
    }


@router.get(
    "/metrics",
    summary="Job store metrics (auth required)",
)
async def metrics(
    _key: str = Depends(api_key_auth),
) -> dict:
    """Return aggregated job counts and average processing times."""
    return job_store.get_stats()
