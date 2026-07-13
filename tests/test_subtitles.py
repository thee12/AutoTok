from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from autotok.audio_models import NarrationAudioRecord
from autotok.audio_storage import AudioStore
from autotok.errors import UserInputError
from autotok.ingestion import build_manual_text_record
from autotok.script_models import NarrationScriptRecord
from autotok.subtitle_models import SubtitleDocument, SubtitleExportFormat, WordTiming
from autotok.subtitle_storage import SubtitleStore
from autotok.subtitles import (
    DEFAULT_MAX_WORDS_PER_CUE,
    ApproximateAudioDurationStrategy,
    ProviderWordTimingStrategy,
    build_subtitle_document,
    export_ass,
    export_srt,
    export_vtt,
    load_word_timings,
    script_words_from_text,
    validate_subtitle_document,
)
from autotok.transform import DeterministicScriptTransformer
from autotok.tts import LocalWavTtsProvider, build_tts_audio_record

FIXED_TIME = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


def test_approximate_strategy_builds_valid_subtitle_document() -> None:
    script, audio = build_script_and_audio()

    document = build_subtitle_document(
        script=script,
        audio=audio,
        timing_strategy=ApproximateAudioDurationStrategy(),
        export_format=SubtitleExportFormat.SRT,
        created_at=FIXED_TIME,
    )

    assert document.subtitle_id.startswith("subtitle_")
    assert document.script_id == script.script_id
    assert document.audio_id == audio.audio_id
    assert document.metadata.approximate is True
    assert document.metadata.timing_strategy == "approximate_audio_duration"
    assert document.metadata.max_words_per_cue == DEFAULT_MAX_WORDS_PER_CUE
    assert document.cues
    assert all(len(cue.text.split()) <= DEFAULT_MAX_WORDS_PER_CUE for cue in document.cues)
    validate_subtitle_document(document, audio=audio)


def test_provider_word_timing_strategy_uses_supplied_timings() -> None:
    script, audio = build_script_and_audio()
    timings = word_timings_for_script(script)

    document = build_subtitle_document(
        script=script,
        audio=audio,
        timing_strategy=ProviderWordTimingStrategy(timings),
        export_format=SubtitleExportFormat.VTT,
        created_at=FIXED_TIME,
    )

    assert document.metadata.approximate is False
    assert document.metadata.timing_strategy == "provider_word_timings"
    assert document.cues[0].start_seconds == 0.0


def test_provider_word_timing_count_must_match_script() -> None:
    script, audio = build_script_and_audio()
    bad_timings = (WordTiming(word="Only", start_seconds=0.0, end_seconds=0.5),)

    with pytest.raises(UserInputError, match="count"):
        build_subtitle_document(
            script=script,
            audio=audio,
            timing_strategy=ProviderWordTimingStrategy(bad_timings),
        )


def test_load_word_timings_reads_json(tmp_path: Path) -> None:
    path = tmp_path / "timings.json"
    path.write_text(
        json.dumps(
            [
                {"word": "Hello", "start_seconds": 0.0, "end_seconds": 0.5},
                {"word": "world", "start_seconds": 0.5, "end_seconds": 1.0},
            ]
        ),
        encoding="utf-8",
    )

    timings = load_word_timings(path)

    assert [timing.word for timing in timings] == ["Hello", "world"]


def test_subtitle_exports_include_expected_headers_and_timing() -> None:
    script, audio = build_script_and_audio()
    document = build_subtitle_document(
        script=script,
        audio=audio,
        timing_strategy=ApproximateAudioDurationStrategy(),
        created_at=FIXED_TIME,
    )

    srt = export_srt(document)
    vtt = export_vtt(document)
    ass = export_ass(document)

    assert "1\n00:00:00,000 -->" in srt
    assert vtt.startswith("WEBVTT")
    assert "[Events]" in ass
    assert "BorderStyle, Outline, Shadow, Alignment" in ass
    assert "Style: Default,Arial Black,86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000," in ass
    assert ",-1,0,0,0,100,100,0,0,1,5,0,5,80,80,0,1" in ass
    assert "Dialogue:" in ass


def test_subtitle_store_saves_and_exports_formats(tmp_path: Path) -> None:
    script, audio = build_script_and_audio(tmp_path)
    document = build_subtitle_document(
        script=script,
        audio=audio,
        timing_strategy=ApproximateAudioDurationStrategy(),
        created_at=FIXED_TIME,
    )
    store = SubtitleStore(tmp_path / "data")

    stored = store.save(document)
    repeated = store.save(document)
    vtt_path = store.export(document.subtitle_id, SubtitleExportFormat.VTT)
    loaded = store.load(document.subtitle_id)

    assert stored.created is True
    assert repeated.created is False
    assert stored.export_path.suffix == ".srt"
    assert vtt_path.suffix == ".vtt"
    assert loaded.document.subtitle_id == document.subtitle_id
    restored = SubtitleDocument.from_dict(
        json.loads(stored.record_path.read_text(encoding="utf-8"))
    )
    assert restored.cues == document.cues


def build_script_and_audio(
    tmp_path: Path | None = None,
) -> tuple[NarrationScriptRecord, NarrationAudioRecord]:
    story = build_manual_text_record(
        "A subtitle story starts here. It keeps going for readable timing.",
        imported_at=FIXED_TIME,
    )
    script = DeterministicScriptTransformer().transform(story, created_at=FIXED_TIME)
    approved_script = script.approve("2026-06-30T12:00:00Z")
    audio_record, source_audio_path = build_tts_audio_record(
        approved_script,
        provider=LocalWavTtsProvider(),
        created_at=FIXED_TIME,
    )
    if tmp_path is None:
        return approved_script, audio_record
    stored_audio = AudioStore(tmp_path / "data").save(
        audio_record, source_audio_path=source_audio_path
    )
    return approved_script, stored_audio.record


def word_timings_for_script(script: NarrationScriptRecord) -> tuple[WordTiming, ...]:
    words = script_words_from_text(script.full_text)
    return tuple(
        WordTiming(word=word, start_seconds=index * 0.3, end_seconds=(index + 1) * 0.3)
        for index, word in enumerate(words)
    )
