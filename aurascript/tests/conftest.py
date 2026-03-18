"""
AuraScript — Shared pytest fixtures.

Loads .env.test before any settings are instantiated, then builds a minimal
FastAPI app with a single protected endpoint so security tests have something
to call against.
"""

from __future__ import annotations

import os
from pathlib import Path

# Load .env.test before importing anything that reads settings.
from dotenv import load_dotenv

_env_test_path = Path(__file__).parent.parent / ".env.test"
load_dotenv(dotenv_path=_env_test_path, override=True)

# Patch module-level singletons before they are imported by tests.
# We must set the env vars *before* config.py is first imported.
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project-id")
os.environ.setdefault(
    "GOOGLE_APPLICATION_CREDENTIALS", "/tmp/test-service-account.json"
)
os.environ.setdefault("VALID_API_KEYS", "test-api-key-aaaa1111,test-api-key-bbbb2222")
os.environ.setdefault(
    "WEBHOOK_SECRET",
    "test-webhook-secret-0000000000000000000000000000000000000000000000",
)

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from aurascript.core.security import APIKeyAuth, RateLimiter, api_key_auth, rate_limiter
from aurascript.config import settings


# ── Minimal test app ───────────────────────────────────────────────────────────


def _build_test_app(auth: APIKeyAuth, limiter: RateLimiter) -> FastAPI:
    """
    Build a throwaway FastAPI app with one protected endpoint.
    Using fresh instances of auth/limiter ensures tests are isolated.
    """
    app = FastAPI()

    @app.get("/protected")
    async def protected_endpoint(
        api_key: str = Depends(auth),
        _rate: None = Depends(limiter),
    ) -> dict:
        return {"status": "ok", "key_prefix": api_key[:8]}

    return app


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def valid_api_key() -> str:
    return "test-api-key-aaaa1111"


@pytest.fixture()
def invalid_api_key() -> str:
    return "totally-wrong-key-xxxx"


@pytest.fixture()
def fresh_auth() -> APIKeyAuth:
    """Fresh APIKeyAuth instance (no shared state)."""
    return APIKeyAuth()


@pytest.fixture()
def fresh_limiter() -> RateLimiter:
    """Fresh RateLimiter instance with no accumulated counts."""
    return RateLimiter()


@pytest.fixture()
def test_app(fresh_auth: APIKeyAuth, fresh_limiter: RateLimiter) -> FastAPI:
    return _build_test_app(fresh_auth, fresh_limiter)


@pytest.fixture()
def sync_client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app, raise_server_exceptions=False)


@pytest_asyncio.fixture()
async def async_client(test_app: FastAPI) -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        yield client
