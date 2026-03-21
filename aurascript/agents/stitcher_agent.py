"""
AuraScript — StitcherAgent.

Takes all corrected, timestamp-adjusted chunk transcripts and sends them to
Gemini 2.0 Flash for global speaker unification, boundary word repair, and
final format cleanup.

On JSON parse failure the agent attempts regex extraction, then falls back
to concatenated raw text — the pipeline never crashes on a parse error.
"""

from __future__ import annotations

import json
import re
from typing import Optional

import anthropic
import structlog

from aurascript.agents.base_agent import BaseAgent
from aurascript.config import Settings
from aurascript.models.agent_state import StitcherInput, StitcherOutput
from aurascript.models.events import (
    AgentDecisionEvent,
    StitchingCompleteEvent,
    StitchingStartedEvent,
)
from aurascript.services.event_bus import EventBus

logger = structlog.get_logger(__name__)

_CHUNK_SEPARATOR = "\n--- CHUNK BOUNDARY ---\n"

# Verbatim stitching system prompt — do NOT alter.
_STITCH_SYSTEM_PROMPT_TEMPLATE = """\
You are AuraScript's transcript unification engine.

INPUT: A Manglish transcript assembled from sequential audio chunks.
Chunks are separated by '--- CHUNK BOUNDARY ---'.
Sections marked with ⚠️ LOW CONFIDENCE were flagged during quality checks.

YOUR TASKS — execute in this exact order:

TASK 1: GLOBAL SPEAKER UNIFICATION
 Speaker labels reset at every chunk boundary. The same person may be
 called [Speaker A] in chunk 1 and [Speaker B] in chunk 2.

 Analyze:
 - Conversation context and topic continuity
 - Speaking style, vocabulary, and language preferences
 - Turn-taking patterns around chunk boundaries

 Assign globally consistent labels: [Speaker 1], [Speaker 2], etc.
 If you genuinely cannot identify a speaker, use [Speaker ?].
 NEVER guess. Uncertainty is better than a wrong label.

TASK 2: BOUNDARY WORD REPAIR
 Find all [cut-off] markers.
 Look at the immediately following chunk for context.
 If you can reconstruct the word with confidence: complete it.
 If not: replace with [inaudible].

TASK 3: OUTPUT CLEANUP
 Remove all '--- CHUNK BOUNDARY ---' markers.
 Remove all ⚠️ LOW CONFIDENCE warning lines.
 Keep ALL timestamps exactly as-is (do not alter any timestamp).
 Keep ALL native language words exactly as-is (no translation).
 Do NOT add, remove, paraphrase, or summarize ANY content.

TASK 4: FINAL FORMAT
 [MM:SS] [Speaker N]: <verbatim text>
 Use [HH:MM:SS] if total duration exceeds 60 minutes.

TASK 5: JSON OUTPUT (mandatory)
 Respond with ONLY this JSON object, no other text:
 {{
   "transcript": "<complete unified transcript>",
   "speaker_map": {{
     "Speaker 1": "<description or 'unknown'>",
     "Speaker 2": "<description or 'unknown'>"
   }},
   "word_count": <integer>,
   "languages_detected": ["<lang1>", "<lang2>"]
 }}

Expected number of unique speakers: {num_speakers}
"""


def _build_stitcher_input_text(stitch_input: StitcherInput) -> str:
    """
    Assemble the full transcript text to send to Gemini.

    Low-confidence chunks are prefixed with a ⚠️ warning line so the
    stitcher knows to treat them with extra caution.
    """
    parts: list[str] = []
    for chunk in stitch_input.corrected_chunks:
        is_low_confidence = (
            chunk.chunk_index in stitch_input.low_confidence_indexes
        )
        prefix = "⚠️ LOW CONFIDENCE — treat with caution:\n" if is_low_confidence else ""
        parts.append(f"{prefix}{chunk.transcript}")
    return _CHUNK_SEPARATOR.join(parts)


def _parse_stitch_response(
    raw: str,
    fallback_transcript: str,
) -> StitcherOutput:
    """
    Parse Gemini's JSON response into a StitcherOutput.

    Three-tier fallback:
    1. Direct json.loads on the full response.
    2. Regex extraction of the first {...} block.
    3. Use raw response as transcript with empty speaker_map.

    Never raises.
    """
    def _word_count(text: str) -> int:
        return len(text.split())

    # Tier 1: direct parse.
    try:
        data = json.loads(raw)
        return StitcherOutput(
            transcript=str(data.get("transcript", fallback_transcript)),
            speaker_map={
                str(k): str(v)
                for k, v in data.get("speaker_map", {}).items()
            },
            word_count=int(
                data.get("word_count", _word_count(data.get("transcript", "")))
            ),
            languages_detected=[
                str(l) for l in data.get("languages_detected", ["unknown"])
            ],
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        pass

    # Tier 2: regex extraction.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return StitcherOutput(
                transcript=str(data.get("transcript", fallback_transcript)),
                speaker_map={
                    str(k): str(v)
                    for k, v in data.get("speaker_map", {}).items()
                },
                word_count=int(
                    data.get("word_count", _word_count(data.get("transcript", "")))
                ),
                languages_detected=[
                    str(l) for l in data.get("languages_detected", ["unknown"])
                ],
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    # Tier 3: JSON parse failed (likely truncated output) — use the full
    # fallback transcript so users always get all chunks, not garbage JSON.
    logger.warning("stitch_json_parse_failed_using_fallback", raw_preview=raw[:300])
    return StitcherOutput(
        transcript=fallback_transcript,
        speaker_map={},
        word_count=_word_count(fallback_transcript),
        languages_detected=["unknown"],
    )


class StitcherAgent(BaseAgent):
    """
    Unifies all chunk transcripts into a single coherent final transcript.
    """

    def __init__(
        self,
        job_id: str,
        event_bus: EventBus,
        settings: Settings,
    ) -> None:
        super().__init__(job_id, event_bus, settings)
        self._client: Optional[anthropic.AsyncAnthropic] = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(
                api_key=self.settings.ANTHROPIC_API_KEY
            )
        return self._client

    async def run(self, input: StitcherInput) -> StitcherOutput:
        """
        Send all chunks to Gemini for unification and return StitcherOutput.
        """
        await self.emit(self._make_event(StitchingStartedEvent))

        input_text = _build_stitcher_input_text(input)
        system_prompt = _STITCH_SYSTEM_PROMPT_TEMPLATE.format(
            num_speakers=input.num_speakers
        )
        fallback_transcript = _CHUNK_SEPARATOR.join(
            c.transcript for c in input.corrected_chunks
        )

        output = await self._call_claude(
            system_prompt, input_text, fallback_transcript
        )

        # Build a 5-line preview for the StitchingCompleteEvent.
        preview_lines = [
            line for line in output.transcript.splitlines() if line.strip()
        ][:5]

        await self.emit(self._make_event(StitchingCompleteEvent))

        await self.emit(
            self._make_event(
                AgentDecisionEvent,
                agent="StitcherAgent",
                decision="stitching_complete",
                reason=(
                    f"Unified {len(input.corrected_chunks)} chunks, "
                    f"{len(output.speaker_map)} speakers, "
                    f"{output.word_count} words, "
                    f"languages={output.languages_detected}"
                ),
            )
        )

        self.logger.info(
            "stitching_complete",
            speakers=len(output.speaker_map),
            word_count=output.word_count,
            languages=output.languages_detected,
        )

        return output

    async def _call_claude(
        self,
        system_prompt: str,
        input_text: str,
        fallback_transcript: str,
    ) -> StitcherOutput:
        """
        Call Claude with the assembled transcript and parse the response.
        Never raises — falls back gracefully on any error.
        """
        try:
            client = self._get_client()

            response = await client.messages.create(
                model="claude-opus-4-5",
                max_tokens=8192,
                system=system_prompt,
                messages=[{"role": "user", "content": input_text}],
            )

            raw = response.content[0].text
            return _parse_stitch_response(raw, fallback_transcript)

        except Exception as exc:
            self.logger.error(
                "stitcher_claude_call_failed",
                error=str(exc),
            )
            # Return a minimal valid output so the pipeline can still complete.
            return StitcherOutput(
                transcript=fallback_transcript,
                speaker_map={},
                word_count=len(fallback_transcript.split()),
                languages_detected=["unknown"],
            )
