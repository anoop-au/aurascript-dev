"""
AuraScript — In-memory job state machine.

Design decisions:
- All mutations go through asyncio.Lock to prevent race conditions.
- task_handle is stored so callers can cancel an in-flight asyncio.Task.
- MAX_CONCURRENT_JOBS is enforced at create time with HTTP 503.
- cleanup_expired_jobs() is called by a background task in main.py lifespan.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, status

from aurascript.config import settings

logger = logging.getLogger(__name__)


# ── Enums ──────────────────────────────────────────────────────────────────────


class JobStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ── Data Model ─────────────────────────────────────────────────────────────────


@dataclass
class JobRecord:
    job_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    language_hint: str
    num_speakers: int

    # Optional fields — populated as the job progresses.
    completed_at: Optional[datetime] = None
    webhook_url: Optional[str] = None

    # All paths accumulated during the job's lifecycle (upload + chunks).
    # Used for guaranteed cleanup regardless of success or failure.
    file_paths: list[Path] = field(default_factory=list)
    # Populated after chunking.
    chunk_paths: list[Path] = field(default_factory=list)

    # Final output.
    transcript: Optional[str] = None
    speaker_map: Optional[dict[str, str]] = None
    # languages_detected, confidence, word_count, processing_time, etc.
    metadata: Optional[dict] = None

    # Error information (set when status → FAILED).
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    # Progress tracking — updated by the pipeline as it runs.
    progress_percent: float = 0.0
    current_stage: str = "PENDING"

    # Handle to the running asyncio.Task. Stored so it can be cancelled.
    task_handle: Optional[asyncio.Task] = None


# ── Store ──────────────────────────────────────────────────────────────────────


class JobStore:
    """
    Thread-safe in-memory store for all active and recently completed jobs.

    A single asyncio.Lock guards all write operations. Reads are lock-free for
    performance; callers must treat returned JobRecord objects as snapshots.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def create_job(
        self,
        language_hint: str,
        num_speakers: int,
        webhook_url: Optional[str] = None,
    ) -> JobRecord:
        """
        Create a new job and return it.

        Raises HTTP 503 (with Retry-After: 30) if MAX_CONCURRENT_JOBS is
        already reached.
        """
        async with self._lock:
            processing_count = sum(
                1
                for j in self._jobs.values()
                if j.status == JobStatus.PROCESSING
            )
            if processing_count >= settings.MAX_CONCURRENT_JOBS:
                logger.warning(
                    "Job creation rejected: max concurrent jobs reached",
                    extra={"max": settings.MAX_CONCURRENT_JOBS},
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": "Server is at capacity. Please try again shortly."
                    },
                    headers={"Retry-After": "30"},
                )

            now = datetime.now(tz=timezone.utc)
            job_id = uuid4().hex
            record = JobRecord(
                job_id=job_id,
                status=JobStatus.PENDING,
                created_at=now,
                updated_at=now,
                language_hint=language_hint,
                num_speakers=num_speakers,
                webhook_url=webhook_url,
            )
            self._jobs[job_id] = record
            logger.info("Job created", extra={"job_id": job_id})
            return record

    async def update_job(self, job_id: str, **kwargs) -> JobRecord:
        """
        Apply *kwargs* as attribute updates on the JobRecord identified by
        *job_id* and refresh *updated_at*.

        Raises KeyError if *job_id* is unknown — callers should validate first.
        """
        async with self._lock:
            record = self._jobs[job_id]
            for key, value in kwargs.items():
                if not hasattr(record, key):
                    raise ValueError(
                        f"JobRecord has no attribute '{key}'"
                    )
                setattr(record, key, value)
            record.updated_at = datetime.now(tz=timezone.utc)
            if kwargs.get("status") in (
                JobStatus.COMPLETED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            ):
                record.completed_at = record.updated_at
            logger.debug(
                "Job updated",
                extra={"job_id": job_id, "changes": list(kwargs.keys())},
            )
            return record

    async def get_job(self, job_id: str) -> Optional[JobRecord]:
        """Return the JobRecord for *job_id*, or None if not found."""
        return self._jobs.get(job_id)

    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel an in-flight job.

        - Cancels the asyncio.Task if one is stored.
        - Sets status to CANCELLED.
        - Returns True if the job existed, False otherwise.
        """
        async with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return False
            if record.task_handle is not None and not record.task_handle.done():
                record.task_handle.cancel()
                logger.info(
                    "Cancelled asyncio task", extra={"job_id": job_id}
                )
            record.status = JobStatus.CANCELLED
            record.updated_at = datetime.now(tz=timezone.utc)
            record.completed_at = record.updated_at
            record.current_stage = "CANCELLED"
            logger.info("Job cancelled", extra={"job_id": job_id})
            return True

    async def cleanup_expired_jobs(self) -> int:
        """
        Remove jobs whose age exceeds JOB_TTL_SECONDS.

        Returns the number of jobs deleted.
        """
        now = datetime.now(tz=timezone.utc)
        expired_ids: list[str] = []

        async with self._lock:
            for job_id, record in self._jobs.items():
                age_seconds = (now - record.created_at).total_seconds()
                if age_seconds > settings.JOB_TTL_SECONDS:
                    expired_ids.append(job_id)

            for job_id in expired_ids:
                del self._jobs[job_id]

        if expired_ids:
            logger.info(
                "Expired jobs cleaned up",
                extra={"count": len(expired_ids), "ids": expired_ids},
            )
        return len(expired_ids)

    def get_stats(self) -> dict[str, int | float]:
        """
        Return a snapshot of job counts by status and average processing time
        for completed jobs.

        This is a synchronous read — no lock needed for a snapshot.
        """
        counts: dict[str, int] = {s.value: 0 for s in JobStatus}
        completed_durations: list[float] = []

        for record in self._jobs.values():
            counts[record.status.value] += 1
            if (
                record.status == JobStatus.COMPLETED
                and record.completed_at is not None
            ):
                completed_durations.append(
                    (record.completed_at - record.created_at).total_seconds()
                )

        avg_processing_seconds = (
            sum(completed_durations) / len(completed_durations)
            if completed_durations
            else 0.0
        )

        return {
            "total_jobs": len(self._jobs),
            **counts,
            "avg_completed_processing_seconds": round(avg_processing_seconds, 2),
        }


# Module-level singleton shared across all routers and services.
job_store = JobStore()
