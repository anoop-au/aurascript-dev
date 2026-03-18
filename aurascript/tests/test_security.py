"""
AuraScript — Security layer tests.

Covers:
- Valid API key → 200
- Invalid API key → 401 (body must not leak key/token hints)
- Per-minute rate limit → 429 after MAX_REQUESTS_PER_MINUTE+1 calls
- Per-day rate limit → 429 after MAX_REQUESTS_PER_DAY+1 calls
- 429 responses include Retry-After header
- Webhook signature valid → True
- Webhook signature tampered → False
- Error responses never contain stack traces or internal file paths
"""

from __future__ import annotations

import hashlib
import hmac
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from aurascript.config import settings
from aurascript.core.security import (
    APIKeyAuth,
    RateLimiter,
    verify_webhook_signature,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _sign_payload(payload: bytes, secret: str) -> str:
    """Produce a valid sha256=<hex> signature for *payload*."""
    digest = hmac.new(
        secret.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()
    return f"sha256={digest}"


def _build_app(auth: APIKeyAuth, limiter: RateLimiter) -> FastAPI:
    from fastapi import Depends

    app = FastAPI()

    @app.get("/protected")
    async def protected(
        api_key: str = Depends(auth),
        _: None = Depends(limiter),
    ) -> dict:
        return {"status": "ok"}

    return app


async def _make_client(auth: APIKeyAuth, limiter: RateLimiter) -> AsyncClient:
    app = _build_app(auth, limiter)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── Authentication tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_valid_api_key_returns_200() -> None:
    auth = APIKeyAuth()
    limiter = RateLimiter()
    async with await _make_client(auth, limiter) as client:
        resp = await client.get(
            "/protected",
            headers={"X-API-Key": "test-api-key-aaaa1111"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_invalid_api_key_returns_401() -> None:
    auth = APIKeyAuth()
    limiter = RateLimiter()
    async with await _make_client(auth, limiter) as client:
        resp = await client.get(
            "/protected",
            headers={"X-API-Key": "not-a-real-key"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_api_key_returns_401() -> None:
    auth = APIKeyAuth()
    limiter = RateLimiter()
    async with await _make_client(auth, limiter) as client:
        resp = await client.get("/protected")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_401_body_does_not_leak_key_or_token() -> None:
    """
    The 401 response body must never contain the words 'key' or 'token'
    so that attackers cannot distinguish between wrong-format and wrong-value.
    """
    auth = APIKeyAuth()
    limiter = RateLimiter()
    async with await _make_client(auth, limiter) as client:
        resp = await client.get(
            "/protected",
            headers={"X-API-Key": "wrong"},
        )
    assert resp.status_code == 401
    body_lower = resp.text.lower()
    assert "key" not in body_lower
    assert "token" not in body_lower


@pytest.mark.asyncio
async def test_401_body_contains_no_stack_trace() -> None:
    auth = APIKeyAuth()
    limiter = RateLimiter()
    async with await _make_client(auth, limiter) as client:
        resp = await client.get(
            "/protected",
            headers={"X-API-Key": "wrong"},
        )
    body_lower = resp.text.lower()
    assert "traceback" not in body_lower
    assert "aurascript" not in body_lower  # no internal paths


# ── Rate limiting — per minute ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_per_minute_rate_limit_triggers_429() -> None:
    """Send MAX_REQUESTS_PER_MINUTE+1 requests; the last one must be 429."""
    auth = APIKeyAuth()
    limiter = RateLimiter()
    # Set a small limit so the test runs fast.
    original_minute_limit = settings.MAX_REQUESTS_PER_MINUTE
    settings.MAX_REQUESTS_PER_MINUTE = 3

    try:
        async with await _make_client(auth, limiter) as client:
            headers = {"X-API-Key": "test-api-key-aaaa1111"}
            responses = []
            for _ in range(settings.MAX_REQUESTS_PER_MINUTE + 1):
                r = await client.get("/protected", headers=headers)
                responses.append(r.status_code)

        assert responses[-1] == 429
        assert all(s == 200 for s in responses[:-1])
    finally:
        settings.MAX_REQUESTS_PER_MINUTE = original_minute_limit


@pytest.mark.asyncio
async def test_per_minute_429_includes_retry_after_header() -> None:
    auth = APIKeyAuth()
    limiter = RateLimiter()
    settings.MAX_REQUESTS_PER_MINUTE = 2

    try:
        async with await _make_client(auth, limiter) as client:
            headers = {"X-API-Key": "test-api-key-aaaa1111"}
            last_resp = None
            for _ in range(settings.MAX_REQUESTS_PER_MINUTE + 1):
                last_resp = await client.get("/protected", headers=headers)

        assert last_resp is not None
        assert last_resp.status_code == 429
        assert "retry-after" in last_resp.headers
        assert int(last_resp.headers["retry-after"]) >= 1
    finally:
        settings.MAX_REQUESTS_PER_MINUTE = 10


# ── Rate limiting — per day ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_per_day_rate_limit_triggers_429() -> None:
    """Send MAX_REQUESTS_PER_DAY+1 requests; the last one must be 429."""
    auth = APIKeyAuth()
    limiter = RateLimiter()
    # Set a very small daily limit and disable per-minute limit for this test.
    settings.MAX_REQUESTS_PER_DAY = 3
    settings.MAX_REQUESTS_PER_MINUTE = 1000

    try:
        async with await _make_client(auth, limiter) as client:
            headers = {"X-API-Key": "test-api-key-aaaa1111"}
            responses = []
            for _ in range(settings.MAX_REQUESTS_PER_DAY + 1):
                r = await client.get("/protected", headers=headers)
                responses.append(r.status_code)

        assert responses[-1] == 429
    finally:
        settings.MAX_REQUESTS_PER_DAY = 200
        settings.MAX_REQUESTS_PER_MINUTE = 10


@pytest.mark.asyncio
async def test_per_day_429_includes_retry_after_header() -> None:
    auth = APIKeyAuth()
    limiter = RateLimiter()
    settings.MAX_REQUESTS_PER_DAY = 2
    settings.MAX_REQUESTS_PER_MINUTE = 1000

    try:
        async with await _make_client(auth, limiter) as client:
            headers = {"X-API-Key": "test-api-key-aaaa1111"}
            last_resp = None
            for _ in range(settings.MAX_REQUESTS_PER_DAY + 1):
                last_resp = await client.get("/protected", headers=headers)

        assert last_resp is not None
        assert last_resp.status_code == 429
        assert "retry-after" in last_resp.headers
        assert int(last_resp.headers["retry-after"]) >= 1
    finally:
        settings.MAX_REQUESTS_PER_DAY = 200
        settings.MAX_REQUESTS_PER_MINUTE = 10


# ── Webhook signature verification ────────────────────────────────────────────


def test_valid_webhook_signature_returns_true() -> None:
    payload = b'{"event": "job.complete", "job_id": "abc123"}'
    signature = _sign_payload(payload, settings.WEBHOOK_SECRET)
    assert verify_webhook_signature(payload, signature) is True


def test_tampered_payload_returns_false() -> None:
    payload = b'{"event": "job.complete", "job_id": "abc123"}'
    signature = _sign_payload(payload, settings.WEBHOOK_SECRET)
    tampered = b'{"event": "job.complete", "job_id": "HACKED"}'
    assert verify_webhook_signature(tampered, signature) is False


def test_wrong_secret_returns_false() -> None:
    payload = b'{"event": "job.complete"}'
    signature = _sign_payload(payload, "wrong-secret")
    assert verify_webhook_signature(payload, signature) is False


def test_malformed_signature_header_returns_false() -> None:
    payload = b'{"event": "test"}'
    assert verify_webhook_signature(payload, "notavalidformat") is False
    assert verify_webhook_signature(payload, "") is False
    assert verify_webhook_signature(payload, "md5=abc123") is False


def test_empty_payload_signature_is_consistent() -> None:
    """Empty-body webhooks should still be verifiable."""
    payload = b""
    signature = _sign_payload(payload, settings.WEBHOOK_SECRET)
    assert verify_webhook_signature(payload, signature) is True


# ── General error response hygiene ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_error_responses_contain_no_internal_paths() -> None:
    """
    All error response bodies must not expose internal file paths,
    Python module names, or stack traces.
    """
    auth = APIKeyAuth()
    limiter = RateLimiter()
    async with await _make_client(auth, limiter) as client:
        resp = await client.get(
            "/protected",
            headers={"X-API-Key": "garbage"},
        )
    body_lower = resp.text.lower()
    for forbidden in ("traceback", "file \"", "/aurascript", "core/security"):
        assert forbidden not in body_lower, (
            f"Response body leaked internal info: {forbidden!r}"
        )
