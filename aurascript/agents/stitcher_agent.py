"""
AuraScript — StitcherAgent (per-chunk with rolling speaker context).

Processes chunks sequentially, passing the accumulated speaker map forward
as context so Claude can maintain consistent speaker labels across boundaries.

Each chunk gets its own Claude call with:
  - The chunk transcript
  - The speaker registry built from all previous chunks

All text manipulation (label substitution, boundary repair) is done in
Python — the LLM outputs only a small JSON correction payload.

On JSON parse failure the agent falls back to the raw chunk transcript so
the pipeline never crashes.
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

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_STITCH_SYSTEM_PROMPT = """\
You are AuraScript's expert diarization and transcript unification engine.

CONTEXT FROM PREVIOUS CHUNKS:
{previous_context}

INPUT: A single Manglish audio chunk transcript.
Chunks marked ⚠️ LOW CONFIDENCE were flagged during quality checks — treat with caution.

YOUR TASKS:

TASK 1: SPEAKER CONTINUITY
Using the context above, assign globally consistent labels to every speaker in this chunk.
Rules:
- If a voice in this chunk matches a speaker already listed in the context, you MUST
  use the same global label (e.g. Speaker 1, Speaker 2).
- If a genuinely new voice appears that was not in the context, assign the next
  sequential number (e.g. if context has Speaker 1 and Speaker 2, assign Speaker 3).
- Assign a numbered global label to EVERY local label — never leave any speaker
  unassigned. Do NOT use "Speaker ?".

TASK 2: BOUNDARY WORD REPAIR
Find all [cut-off] markers. If you can reconstruct the word with confidence from
context, provide the replacement. Otherwise use [inaudible].

TASK 3: OUTPUT CLEANUP
If you see [overlap] tags, separate overlapping speakers into two distinct
timestamped lines — one per speaker.

OUTPUT FORMAT — respond with ONLY this JSON, no other text:
{{
  "speaker_assignments": [
    {{"chunk_index": {chunk_index}, "local": "Speaker A", "global": "Speaker 1"}},
    {{"chunk_index": {chunk_index}, "local": "Speaker B", "global": "Speaker 2"}}
  ],
  "boundary_fixes": [
    {{"chunk_index": {chunk_index}, "original": "[cut-off]", "replacement": "complete_word"}}
  ],
  "languages_detected": ["English", "Malayalam"]
}}

If there are no boundary fixes needed, output an empty array for boundary_fixes.
Expected number of unique speakers across the entire conversation: {num_speakers}
"""

_NO_PREVIOUS_CONTEXT = (
    "No previous context — this is the first chunk. "
    "Assign Speaker 1 to the first voice you encounter, Speaker 2 to the next, etc."
)


def _format_previous_context(speaker_map: dict[str, str]) -> str:
    """Format the accumulated speaker map into a readable context string."""
    if not speaker_map:
        return _NO_PREVIOUS_CONTEXT
    lines = [f"- {label}: known speaker" for label in sorted(speaker_map.keys())]
    return "Known speakers from previous chunks:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Input builder
# ---------------------------------------------------------------------------


def _build_stitcher_input_text(stitch_input: StitcherInput) -> str:
    """
    Build the user message for a single-chunk stitcher call.
    """
    chunk = stitch_input.corrected_chunks[0]
    is_low_confidence = chunk.chunk_index in stitch_input.low_confidence_indexes
    warning = "⚠️ LOW CONFIDENCE — treat with caution\n" if is_low_confidence else ""
    return f"=== CHUNK {chunk.chunk_index} ===\n{warning}{chunk.transcript}"


# ---------------------------------------------------------------------------
# Programmatic correction application
# ---------------------------------------------------------------------------


def _apply_corrections(
    stitch_input: StitcherInput,
    speaker_assignments: list[dict],
    boundary_fixes: list[dict],
) -> str:
    """
    Apply LLM-provided corrections to the chunk transcript in Python.

    1. Speaker label substitution  (local → global)
    2. Boundary word repair        ([cut-off] → completion)
    """
    chunk = stitch_input.corrected_chunks[0]
    chunk_index = chunk.chunk_index
    text = chunk.transcript

    # Build local → global lookup for this chunk.
    speaker_lookup: dict[str, str] = {}
    for assignment in speaker_assignments:
        try:
            if int(assignment["chunk_index"]) == chunk_index:
                speaker_lookup[str(assignment["local"])] = str(assignment["global"])
        except (KeyError, ValueError, TypeError):
            continue

    # Replace local speaker labels.
    local_labels_found = set(re.findall(r"\[Speaker ([^\]]+)\]", text))
    for label_body in local_labels_found:
        local_label = f"Speaker {label_body}"
        global_label = speaker_lookup.get(local_label)
        if global_label:
            text = text.replace(f"[{local_label}]", f"[{global_label}]")

    # Apply boundary fixes (first occurrence each).
    for fix in boundary_fixes:
        try:
            if int(fix["chunk_index"]) == chunk_index:
                text = text.replace(str(fix["original"]), str(fix["replacement"]), 1)
        except (KeyError, ValueError, TypeError):
            continue

    return text.strip()


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def _parse_stitch_response(raw: str, stitch_input: StitcherInput) -> StitcherOutput:
    """
    Parse the LLM's metadata JSON and apply corrections programmatically.

    Three-tier fallback:
    1. Direct json.loads on the full response.
    2. Regex extraction of the first {...} block.
    3. Raw chunk transcript — never crashes.
    """
    fallback_transcript = stitch_input.corrected_chunks[0].transcript

    def _build_output(data: dict) -> StitcherOutput:
        speaker_assignments = data.get("speaker_assignments", [])
        boundary_fixes = data.get("boundary_fixes", [])
        languages = [str(l) for l in data.get("languages_detected", ["unknown"])]

        transcript = _apply_corrections(stitch_input, speaker_assignments, boundary_fixes)

        unique_globals = {str(a["global"]) for a in speaker_assignments if "global" in a}
        speaker_map = {g: "known" for g in sorted(unique_globals)}

        return StitcherOutput(
            transcript=transcript,
            speaker_map=speaker_map,
            word_count=len(transcript.split()),
            languages_detected=languages,
        )

    # Tier 1: direct parse.
    try:
        return _build_output(json.loads(raw))
    except (json.JSONDecodeError, KeyError, ValueError):
        pass

    # Tier 2: regex extraction.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return _build_output(json.loads(match.group(0)))
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    # Tier 3: plain fallback.
    logger.warning("stitch_json_parse_failed_using_fallback", raw_preview=raw[:300])
    return StitcherOutput(
        transcript=fallback_transcript,
        speaker_map={},
        word_count=len(fallback_transcript.split()),
        languages_detected=["unknown"],
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class StitcherAgent(BaseAgent):
    """
    Processes a single chunk with rolling speaker context from previous chunks.
    Called once per chunk by the orchestrator in sequential order.
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
        """Process one chunk with accumulated speaker context."""
        chunk_index = input.corrected_chunks[0].chunk_index

        previous_context = _format_previous_context(input.previous_chunk_speakers)
        system_prompt = _STITCH_SYSTEM_PROMPT.format(
            previous_context=previous_context,
            chunk_index=chunk_index,
            num_speakers=input.num_speakers,
        )
        input_text = _build_stitcher_input_text(input)

        return await self._call_claude(system_prompt, input_text, input)

    async def _call_claude(
        self,
        system_prompt: str,
        input_text: str,
        stitch_input: StitcherInput,
    ) -> StitcherOutput:
        """
        Call Claude for correction metadata for one chunk.
        max_tokens is 1024 — sufficient for single-chunk JSON metadata.
        Never raises — falls back gracefully on any error.
        """
        fallback_transcript = stitch_input.corrected_chunks[0].transcript
        chunk_index = stitch_input.corrected_chunks[0].chunk_index
        try:
            client = self._get_client()
            response = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": input_text}],
                timeout=60.0,
            )
            raw = response.content[0].text
            return _parse_stitch_response(raw, stitch_input)

        except Exception as exc:
            self.logger.error(
                "stitcher_claude_call_failed",
                chunk_index=chunk_index,
                error=str(exc),
            )
            return StitcherOutput(
                transcript=fallback_transcript,
                speaker_map={},
                word_count=len(fallback_transcript.split()),
                languages_detected=["unknown"],
            )
