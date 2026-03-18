"""
AuraScript — WebSocket connection manager.

Maintains a registry of active WebSocket connections per job_id.
Handles:
- Accepting new connections and replaying missed events on reconnect.
- Broadcasting events to all sockets for a job.
- Silently disconnecting dead sockets without affecting live ones.
"""

from __future__ import annotations

import logging

import structlog
from fastapi import WebSocket
from starlette.websockets import WebSocketState

from aurascript.models.events import AnyEvent
from aurascript.services.event_bus import EventBus

logger = structlog.get_logger(__name__)


class ConnectionManager:
    """
    Registry of active WebSocket connections keyed by job_id.

    Thread-safety note: FastAPI/Starlette WebSocket handlers run in a single
    asyncio event loop. The dict operations here are all atomic at the Python
    level, so no explicit lock is needed for the registry itself.
    """

    def __init__(self, bus: EventBus) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._bus = bus

    async def connect(
        self,
        job_id: str,
        ws: WebSocket,
        last_sequence: int = 0,
    ) -> None:
        """
        Accept *ws* and register it under *job_id*.

        If *last_sequence* > 0, immediately replay any cached events with
        sequence > last_sequence to this socket only (reconnection recovery).
        """
        await ws.accept()

        if job_id not in self._connections:
            self._connections[job_id] = set()
        self._connections[job_id].add(ws)

        logger.info(
            "websocket_connected",
            job_id=job_id,
            last_sequence=last_sequence,
            total_connections=len(self._connections[job_id]),
        )

        # Replay missed events for reconnecting clients.
        if last_sequence > 0:
            missed = await self._bus.replay_history(job_id, last_sequence)
            for event in missed:
                await self._send_to_socket(ws, event, job_id)
            if missed:
                logger.info(
                    "replayed_missed_events",
                    job_id=job_id,
                    count=len(missed),
                    from_sequence=last_sequence,
                )

    async def disconnect(self, job_id: str, ws: WebSocket) -> None:
        """Remove *ws* from the registry. Safe to call on already-removed sockets."""
        sockets = self._connections.get(job_id, set())
        sockets.discard(ws)
        if not sockets:
            self._connections.pop(job_id, None)
        logger.info(
            "websocket_disconnected",
            job_id=job_id,
            remaining=len(sockets),
        )

    async def broadcast_to_job(self, job_id: str, event: AnyEvent) -> None:
        """
        Send *event* to every active WebSocket registered for *job_id*.

        Failed sends are handled per-socket: one dead socket does not prevent
        delivery to the others. Dead sockets are disconnected automatically.
        """
        sockets = list(self._connections.get(job_id, set()))
        if not sockets:
            return

        payload = event.model_dump_json()
        dead: list[WebSocket] = []

        for ws in sockets:
            if not await self._send_to_socket(ws, event, job_id, payload):
                dead.append(ws)

        for ws in dead:
            await self.disconnect(job_id, ws)

    def get_active_connection_count(self, job_id: str) -> int:
        """Return the number of live WebSocket connections for *job_id*."""
        return len(self._connections.get(job_id, set()))

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _send_to_socket(
        self,
        ws: WebSocket,
        event: AnyEvent,
        job_id: str,
        payload: str | None = None,
    ) -> bool:
        """
        Send *event* to a single socket.

        Returns True on success, False on any error (connection closed, etc.).
        *payload* can be pre-serialised to avoid re-serialising per socket.
        """
        try:
            if ws.client_state != WebSocketState.CONNECTED:
                return False
            if payload is None:
                payload = event.model_dump_json()
            await ws.send_text(payload)
            return True
        except Exception as exc:
            logger.warning(
                "websocket_send_failed",
                job_id=job_id,
                event_type=event.event_type,
                error=str(exc),
            )
            return False
