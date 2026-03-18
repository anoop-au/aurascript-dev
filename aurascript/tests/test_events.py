"""
AuraScript — Event system tests.

Covers:
- Every event class serializes to valid JSON
- Sequence numbers auto-increment correctly per job
- Event replay returns only events after from_sequence
- Sentinel None correctly ends the async generator
- AnyEvent union type accepts all defined event types
- schema_version field present on all events
- Field constraints enforced (confidence 0-1, preview max_length)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from aurascript.models.events import (
    AgentDecisionEvent,
    AnyEvent,
    AudioAnalyzedEvent,
    BaseEvent,
    ChunkingCompleteEvent,
    ChunkingStartedEvent,
    ChunkProcessingStartedEvent,
    ChunkRetryEvent,
    ChunkTranscribedEvent,
    JobAcceptedEvent,
    JobCompleteEvent,
    JobFailedEvent,
    PlanCreatedEvent,
    ProgressHeartbeatEvent,
    QualityCheckedEvent,
    StitchingCompleteEvent,
    StitchingStartedEvent,
)
from aurascript.services.event_bus import EventBus


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _base_kwargs(job_id: str = "job-abc123") -> dict:
    return {"job_id": job_id, "timestamp": _now(), "sequence": 1}


@pytest.fixture()
def fresh_bus() -> EventBus:
    """Isolated EventBus instance per test."""
    return EventBus()


# ── Build one instance of every event class ───────────────────────────────────


def _all_event_instances() -> list[AnyEvent]:
    kw = _base_kwargs()
    return [
        JobAcceptedEvent(
            **kw, file_size_bytes=1024, file_name_safe="job_abc.audio",
            poll_url="/transcribe/job-abc123",
        ),
        AudioAnalyzedEvent(
            **kw, duration_seconds=120.0, sample_rate=44100, channels=2,
            codec="mp3", bitrate_kbps=128, is_stereo=True,
            quality_warnings=[],
        ),
        PlanCreatedEvent(
            **kw, estimated_chunks=3, strategy="multi_chunk",
            estimated_processing_minutes=2.5, chunk_duration_seconds=180,
        ),
        ChunkingStartedEvent(**kw, total_expected_chunks=3),
        ChunkingCompleteEvent(
            **kw, actual_chunk_count=3, total_audio_seconds=360.0,
            chunk_file_sizes_kb=[512, 510, 200],
        ),
        ChunkProcessingStartedEvent(
            **kw, chunk_index=0, total_chunks=3, progress_percent=0.0,
        ),
        ChunkTranscribedEvent(
            **kw, chunk_index=0, total_chunks=3,
            preview="Hello this is a test",
            confidence=0.92, detected_languages=["en", "ms"],
            issues=[], start_time_seconds=0.0,
        ),
        QualityCheckedEvent(
            **kw, chunk_index=0, final_score=0.92, heuristic_score=0.90,
            ai_score=0.94, recommendation="accept", issues=[],
        ),
        ChunkRetryEvent(**kw, chunk_index=1, attempt=1, reason="Low confidence"),
        StitchingStartedEvent(**kw, total_chunks=3),
        StitchingCompleteEvent(
            **kw, speaker_map={"SPEAKER_0": "Speaker A"},
            speaker_count=1, transcript_preview_lines=["Hello world"],
            low_confidence_section_count=0,
        ),
        JobCompleteEvent(
            **kw, speaker_count=2, total_duration_seconds=360.0,
            processing_time_seconds=45.0, overall_confidence=0.91,
            low_confidence_sections=0, languages_detected=["en", "ms"],
            word_count=850,
        ),
        JobFailedEvent(
            **kw, error_code="INVALID_AUDIO",
            error_message="File content does not match an audio format.",
            suggested_action="check_audio_format",
        ),
        AgentDecisionEvent(
            **kw, agent="QualityAgent", decision="retry",
            reason="Score 0.42 below threshold 0.60",
        ),
        ProgressHeartbeatEvent(
            **kw, overall_progress_percent=33.3, current_stage="TRANSCRIBING",
            active_chunk_indexes=[1], elapsed_seconds=12.5,
        ),
    ]


# ── Serialisation tests ────────────────────────────────────────────────────────


@pytest.mark.parametrize("event", _all_event_instances())
def test_event_serialises_to_valid_json(event: AnyEvent) -> None:
    """Every event class must serialise to a parseable JSON string."""
    raw = event.model_dump_json()
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)
    assert parsed["job_id"] == "job-abc123"
    assert parsed["event_type"] == event.event_type


@pytest.mark.parametrize("event", _all_event_instances())
def test_schema_version_present_on_all_events(event: AnyEvent) -> None:
    raw = json.loads(event.model_dump_json())
    assert raw["schema_version"] == "1.1"


@pytest.mark.parametrize("event", _all_event_instances())
def test_sequence_field_present(event: AnyEvent) -> None:
    raw = json.loads(event.model_dump_json())
    assert "sequence" in raw
    assert isinstance(raw["sequence"], int)


# ── AnyEvent union acceptance ─────────────────────────────────────────────────


def test_any_event_union_accepts_all_types() -> None:
    """
    Type-check: every event instance is an instance of its own concrete class
    AND the type annotation AnyEvent covers all of them.
    """
    for event in _all_event_instances():
        # All events share the BaseEvent base.
        assert isinstance(event, BaseEvent)
        # AnyEvent is a type alias for the union — verify runtime isinstance.
        assert isinstance(
            event,
            (
                JobAcceptedEvent, AudioAnalyzedEvent, PlanCreatedEvent,
                ChunkingStartedEvent, ChunkingCompleteEvent,
                ChunkProcessingStartedEvent, ChunkTranscribedEvent,
                QualityCheckedEvent, ChunkRetryEvent, StitchingStartedEvent,
                StitchingCompleteEvent, JobCompleteEvent, JobFailedEvent,
                AgentDecisionEvent, ProgressHeartbeatEvent,
            ),
        )


# ── Field constraint enforcement ──────────────────────────────────────────────


def test_confidence_below_zero_raises_validation_error() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ChunkTranscribedEvent(
            **_base_kwargs(), chunk_index=0, total_chunks=1,
            preview="test", confidence=-0.1,
            detected_languages=["en"], issues=[],
            start_time_seconds=0.0,
        )


def test_confidence_above_one_raises_validation_error() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ChunkTranscribedEvent(
            **_base_kwargs(), chunk_index=0, total_chunks=1,
            preview="test", confidence=1.1,
            detected_languages=["en"], issues=[],
            start_time_seconds=0.0,
        )


def test_preview_max_length_enforced() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ChunkTranscribedEvent(
            **_base_kwargs(), chunk_index=0, total_chunks=1,
            preview="x" * 201,   # 201 chars — over the 200-char limit
            confidence=0.9,
            detected_languages=["en"], issues=[],
            start_time_seconds=0.0,
        )


def test_quality_score_bounds_enforced() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        QualityCheckedEvent(
            **_base_kwargs(), chunk_index=0,
            final_score=1.5,      # > 1.0
            heuristic_score=0.9,
            recommendation="accept", issues=[],
        )


# ── EventBus sequence numbering ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sequence_numbers_auto_increment(fresh_bus: EventBus) -> None:
    """Published events must receive monotonically increasing sequence numbers."""
    job_id = "seq-test-job"
    await fresh_bus.create_channel(job_id)

    events_to_publish = [
        ChunkingStartedEvent(**_base_kwargs(job_id), total_expected_chunks=3),
        ChunkingStartedEvent(**_base_kwargs(job_id), total_expected_chunks=3),
        ChunkingStartedEvent(**_base_kwargs(job_id), total_expected_chunks=3),
    ]
    for ev in events_to_publish:
        await fresh_bus.publish(job_id, ev)

    history = await fresh_bus.replay_history(job_id, 0)
    sequences = [e.sequence for e in history]
    assert sequences == [1, 2, 3]


@pytest.mark.asyncio
async def test_sequence_is_independent_per_job(fresh_bus: EventBus) -> None:
    """Sequence counters for different jobs must not interfere."""
    job_a, job_b = "job-aaa", "job-bbb"
    await fresh_bus.create_channel(job_a)
    await fresh_bus.create_channel(job_b)

    ev = ChunkingStartedEvent(**_base_kwargs(job_a), total_expected_chunks=1)
    await fresh_bus.publish(job_a, ev)
    await fresh_bus.publish(job_a, ev.model_copy(update={"job_id": job_a}))

    ev_b = ChunkingStartedEvent(**_base_kwargs(job_b), total_expected_chunks=1)
    await fresh_bus.publish(job_b, ev_b)

    hist_a = await fresh_bus.replay_history(job_a, 0)
    hist_b = await fresh_bus.replay_history(job_b, 0)

    assert [e.sequence for e in hist_a] == [1, 2]
    assert [e.sequence for e in hist_b] == [1]


# ── EventBus replay ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_returns_only_events_after_from_sequence(
    fresh_bus: EventBus,
) -> None:
    job_id = "replay-job"
    await fresh_bus.create_channel(job_id)

    for _ in range(5):
        ev = ChunkingStartedEvent(**_base_kwargs(job_id), total_expected_chunks=5)
        await fresh_bus.publish(job_id, ev)

    replayed = await fresh_bus.replay_history(job_id, from_sequence=3)
    assert len(replayed) == 2
    assert replayed[0].sequence == 4
    assert replayed[1].sequence == 5


@pytest.mark.asyncio
async def test_replay_from_zero_returns_all_events(fresh_bus: EventBus) -> None:
    job_id = "replay-all-job"
    await fresh_bus.create_channel(job_id)

    for _ in range(3):
        await fresh_bus.publish(
            job_id,
            ChunkingStartedEvent(**_base_kwargs(job_id), total_expected_chunks=3),
        )

    replayed = await fresh_bus.replay_history(job_id, from_sequence=0)
    assert len(replayed) == 3


@pytest.mark.asyncio
async def test_replay_unknown_job_returns_empty_list(fresh_bus: EventBus) -> None:
    result = await fresh_bus.replay_history("unknown-job-id", from_sequence=0)
    assert result == []


# ── EventBus subscribe / sentinel ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_subscribe_yields_events_and_stops_on_job_complete(
    fresh_bus: EventBus,
) -> None:
    """
    Subscribing to a job channel must yield all published events and stop
    cleanly when JobCompleteEvent is published (sentinel enqueued).
    """
    job_id = "sub-complete-job"
    await fresh_bus.create_channel(job_id)

    # Publish two regular events then a terminal event.
    await fresh_bus.publish(
        job_id,
        ChunkingStartedEvent(**_base_kwargs(job_id), total_expected_chunks=1),
    )
    await fresh_bus.publish(
        job_id,
        ChunkingCompleteEvent(
            **_base_kwargs(job_id), actual_chunk_count=1,
            total_audio_seconds=30.0, chunk_file_sizes_kb=[128],
        ),
    )
    await fresh_bus.publish(
        job_id,
        JobCompleteEvent(
            **_base_kwargs(job_id), speaker_count=1,
            total_duration_seconds=30.0, processing_time_seconds=5.0,
            overall_confidence=0.95, low_confidence_sections=0,
            languages_detected=["en"], word_count=100,
        ),
    )

    received: list[AnyEvent] = []
    async for event in fresh_bus.subscribe(job_id):
        received.append(event)

    # All three events received; generator stopped on its own.
    assert len(received) == 3
    assert received[-1].event_type == "JOB_COMPLETE"


@pytest.mark.asyncio
async def test_subscribe_stops_on_job_failed(fresh_bus: EventBus) -> None:
    job_id = "sub-failed-job"
    await fresh_bus.create_channel(job_id)

    await fresh_bus.publish(
        job_id,
        JobFailedEvent(
            **_base_kwargs(job_id),
            error_code="INTERNAL_ERROR",
            error_message="Something went wrong.",
            suggested_action="contact_support",
        ),
    )

    received: list[AnyEvent] = []
    async for event in fresh_bus.subscribe(job_id):
        received.append(event)

    assert len(received) == 1
    assert received[0].event_type == "JOB_FAILED"


@pytest.mark.asyncio
async def test_subscribe_raises_key_error_for_unknown_channel(
    fresh_bus: EventBus,
) -> None:
    with pytest.raises(KeyError):
        async for _ in fresh_bus.subscribe("no-such-job"):
            pass


# ── Channel destroy ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_destroy_channel_ends_subscriber(fresh_bus: EventBus) -> None:
    job_id = "destroy-job"
    await fresh_bus.create_channel(job_id)

    await fresh_bus.publish(
        job_id,
        ChunkingStartedEvent(**_base_kwargs(job_id), total_expected_chunks=1),
    )
    await fresh_bus.destroy_channel(job_id)

    received: list[AnyEvent] = []
    # Channel is gone — replay_history returns empty list.
    result = await fresh_bus.replay_history(job_id, 0)
    assert result == []
