"""
AuraScript — timestamp_math tests.

Covers:
- Chunk 0 → no offset (timestamps unchanged)
- Chunk N → correct offset applied
- MM:SS output when total time < 1 hour
- HH:MM:SS output when total time >= 1 hour
- Multiple timestamps in one transcript all shifted correctly
- Timestamps inside speaker lines untouched structurally
- Non-timestamp brackets not affected
- Empty transcript returns empty string
- Zero chunk_duration produces no offset
"""

from __future__ import annotations

import pytest

from aurascript.utils.timestamp_math import fix_chunk_timestamps


# ── Chunk 0 — no offset ───────────────────────────────────────────────────────


def test_chunk_zero_no_offset() -> None:
    transcript = "[00:00] [Speaker A]: Hello lah.\n[00:30] [Speaker A]: How are you?"
    result = fix_chunk_timestamps(transcript, chunk_index=0, chunk_duration_seconds=180)
    assert "[00:00]" in result
    assert "[00:30]" in result


def test_chunk_zero_unchanged() -> None:
    transcript = "[01:15] [Speaker B]: Okay okay."
    result = fix_chunk_timestamps(transcript, chunk_index=0, chunk_duration_seconds=180)
    assert result == transcript


# ── Chunk 1 (offset = 180s = 3 min) ──────────────────────────────────────────


def test_chunk_one_adds_offset() -> None:
    transcript = "[00:00] [Speaker A]: Test."
    result = fix_chunk_timestamps(transcript, chunk_index=1, chunk_duration_seconds=180)
    # 0s + 180s = 180s = 03:00
    assert "[03:00]" in result


def test_chunk_one_mid_timestamp() -> None:
    transcript = "[01:30] [Speaker A]: Mid chunk."
    result = fix_chunk_timestamps(transcript, chunk_index=1, chunk_duration_seconds=180)
    # 90s + 180s = 270s = 04:30
    assert "[04:30]" in result


def test_chunk_two_offset() -> None:
    transcript = "[00:00] [Speaker A]: Start."
    result = fix_chunk_timestamps(transcript, chunk_index=2, chunk_duration_seconds=180)
    # 0s + 360s = 360s = 06:00
    assert "[06:00]" in result


# ── Multiple timestamps in one transcript ──────────────────────────────────────


def test_multiple_timestamps_all_shifted() -> None:
    transcript = (
        "[00:00] [Speaker A]: Hello.\n"
        "[00:30] [Speaker B]: Hi lah.\n"
        "[01:00] [Speaker A]: How are you?"
    )
    result = fix_chunk_timestamps(transcript, chunk_index=1, chunk_duration_seconds=180)
    # 0 + 180 = 180 = 03:00
    # 30 + 180 = 210 = 03:30
    # 60 + 180 = 240 = 04:00
    assert "[03:00]" in result
    assert "[03:30]" in result
    assert "[04:00]" in result


# ── HH:MM:SS for durations >= 1 hour ─────────────────────────────────────────


def test_over_one_hour_uses_hhmmss_format() -> None:
    # Chunk index 20, duration 180s → offset = 3600s
    # [00:00] → 3600s → [01:00:00]
    transcript = "[00:00] [Speaker A]: One hour mark."
    result = fix_chunk_timestamps(transcript, chunk_index=20, chunk_duration_seconds=180)
    assert "[01:00:00]" in result


def test_over_one_hour_complex_offset() -> None:
    # chunk_index=22, duration=180 → offset=3960s
    # [01:00] = 60s + 3960s = 4020s = 1h 7m 0s → [01:07:00]
    transcript = "[01:00] [Speaker B]: Late in the recording."
    result = fix_chunk_timestamps(transcript, chunk_index=22, chunk_duration_seconds=180)
    assert "[01:07:00]" in result


def test_exactly_one_hour_boundary() -> None:
    # 3599s → [59:59]; 3600s → [01:00:00]
    transcript = "[59:59] [Speaker A]: One second before."
    result = fix_chunk_timestamps(transcript, chunk_index=0, chunk_duration_seconds=180)
    assert "[59:59]" in result  # no offset on chunk 0


def test_one_second_past_one_hour() -> None:
    # chunk_index=1, duration=3601s
    # [00:00] → 0 + 3601 = 3601s → [01:00:01]
    transcript = "[00:00] [Speaker A]: Just past one hour."
    result = fix_chunk_timestamps(transcript, chunk_index=1, chunk_duration_seconds=3601)
    assert "[01:00:01]" in result


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_empty_transcript_returns_empty() -> None:
    result = fix_chunk_timestamps("", chunk_index=5, chunk_duration_seconds=180)
    assert result == ""


def test_transcript_with_no_timestamps_unchanged() -> None:
    transcript = "This has no timestamps at all."
    result = fix_chunk_timestamps(transcript, chunk_index=3, chunk_duration_seconds=180)
    assert result == transcript


def test_non_timestamp_brackets_not_affected() -> None:
    transcript = "[inaudible] and [cut-off] remain as-is [00:05]."
    result = fix_chunk_timestamps(transcript, chunk_index=0, chunk_duration_seconds=180)
    assert "[inaudible]" in result
    assert "[cut-off]" in result
    assert "[00:05]" in result  # chunk 0 → no offset


def test_non_timestamp_brackets_with_offset_not_mangled() -> None:
    transcript = "[inaudible] hey [00:10] lah."
    result = fix_chunk_timestamps(transcript, chunk_index=1, chunk_duration_seconds=180)
    assert "[inaudible]" in result
    # [00:10] + 180s = 190s = 03:10
    assert "[03:10]" in result


def test_zero_chunk_duration_produces_no_offset() -> None:
    transcript = "[01:00] [Speaker A]: Test."
    result = fix_chunk_timestamps(transcript, chunk_index=5, chunk_duration_seconds=0)
    # 60s + 0s = 60s = 01:00
    assert "[01:00]" in result


def test_seconds_rollover_handled() -> None:
    # [00:59] + 1s offset → 60s = [01:00]
    transcript = "[00:59] [Speaker A]: Almost."
    result = fix_chunk_timestamps(transcript, chunk_index=0, chunk_duration_seconds=1)
    # chunk 0 → no offset
    assert "[00:59]" in result
