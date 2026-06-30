"""Content gate models for Phase 8 scoring and review decisions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

CONTENT_GATE_SCHEMA_VERSION = 1


class ContentGateDecision(StrEnum):
    """Reproducible Phase 8 content gate decisions."""

    APPROVED = "approved"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


class DuplicateKind(StrEnum):
    """Duplicate match type."""

    EXACT = "exact"
    NEAR = "near"


class WarningSeverity(StrEnum):
    """Content warning severity used by local gates."""

    INFO = "info"
    REVIEW = "review"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ContentGateConfig:
    """Deterministic thresholds used for a content gate run."""

    min_words: int = 12
    max_words: int = 450
    min_duration_seconds: int = 10
    max_duration_seconds: int = 180
    auto_approve_min_score: int = 75
    reject_below_score: int = 45
    near_duplicate_threshold: float = 0.82
    words_per_minute: int = 150

    def to_dict(self) -> dict[str, object]:
        """Serialize thresholds to JSON-compatible values."""
        return {
            "min_words": self.min_words,
            "max_words": self.max_words,
            "min_duration_seconds": self.min_duration_seconds,
            "max_duration_seconds": self.max_duration_seconds,
            "auto_approve_min_score": self.auto_approve_min_score,
            "reject_below_score": self.reject_below_score,
            "near_duplicate_threshold": self.near_duplicate_threshold,
            "words_per_minute": self.words_per_minute,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ContentGateConfig:
        """Deserialize threshold configuration."""
        return cls(
            min_words=_required_int(data, "min_words"),
            max_words=_required_int(data, "max_words"),
            min_duration_seconds=_required_int(data, "min_duration_seconds"),
            max_duration_seconds=_required_int(data, "max_duration_seconds"),
            auto_approve_min_score=_required_int(data, "auto_approve_min_score"),
            reject_below_score=_required_int(data, "reject_below_score"),
            near_duplicate_threshold=_required_float(data, "near_duplicate_threshold"),
            words_per_minute=_required_int(data, "words_per_minute"),
        )


@dataclass(frozen=True, slots=True)
class QualityScore:
    """Quality score with component explanations."""

    total: int
    length_score: int
    structure_score: int
    readability_score: int
    originality_score: int
    safety_score: int
    word_count: int
    sentence_count: int
    explanation: str

    def to_dict(self) -> dict[str, object]:
        """Serialize quality score to JSON-compatible values."""
        return {
            "total": self.total,
            "length_score": self.length_score,
            "structure_score": self.structure_score,
            "readability_score": self.readability_score,
            "originality_score": self.originality_score,
            "safety_score": self.safety_score,
            "word_count": self.word_count,
            "sentence_count": self.sentence_count,
            "explanation": self.explanation,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> QualityScore:
        """Deserialize a quality score."""
        return cls(
            total=_required_int(data, "total"),
            length_score=_required_int(data, "length_score"),
            structure_score=_required_int(data, "structure_score"),
            readability_score=_required_int(data, "readability_score"),
            originality_score=_required_int(data, "originality_score"),
            safety_score=_required_int(data, "safety_score"),
            word_count=_required_int(data, "word_count"),
            sentence_count=_required_int(data, "sentence_count"),
            explanation=_required_str(data, "explanation"),
        )


@dataclass(frozen=True, slots=True)
class DuplicateMatch:
    """A story that exactly or nearly matches the assessed story."""

    story_id: str
    kind: DuplicateKind
    similarity: float
    reason: str

    def to_dict(self) -> dict[str, object]:
        """Serialize duplicate match to JSON-compatible values."""
        return {
            "story_id": self.story_id,
            "kind": self.kind.value,
            "similarity": self.similarity,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> DuplicateMatch:
        """Deserialize a duplicate match."""
        return cls(
            story_id=_required_str(data, "story_id"),
            kind=DuplicateKind(_required_str(data, "kind")),
            similarity=_required_float(data, "similarity"),
            reason=_required_str(data, "reason"),
        )


@dataclass(frozen=True, slots=True)
class ContentWarning:
    """A local policy, privacy, or quality warning."""

    code: str
    category: str
    severity: WarningSeverity
    message: str

    def to_dict(self) -> dict[str, object]:
        """Serialize warning to JSON-compatible values."""
        return {
            "code": self.code,
            "category": self.category,
            "severity": self.severity.value,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ContentWarning:
        """Deserialize a content warning."""
        return cls(
            code=_required_str(data, "code"),
            category=_required_str(data, "category"),
            severity=WarningSeverity(_required_str(data, "severity")),
            message=_required_str(data, "message"),
        )


@dataclass(frozen=True, slots=True)
class OverrideEvent:
    """Manual override event for a gate decision."""

    decision: ContentGateDecision
    reason: str
    reviewer: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        """Serialize override event to JSON-compatible values."""
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "reviewer": self.reviewer,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> OverrideEvent:
        """Deserialize an override event."""
        return cls(
            decision=ContentGateDecision(_required_str(data, "decision")),
            reason=_required_str(data, "reason"),
            reviewer=_required_str(data, "reviewer"),
            created_at=_required_str(data, "created_at"),
        )


@dataclass(frozen=True, slots=True)
class ContentGateRecord:
    """Stored Phase 8 gate result for a story."""

    gate_id: str
    story_id: str
    source_content_sha256: str
    created_at: str
    normalized_fingerprint: str
    token_fingerprint: str
    quality_score: QualityScore
    estimated_duration_seconds: int
    duration_suitable: bool
    duplicate_matches: tuple[DuplicateMatch, ...]
    warnings: tuple[ContentWarning, ...]
    reject_reasons: tuple[str, ...]
    review_flags: tuple[str, ...]
    decision: ContentGateDecision
    config: ContentGateConfig = ContentGateConfig()
    override_events: tuple[OverrideEvent, ...] = ()
    schema_version: int = CONTENT_GATE_SCHEMA_VERSION

    @property
    def effective_decision(self) -> ContentGateDecision:
        """Return the override decision when present, otherwise the gate decision."""
        if self.override_events:
            return self.override_events[-1].decision
        return self.decision

    def with_override(self, event: OverrideEvent) -> ContentGateRecord:
        """Return a copy with an appended manual override event."""
        return ContentGateRecord(
            schema_version=self.schema_version,
            gate_id=self.gate_id,
            story_id=self.story_id,
            source_content_sha256=self.source_content_sha256,
            created_at=self.created_at,
            normalized_fingerprint=self.normalized_fingerprint,
            token_fingerprint=self.token_fingerprint,
            quality_score=self.quality_score,
            estimated_duration_seconds=self.estimated_duration_seconds,
            duration_suitable=self.duration_suitable,
            duplicate_matches=self.duplicate_matches,
            warnings=self.warnings,
            reject_reasons=self.reject_reasons,
            review_flags=self.review_flags,
            decision=self.decision,
            config=self.config,
            override_events=(*self.override_events, event),
        )

    def to_dict(self) -> dict[str, object]:
        """Serialize gate record to JSON-compatible values."""
        return {
            "schema_version": self.schema_version,
            "gate_id": self.gate_id,
            "story_id": self.story_id,
            "source_content_sha256": self.source_content_sha256,
            "created_at": self.created_at,
            "normalized_fingerprint": self.normalized_fingerprint,
            "token_fingerprint": self.token_fingerprint,
            "quality_score": self.quality_score.to_dict(),
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "duration_suitable": self.duration_suitable,
            "duplicate_matches": [match.to_dict() for match in self.duplicate_matches],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "reject_reasons": list(self.reject_reasons),
            "review_flags": list(self.review_flags),
            "decision": self.decision.value,
            "effective_decision": self.effective_decision.value,
            "config": self.config.to_dict(),
            "override_events": [event.to_dict() for event in self.override_events],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ContentGateRecord:
        """Deserialize and validate a gate record."""
        schema_version = _required_int(data, "schema_version")
        if schema_version != CONTENT_GATE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported content gate schema_version: {schema_version}")
        quality_data = _required_mapping(data.get("quality_score"), "quality_score")
        config_data = _required_mapping(data.get("config"), "config")
        return cls(
            schema_version=schema_version,
            gate_id=_required_str(data, "gate_id"),
            story_id=_required_str(data, "story_id"),
            source_content_sha256=_required_str(data, "source_content_sha256"),
            created_at=_required_str(data, "created_at"),
            normalized_fingerprint=_required_str(data, "normalized_fingerprint"),
            token_fingerprint=_required_str(data, "token_fingerprint"),
            quality_score=QualityScore.from_dict(quality_data),
            estimated_duration_seconds=_required_int(data, "estimated_duration_seconds"),
            duration_suitable=_required_bool(data, "duration_suitable"),
            duplicate_matches=tuple(
                DuplicateMatch.from_dict(_required_mapping(item, "duplicate_match"))
                for item in _required_sequence(data, "duplicate_matches")
            ),
            warnings=tuple(
                ContentWarning.from_dict(_required_mapping(item, "warning"))
                for item in _required_sequence(data, "warnings")
            ),
            reject_reasons=tuple(_str_sequence(data, "reject_reasons")),
            review_flags=tuple(_str_sequence(data, "review_flags")),
            decision=ContentGateDecision(_required_str(data, "decision")),
            config=ContentGateConfig.from_dict(config_data),
            override_events=tuple(
                OverrideEvent.from_dict(_required_mapping(item, "override_event"))
                for item in _required_sequence(data, "override_events")
            ),
        )


def _required_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object.")
    return value


def _required_sequence(data: Mapping[str, object], key: str) -> Sequence[object]:
    value = data.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{key} must be a list.")
    return value


def _str_sequence(data: Mapping[str, object], key: str) -> Sequence[str]:
    values = _required_sequence(data, key)
    if not all(isinstance(value, str) for value in values):
        raise ValueError(f"{key} must contain only strings.")
    return tuple(str(value) for value in values)


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
    if not isinstance(value, int | float):
        raise ValueError(f"{key} must be a number.")
    return float(value)


def _required_bool(data: Mapping[str, object], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean.")
    return value
