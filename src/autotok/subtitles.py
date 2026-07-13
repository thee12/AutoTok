"""Subtitle timing, validation, and export helpers for Phase 4."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from autotok.audio_models import NarrationAudioRecord
from autotok.errors import UserInputError
from autotok.script_models import NarrationScriptRecord
from autotok.subtitle_models import (
    SubtitleCue,
    SubtitleDocument,
    SubtitleExportFormat,
    SubtitleMetadata,
    TimingStrategyName,
    WordTiming,
)

DEFAULT_MAX_CHARS_PER_LINE = 42
DEFAULT_MAX_LINES_PER_CUE = 2
DEFAULT_MAX_WORDS_PER_CUE = 4
MIN_CUE_DURATION_SECONDS = 0.25
ASS_FONT_NAME = "Arial Black"
ASS_FONT_SIZE = 86
ASS_PRIMARY_COLOUR = "&H00FFFFFF"
ASS_SECONDARY_COLOUR = "&H00FFFFFF"
ASS_OUTLINE_COLOUR = "&H00000000"
ASS_BACK_COLOUR = "&H00000000"
ASS_BOLD = -1
ASS_BORDER_STYLE = 1
ASS_OUTLINE_WIDTH = 5
ASS_SHADOW_DEPTH = 0
ASS_ALIGNMENT_MIDDLE_CENTER = 5
_WORD_PATTERN = re.compile(r"\S+")


class SubtitleTimingStrategy(Protocol):
    """Provider-independent interface for subtitle timing strategies."""

    @property
    def name(self) -> TimingStrategyName:
        """Timing strategy name."""

    @property
    def approximate(self) -> bool:
        """Whether timing is approximate."""

    def build_word_timings(
        self,
        *,
        script: NarrationScriptRecord,
        audio: NarrationAudioRecord,
    ) -> tuple[WordTiming, ...]:
        """Return word timings for a script/audio pair."""


@dataclass(frozen=True, slots=True)
class ProviderWordTimingStrategy:
    """Use provider-supplied word timings when available."""

    word_timings: tuple[WordTiming, ...]
    name: TimingStrategyName = TimingStrategyName.PROVIDER_WORD_TIMINGS
    approximate: bool = False

    def build_word_timings(
        self,
        *,
        script: NarrationScriptRecord,
        audio: NarrationAudioRecord,
    ) -> tuple[WordTiming, ...]:
        """Return validated provider word timings."""
        del audio
        script_words = script_words_from_text(script.full_text)
        if len(self.word_timings) != len(script_words):
            raise UserInputError("Provider word timing count must match the script word count.")
        validate_word_timings(self.word_timings)
        return self.word_timings


@dataclass(frozen=True, slots=True)
class ApproximateAudioDurationStrategy:
    """Fallback timing that distributes script words across audio duration."""

    name: TimingStrategyName = TimingStrategyName.APPROXIMATE_AUDIO_DURATION
    approximate: bool = True

    def build_word_timings(
        self,
        *,
        script: NarrationScriptRecord,
        audio: NarrationAudioRecord,
    ) -> tuple[WordTiming, ...]:
        """Build approximate word timings from audio duration."""
        words = script_words_from_text(script.full_text)
        if not words:
            raise UserInputError("Cannot generate subtitles for an empty script.")
        duration = audio.metadata.duration_seconds
        if duration <= 0:
            raise UserInputError("Audio duration must be greater than zero for subtitles.")
        step = duration / len(words)
        timings = tuple(
            WordTiming(
                word=word,
                start_seconds=round(index * step, 3),
                end_seconds=round((index + 1) * step, 3),
            )
            for index, word in enumerate(words)
        )
        validate_word_timings(timings)
        return timings


def build_subtitle_document(
    *,
    script: NarrationScriptRecord,
    audio: NarrationAudioRecord,
    timing_strategy: SubtitleTimingStrategy,
    export_format: SubtitleExportFormat = SubtitleExportFormat.SRT,
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
    max_lines_per_cue: int = DEFAULT_MAX_LINES_PER_CUE,
    max_words_per_cue: int = DEFAULT_MAX_WORDS_PER_CUE,
    created_at: datetime | None = None,
) -> SubtitleDocument:
    """Build and validate a canonical subtitle document."""
    validate_script_audio_pair(script, audio)
    validate_readability_settings(max_chars_per_line, max_lines_per_cue, max_words_per_cue)
    word_timings = timing_strategy.build_word_timings(script=script, audio=audio)
    cues = build_cues_from_word_timings(
        word_timings,
        max_chars_per_line=max_chars_per_line,
        max_lines_per_cue=max_lines_per_cue,
        max_words_per_cue=max_words_per_cue,
    )
    metadata = SubtitleMetadata(
        timing_strategy=timing_strategy.name,
        export_format=export_format,
        max_chars_per_line=max_chars_per_line,
        max_lines_per_cue=max_lines_per_cue,
        max_words_per_cue=max_words_per_cue,
        approximate=timing_strategy.approximate,
        source_word_count=len(word_timings),
    )
    subtitle_id = stable_subtitle_id(
        script_id=script.script_id,
        audio_id=audio.audio_id,
        timing_strategy=timing_strategy.name,
        export_format=export_format,
        cue_text="\n".join(cue.text for cue in cues),
    )
    document = SubtitleDocument(
        subtitle_id=subtitle_id,
        script_id=script.script_id,
        audio_id=audio.audio_id,
        story_id=script.story_id,
        created_at=_utc_timestamp(created_at),
        metadata=metadata,
        cues=tuple(cues),
    )
    validate_subtitle_document(document, audio=audio)
    return document


def build_cues_from_word_timings(
    word_timings: tuple[WordTiming, ...],
    *,
    max_chars_per_line: int,
    max_lines_per_cue: int,
    max_words_per_cue: int,
) -> list[SubtitleCue]:
    """Group word timings into readable subtitle cues."""
    validate_word_timings(word_timings)
    cues: list[SubtitleCue] = []
    current: list[WordTiming] = []
    max_chars_per_cue = max_chars_per_line * max_lines_per_cue
    for timing in word_timings:
        candidate = [*current, timing]
        if current and (
            len(candidate) > max_words_per_cue
            or len(" ".join(item.word for item in candidate)) > max_chars_per_cue
        ):
            cues.append(_cue_from_words(len(cues) + 1, current, max_chars_per_line))
            current = [timing]
        else:
            current = candidate
    if current:
        cues.append(_cue_from_words(len(cues) + 1, current, max_chars_per_line))
    return cues


def validate_subtitle_document(
    document: SubtitleDocument,
    *,
    audio: NarrationAudioRecord | None = None,
) -> None:
    """Validate cue timing and readability."""
    if not document.cues:
        raise UserInputError("Subtitle document must contain at least one cue.")
    previous_end = -1.0
    for expected_index, cue in enumerate(document.cues, start=1):
        if cue.index != expected_index:
            raise UserInputError("Subtitle cue indexes must be contiguous.")
        if cue.start_seconds < 0 or cue.end_seconds <= cue.start_seconds:
            raise UserInputError("Subtitle cue timing must be positive and ordered.")
        if cue.end_seconds - cue.start_seconds < MIN_CUE_DURATION_SECONDS:
            raise UserInputError("Subtitle cue duration is too short for readability.")
        if cue.start_seconds < previous_end:
            raise UserInputError("Subtitle cues must not overlap.")
        if len(cue.lines) > document.metadata.max_lines_per_cue:
            raise UserInputError("Subtitle cue has too many lines.")
        for line in cue.lines:
            if len(line) > document.metadata.max_chars_per_line:
                raise UserInputError("Subtitle cue line exceeds readability limit.")
        previous_end = cue.end_seconds
    if audio is not None and document.cues[-1].end_seconds > audio.metadata.duration_seconds + 0.05:
        raise UserInputError("Subtitle cues extend beyond narration audio duration.")


def validate_word_timings(word_timings: tuple[WordTiming, ...]) -> None:
    """Validate word-level timing order."""
    if not word_timings:
        raise UserInputError("Word timings must not be empty.")
    previous_end = -1.0
    for timing in word_timings:
        if not timing.word.strip():
            raise UserInputError("Word timings must include non-empty words.")
        if timing.start_seconds < 0 or timing.end_seconds <= timing.start_seconds:
            raise UserInputError("Word timing start/end values must be positive and ordered.")
        if timing.start_seconds < previous_end:
            raise UserInputError("Word timings must not overlap.")
        previous_end = timing.end_seconds


def validate_script_audio_pair(script: NarrationScriptRecord, audio: NarrationAudioRecord) -> None:
    """Validate that an audio artifact belongs to the requested script."""
    if audio.script_id != script.script_id:
        raise UserInputError("Audio artifact does not belong to the requested script.")
    if audio.story_id != script.story_id:
        raise UserInputError("Audio artifact story does not match the script story.")


def validate_readability_settings(
    max_chars_per_line: int,
    max_lines_per_cue: int,
    max_words_per_cue: int,
) -> None:
    """Validate readability controls."""
    if max_chars_per_line < 12 or max_chars_per_line > 80:
        raise UserInputError("max_chars_per_line must be between 12 and 80.")
    if max_lines_per_cue < 1 or max_lines_per_cue > 3:
        raise UserInputError("max_lines_per_cue must be between 1 and 3.")
    if max_words_per_cue < 1 or max_words_per_cue > 16:
        raise UserInputError("max_words_per_cue must be between 1 and 16.")


def script_words_from_text(text: str) -> tuple[str, ...]:
    """Return subtitle words from script text."""
    return tuple(_WORD_PATTERN.findall(text))


def load_word_timings(path: Path) -> tuple[WordTiming, ...]:
    """Load provider word timings from a JSON file."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UserInputError(f"Could not read provider word timings: {path}") from exc
    if not isinstance(payload, list):
        raise UserInputError("Provider word timings file must contain a JSON list.")
    timings: list[WordTiming] = []
    for item in payload:
        if not isinstance(item, dict):
            raise UserInputError("Each provider word timing must be an object.")
        try:
            timings.append(WordTiming.from_dict(item))
        except ValueError as exc:
            raise UserInputError("Provider word timing contains invalid fields.") from exc
    return tuple(timings)


def export_subtitles(document: SubtitleDocument, export_format: SubtitleExportFormat) -> str:
    """Export a subtitle document to SRT, VTT, or ASS text."""
    if export_format is SubtitleExportFormat.SRT:
        return export_srt(document)
    if export_format is SubtitleExportFormat.VTT:
        return export_vtt(document)
    if export_format is SubtitleExportFormat.ASS:
        return export_ass(document)
    raise UserInputError(f"Unsupported subtitle export format: {export_format}")


def export_srt(document: SubtitleDocument) -> str:
    """Export subtitles as SRT."""
    blocks = []
    for cue in document.cues:
        blocks.append(
            f"{cue.index}\n{format_srt_time(cue.start_seconds)} --> "
            f"{format_srt_time(cue.end_seconds)}\n{cue.text}"
        )
    return "\n\n".join(blocks) + "\n"


def export_vtt(document: SubtitleDocument) -> str:
    """Export subtitles as WebVTT."""
    blocks = ["WEBVTT", ""]
    for cue in document.cues:
        blocks.append(
            f"{format_vtt_time(cue.start_seconds)} --> {format_vtt_time(cue.end_seconds)}\n"
            f"{cue.text}"
        )
        blocks.append("")
    return "\n".join(blocks)


def export_ass(document: SubtitleDocument) -> str:
    """Export subtitles as a compact ASS document."""
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{ASS_FONT_NAME},{ASS_FONT_SIZE},{ASS_PRIMARY_COLOUR},"
        f"{ASS_SECONDARY_COLOUR},{ASS_OUTLINE_COLOUR},{ASS_BACK_COLOUR},{ASS_BOLD},"
        "0,0,0,100,100,0,0,"
        f"{ASS_BORDER_STYLE},{ASS_OUTLINE_WIDTH},{ASS_SHADOW_DEPTH},"
        f"{ASS_ALIGNMENT_MIDDLE_CENTER},80,80,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for cue in document.cues:
        text = escape_ass_text(cue.text)
        lines.append(
            f"Dialogue: 0,{format_ass_time(cue.start_seconds)},"
            f"{format_ass_time(cue.end_seconds)},Default,,0,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"


def format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp."""
    hours, minutes, secs, millis = _time_parts(seconds)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def format_vtt_time(seconds: float) -> str:
    """Format seconds as VTT timestamp."""
    hours, minutes, secs, millis = _time_parts(seconds)
    return f"{hours:02}:{minutes:02}:{secs:02}.{millis:03}"


def format_ass_time(seconds: float) -> str:
    """Format seconds as ASS timestamp."""
    hours, minutes, secs, millis = _time_parts(seconds)
    centis = millis // 10
    return f"{hours}:{minutes:02}:{secs:02}.{centis:02}"


def escape_ass_text(text: str) -> str:
    """Escape cue text for ASS dialogue payloads."""
    return text.replace("\n", r"\N").replace("{", r"\{").replace("}", r"\}")


def stable_subtitle_id(
    *,
    script_id: str,
    audio_id: str,
    timing_strategy: TimingStrategyName,
    export_format: SubtitleExportFormat,
    cue_text: str,
) -> str:
    """Build a stable subtitle ID from inputs and generated cue text."""
    payload = "\n".join(
        [script_id, audio_id, timing_strategy.value, export_format.value, cue_text]
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return f"subtitle_{digest[:16]}"


def _cue_from_words(
    index: int,
    words: list[WordTiming],
    max_chars_per_line: int,
) -> SubtitleCue:
    lines = break_lines([timing.word for timing in words], max_chars_per_line=max_chars_per_line)
    return SubtitleCue(
        index=index,
        start_seconds=words[0].start_seconds,
        end_seconds=words[-1].end_seconds,
        lines=tuple(lines),
    )


def break_lines(words: list[str], *, max_chars_per_line: int) -> list[str]:
    """Break words into readable subtitle lines."""
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and len(candidate) > max_chars_per_line:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def _time_parts(seconds: float) -> tuple[int, int, int, int]:
    millis_total = round(seconds * 1000)
    hours, remainder = divmod(millis_total, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1_000)
    return hours, minutes, secs, millis


def _utc_timestamp(value: datetime | None) -> str:
    timestamp = datetime.now(UTC) if value is None else value.astimezone(UTC)
    return timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
