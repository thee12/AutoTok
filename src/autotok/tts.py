"""Narration audio providers for Phase 3."""

from __future__ import annotations

import hashlib
import math
import struct
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from autotok.audio_models import AudioSourceType, NarrationAudioRecord
from autotok.audio_probe import file_sha256, probe_wav_audio
from autotok.errors import ProviderError, UserInputError
from autotok.script_models import NarrationScriptRecord, ReviewStatus

DEFAULT_TTS_TIMEOUT_SECONDS = 30
LOCAL_WAV_PROVIDER_NAME = "local_wav"
LOCAL_WAV_PROVIDER_VERSION = "1"
PYTTSX3_PROVIDER_NAME = "pyttsx3"
PYTTSX3_PROVIDER_VERSION = "1"
PYTTSX3_DEFAULT_RATE_WPM = 175
FAKE_TTS_PROVIDER_NAME = "fake_tts"
FAKE_TTS_PROVIDER_VERSION = "test"
DEFAULT_SAMPLE_RATE_HZ = 16_000
DEFAULT_TONE_HZ = 220
DEFAULT_AMPLITUDE = 0.18

_PYTTSX3_CHILD_CODE = r"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import pyttsx3
except ImportError as exc:
    raise SystemExit("pyttsx3 is not installed") from exc

text_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
voice_id = sys.argv[3]
rate_wpm = int(sys.argv[4])
text = text_path.read_text(encoding="utf-8").strip()
if not text:
    raise SystemExit("script text is empty")

engine = pyttsx3.init()
try:
    engine.setProperty("rate", rate_wpm)
    if voice_id:
        voices = engine.getProperty("voices") or []
        known_voice_ids = {str(getattr(voice, "id", "")) for voice in voices}
        if voice_id not in known_voice_ids:
            raise SystemExit(f"pyttsx3 voice was not found: {voice_id}")
        engine.setProperty("voice", voice_id)
    engine.save_to_file(text, str(output_path))
    engine.runAndWait()
finally:
    engine.stop()

if not output_path.exists() or output_path.stat().st_size <= 0:
    raise SystemExit("pyttsx3 did not produce an audio file")
"""


@dataclass(frozen=True, slots=True)
class ProviderAudioResult:
    """A provider-generated temporary audio file and request metadata."""

    audio_path: Path
    provider_request: dict[str, object]


class TtsProvider(Protocol):
    """Provider-independent interface for approved-script narration audio."""

    provider_name: str
    provider_version: str

    def synthesize(
        self,
        script: NarrationScriptRecord,
        *,
        timeout_seconds: int = DEFAULT_TTS_TIMEOUT_SECONDS,
    ) -> ProviderAudioResult:
        """Generate narration audio for an approved script."""


class LocalWavTtsProvider:
    """Local deterministic WAV provider for credential-free Phase 3 development."""

    provider_name = LOCAL_WAV_PROVIDER_NAME
    provider_version = LOCAL_WAV_PROVIDER_VERSION

    def synthesize(
        self,
        script: NarrationScriptRecord,
        *,
        timeout_seconds: int = DEFAULT_TTS_TIMEOUT_SECONDS,
    ) -> ProviderAudioResult:
        """Generate a valid local WAV placeholder for an approved script."""
        validate_tts_request(script, timeout_seconds=timeout_seconds)
        duration_seconds = max(1, script.duration_budget.estimated_seconds)
        audio_path = _temporary_wav_path(prefix="autotok-local-wav-")
        _write_tone_wav(
            audio_path,
            duration_seconds=duration_seconds,
            sample_rate_hz=DEFAULT_SAMPLE_RATE_HZ,
            frequency_hz=DEFAULT_TONE_HZ,
            amplitude=DEFAULT_AMPLITUDE,
        )
        return ProviderAudioResult(
            audio_path=audio_path,
            provider_request={
                "provider": self.provider_name,
                "provider_version": self.provider_version,
                "timeout_seconds": timeout_seconds,
                "script_id": script.script_id,
                "voice": "local-tone-placeholder",
                "duration_seconds": duration_seconds,
                "network": False,
                "paid_call": False,
            },
        )


class Pyttsx3TtsProvider:
    """Offline pyttsx3 provider that uses locally installed system voices."""

    provider_name = PYTTSX3_PROVIDER_NAME
    provider_version = PYTTSX3_PROVIDER_VERSION

    def __init__(self, *, voice_id: str | None = None, rate_wpm: int = PYTTSX3_DEFAULT_RATE_WPM):
        if rate_wpm <= 0:
            raise UserInputError("pyttsx3 rate must be greater than zero words per minute.")
        self.voice_id = voice_id.strip() if voice_id is not None and voice_id.strip() else None
        self.rate_wpm = rate_wpm

    def synthesize(
        self,
        script: NarrationScriptRecord,
        *,
        timeout_seconds: int = DEFAULT_TTS_TIMEOUT_SECONDS,
    ) -> ProviderAudioResult:
        """Generate spoken narration audio with pyttsx3."""
        validate_tts_request(script, timeout_seconds=timeout_seconds)
        audio_path = _temporary_wav_path(prefix="autotok-pyttsx3-")
        text_path = _temporary_text_path(prefix="autotok-pyttsx3-script-")
        text_path.write_text(script.full_text, encoding="utf-8")
        command = [
            sys.executable,
            "-c",
            _PYTTSX3_CHILD_CODE,
            str(text_path),
            str(audio_path),
            self.voice_id or "",
            str(self.rate_wpm),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(
                f"pyttsx3 narration timed out after {timeout_seconds} seconds."
            ) from exc
        finally:
            text_path.unlink(missing_ok=True)

        if completed.returncode != 0:
            message = _clean_provider_stderr(completed.stderr)
            if "pyttsx3 is not installed" in message:
                raise ProviderError(
                    "pyttsx3 is not installed. Install it with "
                    '`python -m pip install -e ".[tts]"` or `python -m pip install pyttsx3`.'
                )
            raise ProviderError(f"pyttsx3 narration failed: {message}")

        return ProviderAudioResult(
            audio_path=audio_path,
            provider_request={
                "provider": self.provider_name,
                "provider_version": self.provider_version,
                "timeout_seconds": timeout_seconds,
                "script_id": script.script_id,
                "voice": self.voice_id or "system-default",
                "rate_wpm": self.rate_wpm,
                "network": False,
                "paid_call": False,
            },
        )


class FakeTtsProvider:
    """Deterministic test double for narration audio provider tests."""

    provider_name = FAKE_TTS_PROVIDER_NAME
    provider_version = FAKE_TTS_PROVIDER_VERSION

    def synthesize(
        self,
        script: NarrationScriptRecord,
        *,
        timeout_seconds: int = DEFAULT_TTS_TIMEOUT_SECONDS,
    ) -> ProviderAudioResult:
        """Generate a tiny deterministic WAV fixture for tests."""
        validate_tts_request(script, timeout_seconds=timeout_seconds)
        audio_path = _temporary_wav_path(prefix="autotok-fake-tts-")
        _write_tone_wav(
            audio_path,
            duration_seconds=1,
            sample_rate_hz=8_000,
            frequency_hz=440,
            amplitude=0.1,
        )
        return ProviderAudioResult(
            audio_path=audio_path,
            provider_request={
                "provider": self.provider_name,
                "provider_version": self.provider_version,
                "timeout_seconds": timeout_seconds,
                "script_id": script.script_id,
                "voice": "fake-test-tone",
                "duration_seconds": 1,
                "network": False,
                "paid_call": False,
            },
        )


def build_tts_audio_record(
    script: NarrationScriptRecord,
    *,
    provider: TtsProvider,
    timeout_seconds: int = DEFAULT_TTS_TIMEOUT_SECONDS,
    created_at: datetime | None = None,
) -> tuple[NarrationAudioRecord, Path]:
    """Generate, validate, and describe narration audio from an approved script."""
    result = provider.synthesize(script, timeout_seconds=timeout_seconds)
    metadata = probe_wav_audio(result.audio_path)
    timestamp = _utc_timestamp(created_at)
    audio_id = stable_audio_id(
        script_id=script.script_id,
        source_type=AudioSourceType.TTS_GENERATED,
        provider_name=provider.provider_name,
        provider_version=provider.provider_version,
        content_sha256=metadata.content_sha256,
    )
    return (
        NarrationAudioRecord(
            audio_id=audio_id,
            script_id=script.script_id,
            story_id=script.story_id,
            source_type=AudioSourceType.TTS_GENERATED,
            provider_name=provider.provider_name,
            provider_version=provider.provider_version,
            created_at=timestamp,
            metadata=metadata,
            provider_request=result.provider_request,
            source_path=None,
            normalized=False,
        ),
        result.audio_path,
    )


def build_manual_audio_record(
    script: NarrationScriptRecord,
    *,
    audio_path: Path,
    created_at: datetime | None = None,
) -> NarrationAudioRecord:
    """Validate and describe manually supplied narration audio for an approved script."""
    validate_script_approved(script)
    source_path = audio_path.expanduser()
    metadata = probe_wav_audio(source_path)
    timestamp = _utc_timestamp(created_at)
    audio_id = stable_audio_id(
        script_id=script.script_id,
        source_type=AudioSourceType.MANUAL_FILE,
        provider_name="manual",
        provider_version="1",
        content_sha256=metadata.content_sha256,
    )
    return NarrationAudioRecord(
        audio_id=audio_id,
        script_id=script.script_id,
        story_id=script.story_id,
        source_type=AudioSourceType.MANUAL_FILE,
        provider_name="manual",
        provider_version="1",
        created_at=timestamp,
        metadata=metadata,
        provider_request={
            "provider": "manual",
            "provider_version": "1",
            "source_sha256": file_sha256(source_path),
            "network": False,
            "paid_call": False,
        },
        source_path=str(source_path.resolve()),
        normalized=False,
    )


def validate_tts_request(script: NarrationScriptRecord, *, timeout_seconds: int) -> None:
    """Validate common provider request requirements."""
    validate_script_approved(script)
    if timeout_seconds <= 0:
        raise ProviderError("TTS timeout must be greater than zero seconds.")


def validate_script_approved(script: NarrationScriptRecord) -> None:
    """Require explicit script approval before narration audio is produced."""
    if script.review_status is not ReviewStatus.APPROVED:
        raise UserInputError(
            "Narration audio requires an approved script. Run `autotok script approve` first."
        )


def stable_audio_id(
    *,
    script_id: str,
    source_type: AudioSourceType,
    provider_name: str,
    provider_version: str,
    content_sha256: str,
) -> str:
    """Build a stable audio ID from script, source, provider, and file hash."""
    payload = "\n".join(
        [script_id, source_type.value, provider_name, provider_version, content_sha256]
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return f"audio_{digest[:16]}"


def _temporary_wav_path(*, prefix: str) -> Path:
    with tempfile.NamedTemporaryFile(prefix=prefix, suffix=".wav", delete=False) as handle:
        return Path(handle.name)


def _temporary_text_path(*, prefix: str) -> Path:
    with tempfile.NamedTemporaryFile(prefix=prefix, suffix=".txt", delete=False) as handle:
        return Path(handle.name)


def _clean_provider_stderr(value: str) -> str:
    message = value.strip()
    if not message:
        return "provider exited without an error message"
    return " ".join(message.splitlines())


def _write_tone_wav(
    path: Path,
    *,
    duration_seconds: int,
    sample_rate_hz: int,
    frequency_hz: int,
    amplitude: float,
) -> None:
    frame_count = max(1, duration_seconds * sample_rate_hz)
    max_amplitude = int(32767 * amplitude)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate_hz)
        for frame_index in range(frame_count):
            phase = (2 * math.pi * frequency_hz * frame_index) / sample_rate_hz
            sample = int(max_amplitude * math.sin(phase))
            wav_file.writeframesraw(struct.pack("<h", sample))
        wav_file.writeframes(b"")


def _utc_timestamp(value: datetime | None) -> str:
    timestamp = datetime.now(UTC) if value is None else value.astimezone(UTC)
    return timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
