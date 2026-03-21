"""
AuraScript — QualityAgent.

Evaluates a single chunk's transcript quality through two layers:
1. Heuristic checks (always run, no API call) — fast and free.
2. AI validation via Gemini Flash (only when heuristic_score < 0.7).

Final score formula:
  - AI ran:     (heuristic * 0.4) + (ai_score * 0.6)
  - AI skipped: heuristic_score
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional

import structlog

try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

from aurascript.agents.base_agent import BaseAgent
from aurascript.config import Settings
from aurascript.models.agent_state import (
    QualityInput,
    QualityOutput,
    TranscriptionMetadata,
)
from aurascript.models.events import AgentDecisionEvent, QualityCheckedEvent
from aurascript.services.event_bus import EventBus

logger = structlog.get_logger(__name__)

_TIMESTAMP_RE = re.compile(r"\[\d{2}:\d{2}\]")

_AI_QUALITY_PROMPT = """\
Review this Manglish transcript chunk for transcription quality.

Penalize:
- Invented words not matching Manglish phonetics
- Missing speaker changes
- Timestamp format errors
- Signs of hallucination (words that couldn't have been spoken)
- English translations where native words should appear

Respond in STRICT JSON, no other text:
{"score": <float 0.0-1.0>, "issues": [<strings>], \
"recommendation": "<accept|retry|flag>"}

TRANSCRIPT:
{transcript}
"""


def _compute_heuristic_score(
    transcript: str,
    chunk_index: int,
    total_chunks: int,
    metadata: TranscriptionMetadata,
) -> tuple[float, list[str]]:
    """
    Run fast heuristic checks on *transcript* and return (score, issues).

    No API calls. Score starts at 1.0 and penalties are subtracted.
    The result is blended 50/50 with the model's own confidence field.
    """
    score = 1.0
    issues: list[str] = []
    word_count = len(transcript.split())

    # ── Word count penalties ──────────────────────────────────────────────────
    if word_count < 30:
        score -= 0.4
        issues.append("very_few_words")
    elif word_count < 60:
        score -= 0.2
        issues.append("few_words")

    # ── Inaudible marker ratio ────────────────────────────────────────────────
    inaudible_count = transcript.count("[inaudible]")
    inaudible_ratio = inaudible_count / max(word_count, 1)
    if inaudible_ratio > 0.2:
        score -= 0.3
        issues.append("high_inaudible_ratio")
    elif inaudible_ratio > 0.1:
        score -= 0.1
        issues.append("moderate_inaudible_ratio")

    # ── Unexpected cut-off markers ────────────────────────────────────────────
    cutoff_count = transcript.count("[cut-off]")
    is_last_chunk = chunk_index == total_chunks - 1
    if cutoff_count > 0 and not is_last_chunk:
        score -= 0.15
        issues.append("unexpected_cutoff")

    # ── Missing timestamp format ──────────────────────────────────────────────
    timestamp_count = len(_TIMESTAMP_RE.findall(transcript))
    if timestamp_count == 0:
        score -= 0.3
        issues.append("missing_timestamps")

    # ── Blend with model confidence (50/50) ──────────────────────────────────
    blended = (score * 0.5) + (metadata.confidence * 0.5)
    return max(0.0, min(1.0, blended)), issues


class QualityAgent(BaseAgent):
    """
    Scores a single chunk's transcript quality and recommends accept/retry/flag.
    """

    def __init__(
        self,
        job_id: str,
        event_bus: EventBus,
        settings: Settings,
    ) -> None:
        super().__init__(job_id, event_bus, settings)
        self._model: Optional[object] = None

    def _get_client(self) -> "genai.Client":
        if not _GENAI_AVAILABLE:
            raise RuntimeError("google-genai not installed.")
        if self._model is None:
            self._model = genai.Client(api_key=self.settings.GEMINI_API_KEY)
        return self._model  # type: ignore[return-value]

    async def run(self, input: QualityInput) -> QualityOutput:
        """
        Evaluate *input.transcript* and return a QualityOutput.

        Steps:
        1. Run heuristic checks.
        2. If heuristic_score < 0.7, call Gemini for AI validation.
        3. Compute final score and recommendation.
        4. Emit QualityCheckedEvent and AgentDecisionEvent.
        """
        total_chunks = getattr(input, "total_chunks", 1)

        heuristic_score, heuristic_issues = _compute_heuristic_score(
            transcript=input.transcript,
            chunk_index=input.chunk_index,
            total_chunks=total_chunks,
            metadata=input.transcription_metadata,
        )

        ai_score: Optional[float] = None
        ai_issues: list[str] = []
        ai_recommendation: Optional[str] = None

        if heuristic_score < 0.7:
            self.logger.info(
                "heuristic_score_low_triggering_ai",
                chunk_index=input.chunk_index,
                heuristic_score=round(heuristic_score, 3),
            )
            ai_score, ai_issues, ai_recommendation = await self._ai_validate(
                input.transcript, input.chunk_index
            )

        # ── Final score ───────────────────────────────────────────────────────
        if ai_score is not None:
            final_score = (heuristic_score * 0.4) + (ai_score * 0.6)
        else:
            final_score = heuristic_score
        final_score = max(0.0, min(1.0, final_score))

        # ── Recommendation ────────────────────────────────────────────────────
        if ai_recommendation:
            recommendation = ai_recommendation
        elif final_score >= self.settings.QUALITY_SCORE_THRESHOLD:
            recommendation = "accept"
        elif final_score >= self.settings.LOW_CONFIDENCE_THRESHOLD:
            recommendation = "retry"
        else:
            recommendation = "flag"

        all_issues = list(dict.fromkeys(heuristic_issues + ai_issues))

        output = QualityOutput(
            final_score=round(final_score, 4),
            heuristic_score=round(heuristic_score, 4),
            ai_score=round(ai_score, 4) if ai_score is not None else None,
            recommendation=recommendation,
            issues=all_issues,
        )

        await self.emit(
            self._make_event(
                QualityCheckedEvent,
                chunk_index=input.chunk_index,
                score=output.final_score,
                decision=recommendation,
                issues=all_issues,
            )
        )

        await self.emit(
            self._make_event(
                AgentDecisionEvent,
                agent="QualityAgent",
                decision=recommendation,
                reason=(
                    f"final_score={output.final_score:.3f} "
                    f"(heuristic={output.heuristic_score:.3f}"
                    + (
                        f", ai={output.ai_score:.3f}"
                        if output.ai_score is not None
                        else ""
                    )
                    + f") issues={all_issues}"
                ),
            )
        )

        self.logger.info(
            "quality_evaluated",
            chunk_index=input.chunk_index,
            final_score=output.final_score,
            recommendation=recommendation,
        )

        return output

    async def _ai_validate(
        self,
        transcript: str,
        chunk_index: int,
    ) -> tuple[float, list[str], str]:
        """
        Call Gemini to validate the transcript. Returns (score, issues, recommendation).

        On any failure (parse error, API error), returns safe defaults and logs.
        Never raises.
        """
        _default = (0.7, [], "accept")

        try:
            client = self._get_client()
            prompt = _AI_QUALITY_PROMPT.format(transcript=transcript[:4000])

            response = await client.aio.models.generate_content(
                model=self.settings.VERTEX_AI_MODEL_QUALITY,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=512,
                    response_mime_type="application/json",
                ),
            )

            raw = response.text.strip()
            data = json.loads(raw)

            score = float(data.get("score", 0.7))
            score = max(0.0, min(1.0, score))
            issues = [str(i) for i in data.get("issues", [])]
            recommendation = str(data.get("recommendation", "accept"))
            if recommendation not in ("accept", "retry", "flag"):
                recommendation = "accept"

            return score, issues, recommendation

        except json.JSONDecodeError as exc:
            self.logger.warning(
                "ai_quality_json_parse_failed",
                chunk_index=chunk_index,
                error=str(exc),
            )
            return _default

        except Exception as exc:
            self.logger.warning(
                "ai_quality_call_failed",
                chunk_index=chunk_index,
                error=str(exc),
            )
            return _default
