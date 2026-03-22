"""
AuraScript — Agent I/O dataclasses.

These are the typed contracts passed between pipeline stages.
Using dataclasses (not Pydantic) keeps them lightweight; they are never
serialised to JSON directly — only the event models in events.py are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional


@dataclass
class AudioAnalysis:
    """Output of ffprobe analysis. Input to the orchestrator planner."""

    duration_seconds: float
    sample_rate: int
    channels: int
    codec: str
    is_stereo: bool
    warnings: list[str] = field(default_factory=list)
    bitrate_kbps: Optional[int] = None   # None for VBR audio


@dataclass
class ChunkPlan:
    """Output of the orchestrator planner. Drives chunking and UI estimates."""

    chunk_paths: list[Path]
    strategy: Literal["single_chunk", "multi_chunk", "large_file_warning"]
    estimated_minutes: float
    chunk_duration_seconds: int


@dataclass
class TranscriptionInput:
    """Input sent to TranscriptionAgent for a single audio chunk."""

    chunk_path: Path
    chunk_index: int
    total_chunks: int
    language_hint: str
    num_speakers: int


@dataclass
class TranscriptionMetadata:
    """Per-chunk metadata returned alongside the raw transcript text."""

    detected_languages: list[str]
    speaker_count: int
    confidence: float
    issues: list[str] = field(default_factory=list)


@dataclass
class TranscriptionOutput:
    """Output of TranscriptionAgent for a single audio chunk."""

    transcript: str
    metadata: TranscriptionMetadata
    chunk_index: int


@dataclass
class QualityInput:
    """Input sent to QualityAgent to evaluate a single chunk's transcript."""

    transcript: str
    chunk_index: int
    transcription_metadata: TranscriptionMetadata


@dataclass
class QualityOutput:
    """Output of QualityAgent. Drives the retry/flag/accept decision."""

    final_score: float
    heuristic_score: float
    recommendation: Literal["accept", "retry", "flag"]
    issues: list[str] = field(default_factory=list)
    ai_score: Optional[float] = None


@dataclass
class CorrectedChunk:
    """A single chunk after transcription and quality evaluation."""

    chunk_index: int
    transcript: str
    quality_output: QualityOutput
    start_time_seconds: float
    detected_languages: list[str]


@dataclass
class StitcherInput:
    """Input sent to StitcherAgent to unify all chunks into a final transcript."""

    corrected_chunks: list[CorrectedChunk]
    low_confidence_indexes: list[int]
    num_speakers: int
    total_duration_seconds: float
    previous_chunk_speakers: dict[str, str] = field(default_factory=dict)


@dataclass
class StitcherOutput:
    """Final output of StitcherAgent — the completed transcript."""

    transcript: str
    speaker_map: dict[str, str]
    word_count: int
    languages_detected: list[str]
