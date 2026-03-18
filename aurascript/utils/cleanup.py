"""
AuraScript — Guaranteed temp file deletion utilities.

Thin wrappers around SafeFileStorage.cleanup_job_files, exposed here so
that agents and the orchestrator can import a single top-level function
without depending directly on the storage layer.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def cleanup_job_files(paths: list[Path]) -> dict[str, bool]:
    """
    Delete every path in *paths*, tolerating individual failures.

    Returns a mapping of str(path) → True (deleted) / False (failed).
    Intentionally re-implemented here as a standalone async function so
    agents can call it without importing core.storage (avoids circular deps).
    """
    results: dict[str, bool] = {}
    for path in paths:
        key = str(path)
        try:
            if path.exists():
                path.unlink()
                logger.debug("Deleted file: %s", key)
            results[key] = True
        except Exception as exc:
            logger.warning("Failed to delete file %s: %s", key, exc)
            results[key] = False
    return results
