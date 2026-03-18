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
    event_type: Literal["JOB_ACCEPTED"] = "JOB_ACCEPTED"
    file_size_bytes: int
    file_name_safe: str
    poll_url: str
    # websocket_url NOT included: client is already connected


class AudioAnalyzedEvent(BaseEvent):
    event_type: Literal["AUDIO_ANALYZED"] = "AUDIO_ANALYZED"
    duration_seconds: float
    sample_rate: int
    channels: int
    codec: str
    bitrate_kbps: Optional[int] = None     # None for VBR audio
    is_stereo: bool
    quality_warnings: list[str]            # Immediate warnings from ffprobe


class PlanCreatedEvent(BaseEvent):
    event_type: Literal["PLAN_CREATED"] = "PLAN_CREATED"
    estimated_chunks: int
    strategy: Literal["single_chunk", "multi_chunk", "large_file_warning"]
    estimated_processing_minutes: float
    chunk_duration_seconds: int


class ChunkingStartedEvent(BaseEvent):
    event_type: Literal["CHUNKING_STARTED"] = "CHUNKING_STARTED"
    total_expected_chunks: int


class ChunkingCompleteEvent(BaseEvent):
    event_type: Literal["CHUNKING_COMPLETE"] = "CHUNKING_COMPLETE"
    actual_chunk_count: int
    total_audio_seconds: float
    chunk_file_sizes_kb: list[int]


class ChunkProcessingStartedEvent(BaseEvent):
    event_type: Literal["CHUNK_PROCESSING_STARTED"] = "CHUNK_PROCESSING_STARTED"
    chunk_index: int
    total_chunks: int
    progress_percent: float


class ChunkTranscribedEvent(BaseEvent):
    event_type: Literal["CHUNK_TRANSCRIBED"] = "CHUNK_TRANSCRIBED"
    chunk_index: int
    total_chunks: int
    preview: Annotated[str, Field(max_length=200)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    detected_languages: list[str]
    issues: list[str]
    start_time_seconds: float


class QualityCheckedEvent(BaseEvent):
    event_type: Literal["QUALITY_CHECKED"] = "QUALITY_CHECKED"
    chunk_index: int
    final_score: Annotated[float, Field(ge=0.0, le=1.0)]
    heuristic_score: Annotated[float, Field(ge=0.0, le=1.0)]
    ai_score: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = None
    recommendation: Literal["accept", "retry", "flag"]
    issues: list[str]


class ChunkRetryEvent(BaseEvent):
    event_type: Literal["CHUNK_RETRY"] = "CHUNK_RETRY"
    chunk_index: int
    attempt: int
    reason: str


class StitchingStartedEvent(BaseEvent):
    event_type: Literal["STITCHING_STARTED"] = "STITCHING_STARTED"
    total_chunks: int


class StitchingCompleteEvent(BaseEvent):
    event_type: Literal["STITCHING_COMPLETE"] = "STITCHING_COMPLETE"
    speaker_map: dict[str, str]
    speaker_count: int
    transcript_preview_lines: list[str]    # First 5 complete lines
    low_confidence_section_count: int


class JobCompleteEvent(BaseEvent):
    event_type: Literal["JOB_COMPLETE"] = "JOB_COMPLETE"
    speaker_count: int
    total_duration_seconds: float
    processing_time_seconds: float
    overall_confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    low_confidence_sections: int
    languages_detected: list[str]
    word_count: int
    # transcript_url NOT included: frontend constructs from known base URL


class JobFailedEvent(BaseEvent):
    event_type: Literal["JOB_FAILED"] = "JOB_FAILED"
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
    event_type: Literal["AGENT_DECISION"] = "AGENT_DECISION"
    agent: str
    decision: str
    reason: str


class ProgressHeartbeatEvent(BaseEvent):
    event_type: Literal["PROGRESS_HEARTBEAT"] = "PROGRESS_HEARTBEAT"
    overall_progress_percent: float
    current_stage: Literal[
        "ANALYZING",
        "PLANNING",
        "CHUNKING",
        "TRANSCRIBING",
        "QUALITY_CHECKING",
        "STITCHING",
        "FINALIZING",
    ]
    active_chunk_indexes: list[int]
    elapsed_seconds: float


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
