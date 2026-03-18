"""
AuraScript — HTTP request and response Pydantic models.

These are separate from the WebSocket event models in events.py.
Events flow over WebSocket; these schemas are for the REST API contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, Field, HttpUrl


class TranscribeRequest(BaseModel):
    """Form fields sent alongside the audio file upload."""

    language_hint: Annotated[str, Field(max_length=50)] = "auto"
    num_speakers: Annotated[int, Field(ge=1, le=10)] = 2
    webhook_url: Optional[HttpUrl] = None


class TranscribeResponse(BaseModel):
    """202 Accepted response returned immediately after upload."""

    job_id: str
    status: str
    # wss://www.aurascript.au/ws/transcribe/{id}?token=<key>
    websocket_url: str
    # https://www.aurascript.au/transcribe/status/{id}
    poll_url: str
    # https://www.aurascript.au/transcribe/result/{id}
    result_url: str
    message: str


class JobStatusResponse(BaseModel):
    """Polling response for GET /transcribe/status/{job_id}."""

    job_id: str
    status: str
    progress_percent: float
    current_stage: str
    created_at: datetime
    updated_at: datetime
    estimated_completion_seconds: Optional[float] = None


class JobResultResponse(BaseModel):
    """Final result response for GET /transcribe/result/{job_id}."""

    job_id: str
    status: str
    transcript: str
    speaker_map: dict[str, str]
    metadata: dict


class WebhookTestRequest(BaseModel):
    webhook_url: HttpUrl


class WebhookTestResponse(BaseModel):
    delivered: bool
    status_code: Optional[int] = None
    message: str


class HealthResponse(BaseModel):
    """Response for GET /health."""

    status: str
    version: str
    environment: str
    vertex_ai_status: str
    active_jobs: int
    timestamp: datetime


class ErrorResponse(BaseModel):
    """Standard error body shape for all 4xx/5xx responses."""

    error: str
    request_id: Optional[str] = None
