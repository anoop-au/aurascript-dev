"""
AuraScript — Internal async pub/sub event bus.

Each transcription job gets its own channel (asyncio.Queue). The pipeline
publishes events; the WebSocket router subscribes and fans them out to clients.

Key features:
- Sequence counter per job for gap detection by frontend.
- Event history capped at WS_MAX_RECONNECT_HISTORY for reconnecting clients.
- Sentinel None on the queue cleanly terminates async generators.
- All mutations protected by asyncio.Lock.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator, Optional

import structlog

from aurascript.config import settings
from aurascript.models.events import AnyEvent, JobCompleteEvent, JobFailedEvent

logger = structlog.get_logger(__name__)


class EventBus:
    """
    In-process pub/sub bus.

    One channel per job_id. Channels are created before the pipeline starts
    and destroyed after cleanup.
    """

    def __init__(self) -> None:
        # Per-job event queue. None is the sentinel that ends subscribers.
        self._channels: dict[str, asyncio.Queue[AnyEvent | None]] = {}
        # Monotonically increasing sequence numbers per job.
        self._sequence_counters: dict[str, int] = {}
        # Capped event history per job for reconnection replay.
        self._event_history: dict[str, list[AnyEvent]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def create_channel(self, job_id: str) -> None:
        """
        Initialise a channel for *job_id*.

        Should be called once before any publish or subscribe calls for a job.
        Calling again for an existing job_id is a no-op (idempotent).
        """
        async with self._lock:
            if job_id not in self._channels:
                self._channels[job_id] = asyncio.Queue()
                self._sequence_counters[job_id] = 0
                self._event_history[job_id] = []
                logger.debug("channel_created", job_id=job_id)

    async def publish(self, job_id: str, event: AnyEvent) -> None:
        """
        Assign a sequence number to *event*, append to history, and enqueue.

        The sequence counter is incremented atomically under the lock.
        History is capped at WS_MAX_RECONNECT_HISTORY (oldest entries dropped).
        """
        async with self._lock:
            if job_id not in self._channels:
                logger.warning(
                    "publish_to_unknown_channel", job_id=job_id,
                    event_type=event.event_type,
                )
                return

            self._sequence_counters[job_id] += 1
            # Pydantic models are immutable by default; use model_copy to
            # set the sequence without mutating the original.
            event = event.model_copy(
                update={"sequence": self._sequence_counters[job_id]}
            )

            # Append to history and enforce cap.
            history = self._event_history[job_id]
            history.append(event)
            if len(history) > settings.WS_MAX_RECONNECT_HISTORY:
                self._event_history[job_id] = history[
                    -settings.WS_MAX_RECONNECT_HISTORY:
                ]

            await self._channels[job_id].put(event)

        logger.debug(
            "event_published",
            job_id=job_id,
            event_type=event.event_type,
            sequence=event.sequence,
        )

        # If this is a terminal event, enqueue the sentinel so subscribers
        # know to stop. Done outside the lock to avoid deadlock.
        if isinstance(event, (JobCompleteEvent, JobFailedEvent)):
            await self._channels[job_id].put(None)

    async def subscribe(
        self, job_id: str
    ) -> AsyncGenerator[AnyEvent, None]:
        """
        Async generator that yields events for *job_id* until the job ends.

        The generator stops (returns) when it receives the None sentinel,
        which is enqueued automatically after JOB_COMPLETE or JOB_FAILED.

        Raises KeyError if the channel has not been created.
        """
        if job_id not in self._channels:
            raise KeyError(f"No event channel for job_id={job_id!r}")

        queue = self._channels[job_id]
        while True:
            item = await queue.get()
            if item is None:
                # Terminal sentinel — job is done.
                return
            yield item

    async def replay_history(
        self, job_id: str, from_sequence: int
    ) -> list[AnyEvent]:
        """
        Return all cached events for *job_id* with sequence > *from_sequence*.

        Used when a WebSocket client reconnects after a temporary disconnect.
        Returns an empty list for unknown job_ids (safe, avoids 500 errors).
        """
        history = self._event_history.get(job_id, [])
        return [e for e in history if e.sequence > from_sequence]

    async def destroy_channel(self, job_id: str) -> None:
        """
        Tear down the channel for *job_id*.

        Enqueues a None sentinel so any active subscriber exits cleanly,
        then removes all state for the job.
        """
        async with self._lock:
            if job_id not in self._channels:
                return
            # Drain any remaining subscribers.
            await self._channels[job_id].put(None)
            del self._channels[job_id]
            del self._sequence_counters[job_id]
            del self._event_history[job_id]
            logger.debug("channel_destroyed", job_id=job_id)


# Module-level singleton.
_event_bus: Optional[EventBus] = None


def get_instance() -> EventBus:
    """Return the module-level EventBus singleton, creating it on first call."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


# Convenience alias for import.
event_bus = get_instance()
