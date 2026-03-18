"""
AuraScript — Async FFmpeg/ffprobe wrapper.

All subprocess calls use asyncio.create_subprocess_exec with an explicit
argument list. shell=True is NEVER used — it would open command injection
vulnerabilities when file paths contain special characters.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import structlog

from aurascript.config import settings
from aurascript.models.agent_state import AudioAnalysis

logger = structlog.get_logger(__name__)


# ── Exceptions ─────────────────────────────────────────────────────────────────


class AudioProcessingError(Exception):
    """
    Raised when ffprobe or ffmpeg fails or returns unexpected output.

    Attributes:
        message:       Human-readable description.
        ffmpeg_stderr: Raw stderr from the subprocess (may be None).
        returncode:    Process exit code (may be None if process didn't start).
    """

    def __init__(
        self,
        message: str,
        ffmpeg_stderr: Optional[str] = None,
        returncode: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.ffmpeg_stderr = ffmpeg_stderr
        self.returncode = returncode

    def __str__(self) -> str:
        parts = [self.message]
        if self.returncode is not None:
            parts.append(f"returncode={self.returncode}")
        if self.ffmpeg_stderr:
            # Truncate long stderr to avoid flooding logs.
            parts.append(f"stderr={self.ffmpeg_stderr[:500]!r}")
        return " | ".join(parts)


# ── Audio analysis ─────────────────────────────────────────────────────────────


async def analyze_audio(input_path: Path) -> AudioAnalysis:
    """
    Run ffprobe on *input_path* and return an AudioAnalysis dataclass.

    Raises AudioProcessingError if:
    - ffprobe exits with a non-zero returncode.
    - No audio stream is found in the file.
    - Audio duration exceeds MAX_AUDIO_DURATION_SECONDS.
    """
    args = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(input_path),
    ]

    logger.debug("ffprobe_start", path=str(input_path))

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
    except FileNotFoundError as exc:
        raise AudioProcessingError(
            "ffprobe not found. Ensure ffmpeg is installed on this host.",
            returncode=None,
        ) from exc

    if proc.returncode != 0:
        raise AudioProcessingError(
            f"ffprobe failed for {input_path.name}",
            ffmpeg_stderr=stderr_bytes.decode(errors="replace"),
            returncode=proc.returncode,
        )

    try:
        probe = json.loads(stdout_bytes.decode())
    except json.JSONDecodeError as exc:
        raise AudioProcessingError(
            "ffprobe returned invalid JSON output.",
            ffmpeg_stderr=stderr_bytes.decode(errors="replace"),
            returncode=proc.returncode,
        ) from exc

    # ── Extract the first audio stream ────────────────────────────────────────
    audio_streams = [
        s for s in probe.get("streams", []) if s.get("codec_type") == "audio"
    ]
    if not audio_streams:
        raise AudioProcessingError(
            f"No audio stream found in {input_path.name}. "
            "Ensure the file contains valid audio."
        )

    stream = audio_streams[0]
    fmt = probe.get("format", {})

    # Duration: prefer format-level (more reliable for containers).
    raw_duration = fmt.get("duration") or stream.get("duration") or "0"
    try:
        duration_seconds = float(raw_duration)
    except ValueError:
        duration_seconds = 0.0

    # Sample rate.
    try:
        sample_rate = int(stream.get("sample_rate", 0))
    except (ValueError, TypeError):
        sample_rate = 0

    # Channels.
    try:
        channels = int(stream.get("channels", 1))
    except (ValueError, TypeError):
        channels = 1

    # Codec name.
    codec = stream.get("codec_name", "unknown")

    # Bitrate: use stream bit_rate, fall back to format bit_rate.
    raw_bitrate = stream.get("bit_rate") or fmt.get("bit_rate") or "0"
    bitrate_kbps: Optional[int]
    if raw_bitrate in ("N/A", "0", "", None):
        bitrate_kbps = None  # VBR audio
    else:
        try:
            bitrate_kbps = int(raw_bitrate) // 1000
        except (ValueError, TypeError):
            bitrate_kbps = None

    is_stereo = channels == 2

    # ── Hard limit check ──────────────────────────────────────────────────────
    if duration_seconds > settings.MAX_AUDIO_DURATION_SECONDS:
        raise AudioProcessingError(
            f"Audio duration {duration_seconds:.0f}s exceeds the "
            f"{settings.MAX_AUDIO_DURATION_SECONDS}s hard limit. "
            "Please split the file into shorter segments.",
            returncode=None,
        )

    # ── Quality warnings ──────────────────────────────────────────────────────
    warnings: list[str] = []

    if sample_rate > 0 and sample_rate < 8000:
        warnings.append(
            f"Very low sample rate ({sample_rate}Hz). "
            "Accuracy may be significantly reduced."
        )
    elif sample_rate > 0 and sample_rate < 16000:
        warnings.append(
            f"Low sample rate ({sample_rate}Hz). "
            "Consider using 16kHz+ audio for best results."
        )

    if channels > 2:
        warnings.append(
            "Multi-channel audio detected. "
            "Converting to mono for processing."
        )

    if duration_seconds > 3600:
        estimated_minutes = (
            duration_seconds / settings.CHUNK_DURATION_SECONDS
        ) * 0.5  # rough estimate: 30s processing per chunk
        warnings.append(
            f"Audio exceeds 1 hour. "
            f"Processing will take approximately {estimated_minutes:.0f} minutes."
        )

    analysis = AudioAnalysis(
        duration_seconds=duration_seconds,
        sample_rate=sample_rate,
        channels=channels,
        codec=codec,
        bitrate_kbps=bitrate_kbps,
        is_stereo=is_stereo,
        warnings=warnings,
    )

    logger.info(
        "ffprobe_complete",
        path=str(input_path),
        duration=duration_seconds,
        sample_rate=sample_rate,
        channels=channels,
        codec=codec,
        warnings=len(warnings),
    )

    return analysis


# ── Audio chunking ─────────────────────────────────────────────────────────────


async def chunk_audio(
    input_path: Path,
    job_id: str,
    analysis: AudioAnalysis,
) -> list[Path]:
    """
    Split *input_path* into fixed-duration MP3 chunks using ffmpeg.

    Output chunks are written to CHUNKS_DIR/<job_id>/chunk_XXXX.mp3.
    Audio is normalised to 16kHz mono during chunking to minimise size and
    maximise Gemini transcription accuracy.

    Returns a sorted list of chunk Paths.
    Raises AudioProcessingError if ffmpeg fails or produces zero chunks.
    """
    output_dir = settings.CHUNKS_DIR / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    output_pattern = str(output_dir / "chunk_%04d.mp3")

    args = [
        "ffmpeg",
        "-i", str(input_path),
        "-f", "segment",
        "-segment_time", str(settings.CHUNK_DURATION_SECONDS),
        "-c:a", "libmp3lame",
        "-q:a", "4",
        "-ar", "16000",
        "-ac", "1",               # Mono — reduces cost + improves accuracy
        "-reset_timestamps", "1",
        "-loglevel", "error",     # Suppress ffmpeg banner/progress noise
        output_pattern,
    ]

    logger.info(
        "ffmpeg_chunk_start",
        job_id=job_id,
        input=str(input_path),
        chunk_duration=settings.CHUNK_DURATION_SECONDS,
        output_dir=str(output_dir),
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr_bytes = await proc.communicate()
    except FileNotFoundError as exc:
        raise AudioProcessingError(
            "ffmpeg not found. Ensure ffmpeg is installed on this host.",
            returncode=None,
        ) from exc

    if proc.returncode != 0:
        raise AudioProcessingError(
            f"ffmpeg chunking failed for job {job_id}.",
            ffmpeg_stderr=stderr_bytes.decode(errors="replace"),
            returncode=proc.returncode,
        )

    # ── Collect and validate output chunks ────────────────────────────────────
    chunk_paths = sorted(output_dir.glob("chunk_*.mp3"))

    if not chunk_paths:
        raise AudioProcessingError(
            f"ffmpeg produced zero chunks for job {job_id}. "
            "The input file may be silent or unreadable.",
            ffmpeg_stderr=stderr_bytes.decode(errors="replace"),
            returncode=proc.returncode,
        )

    logger.info(
        "ffmpeg_chunk_complete",
        job_id=job_id,
        chunk_count=len(chunk_paths),
    )

    return chunk_paths
