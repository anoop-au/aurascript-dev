"""
AuraScript — OrchestratorAgent.

The master pipeline agent. It NEVER calls Gemini directly — it delegates
all AI work to the specialist agents (Transcription, Quality, Stitcher).

Pipeline stages:
  1. ANALYZE   — ffprobe audio analysis
  2. PLAN      — compute chunk strategy and estimates
  3. CHUNK     — ffmpeg audio splitting
  4. TRANSCRIBE — parallel Gemini transcription (semaphore-limited)
  5. QUALITY   — parallel quality scoring
  6. RETRY     — single retry for low-quality chunks
  7. TIMESTAMPS — fix chunk-relative → global timestamps
  8. STITCH    — Gemini unification (skipped for single-chunk jobs)
  9. COMPLETE  — emit JobCompleteEvent and return result

A heartbeat task runs during Stage 4 to prevent frontend frozen-UI.
All temp files are cleaned up in a `finally` block — guaranteed.
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

try:
    import google.api_core.exceptions
    _GOOGLE_EXCEPTIONS = (
        google.api_core.exceptions.ResourceExhausted,
        google.api_core.exceptions.ServiceUnavailable,
    )
except ImportError:
    _GOOGLE_EXCEPTIONS = ()

from aurascript.agents.base_agent import BaseAgent
from aurascript.agents.quality_agent import QualityAgent
from aurascript.agents.stitcher_agent import StitcherAgent
from aurascript.agents.transcription_agent import TranscriptionAgent
from aurascript.config import Settings
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
    AgentDecisionEvent,
    AudioAnalyzedEvent,
    ChunkingCompleteEvent,
    ChunkingStartedEvent,
    ChunkRetryEvent,
    JobCompleteEvent,
    JobFailedEvent,
    PlanCreatedEvent,
    ProgressHeartbeatEvent,
    StitchingStartedEvent,
)
from aurascript.services.audio_processor import AudioProcessingError, analyze_audio, chunk_audio
from aurascript.services.event_bus import EventBus
from aurascript.utils.cleanup import cleanup_job_files
from aurascript.utils.timestamp_math import fix_chunk_timestamps

logger = structlog.get_logger(__name__)


# ── I/O dataclasses ────────────────────────────────────────────────────────────


@dataclass
class OrchestratorInput:
    audio_path: Path
    language_hint: str
    num_speakers: int


@dataclass
class OrchestratorOutput:
    transcript: str
    speaker_map: dict[str, str]
    metadata: dict


# ── Error classification helpers ───────────────────────────────────────────────


def _classify_error(exc: Exception) -> str:
    if isinstance(exc, AudioProcessingError):
        return "INVALID_AUDIO"
    if _GOOGLE_EXCEPTIONS and isinstance(exc, _GOOGLE_EXCEPTIONS):
        return "TRANSCRIPTION_FAILED"
    if isinstance(exc, IOError):
        return "STORAGE_ERROR"
    return "INTERNAL_ERROR"


_SAFE_MESSAGES: dict[str, str] = {
    "INVALID_AUDIO": "The audio file could not be processed. Please check the file format.",
    "AUDIO_TOO_LONG": "The audio file exceeds the maximum allowed duration.",
    "TRANSCRIPTION_FAILED": "Transcription service temporarily unavailable. Please try again.",
    "QUALITY_TOO_LOW": "Audio quality is too low for accurate transcription.",
    "STORAGE_ERROR": "A storage error occurred. Please try again.",
    "INTERNAL_ERROR": "An internal error occurred. Please try again.",
}

_SUGGESTED_ACTIONS: dict[str, str] = {
    "INVALID_AUDIO": "check_audio_format",
    "AUDIO_TOO_LONG": "split_file",
    "TRANSCRIPTION_FAILED": "retry_upload",
    "QUALITY_TOO_LOW": "check_audio_format",
    "STORAGE_ERROR": "retry_upload",
    "INTERNAL_ERROR": "contact_support",
}


# ── Orchestrator ───────────────────────────────────────────────────────────────


class OrchestratorAgent(BaseAgent):
    """
    Master pipeline agent. Coordinates all stages of a transcription job.
    """

    def __init__(
        self,
        job_id: str,
        event_bus: EventBus,
        settings: Settings,
    ) -> None:
        super().__init__(job_id, event_bus, settings)
        self._current_progress: float = 0.0
        self._active_chunks: list[int] = []

    async def run(self, input: OrchestratorInput) -> OrchestratorOutput:
        job_start = time.monotonic()
        all_file_paths: list[Path] = [input.audio_path]

        try:
            # ── STAGE 1: ANALYZE ──────────────────────────────────────────────
            self._current_progress = 2.0
            await self.emit(self._make_event(
                ProgressHeartbeatEvent,
                overall_progress_percent=2.0,
                current_stage="ANALYZING",
                active_chunk_indexes=[],
                elapsed_seconds=0.0,
            ))

            analysis = await analyze_audio(input.audio_path)

            await self.emit(self._make_event(
                AudioAnalyzedEvent,
                duration_seconds=analysis.duration_seconds,
                sample_rate=analysis.sample_rate,
                channels=analysis.channels,
                codec=analysis.codec,
                bitrate_kbps=analysis.bitrate_kbps,
                is_stereo=analysis.is_stereo,
                quality_warnings=analysis.warnings,
            ))
            await self.emit(self._make_event(
                AgentDecisionEvent,
                agent="Orchestrator",
                decision=(
                    f"Audio analyzed: {analysis.duration_seconds:.0f}s, "
                    f"{analysis.codec}, {analysis.sample_rate}Hz"
                ),
                reason="ffprobe analysis complete",
            ))

            # ── STAGE 2: PLAN ─────────────────────────────────────────────────
            self._current_progress = 5.0
            estimated_chunks = math.ceil(
                analysis.duration_seconds / self.settings.CHUNK_DURATION_SECONDS
            )
            strategy = (
                "single_chunk" if estimated_chunks == 1
                else "large_file_warning" if analysis.duration_seconds > 3600
                else "multi_chunk"
            )
            estimated_minutes = (estimated_chunks * 25) / 60  # empirical

            await self.emit(self._make_event(
                PlanCreatedEvent,
                estimated_chunks=estimated_chunks,
                strategy=strategy,
                estimated_processing_minutes=round(estimated_minutes, 2),
                chunk_duration_seconds=self.settings.CHUNK_DURATION_SECONDS,
            ))

            # ── STAGE 3: CHUNK ────────────────────────────────────────────────
            self._current_progress = 10.0
            await self.emit(self._make_event(
                ChunkingStartedEvent,
                total_expected_chunks=estimated_chunks,
            ))

            chunk_paths = await chunk_audio(
                input.audio_path, self.job_id, analysis
            )
            all_file_paths.extend(chunk_paths)
            total_chunks = len(chunk_paths)

            await self.emit(self._make_event(
                ChunkingCompleteEvent,
                actual_chunk_count=total_chunks,
                total_audio_seconds=analysis.duration_seconds,
                chunk_file_sizes_kb=[
                    int(p.stat().st_size / 1024) for p in chunk_paths
                ],
            ))

            # ── STAGE 4: TRANSCRIBE (PARALLEL) ───────────────────────────────
            self._current_progress = 15.0
            semaphore = asyncio.Semaphore(self.settings.MAX_CONCURRENT_GEMINI_CALLS)

            heartbeat_task = asyncio.create_task(
                self._heartbeat_loop("TRANSCRIBING", job_start)
            )

            transcription_tasks = [
                TranscriptionAgent(self.job_id, self.event_bus, self.settings).run(
                    TranscriptionInput(
                        chunk_path=path,
                        chunk_index=i,
                        total_chunks=total_chunks,
                        language_hint=input.language_hint,
                        num_speakers=input.num_speakers,
                    ),
                    semaphore=semaphore,
                )
                for i, path in enumerate(chunk_paths)
            ]

            raw_results = await asyncio.gather(
                *transcription_tasks, return_exceptions=True
            )
            heartbeat_task.cancel()

            # Resolve partial failures — never let one bad chunk crash the job.
            transcription_outputs: list[TranscriptionOutput] = []
            for i, result in enumerate(raw_results):
                if isinstance(result, Exception):
                    self.logger.error(
                        "chunk_transcription_failed",
                        chunk_index=i,
                        error=str(result),
                    )
                    transcription_outputs.append(TranscriptionOutput(
                        transcript=f"[TRANSCRIPTION_ERROR: chunk {i} failed]",
                        metadata=TranscriptionMetadata(
                            detected_languages=["unknown"],
                            speaker_count=input.num_speakers,
                            confidence=0.0,
                            issues=["agent_exception"],
                        ),
                        chunk_index=i,
                    ))
                else:
                    transcription_outputs.append(result)

            # gather() does not guarantee order — sort by chunk_index.
            transcription_outputs.sort(key=lambda x: x.chunk_index)

            # ── STAGE 5: QUALITY CHECK (PARALLEL) ────────────────────────────
            self._current_progress = 70.0
            quality_tasks = [
                QualityAgent(self.job_id, self.event_bus, self.settings).run(
                    QualityInput(
                        transcript=output.transcript,
                        chunk_index=output.chunk_index,
                        transcription_metadata=output.metadata,
                    )
                )
                for output in transcription_outputs
            ]
            quality_results = await asyncio.gather(
                *quality_tasks, return_exceptions=True
            )

            # ── STAGE 6: RETRY LOGIC ──────────────────────────────────────────
            self._current_progress = 80.0
            final_transcripts: list[str] = []
            low_confidence_indexes: list[int] = []

            for output, quality in zip(transcription_outputs, quality_results):
                i = output.chunk_index

                if isinstance(quality, Exception):
                    # Quality check itself failed — accept the transcript as-is.
                    self.logger.warning(
                        "quality_check_exception", chunk_index=i, error=str(quality)
                    )
                    final_transcripts.append(output.transcript)
                    continue

                if quality.recommendation == "retry":
                    await self.emit(self._make_event(
                        ChunkRetryEvent,
                        chunk_index=i,
                        attempt=1,
                        reason=", ".join(quality.issues),
                    ))

                    try:
                        retry_output = await TranscriptionAgent(
                            self.job_id, self.event_bus, self.settings
                        ).run(
                            TranscriptionInput(
                                chunk_path=chunk_paths[i],
                                chunk_index=i,
                                total_chunks=total_chunks,
                                language_hint=input.language_hint,
                                num_speakers=input.num_speakers,
                            ),
                            semaphore=semaphore,
                            is_retry=True,
                        )

                        retry_quality = await QualityAgent(
                            self.job_id, self.event_bus, self.settings
                        ).run(
                            QualityInput(
                                transcript=retry_output.transcript,
                                chunk_index=i,
                                transcription_metadata=retry_output.metadata,
                            )
                        )

                        if retry_quality.final_score >= self.settings.LOW_CONFIDENCE_THRESHOLD:
                            final_transcripts.append(retry_output.transcript)
                        else:
                            low_confidence_indexes.append(i)
                            final_transcripts.append(
                                f"⚠️ [LOW CONFIDENCE SECTION]\n{retry_output.transcript}"
                            )
                    except Exception as retry_exc:
                        self.logger.error(
                            "chunk_retry_failed", chunk_index=i, error=str(retry_exc)
                        )
                        low_confidence_indexes.append(i)
                        final_transcripts.append(
                            f"⚠️ [LOW CONFIDENCE SECTION]\n{output.transcript}"
                        )

                elif quality.recommendation == "flag":
                    low_confidence_indexes.append(i)
                    final_transcripts.append(
                        f"⚠️ [LOW CONFIDENCE SECTION]\n{output.transcript}"
                    )

                else:  # "accept"
                    final_transcripts.append(output.transcript)

            # ── STAGE 7: TIMESTAMP CORRECTION ────────────────────────────────
            self._current_progress = 88.0
            corrected_transcripts = [
                fix_chunk_timestamps(
                    t, i, self.settings.CHUNK_DURATION_SECONDS
                )
                for i, t in enumerate(final_transcripts)
            ]

            # Build corrected chunk list for stitcher.
            corrected_chunks = [
                CorrectedChunk(
                    chunk_index=output.chunk_index,
                    transcript=corrected_transcripts[output.chunk_index],
                    quality_output=quality if not isinstance(quality, Exception)
                    else QualityOutput(
                        final_score=0.5, heuristic_score=0.5,
                        recommendation="accept", issues=[],
                    ),
                    start_time_seconds=float(
                        output.chunk_index * self.settings.CHUNK_DURATION_SECONDS
                    ),
                    detected_languages=output.metadata.detected_languages,
                )
                for output, quality in zip(transcription_outputs, quality_results)
            ]

            # ── STAGE 8: STITCH ───────────────────────────────────────────────
            self._current_progress = 92.0

            if len(corrected_transcripts) == 1:
                final_transcript = corrected_transcripts[0]
                speaker_map: dict[str, str] = {}
                languages_detected = (
                    transcription_outputs[0].metadata.detected_languages
                )
                word_count = len(final_transcript.split())

                await self.emit(self._make_event(
                    AgentDecisionEvent,
                    agent="Orchestrator",
                    decision="Skipping stitching phase",
                    reason="Single chunk — no boundary repair or speaker "
                           "unification needed. Saves API cost.",
                ))
            else:
                await self.emit(self._make_event(
                    StitchingStartedEvent,
                    total_chunks=len(corrected_transcripts),
                ))

                stitch_input = StitcherInput(
                    corrected_chunks=corrected_chunks,
                    low_confidence_indexes=low_confidence_indexes,
                    num_speakers=input.num_speakers,
                    total_duration_seconds=analysis.duration_seconds,
                )
                stitch_output = await StitcherAgent(
                    self.job_id, self.event_bus, self.settings
                ).run(stitch_input)

                final_transcript = stitch_output.transcript
                speaker_map = stitch_output.speaker_map
                languages_detected = stitch_output.languages_detected
                word_count = stitch_output.word_count

            # ── STAGE 9: COMPLETE ─────────────────────────────────────────────
            self._current_progress = 100.0
            processing_seconds = time.monotonic() - job_start
            overall_confidence = sum(
                o.metadata.confidence for o in transcription_outputs
            ) / len(transcription_outputs)

            await self.emit(self._make_event(
                JobCompleteEvent,
                speaker_count=len(speaker_map) or input.num_speakers,
                total_duration_seconds=analysis.duration_seconds,
                processing_time_seconds=round(processing_seconds, 2),
                overall_confidence=round(overall_confidence, 4),
                low_confidence_sections=len(low_confidence_indexes),
                languages_detected=languages_detected,
                word_count=word_count,
            ))

            self.logger.info(
                "job_complete",
                processing_seconds=round(processing_seconds, 2),
                chunks=total_chunks,
                word_count=word_count,
            )

            return OrchestratorOutput(
                transcript=final_transcript,
                speaker_map=speaker_map,
                metadata={
                    "duration_seconds": analysis.duration_seconds,
                    "processing_seconds": round(processing_seconds, 2),
                    "overall_confidence": round(overall_confidence, 4),
                    "languages_detected": languages_detected,
                    "word_count": word_count,
                    "chunk_count": total_chunks,
                    "low_confidence_sections": len(low_confidence_indexes),
                },
            )

        except Exception as exc:
            error_code = _classify_error(exc)
            self.logger.error(
                "job_failed",
                error_code=error_code,
                error=str(exc),
            )
            await self.emit(self._make_event(
                JobFailedEvent,
                error_code=error_code,
                error_message=_SAFE_MESSAGES.get(
                    error_code, _SAFE_MESSAGES["INTERNAL_ERROR"]
                ),
                suggested_action=_SUGGESTED_ACTIONS.get(
                    error_code, "contact_support"
                ),
            ))
            raise

        finally:
            # Always clean up temp files — success or failure.
            await cleanup_job_files(all_file_paths)

    async def _heartbeat_loop(
        self, stage: str, start_time: float
    ) -> None:
        """
        Emit a ProgressHeartbeatEvent every 5 seconds during long-running stages.
        Prevents the frontend from showing a frozen progress bar.
        """
        while True:
            await asyncio.sleep(5)
            await self.emit(self._make_event(
                ProgressHeartbeatEvent,
                overall_progress_percent=self._current_progress,
                current_stage=stage,
                active_chunk_indexes=list(self._active_chunks),
                elapsed_seconds=round(time.monotonic() - start_time, 1),
            ))
