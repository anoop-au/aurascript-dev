"""
AuraScript — Central configuration via pydantic-settings.

All secrets are loaded from environment variables or an .env file.
No secrets are ever hardcoded here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


def _make_comma_friendly(base_cls: type) -> type:
    """Return a subclass of *base_cls* that falls back to the raw string when
    JSON decoding fails, allowing field_validators to do the real parsing."""

    class _CommaFriendly(base_cls):  # type: ignore[valid-type]
        def decode_complex_value(
            self, field_name: str, field_info: Any, value: Any
        ) -> Any:
            try:
                return super().decode_complex_value(field_name, field_info, value)
            except ValueError:
                return value

    return _CommaFriendly


_CommaFriendlyEnvSource = _make_comma_friendly(EnvSettingsSource)
_CommaFriendlyDotEnvSource = _make_comma_friendly(DotEnvSettingsSource)


class Settings(BaseSettings):
    # ── Identity ──────────────────────────────────────────────────────
    APP_NAME: str = "AuraScript"
    APP_VERSION: str = "1.0.0"
    # Controls feature flags, log verbosity, and URL generation.
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    # ── Server ────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: Annotated[int, Field(ge=1, le=65535)] = 8080
    # Primary domain. Used to construct absolute URLs in API responses.
    PRIMARY_DOMAIN: str = "https://api.aurascript.au"
    # Secondary domain. Redirects handled at Nginx level.
    SECONDARY_DOMAIN: str = "https://www.aurascript.store"

    # ── CORS ──────────────────────────────────────────────────────────
    # Comma-separated list or JSON array. Includes the Lovable origin,
    # the www frontend proxy, and local dev servers.
    ALLOWED_ORIGINS: list[str] = [
        "https://echo-scribe-02.lovable.app",  # Lovable app (canonical origin)
        "https://www.aurascript.au",            # www frontend reverse proxy
        "https://api.aurascript.au",            # API domain (same-origin requests)
        "https://www.aurascript.store",
        "http://localhost:3000",                # Local Lovable dev
        "http://localhost:5173",                # Vite dev server
    ]

    # ── Anthropic Claude API ──────────────────────────────────────────
    # API key from https://console.anthropic.com/
    ANTHROPIC_API_KEY: str = ""

    # ── Google Gemini API ─────────────────────────────────────────────
    # API key from https://aistudio.google.com/app/apikey
    GEMINI_API_KEY: str
    # Model used for per-chunk transcription (Phase 1 of pipeline).
    VERTEX_AI_MODEL_TRANSCRIBE: str = "gemini-2.5-flash-preview-04-17"
    # Model used for final transcript unification (Phase 2 of pipeline).
    VERTEX_AI_MODEL_STITCH: str = "gemini-2.0-flash"
    # Model used for quality scoring and retry decisions.
    VERTEX_AI_MODEL_QUALITY: str = "gemini-2.0-flash"
    # Legacy Vertex AI fields — kept optional for backwards-compatibility.
    GOOGLE_CLOUD_PROJECT: Optional[str] = None
    GOOGLE_CLOUD_LOCATION: Optional[str] = None
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None

    # ── Security ──────────────────────────────────────────────────────
    # Comma-separated API keys. Rotate without restart by updating env var.
    VALID_API_KEYS: set[str]
    # HTTP header name used to pass the API key.
    API_KEY_HEADER: str = "X-API-Key"
    # HMAC-SHA256 signing key for outbound webhook payloads.
    WEBHOOK_SECRET: str
    # Sliding-window burst limit per API key.
    MAX_REQUESTS_PER_MINUTE: Annotated[int, Field(ge=1)] = 10
    # Daily cost-control cap per API key.
    MAX_REQUESTS_PER_DAY: Annotated[int, Field(ge=1)] = 200

    # ── File Handling ─────────────────────────────────────────────────
    # Hard maximum upload size (700 MB).
    MAX_UPLOAD_SIZE_BYTES: Annotated[int, Field(ge=1)] = 734_003_200
    # Directory where raw uploads are written.
    UPLOAD_DIR: Path = Path("/tmp/aurascript/uploads")
    # Directory where audio chunks are written during processing.
    CHUNKS_DIR: Path = Path("/tmp/aurascript/chunks")
    # Whitelist of accepted MIME types validated against Content-Type header.
    ALLOWED_AUDIO_MIME_TYPES: list[str] = [
        "audio/mpeg",
        "audio/mp3",      # browser alias for audio/mpeg
        "audio/wav",
        "audio/x-wav",    # browser alias for audio/wav
        "audio/mp4",
        "audio/m4a",      # browser alias for audio/x-m4a
        "audio/x-m4a",
        "audio/ogg",
        "audio/webm",
        "video/mp4",      # MP4 video (audio extracted during processing)
        "video/webm",     # webm audio recorded via MediaRecorder
        "audio/flac",
        "audio/x-flac",   # browser alias for audio/flac
        "audio/aac",
    ]

    # ── Processing ────────────────────────────────────────────────────
    # Audio is split into chunks of this duration before sending to Gemini.
    CHUNK_DURATION_SECONDS: Annotated[int, Field(ge=10, le=600)] = 180
    # asyncio.Semaphore limit for concurrent Gemini API calls.
    MAX_CONCURRENT_GEMINI_CALLS: Annotated[int, Field(ge=1, le=50)] = 24
    # Reject audio files longer than this. Protects cost + memory.
    MAX_AUDIO_DURATION_SECONDS: Annotated[int, Field(ge=60)] = 7200
    # Quality scores below this trigger an automatic retry.
    QUALITY_SCORE_THRESHOLD: Annotated[float, Field(ge=0.0, le=1.0)] = 0.6
    # Quality scores below this flag a chunk as low-confidence in output.
    LOW_CONFIDENCE_THRESHOLD: Annotated[float, Field(ge=0.0, le=1.0)] = 0.4
    # Maximum number of retry attempts per chunk before flagging and moving on.
    MAX_QUALITY_RETRIES: Annotated[int, Field(ge=0, le=5)] = 1

    # ── Jobs ──────────────────────────────────────────────────────────
    # Jobs older than this are eligible for automatic cleanup.
    JOB_TTL_SECONDS: Annotated[int, Field(ge=60)] = 3600
    # Prevents resource exhaustion on Linode VPS.
    MAX_CONCURRENT_JOBS: Annotated[int, Field(ge=1, le=50)] = 10

    # ── WebSocket ─────────────────────────────────────────────────────
    # How often the server sends a ping to keep connections alive.
    WS_PING_INTERVAL_SECONDS: Annotated[int, Field(ge=5)] = 25
    # How long to wait for a pong before treating the connection as dead.
    WS_PING_TIMEOUT_SECONDS: Annotated[int, Field(ge=1)] = 10
    # Number of events cached per job for late-joining WebSocket clients.
    WS_MAX_RECONNECT_HISTORY: Annotated[int, Field(ge=0)] = 100

    # ── Observability ─────────────────────────────────────────────────
    # Python logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    LOG_LEVEL: str = "INFO"
    # "json" for structured logging in production; "console" for local dev.
    LOG_FORMAT: Literal["json", "console"] = "json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            _CommaFriendlyEnvSource(settings_cls),
            _CommaFriendlyDotEnvSource(settings_cls, env_file=cls.model_config.get("env_file")),
            file_secret_settings,
        )

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list) -> list[str]:
        """Accept a comma-separated string or JSON array from the environment variable."""
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("ALLOWED_AUDIO_MIME_TYPES", mode="before")
    @classmethod
    def parse_mime_types(cls, v: str | list) -> list[str]:
        """Accept a comma-separated string or JSON array from the environment variable."""
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [m.strip() for m in v.split(",") if m.strip()]
        return v

    @field_validator("VALID_API_KEYS", mode="before")
    @classmethod
    def parse_api_keys(cls, v: str | set | list) -> set[str]:
        """Accept a comma-separated string or JSON array from the environment variable."""
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return set(json.loads(v))
            return {k.strip() for k in v.split(",") if k.strip()}
        return set(v)

    @property
    def is_production(self) -> bool:
        """True when ENVIRONMENT == 'production'."""
        return self.ENVIRONMENT == "production"

    @property
    def websocket_base_url(self) -> str:
        """Return wss:// in production, ws:// in development/staging."""
        if self.is_production:
            return "wss://api.aurascript.au"
        return f"ws://localhost:{self.PORT}"


# Module-level singleton. Import `settings` everywhere instead of
# re-instantiating Settings() — this ensures env vars are read once.
settings = Settings()
