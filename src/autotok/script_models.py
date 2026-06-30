"""Narration script models for Phase 2 review artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

SCRIPT_SCHEMA_VERSION = 1


class ReviewStatus(StrEnum):
    """Review states for generated narration scripts."""

    PENDING = "pending_review"
    APPROVED = "approved"


@dataclass(frozen=True, slots=True)
class ScriptSections:
    """Structured narration script sections."""

    hook: str
    body: str
    outro: str

    @property
    def full_text(self) -> str:
        """Return the complete narration script."""
        return "\n\n".join(part for part in (self.hook, self.body, self.outro) if part)

    def to_dict(self) -> dict[str, object]:
        """Serialize sections to JSON-compatible values."""
        return {"hook": self.hook, "body": self.body, "outro": self.outro}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ScriptSections:
        """Deserialize script sections."""
        return cls(
            hook=_required_str(data, "hook"),
            body=_required_str(data, "body"),
            outro=_required_str(data, "outro"),
        )


@dataclass(frozen=True, slots=True)
class TransformationStep:
    """One deterministic transformation step applied to a story."""

    name: str
    description: str

    def to_dict(self) -> dict[str, object]:
        """Serialize the step to JSON-compatible values."""
        return {"name": self.name, "description": self.description}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> TransformationStep:
        """Deserialize a transformation step."""
        return cls(
            name=_required_str(data, "name"),
            description=_required_str(data, "description"),
        )


@dataclass(frozen=True, slots=True)
class DurationBudget:
    """Target duration and estimated speech budget."""

    target_seconds: int
    words_per_minute: int
    max_words: int
    estimated_seconds: int
    word_count: int

    def to_dict(self) -> dict[str, object]:
        """Serialize the budget to JSON-compatible values."""
        return {
            "target_seconds": self.target_seconds,
            "words_per_minute": self.words_per_minute,
            "max_words": self.max_words,
            "estimated_seconds": self.estimated_seconds,
            "word_count": self.word_count,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> DurationBudget:
        """Deserialize a duration budget."""
        return cls(
            target_seconds=_required_int(data, "target_seconds"),
            words_per_minute=_required_int(data, "words_per_minute"),
            max_words=_required_int(data, "max_words"),
            estimated_seconds=_required_int(data, "estimated_seconds"),
            word_count=_required_int(data, "word_count"),
        )


@dataclass(frozen=True, slots=True)
class PrivacyReport:
    """Summary of deterministic privacy-cleaning redactions."""

    email_redactions: int = 0
    phone_redactions: int = 0
    handle_redactions: int = 0

    @property
    def total_redactions(self) -> int:
        """Return the total number of redactions."""
        return self.email_redactions + self.phone_redactions + self.handle_redactions

    def to_dict(self) -> dict[str, object]:
        """Serialize the report to JSON-compatible values."""
        return {
            "email_redactions": self.email_redactions,
            "phone_redactions": self.phone_redactions,
            "handle_redactions": self.handle_redactions,
            "total_redactions": self.total_redactions,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> PrivacyReport:
        """Deserialize a privacy report."""
        return cls(
            email_redactions=_required_int(data, "email_redactions"),
            phone_redactions=_required_int(data, "phone_redactions"),
            handle_redactions=_required_int(data, "handle_redactions"),
        )


@dataclass(frozen=True, slots=True)
class NarrationScriptRecord:
    """Reviewable narration script generated from an imported story."""

    script_id: str
    story_id: str
    source_content_sha256: str
    provider_name: str
    provider_version: str
    created_at: str
    sections: ScriptSections
    duration_budget: DurationBudget
    privacy_report: PrivacyReport
    transformation_steps: tuple[TransformationStep, ...]
    review_status: ReviewStatus = ReviewStatus.PENDING
    approved_at: str | None = None
    schema_version: int = SCRIPT_SCHEMA_VERSION

    @property
    def full_text(self) -> str:
        """Return the complete narration script text."""
        return self.sections.full_text

    def approve(self, approved_at: str) -> NarrationScriptRecord:
        """Return a copy marked approved."""
        return replace(self, review_status=ReviewStatus.APPROVED, approved_at=approved_at)

    def to_dict(self) -> dict[str, object]:
        """Serialize the script record to JSON-compatible values."""
        return {
            "schema_version": self.schema_version,
            "script_id": self.script_id,
            "story_id": self.story_id,
            "source_content_sha256": self.source_content_sha256,
            "provider_name": self.provider_name,
            "provider_version": self.provider_version,
            "created_at": self.created_at,
            "sections": self.sections.to_dict(),
            "duration_budget": self.duration_budget.to_dict(),
            "privacy_report": self.privacy_report.to_dict(),
            "transformation_steps": [step.to_dict() for step in self.transformation_steps],
            "review_status": self.review_status.value,
            "approved_at": self.approved_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> NarrationScriptRecord:
        """Deserialize and validate a narration script record."""
        schema_version = _required_int(data, "schema_version")
        if schema_version != SCRIPT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported script schema_version: {schema_version}")

        sections_data = _required_mapping(data, "sections")
        budget_data = _required_mapping(data, "duration_budget")
        privacy_data = _required_mapping(data, "privacy_report")
        steps_data = data.get("transformation_steps")
        if not isinstance(steps_data, Sequence) or isinstance(steps_data, str):
            raise ValueError("transformation_steps must be a list.")

        try:
            review_status = ReviewStatus(_required_str(data, "review_status"))
        except ValueError as exc:
            raise ValueError("review_status is unsupported.") from exc

        return cls(
            schema_version=schema_version,
            script_id=_required_str(data, "script_id"),
            story_id=_required_str(data, "story_id"),
            source_content_sha256=_required_str(data, "source_content_sha256"),
            provider_name=_required_str(data, "provider_name"),
            provider_version=_required_str(data, "provider_version"),
            created_at=_required_str(data, "created_at"),
            sections=ScriptSections.from_dict(sections_data),
            duration_budget=DurationBudget.from_dict(budget_data),
            privacy_report=PrivacyReport.from_dict(privacy_data),
            transformation_steps=_steps_from_sequence(steps_data),
            review_status=review_status,
            approved_at=_optional_str(data, "approved_at"),
        )


def _steps_from_sequence(values: Sequence[object]) -> tuple[TransformationStep, ...]:
    steps: list[TransformationStep] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError("Each transformation step must be an object.")
        steps.append(TransformationStep.from_dict(value))
    return tuple(steps)


def _required_mapping(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object.")
    return value


def _required_str(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string.")
    return value


def _optional_str(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null.")
    return value or None


def _required_int(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer.")
    return value
