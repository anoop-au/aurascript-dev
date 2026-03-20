"""
AuraScript — API key authentication, rate limiting, and webhook signature
verification.

Security design principles:
- Constant-time comparison for all secret checks (secrets.compare_digest).
- Error messages never reveal whether the key format was wrong or unknown.
- Rate-limit state is in-process only; restarting the server resets counters.
  For a production multi-process deployment, replace with Redis.

FastAPI note: Request injection only works reliably in TOP-LEVEL async functions,
NOT in class __call__ methods (FastAPI 0.115.x + Pydantic v2 limitation).
Both classes expose an as_dependency() method that returns a proper closure
suitable for use with Depends().
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
import time
from typing import Callable

from fastapi import HTTPException, Request, status

from aurascript.config import settings

logger = logging.getLogger(__name__)


# ── API Key Authentication ─────────────────────────────────────────────────────


class APIKeyAuth:
    """
    Validates the API key sent in the configured request header.

    Usage (production)::

        api_key: str = Depends(api_key_auth)   # module-level singleton dep

    Usage (tests, isolated state)::

        auth = APIKeyAuth()
        api_key: str = Depends(auth.as_dependency())
    """

    def __init__(self) -> None:
        self._header_name: str = settings.API_KEY_HEADER

    def is_valid(self, candidate: str) -> bool:
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

    def as_dependency(self) -> Callable:
        """Return a plain async function usable with FastAPI Depends()."""
        auth = self

        async def _dep(request: Request) -> str:
            raw_key = request.headers.get(auth._header_name, "")
            if not auth.is_valid(raw_key):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"error": "Unauthorized"},
                )
            return raw_key

        return _dep


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

    Usage (production)::

        _: None = Depends(rate_limiter)   # module-level singleton dep

    Usage (tests, isolated state)::

        limiter = RateLimiter()
        _: None = Depends(limiter.as_dependency())
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

    async def check(self, api_key: str) -> None:
        """Enforce rate limits for *api_key*. Raises 429 if limit exceeded."""
        if not api_key:
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

    def as_dependency(self) -> Callable:
        """Return a plain async function usable with FastAPI Depends()."""
        limiter = self

        async def _dep(request: Request) -> None:
            api_key = request.headers.get(settings.API_KEY_HEADER, "")
            await limiter.check(api_key)

        return _dep


# ── Module-level singletons and dependency functions ───────────────────────────
# FastAPI only injects Request correctly in top-level async functions, NOT inside
# class __call__ methods. Use as_dependency() closures everywhere.

_api_key_auth_instance = APIKeyAuth()
_rate_limiter_instance = RateLimiter()

# These are the actual FastAPI dependency callables used across all routers.
api_key_auth = _api_key_auth_instance.as_dependency()
rate_limiter = _rate_limiter_instance.as_dependency()


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
