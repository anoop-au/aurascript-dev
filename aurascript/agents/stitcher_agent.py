"""
AuraScript — StitcherAgent (Map-Reduce / Metadata-only).

The LLM is asked only for a small JSON correction payload:
  - speaker_assignments: maps per-chunk local labels → global labels
  - boundary_fixes: targeted [cut-off] repairs
  - languages_detected

All text manipulation (label substitution, boundary repair, concatenation)
is done in Python — the LLM never rewrites the full transcript.

On JSON parse failure the agent falls back to concatenated raw chunks so the
pipeline never crashes.
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
You are AuraScript's transcript analysis engine.

INPUT: A Manglish transcript assembled from sequential audio chunks.
Each chunk is prefixed with its index: === CHUNK N ===
Chunks marked ⚠️ LOW CONFIDENCE were flagged during quality checks — treat with caution.

YOUR TASKS:

TASK 1: GLOBAL SPEAKER UNIFICATION
Speaker labels reset at every chunk boundary. The same person may be called
[Speaker A] in chunk 0 and [Speaker B] in chunk 1.
Analyse conversation context, speaking style, vocabulary, and turn-taking patterns.
Assign globally consistent labels: Speaker 1, Speaker 2, etc.
If genuinely uncertain, use Speaker ? — NEVER guess.

TASK 2: BOUNDARY WORD REPAIR
Find all [cut-off] markers. Look at the adjacent chunk for context.
If you can reconstruct the word with confidence, provide the replacement text.
If not, use [inaudible].

TASK 3: OUTPUT CLEANUP
If you see [overlap] tags, ensure the dialogue flows logically.
If two speakers are talking over each other, separate them into two
distinct timestamped lines — one per speaker.

OUTPUT FORMAT — respond with ONLY this JSON, no other text:
{{
  "speaker_assignments": [
    {{"chunk_index": 0, "local": "Speaker A", "global": "Speaker 1"}},
    {{"chunk_index": 1, "local": "Speaker B", "global": "Speaker 1"}}
  ],
  "boundary_fixes": [
    {{"chunk_index": 1, "original": "[cut-off]", "replacement": "complete_word"}}
  ],
  "languages_detected": ["English", "Malayalam"]
}}

If there are no boundary fixes needed, output an empty array for boundary_fixes.
Expected number of unique speakers: {num_speakers}
"""

# ---------------------------------------------------------------------------
# Input builder
# ---------------------------------------------------------------------------


def _build_stitcher_input_text(stitch_input: StitcherInput) -> str:
    """
    Assemble the transcript text to send to the LLM, with clear chunk index
    markers so the model can reference specific chunks in its JSON output.
    """
    parts: list[str] = []
    for chunk in stitch_input.corrected_chunks:
        is_low_confidence = chunk.chunk_index in stitch_input.low_confidence_indexes
        warning = "⚠️ LOW CONFIDENCE — treat with caution\n" if is_low_confidence else ""
        parts.append(f"=== CHUNK {chunk.chunk_index} ===\n{warning}{chunk.transcript}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Programmatic correction application
# ---------------------------------------------------------------------------


def _apply_corrections(
    stitch_input: StitcherInput,
    speaker_assignments: list[dict],
    boundary_fixes: list[dict],
) -> str:
    """
    Apply LLM-provided corrections to the raw chunk transcripts in Python.

    1. Per-chunk speaker label substitution  (local → global)
    2. Per-chunk boundary word repair        ([cut-off] → completion)
    3. Concatenate all chunks into one transcript
    """
    # Build (chunk_index, local_label) → global_label lookup.
    speaker_lookup: dict[tuple[int, str], str] = {}
    for assignment in speaker_assignments:
        try:
            key = (int(assignment["chunk_index"]), str(assignment["local"]))
            speaker_lookup[key] = str(assignment["global"])
        except (KeyError, ValueError, TypeError):
            continue

    # Build chunk_index → [(original, replacement)] lookup.
    fix_lookup: dict[int, list[tuple[str, str]]] = {}
    for fix in boundary_fixes:
        try:
            idx = int(fix["chunk_index"])
            fix_lookup.setdefault(idx, []).append(
                (str(fix["original"]), str(fix["replacement"]))
            )
        except (KeyError, ValueError, TypeError):
            continue

    processed: list[str] = []
    for chunk in stitch_input.corrected_chunks:
        text = chunk.transcript

        # Replace all local speaker labels for this chunk.
        # Transcript lines look like: [MM:SS] [Speaker A]: …
        local_labels_found = set(re.findall(r"\[Speaker ([^\]]+)\]", text))
        for label_body in local_labels_found:
            local_label = f"Speaker {label_body}"
            global_label = speaker_lookup.get((chunk.chunk_index, local_label))
            if global_label:
                text = text.replace(f"[{local_label}]", f"[{global_label}]")

        # Apply boundary fixes for this chunk (first occurrence each).
        for original, replacement in fix_lookup.get(chunk.chunk_index, []):
            text = text.replace(original, replacement, 1)

        processed.append(text.strip())

    return "\n".join(processed)


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def _parse_stitch_response(raw: str, stitch_input: StitcherInput) -> StitcherOutput:
    """
    Parse the LLM's metadata JSON and apply corrections programmatically.

    Three-tier fallback:
    1. Direct json.loads on the full response.
    2. Regex extraction of the first {...} block.
    3. Plain concatenation of raw chunks — never crashes.
    """
    fallback_transcript = "\n".join(c.transcript for c in stitch_input.corrected_chunks)

    def _build_output(data: dict) -> StitcherOutput:
        speaker_assignments = data.get("speaker_assignments", [])
        boundary_fixes = data.get("boundary_fixes", [])
        languages = [str(l) for l in data.get("languages_detected", ["unknown"])]

        transcript = _apply_corrections(stitch_input, speaker_assignments, boundary_fixes)

        # speaker_map: global_label → "unknown" (descriptions not provided in metadata mode)
        unique_globals = {str(a["global"]) for a in speaker_assignments if "global" in a}
        speaker_map = {g: "unknown" for g in sorted(unique_globals)}

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
    Unifies all chunk transcripts into a single coherent final transcript
    using a Map-Reduce approach: the LLM outputs only correction metadata,
    Python applies the corrections.
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
        """Send chunks to Claude for metadata, apply corrections in Python."""
        await self.emit(self._make_event(StitchingStartedEvent))

        input_text = _build_stitcher_input_text(input)
        system_prompt = _STITCH_SYSTEM_PROMPT.format(num_speakers=input.num_speakers)

        output = await self._call_claude(system_prompt, input_text, input)

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
        stitch_input: StitcherInput,
    ) -> StitcherOutput:
        """
        Call Claude for correction metadata only (not the full transcript).
        max_tokens is 2048 — sufficient for JSON metadata on any realistic job.
        Never raises — falls back gracefully on any error.
        """
        fallback_transcript = "\n".join(
            c.transcript for c in stitch_input.corrected_chunks
        )
        try:
            client = self._get_client()
            response = await client.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": input_text}],
                timeout=60.0,
            )
            raw = response.content[0].text
            return _parse_stitch_response(raw, stitch_input)

        except Exception as exc:
            self.logger.error("stitcher_claude_call_failed", error=str(exc))
            return StitcherOutput(
                transcript=fallback_transcript,
                speaker_map={},
                word_count=len(fallback_transcript.split()),
                languages_detected=["unknown"],
            )
