"""
AuraScript — Abstract base class for all pipeline agents.

All agents share:
- A reference to the EventBus so they can emit typed events.
- A _make_event() factory that auto-injects job_id and timestamp.
- An emit() helper that publishes to the bus (and thus fans out to WebSocket).
- A structlog logger bound with agent name and job_id.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import structlog

from aurascript.config import Settings
from aurascript.models.events import AnyEvent
from aurascript.services.event_bus import EventBus


class BaseAgent(ABC):
    """
    Abstract base for TranscriptionAgent, QualityAgent, StitcherAgent,
    and OrchestratorAgent.

    Subclasses implement `run()` with typed input/output dataclasses.
    """

    def __init__(
        self,
        job_id: str,
        event_bus: EventBus,
        settings: Settings,
    ) -> None:
        self.job_id = job_id
        self.event_bus = event_bus
        self.settings = settings
        self._sequence = 0
        self.logger = structlog.get_logger().bind(
            agent=self.__class__.__name__,
            job_id=job_id,
        )

    @abstractmethod
    async def run(self, input: Any) -> Any:
        """Execute this agent's task. Implemented by each subclass."""
        ...

    async def emit(self, event: AnyEvent) -> None:
        """Publish *event* to the event bus, which fans out to WebSocket clients."""
        await self.event_bus.publish(self.job_id, event)
        self.logger.debug("event_emitted", event_type=event.event_type)

    def _make_event(self, event_class: type, **kwargs: Any) -> AnyEvent:
        """
        Construct an event, injecting job_id and timestamp automatically.

        sequence is set to 0 here — the EventBus assigns the real value
        atomically on publish.
        """
        return event_class(
            job_id=self.job_id,
            timestamp=datetime.now(tz=timezone.utc),
            sequence=0,
            **kwargs,
        )
