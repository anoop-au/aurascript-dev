"""
AuraScript — Typed WebSocket event models.

THIS IS THE PUBLIC API CONTRACT WITH THE LOVABLE FRONTEND.
Treat it as a versioned public interface.

Rules:
- NEVER remove or rename existing fields.
- NEVER change existing field types in a breaking way.
- To evolve: only ADD new Optional fields.
- schema_version = "1.1" must remain on all events.

Frontend uses event_type as a discriminator for switch/case routing.
sequence is monotonically increasing per job; gaps indicate dropped messages.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field


class BaseEvent(BaseModel):
    """
    Base for all WebSocket events.

    Frontend uses event_type as discriminator for switch/case routing.
    sequence is monotonically increasing per job.
    Frontend detects dropped messages by checking for gaps in sequence.
    schema_version enables future non-breaking evolution.
    """

    event_type: str
    job_id: str
    timestamp: datetime
    sequence: int
    schema_version: Literal["1.1"] = "1.1"


class JobAcceptedEvent(BaseEvent):
    event_type: Literal["job.accepted"] = "job.accepted"
    message: str


class AudioAnalyzedEvent(BaseEvent):
    event_type: Literal["job.audio_analyzed"] = "job.audio_analyzed"
    duration_seconds: float
    sample_rate: int
    channels: int
    codec: str
    bitrate: Optional[int] = None      # kbps; None for VBR audio
    quality_warnings: list[str]


class PlanCreatedEvent(BaseEvent):
    event_type: Literal["job.plan_created"] = "job.plan_created"
    chunk_count: int
    strategy: Literal["single_chunk", "multi_chunk", "large_file_warning"]
    estimated_duration_seconds: float


class ChunkingStartedEvent(BaseEvent):
    event_type: Literal["job.chunking_started"] = "job.chunking_started"


class ChunkingCompleteEvent(BaseEvent):
    event_type: Literal["job.chunking_complete"] = "job.chunking_complete"
    chunk_count: int


class ChunkProcessingStartedEvent(BaseEvent):
    event_type: Literal["job.chunk_processing_started"] = "job.chunk_processing_started"
    chunk_index: int
    total_chunks: int


class ChunkTranscribedEvent(BaseEvent):
    event_type: Literal["job.chunk_transcribed"] = "job.chunk_transcribed"
    chunk_index: int
    preview: Annotated[str, Field(max_length=200)]
    confidence_score: Annotated[float, Field(ge=0.0, le=1.0)]


class QualityCheckedEvent(BaseEvent):
    event_type: Literal["job.quality_checked"] = "job.quality_checked"
    chunk_index: int
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    decision: Literal["accept", "retry", "flag"]
    issues: list[str]


class ChunkRetryEvent(BaseEvent):
    event_type: Literal["job.chunk_retry"] = "job.chunk_retry"
    chunk_index: int
    reason: str


class StitchingStartedEvent(BaseEvent):
    event_type: Literal["job.stitching_started"] = "job.stitching_started"


class StitchingCompleteEvent(BaseEvent):
    event_type: Literal["job.stitching_complete"] = "job.stitching_complete"


class JobCompleteEvent(BaseEvent):
    event_type: Literal["job.complete"] = "job.complete"
    transcript: str
    speaker_map: dict[str, str]
    metadata: dict


class JobFailedEvent(BaseEvent):
    event_type: Literal["job.failed"] = "job.failed"
    error_code: Literal[
        "INVALID_AUDIO",
        "AUDIO_TOO_LONG",
        "TRANSCRIPTION_FAILED",
        "QUALITY_TOO_LOW",
        "STORAGE_ERROR",
        "INTERNAL_ERROR",
    ]
    error_message: str
    suggested_action: Literal[
        "retry_upload",
        "check_audio_format",
        "split_file",
        "contact_support",
    ]


class AgentDecisionEvent(BaseEvent):
    event_type: Literal["job.agent_decision"] = "job.agent_decision"
    agent: str
    decision: str
    reason: str


class ProgressHeartbeatEvent(BaseEvent):
    event_type: Literal["job.progress_heartbeat"] = "job.progress_heartbeat"
    progress_pct: float
    chunks_done: int
    total_chunks: int


# Type alias used throughout the codebase for type hints and queue signatures.
AnyEvent = (
    JobAcceptedEvent
    | AudioAnalyzedEvent
    | PlanCreatedEvent
    | ChunkingStartedEvent
    | ChunkingCompleteEvent
    | ChunkProcessingStartedEvent
    | ChunkTranscribedEvent
    | QualityCheckedEvent
    | ChunkRetryEvent
    | StitchingStartedEvent
    | StitchingCompleteEvent
    | JobCompleteEvent
    | JobFailedEvent
    | AgentDecisionEvent
    | ProgressHeartbeatEvent
)
