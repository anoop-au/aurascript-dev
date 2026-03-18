"""
AuraScript — Audio processor tests.

All ffprobe/ffmpeg calls are intercepted by mocking
asyncio.create_subprocess_exec so no real binary is required.

Covers:
- Successful analyze_audio returns correct AudioAnalysis
- Very low sample rate (<8000 Hz) generates warning
- Low sample rate (<16000 Hz) generates warning
- Multi-channel (>2) audio generates warning
- Duration > 1 hour generates warning
- Duration exceeding MAX_AUDIO_DURATION_SECONDS raises AudioProcessingError
- ffprobe non-zero exit raises AudioProcessingError
- No audio stream in file raises AudioProcessingError
- ffprobe not found (FileNotFoundError) raises AudioProcessingError
- VBR audio (bit_rate "N/A") sets bitrate_kbps to None
- chunk_audio success returns sorted list of Paths
- ffmpeg non-zero exit raises AudioProcessingError
- Zero chunks produced raises AudioProcessingError
- ffmpeg not found raises AudioProcessingError
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aurascript.config import settings
from aurascript.services.audio_processor import (
    AudioProcessingError,
    analyze_audio,
    chunk_audio,
)
from aurascript.models.agent_state import AudioAnalysis


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_ffprobe_output(
    duration: float = 120.0,
    sample_rate: int = 44100,
    channels: int = 2,
    codec: str = "mp3",
    bit_rate: str = "128000",
) -> bytes:
    """Build a minimal ffprobe JSON payload."""
    probe = {
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": codec,
                "sample_rate": str(sample_rate),
                "channels": channels,
                "bit_rate": bit_rate,
                "duration": str(duration),
            }
        ],
        "format": {
            "duration": str(duration),
            "bit_rate": bit_rate,
        },
    }
    return json.dumps(probe).encode()


def _mock_proc(
    stdout: bytes = b"",
    stderr: bytes = b"",
    returncode: int = 0,
) -> MagicMock:
    """Create a mock asyncio.Process that behaves like communicate() returns."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


def _patch_exec(proc: MagicMock):
    """Patch asyncio.create_subprocess_exec to return *proc*."""
    return patch(
        "aurascript.services.audio_processor.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=proc),
    )


# ── analyze_audio — success ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_audio_returns_correct_analysis(tmp_path: Path) -> None:
    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(b"\xff\xfb" * 100)  # dummy content

    proc = _mock_proc(stdout=_make_ffprobe_output(
        duration=120.0, sample_rate=44100, channels=2,
        codec="mp3", bit_rate="128000",
    ))

    with _patch_exec(proc):
        result = await analyze_audio(audio_file)

    assert isinstance(result, AudioAnalysis)
    assert result.duration_seconds == 120.0
    assert result.sample_rate == 44100
    assert result.channels == 2
    assert result.codec == "mp3"
    assert result.bitrate_kbps == 128
    assert result.is_stereo is True
    assert result.warnings == []


@pytest.mark.asyncio
async def test_analyze_audio_mono_sets_is_stereo_false(tmp_path: Path) -> None:
    audio_file = tmp_path / "mono.wav"
    audio_file.write_bytes(b"RIFF")

    proc = _mock_proc(stdout=_make_ffprobe_output(channels=1))

    with _patch_exec(proc):
        result = await analyze_audio(audio_file)

    assert result.is_stereo is False
    assert result.channels == 1


@pytest.mark.asyncio
async def test_analyze_audio_vbr_sets_bitrate_none(tmp_path: Path) -> None:
    audio_file = tmp_path / "vbr.ogg"
    audio_file.write_bytes(b"OggS")

    proc = _mock_proc(
        stdout=_make_ffprobe_output(bit_rate="N/A"),
    )

    with _patch_exec(proc):
        result = await analyze_audio(audio_file)

    assert result.bitrate_kbps is None


@pytest.mark.asyncio
async def test_analyze_audio_zero_bitrate_sets_bitrate_none(
    tmp_path: Path,
) -> None:
    audio_file = tmp_path / "unknown.flac"
    audio_file.write_bytes(b"fLaC")

    proc = _mock_proc(stdout=_make_ffprobe_output(bit_rate="0"))

    with _patch_exec(proc):
        result = await analyze_audio(audio_file)

    assert result.bitrate_kbps is None


# ── analyze_audio — quality warnings ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_audio_very_low_sample_rate_warning(
    tmp_path: Path,
) -> None:
    audio_file = tmp_path / "low.mp3"
    audio_file.write_bytes(b"\xff\xfb")

    proc = _mock_proc(stdout=_make_ffprobe_output(sample_rate=6000))

    with _patch_exec(proc):
        result = await analyze_audio(audio_file)

    assert len(result.warnings) == 1
    assert "Very low sample rate" in result.warnings[0]
    assert "6000" in result.warnings[0]


@pytest.mark.asyncio
async def test_analyze_audio_low_sample_rate_warning(tmp_path: Path) -> None:
    audio_file = tmp_path / "low.mp3"
    audio_file.write_bytes(b"\xff\xfb")

    proc = _mock_proc(stdout=_make_ffprobe_output(sample_rate=11025))

    with _patch_exec(proc):
        result = await analyze_audio(audio_file)

    assert len(result.warnings) == 1
    assert "Low sample rate" in result.warnings[0]
    assert "11025" in result.warnings[0]


@pytest.mark.asyncio
async def test_analyze_audio_multichannel_warning(tmp_path: Path) -> None:
    audio_file = tmp_path / "surround.wav"
    audio_file.write_bytes(b"RIFF")

    proc = _mock_proc(stdout=_make_ffprobe_output(channels=6))

    with _patch_exec(proc):
        result = await analyze_audio(audio_file)

    assert any("Multi-channel" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_analyze_audio_over_one_hour_warning(tmp_path: Path) -> None:
    audio_file = tmp_path / "long.mp3"
    audio_file.write_bytes(b"\xff\xfb")

    proc = _mock_proc(stdout=_make_ffprobe_output(duration=4000.0))

    with _patch_exec(proc):
        result = await analyze_audio(audio_file)

    assert any("exceeds 1 hour" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_normal_audio_produces_no_warnings(tmp_path: Path) -> None:
    audio_file = tmp_path / "good.mp3"
    audio_file.write_bytes(b"\xff\xfb")

    proc = _mock_proc(stdout=_make_ffprobe_output(
        duration=300.0, sample_rate=44100, channels=2,
    ))

    with _patch_exec(proc):
        result = await analyze_audio(audio_file)

    assert result.warnings == []


# ── analyze_audio — error paths ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_audio_duration_exceeds_limit_raises(
    tmp_path: Path,
) -> None:
    audio_file = tmp_path / "huge.mp3"
    audio_file.write_bytes(b"\xff\xfb")

    over_limit = float(settings.MAX_AUDIO_DURATION_SECONDS + 60)
    proc = _mock_proc(stdout=_make_ffprobe_output(duration=over_limit))

    with _patch_exec(proc):
        with pytest.raises(AudioProcessingError) as exc_info:
            await analyze_audio(audio_file)

    assert "hard limit" in str(exc_info.value).lower() or "limit" in str(
        exc_info.value
    )


@pytest.mark.asyncio
async def test_analyze_audio_nonzero_returncode_raises(tmp_path: Path) -> None:
    audio_file = tmp_path / "bad.mp3"
    audio_file.write_bytes(b"\xff\xfb")

    proc = _mock_proc(
        stdout=b"", stderr=b"No such file", returncode=1
    )

    with _patch_exec(proc):
        with pytest.raises(AudioProcessingError) as exc_info:
            await analyze_audio(audio_file)

    err = exc_info.value
    assert err.returncode == 1


@pytest.mark.asyncio
async def test_analyze_audio_no_audio_stream_raises(tmp_path: Path) -> None:
    audio_file = tmp_path / "video_only.mp4"
    audio_file.write_bytes(b"ftyp")

    probe_no_audio = json.dumps({
        "streams": [{"codec_type": "video", "codec_name": "h264"}],
        "format": {"duration": "10.0"},
    }).encode()

    proc = _mock_proc(stdout=probe_no_audio)

    with _patch_exec(proc):
        with pytest.raises(AudioProcessingError) as exc_info:
            await analyze_audio(audio_file)

    assert "No audio stream" in str(exc_info.value)


@pytest.mark.asyncio
async def test_analyze_audio_ffprobe_not_found_raises(tmp_path: Path) -> None:
    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(b"\xff\xfb")

    with patch(
        "aurascript.services.audio_processor.asyncio.create_subprocess_exec",
        side_effect=FileNotFoundError("ffprobe not found"),
    ):
        with pytest.raises(AudioProcessingError) as exc_info:
            await analyze_audio(audio_file)

    assert "ffprobe not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_analyze_audio_invalid_json_raises(tmp_path: Path) -> None:
    audio_file = tmp_path / "corrupt.mp3"
    audio_file.write_bytes(b"\xff\xfb")

    proc = _mock_proc(stdout=b"this is not json", returncode=0)

    with _patch_exec(proc):
        with pytest.raises(AudioProcessingError) as exc_info:
            await analyze_audio(audio_file)

    assert "invalid JSON" in str(exc_info.value).lower() or "JSON" in str(
        exc_info.value
    )


# ── chunk_audio — success ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chunk_audio_returns_sorted_chunk_paths(tmp_path: Path) -> None:
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"\xff\xfb")

    analysis = AudioAnalysis(
        duration_seconds=600.0, sample_rate=44100, channels=2,
        codec="mp3", is_stereo=True,
    )

    job_id = "test-chunk-job"
    chunk_dir = settings.CHUNKS_DIR / job_id
    chunk_dir.mkdir(parents=True, exist_ok=True)

    # Create fake chunk files so the glob succeeds.
    (chunk_dir / "chunk_0000.mp3").write_bytes(b"\xff\xfb")
    (chunk_dir / "chunk_0001.mp3").write_bytes(b"\xff\xfb")
    (chunk_dir / "chunk_0002.mp3").write_bytes(b"\xff\xfb")

    proc = _mock_proc(stdout=b"", stderr=b"", returncode=0)

    with _patch_exec(proc):
        result = await chunk_audio(audio_file, job_id, analysis)

    assert len(result) == 3
    names = [p.name for p in result]
    assert names == sorted(names)
    assert all(p.suffix == ".mp3" for p in result)


@pytest.mark.asyncio
async def test_chunk_audio_creates_output_directory(tmp_path: Path) -> None:
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"\xff\xfb")

    analysis = AudioAnalysis(
        duration_seconds=60.0, sample_rate=16000, channels=1,
        codec="mp3", is_stereo=False,
    )

    job_id = "dir-create-job"
    expected_dir = settings.CHUNKS_DIR / job_id

    # Ensure directory does NOT exist before the call.
    if expected_dir.exists():
        for f in expected_dir.iterdir():
            f.unlink()
        expected_dir.rmdir()

    # Create chunk files for glob to find (simulating ffmpeg output).
    proc = _mock_proc(returncode=0)

    async def side_effect_create_dir(*args, **kwargs):
        # Simulate ffmpeg writing a chunk file.
        expected_dir.mkdir(parents=True, exist_ok=True)
        (expected_dir / "chunk_0000.mp3").write_bytes(b"\xff\xfb")
        return proc

    with patch(
        "aurascript.services.audio_processor.asyncio.create_subprocess_exec",
        side_effect=side_effect_create_dir,
    ):
        result = await chunk_audio(audio_file, job_id, analysis)

    assert expected_dir.exists()
    assert len(result) == 1


# ── chunk_audio — error paths ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chunk_audio_ffmpeg_nonzero_exit_raises(tmp_path: Path) -> None:
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"\xff\xfb")

    analysis = AudioAnalysis(
        duration_seconds=60.0, sample_rate=44100, channels=2,
        codec="mp3", is_stereo=True,
    )

    proc = _mock_proc(
        stdout=b"", stderr=b"Invalid data found", returncode=1
    )

    with _patch_exec(proc):
        with pytest.raises(AudioProcessingError) as exc_info:
            await chunk_audio(audio_file, "fail-job", analysis)

    err = exc_info.value
    assert err.returncode == 1
    assert "Invalid data found" in (err.ffmpeg_stderr or "")


@pytest.mark.asyncio
async def test_chunk_audio_zero_chunks_raises(tmp_path: Path) -> None:
    audio_file = tmp_path / "silent.mp3"
    audio_file.write_bytes(b"\xff\xfb")

    analysis = AudioAnalysis(
        duration_seconds=60.0, sample_rate=44100, channels=2,
        codec="mp3", is_stereo=True,
    )

    job_id = "zero-chunks-job"
    chunk_dir = settings.CHUNKS_DIR / job_id
    chunk_dir.mkdir(parents=True, exist_ok=True)
    # No chunk files created — simulates ffmpeg silently producing nothing.

    proc = _mock_proc(returncode=0)

    with _patch_exec(proc):
        with pytest.raises(AudioProcessingError) as exc_info:
            await chunk_audio(audio_file, job_id, analysis)

    assert "zero chunks" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_chunk_audio_ffmpeg_not_found_raises(tmp_path: Path) -> None:
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"\xff\xfb")

    analysis = AudioAnalysis(
        duration_seconds=60.0, sample_rate=44100, channels=2,
        codec="mp3", is_stereo=True,
    )

    with patch(
        "aurascript.services.audio_processor.asyncio.create_subprocess_exec",
        side_effect=FileNotFoundError("ffmpeg: No such file"),
    ):
        with pytest.raises(AudioProcessingError) as exc_info:
            await chunk_audio(audio_file, "no-ffmpeg-job", analysis)

    assert "ffmpeg not found" in str(exc_info.value).lower()


# ── AudioProcessingError str representation ───────────────────────────────────


def test_audio_processing_error_str_includes_all_fields() -> None:
    err = AudioProcessingError(
        message="Something failed",
        ffmpeg_stderr="error: codec not found",
        returncode=1,
    )
    s = str(err)
    assert "Something failed" in s
    assert "returncode=1" in s
    assert "codec not found" in s


def test_audio_processing_error_minimal_str() -> None:
    err = AudioProcessingError("Simple error")
    assert str(err) == "Simple error"
    assert err.ffmpeg_stderr is None
    assert err.returncode is None
