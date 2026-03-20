"""
AuraScript — TranscriptionAgent.

Sends a single audio chunk to Gemini 2.0 Flash via Vertex AI and parses
the structured transcript + metadata block from the response.

Key design decisions:
- temperature=0.0 for deterministic, accurate output.
- BLOCK_NONE safety settings — transcription of real conversations requires
  unfiltered output (slang, profanity, sensitive topics all appear in audio).
- Tenacity retry on transient Google API errors (rate limits, timeouts).
- Metadata block parsed with regex; parse failure is logged but never crashes.
- is_retry=True adds an explicit instruction to the prompt telling Gemini
  that a previous attempt was flagged for quality issues.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

try:
    import google.api_core.exceptions
    import vertexai
    from vertexai.generative_models import (
        GenerationConfig,
        GenerativeModel,
        HarmBlockThreshold,
        HarmCategory,
        Part,
    )
    _VERTEX_AVAILABLE = True
except ImportError:
    _VERTEX_AVAILABLE = False

from aurascript.agents.base_agent import BaseAgent
from aurascript.config import Settings
from aurascript.models.agent_state import (
    TranscriptionInput,
    TranscriptionMetadata,
    TranscriptionOutput,
)
from aurascript.models.events import (
    AgentDecisionEvent,
    ChunkProcessingStartedEvent,
    ChunkTranscribedEvent,
)
from aurascript.services.event_bus import EventBus

logger = structlog.get_logger(__name__)

# Verbatim system prompt — do NOT alter. This is the 97% accuracy prompt.
_SYSTEM_PROMPT_TEMPLATE = """\
You are AuraScript's expert transcription engine, specializing in \
Manglish — the natural, fluid code-switching between English and \
Southeast Asian languages including:
 - Bahasa Malaysia / Bahasa Indonesia
 - Mandarin Chinese (and regional variants)
 - Cantonese
 - Hokkien / Hakka / Teochew
 - Tamil
 - Tagalog

YOUR ABSOLUTE RULES:

1. VERBATIM ACCURACY
   Transcribe EXACTLY what is spoken. Every word, every syllable.
   Preserve natural speech patterns including fillers:
   "lah", "mah", "lor", "wor", "kan", "leh", "ah", "oh", "wah".

2. ZERO TRANSLATION
   NEVER convert native language words to English equivalents.
   If the speaker says "makan", write "makan". Not "eat".
   If the speaker says "pergi", write "pergi". Not "go".

3. PHONETIC PRESERVATION
   For unclear native words, transcribe the exact phonetics you hear.
   Do NOT substitute a more familiar word.

4. UNCERTAINTY HANDLING
   Unclear audio → [inaudible]
   Cut-off word at chunk end → write partial syllables + [cut-off]
   Overlapping speech → transcribe what is most audible, add [overlap]

5. FORMAT — STRICT, NO DEVIATION
   Every speaker turn must follow this exact format:
   [MM:SS] [Speaker X]: <verbatim text>

   - Timestamps are RELATIVE to THIS chunk, starting at [00:00]
   - New timestamp on every speaker change
   - New timestamp every 30 seconds if same speaker continues
   - Speakers labeled A, B, C... in order of first appearance

6. BACKGROUND ANNOTATION
   Non-speech sounds that affect comprehension:
   [background: description] — e.g. [background: loud traffic]
   [laughter], [pause], [crosstalk]

7. METADATA BLOCK (MANDATORY — append to EVERY response)
   ---METADATA---
   detected_languages: [comma-separated list]
   speaker_count: <integer>
   confidence: <float 0.0-1.0>
   issues: [comma-separated: audio_cutoff|noise|overlap|low_quality|none]
   ---END METADATA---

{language_hint_instruction}
Expected speakers in this chunk: {num_speakers}
"""

_RETRY_PROMPT_SUFFIX = (
    "\n\nIMPORTANT: A previous transcription attempt for this chunk was "
    "flagged for quality issues. Please transcribe with extra care, paying "
    "special attention to speaker identification and verbatim accuracy."
)

# Metadata block regex — lenient to handle minor model formatting variations.
_METADATA_RE = re.compile(
    r"---METADATA---\s*"
    r"detected_languages:\s*(?P<langs>[^\n]+)\s*"
    r"speaker_count:\s*(?P<speaker_count>\d+)\s*"
    r"confidence:\s*(?P<confidence>[\d.]+)\s*"
    r"issues:\s*(?P<issues>[^\n]+)\s*"
    r"---END METADATA---",
    re.IGNORECASE | re.DOTALL,
)


def _build_system_prompt(
    language_hint: str,
    num_speakers: int,
    is_retry: bool,
) -> str:
    lang_instruction = (
        f"Primary language hint: {language_hint}. "
        "Prioritize this language's phonetics when audio is ambiguous."
        if language_hint
        else ""
    )
    prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        language_hint_instruction=lang_instruction,
        num_speakers=num_speakers,
    )
    if is_retry:
        prompt += _RETRY_PROMPT_SUFFIX
    return prompt


def _parse_metadata(response_text: str) -> tuple[str, TranscriptionMetadata]:
    """
    Extract the ---METADATA--- block from the model response.

    Returns (transcript_text, metadata). On any parse failure, returns the
    full response as transcript and a safe default metadata object.
    Never raises.
    """
    match = _METADATA_RE.search(response_text)
    if not match:
        logger.warning("metadata_parse_failed", response_preview=response_text[:200])
        transcript = response_text.strip()
        return transcript, TranscriptionMetadata(
            detected_languages=["unknown"],
            speaker_count=1,
            confidence=0.5,
            issues=["metadata_parse_failed"],
        )

    # Transcript is everything before the metadata block.
    transcript = response_text[: match.start()].strip()

    try:
        langs_raw = match.group("langs").strip().strip("[]")
        detected_languages = [
            l.strip() for l in langs_raw.split(",") if l.strip()
        ] or ["unknown"]
        speaker_count = int(match.group("speaker_count"))
        confidence = max(0.0, min(1.0, float(match.group("confidence"))))
        issues_raw = match.group("issues").strip().strip("[]")
        issues = [
            i.strip() for i in issues_raw.split(",")
            if i.strip() and i.strip().lower() != "none"
        ]
    except (ValueError, AttributeError) as exc:
        logger.warning("metadata_field_parse_failed", error=str(exc))
        return transcript, TranscriptionMetadata(
            detected_languages=["unknown"],
            speaker_count=1,
            confidence=0.5,
            issues=["metadata_parse_failed"],
        )

    return transcript, TranscriptionMetadata(
        detected_languages=detected_languages,
        speaker_count=speaker_count,
        confidence=confidence,
        issues=issues,
    )


class TranscriptionAgent(BaseAgent):
    """
    Sends one audio chunk to Gemini 2.0 Flash and returns the transcript.

    Vertex AI is initialised lazily on first run() call so tests can
    construct this class without a real GCP project.
    """

    def __init__(
        self,
        job_id: str,
        event_bus: EventBus,
        settings: Settings,
    ) -> None:
        super().__init__(job_id, event_bus, settings)
        self._model: Optional[object] = None

    def _get_model(self) -> "GenerativeModel":
        if not _VERTEX_AVAILABLE:
            raise RuntimeError(
                "google-cloud-aiplatform is not installed. "
                "Run: pip install google-cloud-aiplatform"
            )
        if self._model is None:
            vertexai.init(
                project=self.settings.GOOGLE_CLOUD_PROJECT,
                location=self.settings.GOOGLE_CLOUD_LOCATION,
            )
            self._model = GenerativeModel(
                self.settings.VERTEX_AI_MODEL_TRANSCRIBE
            )
        return self._model  # type: ignore[return-value]

    async def run(
        self,
        input: TranscriptionInput,
        semaphore: Optional[asyncio.Semaphore] = None,
        is_retry: bool = False,
    ) -> TranscriptionOutput:
        """
        Transcribe *input.chunk_path* and return a TranscriptionOutput.

        Uses *semaphore* to cap concurrent Gemini calls if provided.
        """
        sem = semaphore or asyncio.Semaphore(
            self.settings.MAX_CONCURRENT_GEMINI_CALLS
        )

        await self.emit(
            self._make_event(
                ChunkProcessingStartedEvent,
                chunk_index=input.chunk_index,
                total_chunks=input.total_chunks,
            )
        )

        async with sem:
            result = await self._call_gemini(input, is_retry)

        await self.emit(
            self._make_event(
                ChunkTranscribedEvent,
                chunk_index=input.chunk_index,
                preview=result.transcript[:200],
                confidence_score=result.metadata.confidence,
            )
        )

        self.logger.info(
            "chunk_transcribed",
            chunk_index=input.chunk_index,
            confidence=result.metadata.confidence,
            languages=result.metadata.detected_languages,
        )

        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(
            (
                *(
                    (
                        google.api_core.exceptions.ResourceExhausted,
                        google.api_core.exceptions.ServiceUnavailable,
                        google.api_core.exceptions.DeadlineExceeded,
                    )
                    if _VERTEX_AVAILABLE
                    else ()
                ),
            )
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _call_gemini(
        self, input: TranscriptionInput, is_retry: bool
    ) -> TranscriptionOutput:
        """Send the audio chunk to Gemini and parse the response."""
        model = self._get_model()

        system_prompt = _build_system_prompt(
            input.language_hint, input.num_speakers, is_retry
        )

        # Read audio bytes from disk.
        audio_bytes = input.chunk_path.read_bytes()
        audio_part = Part.from_data(data=audio_bytes, mime_type="audio/mpeg")

        generation_config = GenerationConfig(
            temperature=0.0,        # Deterministic — critical for accuracy
            max_output_tokens=8192,
            top_p=1.0,
        )

        safety_settings = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        }

        response = await asyncio.to_thread(
            model.generate_content,
            [system_prompt, audio_part],
            generation_config=generation_config,
            safety_settings=safety_settings,
        )

        raw_text = response.text
        transcript, metadata = _parse_metadata(raw_text)

        return TranscriptionOutput(
            transcript=transcript,
            metadata=metadata,
            chunk_index=input.chunk_index,
        )
