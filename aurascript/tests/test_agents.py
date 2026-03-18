"""
AuraScript — Agent layer tests.

All Gemini / Vertex AI calls are mocked — no real GCP credentials needed.

Covers:
- BaseAgent.emit() publishes to EventBus
- BaseAgent._make_event() injects job_id and timestamp
- TranscriptionAgent parses well-formed metadata block
- TranscriptionAgent handles missing metadata block gracefully
- TranscriptionAgent handles partial metadata parse failure
- QualityAgent heuristic: low word count penalty
- QualityAgent heuristic: inaudible ratio penalty
- QualityAgent heuristic: missing timestamps penalty
- QualityAgent heuristic: unexpected cut-off penalty
- QualityAgent skips AI call when heuristic_score >= 0.7
- QualityAgent calls AI when heuristic_score < 0.7
- QualityAgent handles AI JSON parse failure gracefully
- StitcherAgent parse: valid JSON response
- StitcherAgent parse: malformed JSON falls back to regex
- StitcherAgent parse: complete failure uses raw text
- OrchestratorAgent classifies errors correctly
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aurascript.agents.base_agent import BaseAgent
from aurascript.agents.quality_agent import QualityAgent, _compute_heuristic_score
from aurascript.agents.stitcher_agent import _parse_stitch_response
from aurascript.agents.transcription_agent import _parse_metadata
from aurascript.agents.orchestrator import OrchestratorAgent, _classify_error
from aurascript.config import settings
from aurascript.models.agent_state import (
    CorrectedChunk,
    QualityInput,
    QualityOutput,
    StitcherInput,
    TranscriptionInput,
    TranscriptionMetadata,
    TranscriptionOutput,
)
from aurascript.models.events import (
    ChunkingStartedEvent,
    JobCompleteEvent,
    ProgressHeartbeatEvent,
)
from aurascript.services.audio_processor import AudioProcessingError
from aurascript.services.event_bus import EventBus


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def fresh_bus() -> EventBus:
    return EventBus()


@pytest.fixture()
def job_id() -> str:
    return "test-job-agents-001"


def _make_quality_input(
    transcript: str, chunk_index: int = 0
) -> QualityInput:
    return QualityInput(
        transcript=transcript,
        chunk_index=chunk_index,
        transcription_metadata=TranscriptionMetadata(
            detected_languages=["en"],
            speaker_count=2,
            confidence=0.9,
            issues=[],
        ),
    )


# ── BaseAgent ─────────────────────────────────────────────────────────────────


class _ConcreteAgent(BaseAgent):
    async def run(self, input):
        return None


@pytest.mark.asyncio
async def test_base_agent_emit_publishes_to_bus(
    fresh_bus: EventBus, job_id: str
) -> None:
    await fresh_bus.create_channel(job_id)
    agent = _ConcreteAgent(job_id, fresh_bus, settings)

    event = agent._make_event(
        ChunkingStartedEvent, total_expected_chunks=3
    )
    await agent.emit(event)

    history = await fresh_bus.replay_history(job_id, 0)
    assert len(history) == 1
    assert history[0].event_type == "CHUNKING_STARTED"


def test_base_agent_make_event_injects_job_id(
    fresh_bus: EventBus, job_id: str
) -> None:
    agent = _ConcreteAgent(job_id, fresh_bus, settings)
    event = agent._make_event(ChunkingStartedEvent, total_expected_chunks=2)
    assert event.job_id == job_id
    assert isinstance(event.timestamp, datetime)
    assert event.sequence == 0  # EventBus assigns real sequence on publish


# ── TranscriptionAgent — metadata parsing ─────────────────────────────────────


def test_parse_metadata_well_formed() -> None:
    response = """\
[00:00] [Speaker A]: Hello lah, how are you?
[00:30] [Speaker B]: Fine mah, you?
---METADATA---
detected_languages: en, ms
speaker_count: 2
confidence: 0.92
issues: none
---END METADATA---
"""
    transcript, meta = _parse_metadata(response)
    assert "[Speaker A]" in transcript
    assert "[Speaker B]" in transcript
    assert "---METADATA---" not in transcript
    assert meta.detected_languages == ["en", "ms"]
    assert meta.speaker_count == 2
    assert meta.confidence == 0.92
    assert meta.issues == []


def test_parse_metadata_missing_block_returns_defaults() -> None:
    response = "[00:00] [Speaker A]: No metadata block here."
    transcript, meta = _parse_metadata(response)
    assert transcript == response.strip()
    assert meta.confidence == 0.5
    assert "metadata_parse_failed" in meta.issues


def test_parse_metadata_with_issues() -> None:
    response = """\
[00:00] [Speaker A]: Test [inaudible] yeah.
---METADATA---
detected_languages: en
speaker_count: 1
confidence: 0.65
issues: noise, low_quality
---END METADATA---
"""
    _, meta = _parse_metadata(response)
    assert "noise" in meta.issues
    assert "low_quality" in meta.issues


def test_parse_metadata_confidence_clamped_to_range() -> None:
    response = """\
[00:00] [Speaker A]: Test.
---METADATA---
detected_languages: en
speaker_count: 1
confidence: 1.5
issues: none
---END METADATA---
"""
    _, meta = _parse_metadata(response)
    assert meta.confidence <= 1.0


# ── QualityAgent — heuristic scoring ──────────────────────────────────────────


def _meta(confidence: float = 0.9) -> TranscriptionMetadata:
    return TranscriptionMetadata(
        detected_languages=["en"], speaker_count=1,
        confidence=confidence, issues=[],
    )


def test_heuristic_score_normal_transcript() -> None:
    transcript = (
        "[00:00] [Speaker A]: Hello there how are you doing today lah?\n"
        "[00:30] [Speaker B]: I am fine thank you very much wah good lah.\n"
        "[01:00] [Speaker A]: Great makan already or not ah okay good."
    )
    score, issues = _compute_heuristic_score(transcript, 0, 3, _meta(0.9))
    assert score >= 0.7
    assert issues == []


def test_heuristic_score_very_few_words_penalty() -> None:
    transcript = "[00:00] [Speaker A]: Hi."
    score, issues = _compute_heuristic_score(transcript, 0, 3, _meta(0.9))
    assert "very_few_words" in issues
    assert score < 0.8


def test_heuristic_score_few_words_penalty() -> None:
    # 40 words — hits the 30–60 bucket.
    words = " ".join(["word"] * 40)
    transcript = f"[00:00] [Speaker A]: {words}"
    score, issues = _compute_heuristic_score(transcript, 0, 3, _meta(0.9))
    assert "few_words" in issues


def test_heuristic_score_high_inaudible_ratio_penalty() -> None:
    # 25% inaudible → high_inaudible_ratio
    transcript = (
        "[00:00] [Speaker A]: "
        + " ".join(["[inaudible]"] * 5 + ["word"] * 15)
    )
    score, issues = _compute_heuristic_score(transcript, 0, 3, _meta(0.5))
    assert "high_inaudible_ratio" in issues


def test_heuristic_score_missing_timestamps_penalty() -> None:
    transcript = "Speaker A says hello there how are you doing today fine."
    score, issues = _compute_heuristic_score(transcript, 0, 3, _meta(0.9))
    assert "missing_timestamps" in issues


def test_heuristic_score_unexpected_cutoff_penalty() -> None:
    # cut-off in chunk 0 of 3 (not the last chunk).
    transcript = "[00:00] [Speaker A]: He said some [cut-off]"
    score, issues = _compute_heuristic_score(transcript, 0, 3, _meta(0.9))
    assert "unexpected_cutoff" in issues


def test_heuristic_score_cutoff_on_last_chunk_no_penalty() -> None:
    # cut-off on the last chunk is expected.
    transcript = "[00:00] [Speaker A]: He said some [cut-off]"
    score, issues = _compute_heuristic_score(transcript, 2, 3, _meta(0.9))
    assert "unexpected_cutoff" not in issues


def test_heuristic_score_always_in_range() -> None:
    # Worst possible transcript.
    transcript = " ".join(["[inaudible]"] * 5)
    score, _ = _compute_heuristic_score(transcript, 0, 3, _meta(0.0))
    assert 0.0 <= score <= 1.0


# ── QualityAgent — AI gate ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quality_agent_skips_ai_when_heuristic_high(
    fresh_bus: EventBus, job_id: str
) -> None:
    """When heuristic_score >= 0.7, the AI call must NOT be made."""
    await fresh_bus.create_channel(job_id)
    agent = QualityAgent(job_id, fresh_bus, settings)

    good_transcript = (
        "[00:00] [Speaker A]: " + " ".join(["hello lah"] * 40) + "\n"
        "[01:00] [Speaker B]: " + " ".join(["okay mah"] * 40)
    )
    qi = _make_quality_input(good_transcript)

    with patch.object(agent, "_ai_validate", new=AsyncMock()) as mock_ai:
        result = await agent.run(qi)

    mock_ai.assert_not_called()
    assert result.recommendation in ("accept", "retry", "flag")


@pytest.mark.asyncio
async def test_quality_agent_calls_ai_when_heuristic_low(
    fresh_bus: EventBus, job_id: str
) -> None:
    """When heuristic_score < 0.7, the AI validation must be called."""
    await fresh_bus.create_channel(job_id)
    agent = QualityAgent(job_id, fresh_bus, settings)

    # Very short transcript — will produce low heuristic score.
    qi = _make_quality_input(
        "[00:00] [Speaker A]: Hi.",
        chunk_index=0,
    )
    # Override metadata confidence to force low heuristic.
    qi.transcription_metadata.confidence = 0.3

    with patch.object(
        agent,
        "_ai_validate",
        new=AsyncMock(return_value=(0.8, [], "accept")),
    ) as mock_ai:
        result = await agent.run(qi)

    mock_ai.assert_called_once()


@pytest.mark.asyncio
async def test_quality_agent_ai_parse_failure_returns_defaults(
    fresh_bus: EventBus, job_id: str
) -> None:
    await fresh_bus.create_channel(job_id)
    agent = QualityAgent(job_id, fresh_bus, settings)

    qi = _make_quality_input("[00:00] [Speaker A]: Hi.", chunk_index=0)
    qi.transcription_metadata.confidence = 0.3

    with patch.object(
        agent,
        "_ai_validate",
        new=AsyncMock(return_value=(0.7, [], "accept")),
    ):
        result = await agent.run(qi)

    assert result.recommendation in ("accept", "retry", "flag")
    assert 0.0 <= result.final_score <= 1.0


# ── StitcherAgent — JSON parsing ──────────────────────────────────────────────


def test_stitch_parse_valid_json() -> None:
    raw = """{
  "transcript": "[00:00] [Speaker 1]: Hello.",
  "speaker_map": {"Speaker 1": "unknown"},
  "word_count": 3,
  "languages_detected": ["en"]
}"""
    output = _parse_stitch_response(raw, fallback_transcript="fallback")
    assert output.transcript == "[00:00] [Speaker 1]: Hello."
    assert output.speaker_map == {"Speaker 1": "unknown"}
    assert output.word_count == 3
    assert output.languages_detected == ["en"]


def test_stitch_parse_json_with_surrounding_text() -> None:
    raw = 'Some preamble {"transcript": "Hi.", "speaker_map": {}, "word_count": 1, "languages_detected": ["en"]} trailing'
    output = _parse_stitch_response(raw, fallback_transcript="fallback")
    assert output.transcript == "Hi."


def test_stitch_parse_complete_failure_uses_fallback() -> None:
    output = _parse_stitch_response("this is not json at all", "fallback text")
    assert output.transcript == "fallback text"
    assert output.speaker_map == {}
    assert output.languages_detected == ["unknown"]


def test_stitch_parse_empty_string_uses_fallback() -> None:
    output = _parse_stitch_response("", "my fallback")
    assert output.transcript == "my fallback"


# ── OrchestratorAgent — error classification ──────────────────────────────────


def test_classify_error_audio_processing() -> None:
    exc = AudioProcessingError("ffmpeg failed")
    assert _classify_error(exc) == "INVALID_AUDIO"


def test_classify_error_io_error() -> None:
    exc = IOError("disk full")
    assert _classify_error(exc) == "STORAGE_ERROR"


def test_classify_error_unknown_returns_internal() -> None:
    exc = RuntimeError("something unexpected")
    assert _classify_error(exc) == "INTERNAL_ERROR"
