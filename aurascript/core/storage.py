"""
AuraScript — Safe async file storage.

Design decisions:
- Original filenames from the client are NEVER used; we generate safe names.
- MIME type is validated against both the Content-Type header AND magic bytes.
- Files are streamed in 1 MB chunks; partial files are deleted on size breach.
- python-magic (libmagic) provides the magic-byte check; it must be installed
  on the host (apt install libmagic1 / brew install libmagic).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from uuid import uuid4

import aiofiles
import magic
from fastapi import HTTPException, UploadFile, status

from aurascript.config import settings

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024  # 1 MB streaming chunk

# Magic-byte prefixes that indicate valid audio content.
# python-magic returns a human-readable description string; we check substrings.
_AUDIO_MAGIC_SIGNATURES: tuple[str, ...] = (
    "MPEG",          # MP3
    "WAVE",          # WAV
    "MP4",           # M4A / MP4
    "ISO Media",     # M4A / MP4 variant
    "Ogg",           # OGG
    "WebM",          # WEBM
    "FLAC",          # FLAC
    "AAC",           # AAC (ADTS)
    "Audio",         # Generic catch-all
    "audio",         # Lowercase variant
    "AIFF",          # AIFF (less common)
)


class SafeFileStorage:
    """
    Async-safe file storage layer.

    Methods raise HTTPException for user-facing errors so that calling code
    in routers can use them directly without wrapping.
    """

    async def save_upload(self, file: UploadFile, job_id: str) -> Path:
        """
        Validate and stream *file* to disk.

        Steps:
        1. Validate Content-Type header against the MIME whitelist.
        2. Read the first 512 bytes and validate magic bytes via libmagic.
        3. Stream the remainder to a safe, server-generated filename.
        4. Reject and delete if the total size exceeds MAX_UPLOAD_SIZE_BYTES.

        Returns the resolved absolute Path to the saved file.
        Raises HTTPException (400, 413) on validation failures.
        """
        # ── Step 1: Content-Type header check ────────────────────────────────
        content_type = (file.content_type or "").split(";")[0].strip().lower()
        if content_type not in [m.lower() for m in settings.ALLOWED_AUDIO_MIME_TYPES]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Unsupported media type.",
                    "allowed_types": settings.ALLOWED_AUDIO_MIME_TYPES,
                },
            )

        # ── Step 2: Magic-byte validation ─────────────────────────────────────
        header_bytes = await file.read(512)
        if not header_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "Uploaded file is empty."},
            )

        mime_description = magic.from_buffer(header_bytes)
        if not any(sig in mime_description for sig in _AUDIO_MAGIC_SIGNATURES):
            logger.warning(
                "Magic-byte check failed",
                extra={"mime_description": mime_description, "job_id": job_id},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "File content does not match an audio format."},
            )

        # ── Step 3: Prepare destination path ──────────────────────────────────
        settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = f"{job_id}_{uuid4().hex[:8]}.audio"
        dest: Path = settings.UPLOAD_DIR / safe_name

        # ── Step 4: Stream to disk with size guard ────────────────────────────
        total_bytes = len(header_bytes)
        try:
            async with aiofiles.open(dest, "wb") as fp:
                await fp.write(header_bytes)

                while True:
                    chunk = await file.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > settings.MAX_UPLOAD_SIZE_BYTES:
                        # Stop immediately and remove partial file.
                        break
                    await fp.write(chunk)
        except Exception as exc:
            # Clean up partial file on any I/O error.
            await self._delete_silently(dest)
            logger.error(
                "Upload streaming failed",
                extra={"job_id": job_id, "error": str(exc)},
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "Storage error. Please try again."},
            ) from exc

        if total_bytes > settings.MAX_UPLOAD_SIZE_BYTES:
            await self._delete_silently(dest)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={"error": "File exceeds 700MB limit."},
            )

        logger.debug(
            "Upload saved",
            extra={"job_id": job_id, "path": str(dest), "bytes": total_bytes},
        )
        return dest.resolve()

    async def cleanup_job_files(self, paths: list[Path]) -> dict[str, bool]:
        """
        Delete every path in *paths*.

        One failure does not prevent deletion of the remaining files.
        Returns a mapping of str(path) → True (deleted) / False (failed).
        """
        results: dict[str, bool] = {}
        for path in paths:
            key = str(path)
            try:
                if path.exists():
                    path.unlink()
                    logger.debug("Deleted file", extra={"path": key})
                results[key] = True
            except Exception as exc:
                logger.warning(
                    "Failed to delete file",
                    extra={"path": key, "error": str(exc)},
                )
                results[key] = False
        return results

    async def scan_orphaned_files(self, max_age_hours: int = 2) -> list[Path]:
        """
        Scan UPLOAD_DIR and CHUNKS_DIR for files older than *max_age_hours*.

        Returns a list of orphaned Paths suitable for cleanup on startup.
        """
        cutoff = time.time() - (max_age_hours * 3600)
        orphans: list[Path] = []

        for directory in (settings.UPLOAD_DIR, settings.CHUNKS_DIR):
            if not directory.exists():
                continue
            for path in directory.iterdir():
                if path.is_file() and path.stat().st_mtime < cutoff:
                    orphans.append(path)
                    logger.debug(
                        "Found orphaned file",
                        extra={"path": str(path)},
                    )

        return orphans

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    async def _delete_silently(path: Path) -> None:
        """Attempt to delete *path*, suppressing all errors."""
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
