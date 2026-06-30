"""Narration audio providers for Phase 3."""

from __future__ import annotations

import hashlib
import math
import struct
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
FAKE_TTS_PROVIDER_NAME = "fake_tts"
FAKE_TTS_PROVIDER_VERSION = "test"
DEFAULT_SAMPLE_RATE_HZ = 16_000
DEFAULT_TONE_HZ = 220
DEFAULT_AMPLITUDE = 0.18


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
