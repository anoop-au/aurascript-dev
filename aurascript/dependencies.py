"""
AuraScript — Shared FastAPI dependency instances.

Import these singletons in routers instead of constructing new objects
per request. This ensures rate-limit counters, job state, WebSocket
connections, and the event bus all share a single in-process state.
"""

from __future__ import annotations

from aurascript.core.connection_manager import ConnectionManager
from aurascript.core.job_store import job_store
from aurascript.core.security import api_key_auth, rate_limiter
from aurascript.core.storage import SafeFileStorage
from aurascript.services.event_bus import event_bus
from aurascript.services.webhook_service import WebhookService

# Re-export singletons for clean imports in routers.
__all__ = [
    "api_key_auth",
    "rate_limiter",
    "job_store",
    "event_bus",
    "storage",
    "connection_manager",
    "webhook_service",
]

storage = SafeFileStorage()
connection_manager = ConnectionManager(bus=event_bus)
webhook_service = WebhookService()
