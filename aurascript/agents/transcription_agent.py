"""
AuraScript — TranscriptionAgent.

Sends a single audio chunk to Gemini 2.0 Flash via Vertex AI and returns
a structured transcript + metadata using native JSON schema output.

Key design decisions:
- temperature=0.0 for deterministic, accurate output.
- BLOCK_NONE safety settings — transcription of real conversations requires
  unfiltered output (slang, profanity, sensitive topics all appear in audio).
- Tenacity retry on transient Google API errors (rate limits, timeouts).
- response_schema=GeminiChunkResponse guarantees valid JSON — no regex needed.
- is_retry=True adds an explicit instruction to the prompt telling Gemini
  that a previous attempt was flagged for quality issues.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from pydantic import BaseModel

import structlog
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

try:
    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types as genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    genai_errors = None  # type: ignore
    _GENAI_AVAILABLE = False


def _is_retryable_gemini_error(exc: BaseException) -> bool:
    """Retry on 5xx server errors and 429 rate-limit responses only."""
    if genai_errors is None:
        return False
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError) and getattr(exc, "code", 0) == 429:
        return True
    return False

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


class GeminiChunkResponse(BaseModel):
    """Strict schema Gemini must return for each audio chunk."""
    transcript: str
    detected_languages: list[str]
    speaker_count: int
    confidence: float
    issues: list[str]


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

7. MALAYALAM SCRIPT RULES
   When transcribing Malayalam, use proper Malayalam script (മലയാളം).
   Do NOT use English letters (Manglish spelling) for Malayalam words
   unless the speaker is explicitly spelling something out.
   Ensure correct usage of chillaksharam (ൽ, ൾ, ൺ, ൻ, ർ).

8. OUTPUT FORMAT (MANDATORY)
   Return a single JSON object with these exact fields:
   - "transcript": the full verbatim transcript text (string)
   - "detected_languages": list of language names spoken (e.g. ["English", "Mandarin"])
   - "speaker_count": number of distinct speakers detected (integer)
   - "confidence": transcription confidence 0.0–1.0 (float)
   - "issues": list of issues from [audio_cutoff, noise, overlap, low_quality] — empty list if none

{language_hint_instruction}
Expected speakers in this chunk: {num_speakers}
"""

_RETRY_PROMPT_SUFFIX = (
    "\n\nIMPORTANT: A previous transcription attempt for this chunk was "
    "flagged for quality issues. Please transcribe with extra care, paying "
    "special attention to speaker identification and verbatim accuracy."
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


class TranscriptionAgent(BaseAgent):
    """
    Sends one audio chunk to Gemini 2.0 Flash and returns the transcript.

    The Gemini client is initialised lazily on first run() call so tests can
    construct this class without a real API key.
    """

    def __init__(
        self,
        job_id: str,
        event_bus: EventBus,
        settings: Settings,
    ) -> None:
        super().__init__(job_id, event_bus, settings)
        self._client: Optional[object] = None

    def _get_client(self) -> "genai.Client":
        if not _GENAI_AVAILABLE:
            raise RuntimeError(
                "google-genai is not installed. "
                "Run: pip install google-genai"
            )
        if self._client is None:
            self._client = genai.Client(api_key=self.settings.GEMINI_API_KEY)
        return self._client  # type: ignore[return-value]

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
        retry=retry_if_exception(_is_retryable_gemini_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _call_gemini(
        self, input: TranscriptionInput, is_retry: bool
    ) -> TranscriptionOutput:
        """Send the audio chunk to Gemini and parse the response."""
        client = self._get_client()

        system_prompt = _build_system_prompt(
            input.language_hint, input.num_speakers, is_retry
        )

        # Read audio bytes from disk.
        audio_bytes = input.chunk_path.read_bytes()

        response = await client.aio.models.generate_content(
            model=self.settings.VERTEX_AI_MODEL_TRANSCRIBE,
            contents=genai_types.Part.from_bytes(
                data=audio_bytes, mime_type="audio/mpeg"
            ),
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.0,        # Deterministic — critical for accuracy
                max_output_tokens=16384,
                top_p=1.0,
                response_mime_type="application/json",
                response_schema=GeminiChunkResponse,
                safety_settings=[
                    genai_types.SafetySetting(
                        category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"
                    ),
                    genai_types.SafetySetting(
                        category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"
                    ),
                    genai_types.SafetySetting(
                        category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"
                    ),
                    genai_types.SafetySetting(
                        category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"
                    ),
                ],
            ),
        )

        # Gemini sometimes wraps JSON in markdown fences despite response_mime_type.
        raw = (response.text or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
            raw = raw.strip()

        parsed = GeminiChunkResponse.model_validate_json(raw)

        return TranscriptionOutput(
            transcript=parsed.transcript,
            metadata=TranscriptionMetadata(
                detected_languages=parsed.detected_languages or ["unknown"],
                speaker_count=parsed.speaker_count,
                confidence=max(0.0, min(1.0, parsed.confidence)),
                issues=parsed.issues,
            ),
            chunk_index=input.chunk_index,
        )
