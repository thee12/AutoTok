"""Story-to-script transformation providers for Phase 2."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from autotok.errors import UserInputError
from autotok.models import StoryRecord
from autotok.script_models import (
    DurationBudget,
    NarrationScriptRecord,
    PrivacyReport,
    ScriptSections,
    TransformationStep,
)

DEFAULT_TARGET_SECONDS = 60
DEFAULT_WORDS_PER_MINUTE = 150
MIN_TARGET_SECONDS = 15
MAX_TARGET_SECONDS = 180
DETERMINISTIC_PROVIDER_NAME = "deterministic_baseline"
DETERMINISTIC_PROVIDER_VERSION = "1"

_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)")
_HANDLE_PATTERN = re.compile(r"(?<!\w)@[A-Za-z0-9_]{3,30}\b")
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
_WORD_PATTERN = re.compile(r"\S+")


class ScriptTransformer(Protocol):
    """Provider-independent interface for story-to-script transformation."""

    provider_name: str
    provider_version: str

    def transform(
        self,
        story: StoryRecord,
        *,
        target_seconds: int = DEFAULT_TARGET_SECONDS,
        created_at: datetime | None = None,
    ) -> NarrationScriptRecord:
        """Transform a story into a reviewable narration script."""


@dataclass(frozen=True, slots=True)
class TransformationDraft:
    """Provider output before script ID assignment."""

    sections: ScriptSections
    privacy_report: PrivacyReport
    transformation_steps: tuple[TransformationStep, ...]


class DeterministicScriptTransformer:
    """Deterministic local baseline transformer for Phase 2."""

    provider_name = DETERMINISTIC_PROVIDER_NAME
    provider_version = DETERMINISTIC_PROVIDER_VERSION

    def transform(
        self,
        story: StoryRecord,
        *,
        target_seconds: int = DEFAULT_TARGET_SECONDS,
        created_at: datetime | None = None,
    ) -> NarrationScriptRecord:
        """Transform a story using local cleaning, redaction, and budgeting rules."""
        _validate_target_seconds(target_seconds)
        draft = self.build_draft(story, target_seconds=target_seconds)
        duration_budget = build_duration_budget(
            draft.sections.full_text,
            target_seconds=target_seconds,
            words_per_minute=DEFAULT_WORDS_PER_MINUTE,
        )
        timestamp = _utc_timestamp(created_at)
        script_id = stable_script_id(
            story_id=story.story_id,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            target_seconds=target_seconds,
            full_text=draft.sections.full_text,
        )
        return NarrationScriptRecord(
            script_id=script_id,
            story_id=story.story_id,
            source_content_sha256=story.source.content_sha256,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            created_at=timestamp,
            sections=draft.sections,
            duration_budget=duration_budget,
            privacy_report=draft.privacy_report,
            transformation_steps=draft.transformation_steps,
        )

    def build_draft(self, story: StoryRecord, *, target_seconds: int) -> TransformationDraft:
        """Build a deterministic script draft before metadata wrapping."""
        cleaned = baseline_clean(story.normalized_text)
        redacted, privacy_report = redact_private_text(cleaned)
        budget = build_duration_budget(
            redacted,
            target_seconds=target_seconds,
            words_per_minute=DEFAULT_WORDS_PER_MINUTE,
        )
        body = truncate_to_words(redacted, budget.max_words)
        title = story.source.title or "this story"
        hook = build_hook(title, body)
        outro = "What would you do next?"
        sections = ScriptSections(hook=hook, body=body, outro=outro)
        steps = (
            TransformationStep(
                name="baseline_clean",
                description="Collapsed whitespace and normalized paragraph spacing.",
            ),
            TransformationStep(
                name="privacy_redaction",
                description="Redacted emails, phone numbers, and social handles.",
            ),
            TransformationStep(
                name="duration_budget",
                description=f"Limited script body for a {target_seconds}-second target.",
            ),
            TransformationStep(
                name="section_structure",
                description="Built hook, body, and outro sections for narration review.",
            ),
        )
        return TransformationDraft(
            sections=sections,
            privacy_report=privacy_report,
            transformation_steps=steps,
        )


class FakeScriptTransformer:
    """Deterministic test double for provider-independent transformation tests."""

    provider_name = "fake"
    provider_version = "test"

    def transform(
        self,
        story: StoryRecord,
        *,
        target_seconds: int = DEFAULT_TARGET_SECONDS,
        created_at: datetime | None = None,
    ) -> NarrationScriptRecord:
        """Return a predictable script for tests."""
        _validate_target_seconds(target_seconds)
        sections = ScriptSections(
            hook="Fake hook.",
            body=f"Fake body for {story.story_id}.",
            outro="Fake outro.",
        )
        timestamp = _utc_timestamp(created_at)
        return NarrationScriptRecord(
            script_id=stable_script_id(
                story_id=story.story_id,
                provider_name=self.provider_name,
                provider_version=self.provider_version,
                target_seconds=target_seconds,
                full_text=sections.full_text,
            ),
            story_id=story.story_id,
            source_content_sha256=story.source.content_sha256,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            created_at=timestamp,
            sections=sections,
            duration_budget=build_duration_budget(
                sections.full_text,
                target_seconds=target_seconds,
                words_per_minute=DEFAULT_WORDS_PER_MINUTE,
            ),
            privacy_report=PrivacyReport(),
            transformation_steps=(
                TransformationStep(
                    name="fake_provider", description="Returned fake script output."
                ),
            ),
        )


def baseline_clean(text: str) -> str:
    """Apply deterministic baseline cleanup without changing story meaning."""
    paragraphs = [" ".join(part.split()) for part in re.split(r"\n{2,}", text)]
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph).strip()


def redact_private_text(text: str) -> tuple[str, PrivacyReport]:
    """Redact common personal contact details from script text."""
    text, email_count = _EMAIL_PATTERN.subn("[redacted email]", text)
    text, phone_count = _PHONE_PATTERN.subn("[redacted phone]", text)
    text, handle_count = _HANDLE_PATTERN.subn("[redacted handle]", text)
    return (
        text,
        PrivacyReport(
            email_redactions=email_count,
            phone_redactions=phone_count,
            handle_redactions=handle_count,
        ),
    )


def build_duration_budget(
    text: str,
    *,
    target_seconds: int,
    words_per_minute: int,
) -> DurationBudget:
    """Estimate duration and word budget for narration text."""
    _validate_target_seconds(target_seconds)
    if words_per_minute <= 0:
        raise UserInputError("Words per minute must be greater than zero.")
    words = _WORD_PATTERN.findall(text)
    max_words = max(1, (target_seconds * words_per_minute) // 60)
    estimated_seconds = max(1, round((len(words) / words_per_minute) * 60)) if words else 0
    return DurationBudget(
        target_seconds=target_seconds,
        words_per_minute=words_per_minute,
        max_words=max_words,
        estimated_seconds=estimated_seconds,
        word_count=len(words),
    )


def truncate_to_words(text: str, max_words: int) -> str:
    """Trim text to a word budget, preferring whole sentences when possible."""
    words = _WORD_PATTERN.findall(text)
    if len(words) <= max_words:
        return text

    sentences = _SENTENCE_SPLIT_PATTERN.split(text)
    selected: list[str] = []
    selected_word_count = 0
    for sentence in sentences:
        sentence_word_count = len(_WORD_PATTERN.findall(sentence))
        if selected and selected_word_count + sentence_word_count > max_words:
            break
        if sentence_word_count > max_words:
            break
        selected.append(sentence)
        selected_word_count += sentence_word_count

    if selected:
        return " ".join(selected).strip()
    return " ".join(words[:max_words]).strip()


def build_hook(title: str, body: str) -> str:
    """Build a deterministic hook from title and script body."""
    first_sentence = _SENTENCE_SPLIT_PATTERN.split(body, maxsplit=1)[0].strip()
    if title != "this story":
        return f"This story starts with {title}: {first_sentence}"
    return f"This story starts with a moment nobody expected: {first_sentence}"


def stable_script_id(
    *,
    story_id: str,
    provider_name: str,
    provider_version: str,
    target_seconds: int,
    full_text: str,
) -> str:
    """Build a stable script ID from transformation inputs and output."""
    payload = "\n".join(
        [story_id, provider_name, provider_version, str(target_seconds), full_text]
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return f"script_{digest[:16]}"


def _validate_target_seconds(target_seconds: int) -> None:
    if target_seconds < MIN_TARGET_SECONDS or target_seconds > MAX_TARGET_SECONDS:
        raise UserInputError(
            f"Target seconds must be between {MIN_TARGET_SECONDS} and {MAX_TARGET_SECONDS}."
        )


def _utc_timestamp(value: datetime | None) -> str:
    timestamp = datetime.now(UTC) if value is None else value.astimezone(UTC)
    return timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
