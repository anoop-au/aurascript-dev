"""
AuraScript — Disk-backed result persistence.

Completed job results are written as JSON to RESULTS_DIR so they survive
WebSocket disconnects, in-memory TTL eviction, and container restarts.
The directory lives on the aurascript_tmp Docker volume (/tmp/aurascript).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


async def save_result(
    results_dir: Path,
    job_id: str,
    transcript: str,
    speaker_map: dict,
    metadata: dict,
) -> None:
    """Write job result to {results_dir}/{job_id}.json (non-blocking)."""
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{job_id}.json"
    data = json.dumps({
        "job_id": job_id,
        "transcript": transcript,
        "speaker_map": speaker_map,
        "metadata": metadata,
    })
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, path.write_text, data)
    logger.debug("result_saved_to_disk", extra={"job_id": job_id})


def load_result(results_dir: Path, job_id: str) -> Optional[dict]:
    """Read {results_dir}/{job_id}.json. Returns None if missing or corrupt."""
    path = results_dir / f"{job_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        logger.warning("result_file_corrupt", extra={"job_id": job_id})
        return None
