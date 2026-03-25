"""
AuraScript — OrchestratorAgent.

The master pipeline agent. It NEVER calls Gemini directly — it delegates
all AI work to the specialist agents (Transcription, Quality, Stitcher).

Pipeline stages:
  1. ANALYZE   — ffprobe audio analysis
  2. PLAN      — compute chunk strategy and estimates
  3. CHUNK     — ffmpeg audio splitting
  4. PER-CHUNK VERTICAL PIPELINE — each chunk runs Transcribe → Quality →
                 Retry → Timestamp fix concurrently as one isolated task
  5. STITCH    — Claude unification (skipped for single-chunk jobs)
  6. COMPLETE  — emit JobCompleteEvent and return result

A heartbeat task runs during Stage 4 to prevent frontend frozen-UI.
All temp files are cleaned up in a `finally` block — guaranteed.
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from pathlib import Path

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
from aurascript.services.audio_processor import AudioProcessingError, analyze_audio, stream_chunk_audio
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
    translate_to: str | None = None


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
        self._chunks_done: int = 0
        self._total_chunks: int = 0

    async def _process_single_chunk_pipeline(
        self,
        chunk_path: Path,
        chunk_index: int,
        total_chunks: int,
        input_data: OrchestratorInput,
        semaphore: asyncio.Semaphore,
    ) -> CorrectedChunk:
        """
        Handles the full vertical pipeline for a single chunk:
        Transcribe → Quality Check → Retry → Timestamp Fix.

        Never raises — all exceptions are caught and a fallback CorrectedChunk
        is returned so one bad chunk never crashes the whole job.
        """
        _fallback_qual = QualityOutput(
            final_score=0.5, heuristic_score=0.5,
            recommendation="accept", issues=[],
        )

        def _fallback_chunk(transcript: str, qual: QualityOutput) -> CorrectedChunk:
            corrected = fix_chunk_timestamps(
                transcript, chunk_index, self.settings.CHUNK_DURATION_SECONDS
            )
            return CorrectedChunk(
                chunk_index=chunk_index,
                transcript=corrected,
                quality_output=qual,
                start_time_seconds=float(
                    chunk_index * self.settings.CHUNK_DURATION_SECONDS
                ),
                detected_languages=["unknown"],
            )

        # ── Step 1: Transcribe ────────────────────────────────────────────────
        try:
            trans_out = await TranscriptionAgent(
                self.job_id, self.event_bus, self.settings
            ).run(
                TranscriptionInput(
                    chunk_path=chunk_path,
                    chunk_index=chunk_index,
                    total_chunks=total_chunks,
                    language_hint=input_data.language_hint,
                    num_speakers=input_data.num_speakers,
                    translate_to=input_data.translate_to,
                ),
                semaphore=semaphore,
            )
        except Exception as exc:
            self.logger.error(
                "chunk_transcription_failed", chunk_index=chunk_index, error=str(exc)
            )
            self._chunks_done += 1
            return _fallback_chunk(
                f"[TRANSCRIPTION_ERROR: chunk {chunk_index} failed]",
                QualityOutput(
                    final_score=0.0, heuristic_score=0.0,
                    recommendation="flag", issues=["agent_exception"],
                ),
            )

        self._chunks_done += 1

        # ── Step 2: Quality Check ─────────────────────────────────────────────
        try:
            qual_out = await QualityAgent(
                self.job_id, self.event_bus, self.settings
            ).run(
                QualityInput(
                    transcript=trans_out.transcript,
                    chunk_index=chunk_index,
                    transcription_metadata=trans_out.metadata,
                    translate_to=input_data.translate_to,
                )
            )
        except Exception as exc:
            self.logger.warning(
                "quality_check_exception", chunk_index=chunk_index, error=str(exc)
            )
            corrected = fix_chunk_timestamps(
                trans_out.transcript, chunk_index, self.settings.CHUNK_DURATION_SECONDS
            )
            return CorrectedChunk(
                chunk_index=chunk_index,
                transcript=corrected,
                quality_output=_fallback_qual,
                start_time_seconds=float(
                    chunk_index * self.settings.CHUNK_DURATION_SECONDS
                ),
                detected_languages=trans_out.metadata.detected_languages,
            )

        # ── Step 3: Retry if recommended ──────────────────────────────────────
        if qual_out.recommendation == "retry":
            await self.emit(self._make_event(
                ChunkRetryEvent,
                chunk_index=chunk_index,
                reason=", ".join(qual_out.issues),
            ))
            try:
                retry_out = await TranscriptionAgent(
                    self.job_id, self.event_bus, self.settings
                ).run(
                    TranscriptionInput(
                        chunk_path=chunk_path,
                        chunk_index=chunk_index,
                        total_chunks=total_chunks,
                        language_hint=input_data.language_hint,
                        num_speakers=input_data.num_speakers,
                        translate_to=input_data.translate_to,
                    ),
                    semaphore=semaphore,
                    is_retry=True,
                )
                retry_qual = await QualityAgent(
                    self.job_id, self.event_bus, self.settings
                ).run(
                    QualityInput(
                        transcript=retry_out.transcript,
                        chunk_index=chunk_index,
                        transcription_metadata=retry_out.metadata,
                        translate_to=input_data.translate_to,
                    )
                )
                low = retry_qual.final_score < self.settings.LOW_CONFIDENCE_THRESHOLD
                final_text = (
                    f"⚠️ [LOW CONFIDENCE SECTION]\n{retry_out.transcript}"
                    if low else retry_out.transcript
                )
                corrected = fix_chunk_timestamps(
                    final_text, chunk_index, self.settings.CHUNK_DURATION_SECONDS
                )
                return CorrectedChunk(
                    chunk_index=chunk_index,
                    transcript=corrected,
                    quality_output=retry_qual,
                    start_time_seconds=float(
                        chunk_index * self.settings.CHUNK_DURATION_SECONDS
                    ),
                    detected_languages=retry_out.metadata.detected_languages,
                )
            except Exception as retry_exc:
                self.logger.error(
                    "chunk_retry_failed", chunk_index=chunk_index, error=str(retry_exc)
                )
                return _fallback_chunk(
                    f"⚠️ [LOW CONFIDENCE SECTION]\n{trans_out.transcript}",
                    qual_out,
                )

        # ── Step 4: Timestamp Correction ──────────────────────────────────────
        if qual_out.recommendation == "flag":
            final_text = f"⚠️ [LOW CONFIDENCE SECTION]\n{trans_out.transcript}"
        else:
            final_text = trans_out.transcript

        corrected = fix_chunk_timestamps(
            final_text, chunk_index, self.settings.CHUNK_DURATION_SECONDS
        )
        return CorrectedChunk(
            chunk_index=chunk_index,
            transcript=corrected,
            quality_output=qual_out,
            start_time_seconds=float(
                chunk_index * self.settings.CHUNK_DURATION_SECONDS
            ),
            detected_languages=trans_out.metadata.detected_languages,
        )

    async def run(self, input: OrchestratorInput) -> OrchestratorOutput:
        job_start = time.monotonic()
        all_file_paths: list[Path] = [input.audio_path]

        try:
            # ── STAGE 1: ANALYZE ──────────────────────────────────────────────
            self._current_progress = 2.0
            await self.emit(self._make_event(
                ProgressHeartbeatEvent,
                progress_pct=2.0,
                chunks_done=0,
                total_chunks=0,
            ))

            analysis = await analyze_audio(input.audio_path)

            await self.emit(self._make_event(
                AudioAnalyzedEvent,
                duration_seconds=analysis.duration_seconds,
                sample_rate=analysis.sample_rate,
                channels=analysis.channels,
                codec=analysis.codec,
                bitrate=analysis.bitrate_kbps,
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
                chunk_count=estimated_chunks,
                strategy=strategy,
                estimated_duration_seconds=round(estimated_minutes * 60, 1),
            ))

            # ── STAGE 3 + 4: STREAM CHUNKS & SPAWN VERTICAL PIPELINES ────────
            # ffmpeg writes each closed chunk filename to a CSV list file the
            # instant it is safe to read.  We tail that file and immediately
            # spawn a full Transcribe → Quality → Retry → Timestamp pipeline
            # task per chunk — transcription starts before ffmpeg has finished
            # splitting the file.
            self._current_progress = 10.0
            await self.emit(self._make_event(ChunkingStartedEvent))

            semaphore = asyncio.Semaphore(self.settings.MAX_CONCURRENT_GEMINI_CALLS)
            heartbeat_task = asyncio.create_task(
                self._heartbeat_loop("TRANSCRIBING", job_start)
            )

            pipeline_tasks: list[asyncio.Task] = []
            chunk_index = 0

            async for chunk_path in stream_chunk_audio(
                input.audio_path, self.job_id, analysis
            ):
                all_file_paths.append(chunk_path)
                pipeline_tasks.append(asyncio.create_task(
                    self._process_single_chunk_pipeline(
                        chunk_path=chunk_path,
                        chunk_index=chunk_index,
                        total_chunks=estimated_chunks,  # from Stage 2 plan
                        input_data=input,
                        semaphore=semaphore,
                    )
                ))
                chunk_index += 1

            # Generator exhausted = ffmpeg has finished writing all chunks.
            total_chunks = chunk_index
            self._total_chunks = total_chunks
            self._current_progress = 15.0

            await self.emit(self._make_event(
                ChunkingCompleteEvent,
                chunk_count=total_chunks,
            ))

            # Add the CSV list file to cleanup.
            list_file = self.settings.CHUNKS_DIR / self.job_id / "chunk_list.csv"
            if list_file.exists():
                all_file_paths.append(list_file)

            CHUNK_TIMEOUT = 120  # seconds per chunk

            async def _transcribe_with_timeout(task):
                try:
                    return await asyncio.wait_for(task, timeout=CHUNK_TIMEOUT)
                except asyncio.TimeoutError:
                    return TimeoutError("chunk timed out after 120s")

            raw_results = await asyncio.gather(
                *[_transcribe_with_timeout(t) for t in pipeline_tasks],
                return_exceptions=True
            )

            # Safety net for any unexpected top-level exception.
            corrected_chunks: list[CorrectedChunk] = []
            for i, result in enumerate(raw_results):
                if isinstance(result, Exception):
                    self.logger.error(
                        "chunk_pipeline_failed", chunk_index=i, error=str(result)
                    )
                    corrected_chunks.append(CorrectedChunk(
                        chunk_index=i,
                        transcript=f"[TRANSCRIPTION_ERROR: chunk {i} failed]",
                        quality_output=QualityOutput(
                            final_score=0.0, heuristic_score=0.0,
                            recommendation="flag", issues=["agent_exception"],
                        ),
                        start_time_seconds=float(
                            i * self.settings.CHUNK_DURATION_SECONDS
                        ),
                        detected_languages=["unknown"],
                    ))
                else:
                    corrected_chunks.append(result)

            corrected_chunks.sort(key=lambda c: c.chunk_index)

            low_confidence_indexes = [
                c.chunk_index for c in corrected_chunks
                if c.quality_output.final_score < self.settings.LOW_CONFIDENCE_THRESHOLD
            ]

            # ── STAGE 5: STITCH ───────────────────────────────────────────────
            self._current_progress = 92.0

            if len(corrected_chunks) == 1:
                final_transcript = corrected_chunks[0].transcript
                speaker_map: dict[str, str] = {}
                languages_detected = corrected_chunks[0].detected_languages
                word_count = len(final_transcript.split())

                await self.emit(self._make_event(
                    AgentDecisionEvent,
                    agent="Orchestrator",
                    decision="Skipping stitching phase",
                    reason="Single chunk — no boundary repair or speaker "
                           "unification needed. Saves API cost.",
                ))
            else:
                await self.emit(self._make_event(StitchingStartedEvent))

                # Process chunks sequentially, rolling the speaker map forward
                # so each chunk receives the speaker context from all prior chunks.
                context_speaker_map: dict[str, str] = {}
                all_transcripts: list[str] = []
                all_languages: set[str] = set()

                for chunk in corrected_chunks:
                    stitch_input = StitcherInput(
                        corrected_chunks=[chunk],
                        low_confidence_indexes=low_confidence_indexes,
                        num_speakers=input.num_speakers,
                        total_duration_seconds=analysis.duration_seconds,
                        previous_chunk_speakers=dict(context_speaker_map),
                    )
                    stitch_output = await StitcherAgent(
                        self.job_id, self.event_bus, self.settings
                    ).run(stitch_input)

                    all_transcripts.append(stitch_output.transcript)
                    context_speaker_map.update(stitch_output.speaker_map)
                    all_languages.update(stitch_output.languages_detected)

                final_transcript = "\n".join(all_transcripts)
                speaker_map = context_speaker_map
                languages_detected = sorted(all_languages - {"unknown"}) or ["unknown"]
                word_count = len(final_transcript.split())

            # ── STAGE 6: COMPLETE ─────────────────────────────────────────────
            heartbeat_task.cancel()
            self._current_progress = 100.0
            processing_seconds = time.monotonic() - job_start
            overall_confidence = sum(
                c.quality_output.final_score for c in corrected_chunks
            ) / len(corrected_chunks)

            await self.emit(self._make_event(
                JobCompleteEvent,
                transcript=final_transcript,
                speaker_map=speaker_map,
                metadata={
                    "duration_seconds": analysis.duration_seconds,
                    "chunk_count": total_chunks,
                    "processing_time_seconds": round(processing_seconds, 2),
                    "overall_confidence": round(overall_confidence, 4),
                    "languages_detected": languages_detected,
                    "word_count": word_count,
                    "low_confidence_sections": len(low_confidence_indexes),
                },
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
                progress_pct=self._current_progress,
                chunks_done=self._chunks_done,
                total_chunks=self._total_chunks,
            ))
