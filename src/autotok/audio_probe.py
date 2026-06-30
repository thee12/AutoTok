"""Audio probing and validation helpers for Phase 3."""

from __future__ import annotations

import hashlib
import wave
from pathlib import Path

from autotok.audio_models import AudioMetadata
from autotok.errors import UnsupportedMediaError, UserInputError

SUPPORTED_WAV_SAMPLE_WIDTHS = {1, 2, 3, 4}
SUPPORTED_WAV_CHANNELS = {1, 2}


def probe_wav_audio(path: Path) -> AudioMetadata:
    """Probe and validate a local WAV PCM file."""
    audio_path = path.expanduser()
    if not audio_path.exists():
        raise UserInputError(f"Audio file does not exist: {audio_path}")
    if not audio_path.is_file():
        raise UserInputError(f"Audio path is not a file: {audio_path}")

    try:
        with wave.open(str(audio_path), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
    except (wave.Error, EOFError) as exc:
        raise UnsupportedMediaError(
            f"Audio file must be a readable WAV PCM file: {audio_path}"
        ) from exc

    if channels not in SUPPORTED_WAV_CHANNELS:
        raise UnsupportedMediaError("Narration WAV audio must be mono or stereo.")
    if sample_width not in SUPPORTED_WAV_SAMPLE_WIDTHS:
        raise UnsupportedMediaError("Narration WAV audio has an unsupported sample width.")
    if sample_rate <= 0:
        raise UnsupportedMediaError("Narration WAV audio has an invalid sample rate.")
    if frame_count <= 0:
        raise UnsupportedMediaError("Narration WAV audio must contain at least one frame.")

    duration_seconds = round(frame_count / sample_rate, 3)
    return AudioMetadata(
        format_name="wav_pcm",
        duration_seconds=duration_seconds,
        sample_rate_hz=sample_rate,
        channels=channels,
        sample_width_bytes=sample_width,
        frame_count=frame_count,
        content_sha256=file_sha256(audio_path),
        file_size_bytes=audio_path.stat().st_size,
    )


def file_sha256(path: Path) -> str:
    """Return a SHA-256 digest for a local file."""
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
