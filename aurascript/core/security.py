"""
AuraScript — API key authentication, rate limiting, and webhook signature
verification.

Security design principles:
- Constant-time comparison for all secret checks (secrets.compare_digest).
- Error messages never reveal whether the key format was wrong or unknown.
- Rate-limit state is in-process only; restarting the server resets counters.
  For a production multi-process deployment, replace with Redis.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from aurascript.config import settings

logger = logging.getLogger(__name__)


# ── API Key Authentication ─────────────────────────────────────────────────────


class APIKeyAuth:
    """
    FastAPI dependency that validates the API key sent in the configured
    request header (default: X-API-Key).

    Usage::

        @router.post("/transcribe")
        async def transcribe(api_key: str = Depends(api_key_auth)):
            ...
    """

    def __init__(self) -> None:
        self._header_name: str = settings.API_KEY_HEADER

    async def __call__(self, request: Request) -> str:
        raw_key = request.headers.get(self._header_name, "")
        if not self._is_valid(raw_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "Unauthorized"},
            )
        return raw_key

    def _is_valid(self, candidate: str) -> bool:
        """
        Check *candidate* against every configured API key using constant-time
        comparison. Returns True as soon as one match is found.

        The loop over all valid keys is intentional: secrets.compare_digest
        requires both arguments to be the same type and prevents short-circuit
        leakage, but we must also avoid exposing the number of keys via timing.
        """
        if not candidate:
            return False
        matched = False
        for valid_key in settings.VALID_API_KEYS:
            if secrets.compare_digest(
                candidate.encode("utf-8"), valid_key.encode("utf-8")
            ):
                matched = True
        return matched


# Module-level singleton — reuse across requests so rate-limit state persists.
api_key_auth = APIKeyAuth()


# ── Rate Limiter ───────────────────────────────────────────────────────────────


class _KeyBucket:
    """Per-API-key sliding window counters protected by an asyncio.Lock."""

    __slots__ = ("lock", "minute_timestamps", "day_timestamps")

    def __init__(self) -> None:
        self.lock: asyncio.Lock = asyncio.Lock()
        self.minute_timestamps: list[float] = []
        self.day_timestamps: list[float] = []


class RateLimiter:
    """
    Dual sliding-window rate limiter.

    - Per-minute window: burst protection.
    - Per-day window: cost control.

    Counters are per API key and stored in memory. Restarting the process
    resets all counters. Buckets are created lazily on first use.

    Usage::

        @router.post("/transcribe")
        async def transcribe(
            api_key: str = Depends(api_key_auth),
            _: None = Depends(rate_limiter),
        ): ...
    """

    def __init__(self) -> None:
        self._buckets: dict[str, _KeyBucket] = {}
        self._buckets_lock: asyncio.Lock = asyncio.Lock()

    async def _get_bucket(self, api_key: str) -> _KeyBucket:
        """Return existing bucket or create one, thread-safely."""
        async with self._buckets_lock:
            if api_key not in self._buckets:
                self._buckets[api_key] = _KeyBucket()
            return self._buckets[api_key]

    async def __call__(self, request: Request) -> None:
        api_key = request.headers.get(settings.API_KEY_HEADER, "")
        if not api_key:
            # Auth dependency runs first; if we're here without a key it's an
            # unusual path. Let auth handle the 401.
            return

        bucket = await self._get_bucket(api_key)
        now = time.monotonic()
        minute_window_start = now - 60.0
        day_window_start = now - 86400.0

        async with bucket.lock:
            # Prune expired timestamps.
            bucket.minute_timestamps = [
                t for t in bucket.minute_timestamps if t > minute_window_start
            ]
            bucket.day_timestamps = [
                t for t in bucket.day_timestamps if t > day_window_start
            ]

            minute_count = len(bucket.minute_timestamps)
            day_count = len(bucket.day_timestamps)

            # Check per-day limit first (more informative message).
            if day_count >= settings.MAX_REQUESTS_PER_DAY:
                logger.warning(
                    "Daily rate limit exceeded",
                    extra={"api_key_prefix": api_key[:8]},
                )
                seconds_until_reset = int(
                    bucket.day_timestamps[0] + 86400.0 - now
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "Daily request limit reached. "
                        f"Resets in {seconds_until_reset} seconds."
                    },
                    headers={"Retry-After": str(max(seconds_until_reset, 1))},
                )

            # Check per-minute limit.
            if minute_count >= settings.MAX_REQUESTS_PER_MINUTE:
                logger.warning(
                    "Per-minute rate limit exceeded",
                    extra={"api_key_prefix": api_key[:8]},
                )
                seconds_until_reset = int(
                    bucket.minute_timestamps[0] + 60.0 - now
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={"error": "Too many requests. Try again shortly."},
                    headers={"Retry-After": str(max(seconds_until_reset, 1))},
                )

            # Record this request.
            bucket.minute_timestamps.append(now)
            bucket.day_timestamps.append(now)

    async def reset_key(self, api_key: str) -> None:
        """Clear all rate-limit counters for *api_key*. Admin use only."""
        bucket = await self._get_bucket(api_key)
        async with bucket.lock:
            bucket.minute_timestamps.clear()
            bucket.day_timestamps.clear()
        logger.info("Rate limit counters reset", extra={"api_key_prefix": api_key[:8]})

    def get_usage_stats(self, api_key: str) -> dict[str, int | float]:
        """
        Return current usage statistics for *api_key*.

        Returns zeroes for unknown keys (safe to expose — no info leakage).
        """
        bucket = self._buckets.get(api_key)
        if bucket is None:
            return {
                "requests_last_minute": 0,
                "requests_today": 0,
                "limit_per_minute": settings.MAX_REQUESTS_PER_MINUTE,
                "limit_per_day": settings.MAX_REQUESTS_PER_DAY,
                "remaining_minute": settings.MAX_REQUESTS_PER_MINUTE,
                "remaining_day": settings.MAX_REQUESTS_PER_DAY,
            }
        now = time.monotonic()
        minute_count = sum(
            1 for t in bucket.minute_timestamps if t > now - 60.0
        )
        day_count = sum(
            1 for t in bucket.day_timestamps if t > now - 86400.0
        )
        return {
            "requests_last_minute": minute_count,
            "requests_today": day_count,
            "limit_per_minute": settings.MAX_REQUESTS_PER_MINUTE,
            "limit_per_day": settings.MAX_REQUESTS_PER_DAY,
            "remaining_minute": max(
                0, settings.MAX_REQUESTS_PER_MINUTE - minute_count
            ),
            "remaining_day": max(
                0, settings.MAX_REQUESTS_PER_DAY - day_count
            ),
        }


# Module-level singleton.
rate_limiter = RateLimiter()


# ── Webhook Signature Verification ────────────────────────────────────────────


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify an inbound webhook payload against the HMAC-SHA256 signature.

    The expected signature format is ``sha256=<hex_digest>`` (same convention
    as GitHub webhooks). Pass the raw ``X-Webhook-Signature`` header value as
    *signature*.

    Returns True if authentic, False otherwise.
    Never raises — callers must check the return value.
    """
    try:
        prefix, received_hex = signature.split("=", 1)
        if prefix != "sha256":
            return False
    except ValueError:
        return False

    expected_hex = hmac.new(
        settings.WEBHOOK_SECRET.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return secrets.compare_digest(expected_hex, received_hex)
