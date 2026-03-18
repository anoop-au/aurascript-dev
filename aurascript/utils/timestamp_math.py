"""
AuraScript — Chunk timestamp offset correction.

Each audio chunk's timestamps are relative to that chunk's start (00:00).
After transcription, every chunk must have its timestamps shifted by
(chunk_index * chunk_duration_seconds) to produce global timestamps.
"""

from __future__ import annotations

import re

# Matches [MM:SS] timestamps produced by the transcription agent.
_TIMESTAMP_PATTERN = re.compile(r"\[(\d{2}):(\d{2})\]")


def fix_chunk_timestamps(
    raw_transcript: str,
    chunk_index: int,
    chunk_duration_seconds: int,
) -> str:
    """
    Shift every [MM:SS] timestamp in *raw_transcript* by the chunk's offset.

    chunk_index=0 → no shift (offset = 0s)
    chunk_index=1 → shift by chunk_duration_seconds
    chunk_index=2 → shift by 2 * chunk_duration_seconds
    etc.

    Output format:
    - [HH:MM:SS] when the absolute time >= 3600 seconds (1 hour)
    - [MM:SS]    otherwise

    Args:
        raw_transcript:        The raw transcript text from the model.
        chunk_index:           Zero-based index of the chunk.
        chunk_duration_seconds: Duration of each chunk (from settings).

    Returns:
        The transcript string with all timestamps replaced by absolute values.
    """
    offset_seconds = chunk_index * chunk_duration_seconds

    def _replace(match: re.Match) -> str:
        chunk_mm = int(match.group(1))
        chunk_ss = int(match.group(2))
        total_seconds = (chunk_mm * 60) + chunk_ss + offset_seconds

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"[{hours:02d}:{minutes:02d}:{seconds:02d}]"
        return f"[{minutes:02d}:{seconds:02d}]"

    return _TIMESTAMP_PATTERN.sub(_replace, raw_transcript)
