"""Subtitle document models for Phase 4 artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

SUBTITLE_SCHEMA_VERSION = 1


class TimingStrategyName(StrEnum):
    """Supported Phase 4 subtitle timing strategies."""

    PROVIDER_WORD_TIMINGS = "provider_word_timings"
    APPROXIMATE_AUDIO_DURATION = "approximate_audio_duration"


class SubtitleExportFormat(StrEnum):
    """Supported subtitle export formats."""

    SRT = "srt"
    VTT = "vtt"
    ASS = "ass"


@dataclass(frozen=True, slots=True)
class WordTiming:
    """Timing for one spoken word."""

    word: str
    start_seconds: float
    end_seconds: float

    def to_dict(self) -> dict[str, object]:
        """Serialize word timing to JSON-compatible values."""
        return {
            "word": self.word,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> WordTiming:
        """Deserialize word timing."""
        return cls(
            word=_required_str(data, "word"),
            start_seconds=_required_float(data, "start_seconds"),
            end_seconds=_required_float(data, "end_seconds"),
        )


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    """One timed subtitle cue."""

    index: int
    start_seconds: float
    end_seconds: float
    lines: tuple[str, ...]

    @property
    def text(self) -> str:
        """Return cue text with display line breaks."""
        return "\n".join(self.lines)

    def to_dict(self) -> dict[str, object]:
        """Serialize cue to JSON-compatible values."""
        return {
            "index": self.index,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "lines": list(self.lines),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> SubtitleCue:
        """Deserialize subtitle cue."""
        lines = data.get("lines")
        if not isinstance(lines, Sequence) or isinstance(lines, str):
            raise ValueError("lines must be a list of strings.")
        return cls(
            index=_required_int(data, "index"),
            start_seconds=_required_float(data, "start_seconds"),
            end_seconds=_required_float(data, "end_seconds"),
            lines=tuple(_required_sequence_str(lines, "lines")),
        )


@dataclass(frozen=True, slots=True)
class SubtitleMetadata:
    """Subtitle generation metadata and readability settings."""

    timing_strategy: TimingStrategyName
    export_format: SubtitleExportFormat
    max_chars_per_line: int
    max_lines_per_cue: int
    max_words_per_cue: int
    approximate: bool
    source_word_count: int

    def to_dict(self) -> dict[str, object]:
        """Serialize metadata to JSON-compatible values."""
        return {
            "timing_strategy": self.timing_strategy.value,
            "export_format": self.export_format.value,
            "max_chars_per_line": self.max_chars_per_line,
            "max_lines_per_cue": self.max_lines_per_cue,
            "max_words_per_cue": self.max_words_per_cue,
            "approximate": self.approximate,
            "source_word_count": self.source_word_count,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> SubtitleMetadata:
        """Deserialize subtitle metadata."""
        try:
            timing_strategy = TimingStrategyName(_required_str(data, "timing_strategy"))
            export_format = SubtitleExportFormat(_required_str(data, "export_format"))
        except ValueError as exc:
            raise ValueError("Subtitle metadata contains an unsupported enum value.") from exc
        return cls(
            timing_strategy=timing_strategy,
            export_format=export_format,
            max_chars_per_line=_required_int(data, "max_chars_per_line"),
            max_lines_per_cue=_required_int(data, "max_lines_per_cue"),
            max_words_per_cue=_required_int(data, "max_words_per_cue"),
            approximate=_required_bool(data, "approximate"),
            source_word_count=_required_int(data, "source_word_count"),
        )


@dataclass(frozen=True, slots=True)
class SubtitleDocument:
    """Canonical subtitle document generated from narration audio and script."""

    subtitle_id: str
    script_id: str
    audio_id: str
    story_id: str
    created_at: str
    metadata: SubtitleMetadata
    cues: tuple[SubtitleCue, ...]
    schema_version: int = SUBTITLE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        """Serialize document to JSON-compatible values."""
        return {
            "schema_version": self.schema_version,
            "subtitle_id": self.subtitle_id,
            "script_id": self.script_id,
            "audio_id": self.audio_id,
            "story_id": self.story_id,
            "created_at": self.created_at,
            "metadata": self.metadata.to_dict(),
            "cues": [cue.to_dict() for cue in self.cues],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> SubtitleDocument:
        """Deserialize and validate a subtitle document."""
        schema_version = _required_int(data, "schema_version")
        if schema_version != SUBTITLE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported subtitle schema_version: {schema_version}")
        metadata_data = data.get("metadata")
        if not isinstance(metadata_data, Mapping):
            raise ValueError("metadata must be an object.")
        cues_data = data.get("cues")
        if not isinstance(cues_data, Sequence) or isinstance(cues_data, str):
            raise ValueError("cues must be a list.")
        return cls(
            schema_version=schema_version,
            subtitle_id=_required_str(data, "subtitle_id"),
            script_id=_required_str(data, "script_id"),
            audio_id=_required_str(data, "audio_id"),
            story_id=_required_str(data, "story_id"),
            created_at=_required_str(data, "created_at"),
            metadata=SubtitleMetadata.from_dict(metadata_data),
            cues=_cues_from_sequence(cues_data),
        )


def _cues_from_sequence(values: Sequence[object]) -> tuple[SubtitleCue, ...]:
    cues: list[SubtitleCue] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError("Each cue must be an object.")
        cues.append(SubtitleCue.from_dict(value))
    return tuple(cues)


def _required_sequence_str(values: Sequence[object], key: str) -> list[str]:
    strings: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{key} must contain non-empty strings.")
        strings.append(value)
    return strings


def _required_str(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string.")
    return value


def _required_int(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer.")
    return value


def _required_float(data: Mapping[str, object], key: str) -> float:
    value = data.get(key)
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"{key} must be a number.")


def _required_bool(data: Mapping[str, object], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean.")
    return value
