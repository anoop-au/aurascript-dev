"""
AuraScript — WebSocket transcription event stream.

Endpoint: ws[s]://host/ws/transcribe/{job_id}?token=<api_key>&last_sequence=N

Authentication is performed BEFORE ws.accept() — an unauthenticated client
receives close code 1008 (Policy Violation) and the connection is never opened.

Reconnection: pass last_sequence=N to replay all events with sequence > N.
"""

from __future__ import annotations

import asyncio
import secrets
import logging

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from aurascript.config import settings
from aurascript.core.job_store import JobStatus, job_store
from aurascript.dependencies import connection_manager, event_bus

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/transcribe/{job_id}")
async def transcription_websocket(
    websocket: WebSocket,
    job_id: str,
    token: str = Query(..., description="API key for authentication"),
    last_sequence: int = Query(0, ge=0, description="Resume from this sequence number"),
) -> None:
    """
    Real-time event stream for a transcription job.

    The frontend connects immediately after receiving the 202 from POST /transcribe.
    Events are pushed as they are emitted by the pipeline agents.
    """
    log = logger.bind(job_id=job_id)

    # ── Authentication BEFORE accept ──────────────────────────────────────────
    # Constant-time comparison against every valid key.
    authenticated = any(
        secrets.compare_digest(token.encode(), key.encode())
        for key in settings.VALID_API_KEYS
    )
    if not authenticated:
        log.warning("websocket_auth_failed")
        await websocket.close(code=1008)
        return

    # ── Check job exists ──────────────────────────────────────────────────────
    job = await job_store.get_job(job_id)
    if job is None:
        await websocket.accept()
        await websocket.send_json({
            "event_type": "JOB_FAILED",
            "job_id": job_id,
            "error_code": "INTERNAL_ERROR",
            "error_message": f"Job {job_id!r} not found.",
        })
        await websocket.close(code=1008)
        return

    # ── Accept the connection ─────────────────────────────────────────────────
    await connection_manager.connect(job_id, websocket, last_sequence)
    log.info("websocket_accepted", last_sequence=last_sequence)

    # ── Serve already-terminal jobs immediately ───────────────────────────────
    if job.status == JobStatus.COMPLETED:
        history = await event_bus.replay_history(job_id, 0)
        terminal = next(
            (e for e in reversed(history) if e.event_type == "JOB_COMPLETE"), None
        )
        if terminal:
            await connection_manager.broadcast_to_job(job_id, terminal)
        await connection_manager.disconnect(job_id, websocket)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=1000)
        return

    if job.status == JobStatus.FAILED:
        history = await event_bus.replay_history(job_id, 0)
        terminal = next(
            (e for e in reversed(history) if e.event_type == "JOB_FAILED"), None
        )
        if terminal:
            await connection_manager.broadcast_to_job(job_id, terminal)
        await connection_manager.disconnect(job_id, websocket)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=1000)
        return

    # ── Main event loop + keepalive ───────────────────────────────────────────
    keepalive_task = asyncio.create_task(_keepalive(websocket, job_id))

    try:
        # event_bus.subscribe() raises KeyError if channel not yet created;
        # that can happen if the client connects before the pipeline starts.
        # Retry briefly to handle the race condition.
        for _ in range(10):
            try:
                async for event in event_bus.subscribe(job_id):
                    await connection_manager.broadcast_to_job(job_id, event)
                break  # generator exhausted (job done) — exit cleanly
            except KeyError:
                await asyncio.sleep(0.3)

    except WebSocketDisconnect:
        log.info("websocket_client_disconnected")

    except Exception as exc:
        log.error("websocket_loop_error", error=str(exc))

    finally:
        keepalive_task.cancel()
        await connection_manager.disconnect(job_id, websocket)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=1000)
        log.info("websocket_closed")


async def _keepalive(websocket: WebSocket, job_id: str) -> None:
    """
    Send a WebSocket ping every WS_PING_INTERVAL_SECONDS.
    Closes the connection if no pong is received within WS_PING_TIMEOUT_SECONDS.
    """
    log = logger.bind(job_id=job_id, component="keepalive")
    try:
        while True:
            await asyncio.sleep(settings.WS_PING_INTERVAL_SECONDS)
            if websocket.client_state != WebSocketState.CONNECTED:
                return
            try:
                await asyncio.wait_for(
                    websocket.send_bytes(b"ping"),
                    timeout=settings.WS_PING_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                log.warning("websocket_ping_timeout")
                await websocket.close(code=1001)
                return
            except Exception:
                return
    except asyncio.CancelledError:
        pass
