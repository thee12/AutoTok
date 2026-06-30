from __future__ import annotations

import json
import struct
import wave
from datetime import UTC, datetime
from pathlib import Path

import pytest

from autotok.audio_models import AudioSourceType, NarrationAudioRecord
from autotok.audio_probe import probe_wav_audio
from autotok.audio_storage import AudioStore
from autotok.errors import UnsupportedMediaError, UserInputError
from autotok.ingestion import build_manual_text_record
from autotok.script_models import NarrationScriptRecord
from autotok.transform import DeterministicScriptTransformer
from autotok.tts import (
    FakeTtsProvider,
    LocalWavTtsProvider,
    build_manual_audio_record,
    build_tts_audio_record,
)

FIXED_TIME = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


def test_probe_wav_audio_returns_metadata(tmp_path: Path) -> None:
    audio_path = tmp_path / "narration.wav"
    write_test_wav(audio_path, sample_rate=8_000, frame_count=8_000)

    metadata = probe_wav_audio(audio_path)

    assert metadata.format_name == "wav_pcm"
    assert metadata.duration_seconds == 1.0
    assert metadata.sample_rate_hz == 8_000
    assert metadata.channels == 1
    assert metadata.frame_count == 8_000
    assert metadata.file_size_bytes > 0


def test_probe_wav_audio_rejects_invalid_file(tmp_path: Path) -> None:
    bad_path = tmp_path / "not-a-wav.wav"
    bad_path.write_text("nope", encoding="utf-8")

    with pytest.raises(UnsupportedMediaError, match="WAV PCM"):
        probe_wav_audio(bad_path)


def test_local_wav_provider_requires_approved_script() -> None:
    script = build_pending_script()

    with pytest.raises(UserInputError, match="approved script"):
        build_tts_audio_record(script, provider=LocalWavTtsProvider(), created_at=FIXED_TIME)


def test_fake_tts_provider_generates_valid_record() -> None:
    script = build_pending_script().approve("2026-06-30T12:00:00Z")

    record, audio_path = build_tts_audio_record(
        script,
        provider=FakeTtsProvider(),
        created_at=FIXED_TIME,
    )

    assert record.audio_id.startswith("audio_")
    assert record.source_type is AudioSourceType.TTS_GENERATED
    assert record.provider_name == "fake_tts"
    assert record.metadata.duration_seconds == 1.0
    assert record.provider_request["paid_call"] is False
    assert audio_path.exists()


def test_manual_audio_record_preserves_source_path(tmp_path: Path) -> None:
    script = build_pending_script().approve("2026-06-30T12:00:00Z")
    audio_path = tmp_path / "manual.wav"
    write_test_wav(audio_path, sample_rate=16_000, frame_count=16_000)

    record = build_manual_audio_record(script, audio_path=audio_path, created_at=FIXED_TIME)

    assert record.source_type is AudioSourceType.MANUAL_FILE
    assert record.provider_name == "manual"
    assert record.source_path == str(audio_path.resolve())
    assert record.metadata.duration_seconds == 1.0


def test_audio_store_saves_and_loads_audio(tmp_path: Path) -> None:
    script = build_pending_script().approve("2026-06-30T12:00:00Z")
    record, source_audio_path = build_tts_audio_record(
        script,
        provider=FakeTtsProvider(),
        created_at=FIXED_TIME,
    )
    store = AudioStore(tmp_path / "data")

    stored = store.save(record, source_audio_path=source_audio_path)
    repeated = store.save(record, source_audio_path=source_audio_path)
    loaded = store.load(record.audio_id)

    assert stored.created is True
    assert repeated.created is False
    assert loaded.record.audio_id == record.audio_id
    assert loaded.audio_path.read_bytes() == source_audio_path.read_bytes()
    payload = json.loads(loaded.record_path.read_text(encoding="utf-8"))
    restored = NarrationAudioRecord.from_dict(payload)
    assert restored.metadata.content_sha256 == record.metadata.content_sha256


def build_pending_script() -> NarrationScriptRecord:
    story = build_manual_text_record("A source story for narration.", imported_at=FIXED_TIME)
    return DeterministicScriptTransformer().transform(story, created_at=FIXED_TIME)


def write_test_wav(path: Path, *, sample_rate: int, frame_count: int) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frame = struct.pack("<h", 0)
        for _ in range(frame_count):
            wav_file.writeframesraw(frame)
        wav_file.writeframes(b"")
