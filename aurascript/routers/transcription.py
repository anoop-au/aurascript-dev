"""
AuraScript — HTTP transcription endpoints.

POST   /transcribe                  Upload audio, start job → 202
GET    /transcribe/status/{job_id}  Poll job status → 200
GET    /transcribe/result/{job_id}  Fetch final transcript → 200/202/422/404
DELETE /transcribe/{job_id}         Cancel a job → 200
POST   /transcribe/webhook-test     Test webhook delivery → 200
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)

from aurascript.config import settings
from aurascript.core.job_store import JobStatus, job_store
from aurascript.core.security import APIKeyAuth, RateLimiter
from aurascript.core.storage import SafeFileStorage
from aurascript.dependencies import (
    api_key_auth,
    rate_limiter,
    storage,
    webhook_service,
)
from aurascript.models.schemas import (
    JobResultResponse,
    JobStatusResponse,
    TranscribeResponse,
    WebhookTestRequest,
    WebhookTestResponse,
)
from aurascript.models.events import AgentDecisionEvent
from aurascript.services import pipeline
from aurascript.utils.cleanup import cleanup_job_files
from aurascript.utils.result_store import load_result

import datetime
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Transcription"])


# ── POST /transcribe ───────────────────────────────────────────────────────────


@router.post(
    "/transcribe",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TranscribeResponse,
    summary="Submit audio for transcription",
)
async def submit_transcription(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    language_hint: str = Form("auto", max_length=50),
    num_speakers: int = Form(2, ge=1, le=10),
    translate_to: Optional[str] = Form(None, max_length=50),
    webhook_url: Optional[str] = Form(None),
    api_key: str = Depends(api_key_auth),
    _rate: None = Depends(rate_limiter),
) -> TranscribeResponse:
    """
    Accept a multipart audio upload and enqueue it for transcription.

    Returns immediately with a 202 and URLs for WebSocket, polling, and result.
    The actual transcription runs asynchronously in the background.
    """
    logger.info("transcribe_request_received", language_hint=language_hint, translate_to=translate_to, num_speakers=num_speakers)

    # Create job record (also enforces MAX_CONCURRENT_JOBS → 503 if full).
    job = await job_store.create_job(
        language_hint=language_hint,
        num_speakers=num_speakers,
        webhook_url=webhook_url,
    )
    job_id = job.job_id

    try:
        # Save the upload (validates MIME + magic bytes, enforces 700MB limit).
        audio_path = await storage.save_upload(file, job_id)
        await job_store.update_job(job_id, file_paths=[audio_path])
    except HTTPException:
        # Cleanup the job record on upload failure.
        await job_store.cancel_job(job_id)
        raise

    # Launch the pipeline as a background task.
    background_tasks.add_task(
        pipeline.process_transcription_job,
        job_id=job_id,
        audio_path=audio_path,
        language_hint=language_hint,
        num_speakers=num_speakers,
        translate_to=translate_to,
        webhook_url=webhook_url,
        webhook_service=webhook_service,
    )

    ws_url = (
        f"{settings.websocket_base_url}/ws/transcribe/{job_id}"
        f"?token={api_key}"
    )
    poll_url = f"{settings.PRIMARY_DOMAIN}/transcribe/status/{job_id}"
    result_url = f"{settings.PRIMARY_DOMAIN}/transcribe/result/{job_id}"

    return TranscribeResponse(
        job_id=job_id,
        status="PENDING",
        websocket_url=ws_url,
        poll_url=poll_url,
        result_url=result_url,
        message=(
            "Job accepted. Connect to websocket_url for real-time progress, "
            "or poll poll_url every few seconds."
        ),
    )


# ── GET /transcribe/status/{job_id} ───────────────────────────────────────────


@router.get(
    "/transcribe/status/{job_id}",
    response_model=JobStatusResponse,
    summary="Poll job status",
)
async def get_job_status(
    job_id: str,
    _key: str = Depends(api_key_auth),
) -> JobStatusResponse:
    job = await job_store.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"Job {job_id!r} not found."},
        )

    # Rough completion estimate: ~25s per remaining chunk + 30s for stitching.
    estimated_completion: Optional[float] = None
    if job.status == JobStatus.PROCESSING and job.progress_percent < 100.0:
        remaining_progress = 100.0 - job.progress_percent
        estimated_completion = round((remaining_progress / 100.0) * 300.0, 1)

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status.value,
        progress_pct=job.progress_percent,
        current_stage=job.current_stage,
        created_at=job.created_at,
        updated_at=job.updated_at,
        estimated_completion_seconds=estimated_completion,
    )


# ── GET /transcribe/result/{job_id} ───────────────────────────────────────────


@router.get(
    "/transcribe/result/{job_id}",
    summary="Fetch final transcript",
)
async def get_job_result(
    job_id: str,
    _key: str = Depends(api_key_auth),
):
    job = await job_store.get_job(job_id)
    if job is None:
        # In-memory record evicted (TTL or restart) — try disk fallback.
        data = load_result(settings.RESULTS_DIR, job_id)
        if data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Job {job_id!r} not found."},
            )
        return JobResultResponse(
            job_id=data["job_id"],
            status="COMPLETED",
            transcript=data["transcript"],
            speaker_map=data["speaker_map"],
            metadata=data["metadata"],
        )

    if job.status == JobStatus.PROCESSING or job.status == JobStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail={
                "error": "Transcription in progress.",
                "progress_percent": job.progress_percent,
                "current_stage": job.current_stage,
            },
        )

    if job.status == JobStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": job.error_message or "Transcription failed.",
                "error_code": job.error_code,
            },
        )

    if job.status == JobStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"error": "Job was cancelled."},
        )

    return JobResultResponse(
        job_id=job.job_id,
        status=job.status.value,
        transcript=job.transcript or "",
        speaker_map=job.speaker_map or {},
        metadata=job.metadata or {},
    )


# ── DELETE /transcribe/{job_id} ───────────────────────────────────────────────


@router.delete(
    "/transcribe/{job_id}",
    summary="Cancel a transcription job",
)
async def cancel_job(
    job_id: str,
    _key: str = Depends(api_key_auth),
) -> dict:
    job = await job_store.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"Job {job_id!r} not found."},
        )

    cancelled = await job_store.cancel_job(job_id)

    # Clean up any files associated with the job immediately.
    all_paths = list(job.file_paths) + list(job.chunk_paths)
    if all_paths:
        await cleanup_job_files(all_paths)

    return {
        "job_id": job_id,
        "cancelled": cancelled,
        "message": "Job cancelled and files cleaned up." if cancelled
        else "Job could not be cancelled (already in terminal state).",
    }


# ── POST /transcribe/webhook-test ─────────────────────────────────────────────


@router.post(
    "/transcribe/webhook-test",
    response_model=WebhookTestResponse,
    summary="Test webhook delivery to a URL",
)
async def test_webhook(
    body: WebhookTestRequest,
    _key: str = Depends(api_key_auth),
) -> WebhookTestResponse:
    """
    Send a test payload to *webhook_url* so callers can verify their
    endpoint is reachable and correctly verifying the HMAC signature.
    """
    test_event = AgentDecisionEvent(
        job_id="webhook-test",
        timestamp=datetime.datetime.now(tz=datetime.timezone.utc),
        sequence=1,
        agent="AuraScript",
        decision="webhook_test",
        reason="This is a test delivery to verify your webhook endpoint.",
    )

    success, status_code = await webhook_service.deliver_sync(
        str(body.webhook_url), test_event, "webhook-test"
    )

    return WebhookTestResponse(
        delivered=success,
        status_code=status_code,
        message=(
            "Webhook delivered successfully."
            if success
            else f"Webhook delivery failed. Last status: {status_code}"
        ),
    )
