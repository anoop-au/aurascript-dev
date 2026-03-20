"""
AuraScript — Top-level job orchestration service.

This module bridges the HTTP layer and the agent layer. It:
1. Creates the EventBus channel for the job.
2. Updates JobRecord state as the pipeline progresses.
3. Delivers a webhook on job completion or failure (if configured).
4. Wraps OrchestratorAgent.run() so any unhandled exception marks the
   job FAILED rather than leaving it stuck in PROCESSING.

pipeline.process_transcription_job() is launched as a FastAPI BackgroundTask
so the HTTP 202 response returns immediately.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import structlog

from aurascript.agents.orchestrator import OrchestratorAgent, OrchestratorInput
from aurascript.config import settings
from aurascript.core.job_store import JobStatus, job_store
from aurascript.models.events import JobCompleteEvent, JobFailedEvent
from aurascript.services.event_bus import event_bus
from aurascript.services.webhook_service import WebhookService

logger = structlog.get_logger(__name__)


async def process_transcription_job(
    job_id: str,
    audio_path: Path,
    language_hint: str,
    num_speakers: int,
    webhook_url: str | None,
    webhook_service: WebhookService,
) -> None:
    """
    Run the full transcription pipeline for *job_id*.

    Designed to be launched as a FastAPI BackgroundTask. Updates job state,
    writes the final transcript to the JobRecord, and delivers webhooks.
    """
    log = logger.bind(job_id=job_id)

    # Create the EventBus channel before any agent can publish to it.
    await event_bus.create_channel(job_id)

    try:
        await job_store.update_job(
            job_id,
            status=JobStatus.PROCESSING,
            current_stage="ANALYZING",
        )

        orchestrator = OrchestratorAgent(
            job_id=job_id,
            event_bus=event_bus,
            settings=settings,
        )

        result = await orchestrator.run(
            OrchestratorInput(
                audio_path=audio_path,
                language_hint=language_hint,
                num_speakers=num_speakers,
            )
        )

        # Persist the transcript and mark COMPLETED.
        await job_store.update_job(
            job_id,
            status=JobStatus.COMPLETED,
            transcript=result.transcript,
            speaker_map=result.speaker_map,
            metadata=result.metadata,
            progress_percent=100.0,
            current_stage="COMPLETED",
        )
        log.info("pipeline_completed")

        # Deliver completion webhook if configured.
        if webhook_url:
            job = await job_store.get_job(job_id)
            if job:
                complete_event = JobCompleteEvent(
                    job_id=job_id,
                    timestamp=job.completed_at or __import__("datetime").datetime.now(
                        tz=__import__("datetime").timezone.utc
                    ),
                    sequence=0,
                    transcript=result.transcript,
                    speaker_map=result.speaker_map,
                    metadata=result.metadata,
                )
                await webhook_service.deliver(webhook_url, complete_event, job_id)

    except asyncio.CancelledError:
        log.info("pipeline_cancelled")
        await job_store.update_job(
            job_id,
            status=JobStatus.CANCELLED,
            current_stage="CANCELLED",
        )
        raise

    except Exception as exc:
        log.error("pipeline_unhandled_exception", error=str(exc))
        await job_store.update_job(
            job_id,
            status=JobStatus.FAILED,
            error_code="INTERNAL_ERROR",
            error_message=str(exc),
            current_stage="FAILED",
        )

        # Deliver failure webhook if configured.
        if webhook_url:
            fail_event = JobFailedEvent(
                job_id=job_id,
                timestamp=__import__("datetime").datetime.now(
                    tz=__import__("datetime").timezone.utc
                ),
                sequence=0,
                error_code="INTERNAL_ERROR",
                error_message="An internal error occurred. Please try again.",
                suggested_action="contact_support",
            )
            await webhook_service.deliver(webhook_url, fail_event, job_id)

    finally:
        # Tear down the EventBus channel once all subscribers have been
        # notified (JobComplete/Failed events close their generators).
        await asyncio.sleep(2)  # brief grace period for slow subscribers
        await event_bus.destroy_channel(job_id)
