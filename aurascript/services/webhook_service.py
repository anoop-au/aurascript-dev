"""
AuraScript — Outbound webhook delivery service.

Sends signed event payloads to a caller-supplied URL with:
- HMAC-SHA256 request signing (X-AuraScript-Signature header).
- 3 retry attempts with fixed delays [5, 15, 30] seconds.
- Fire-and-forget via asyncio.create_task (never blocks the pipeline).
- Full delivery logging for every attempt and final outcome.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from typing import Optional

import httpx
import structlog

from aurascript.config import settings
from aurascript.models.events import AnyEvent

logger = structlog.get_logger(__name__)

_RETRY_DELAYS = [5, 15, 30]   # seconds between attempts
_HTTP_TIMEOUT = 10.0           # seconds per request


class WebhookService:
    """Delivers signed event payloads to registered webhook URLs."""

    async def deliver(
        self,
        webhook_url: str,
        event: AnyEvent,
        job_id: str,
    ) -> None:
        """
        Fire-and-forget delivery: schedules the actual HTTP call as a
        background asyncio Task so it never blocks the pipeline.
        """
        asyncio.create_task(
            self._deliver_with_retry(webhook_url, event, job_id)
        )

    async def deliver_sync(
        self,
        webhook_url: str,
        event: AnyEvent,
        job_id: str,
    ) -> tuple[bool, Optional[int]]:
        """
        Synchronous (awaitable) delivery used by the webhook-test endpoint.

        Returns (success: bool, status_code: Optional[int]).
        """
        return await self._deliver_with_retry(webhook_url, event, job_id)

    async def _deliver_with_retry(
        self,
        webhook_url: str,
        event: AnyEvent,
        job_id: str,
    ) -> tuple[bool, Optional[int]]:
        """
        Attempt delivery up to 3 times with increasing delays.

        Returns (True, status_code) on success, (False, last_status_code) on failure.
        """
        payload = event.model_dump_json().encode()
        signature = self._sign(payload)
        headers = self._build_headers(job_id, event, signature)

        last_status: Optional[int] = None

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
                try:
                    response = await client.post(
                        webhook_url,
                        content=payload,
                        headers=headers,
                    )
                    last_status = response.status_code

                    if response.is_success:
                        logger.info(
                            "webhook_delivered",
                            job_id=job_id,
                            event_type=event.event_type,
                            url=webhook_url,
                            attempt=attempt,
                            status_code=last_status,
                        )
                        return True, last_status

                    logger.warning(
                        "webhook_non_2xx",
                        job_id=job_id,
                        event_type=event.event_type,
                        url=webhook_url,
                        attempt=attempt,
                        status_code=last_status,
                    )

                except httpx.RequestError as exc:
                    logger.warning(
                        "webhook_request_error",
                        job_id=job_id,
                        event_type=event.event_type,
                        url=webhook_url,
                        attempt=attempt,
                        error=str(exc),
                    )

                # Don't sleep after the final attempt.
                if attempt < len(_RETRY_DELAYS):
                    await asyncio.sleep(delay)

        logger.error(
            "webhook_all_attempts_failed",
            job_id=job_id,
            event_type=event.event_type,
            url=webhook_url,
            last_status_code=last_status,
        )
        return False, last_status

    @staticmethod
    def _sign(payload: bytes) -> str:
        digest = hmac.new(
            settings.WEBHOOK_SECRET.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={digest}"

    @staticmethod
    def _build_headers(
        job_id: str,
        event: AnyEvent,
        signature: str,
    ) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-AuraScript-Job-ID": job_id,
            "X-AuraScript-Event-Type": event.event_type,
            "X-AuraScript-Signature": signature,
            "X-AuraScript-Schema-Version": "1.1",
            "User-Agent": "AuraScript-Webhook/1.0",
        }
