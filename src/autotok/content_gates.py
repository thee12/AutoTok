"""Deterministic Phase 8 story scoring, duplicate detection, and content gates."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from autotok.content_gate_models import (
    ContentGateConfig,
    ContentGateDecision,
    ContentGateRecord,
    ContentWarning,
    DuplicateKind,
    DuplicateMatch,
    OverrideEvent,
    QualityScore,
    WarningSeverity,
)
from autotok.errors import UserInputError
from autotok.models import StoryRecord

_WORD_PATTERN = re.compile(r"[A-Za-z0-9']+")
_SENTENCE_PATTERN = re.compile(r"[.!?]+")
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)")
_HANDLE_PATTERN = re.compile(r"(?<!\w)@[A-Za-z0-9_]{3,30}\b")

SELF_HARM_TERMS = (
    "kill myself",
    "suicide",
    "self harm",
    "self-harm",
)
VIOLENCE_TERMS = (
    "stabbed",
    "shooting",
    "murder",
    "assault",
)
MINOR_SAFETY_TERMS = (
    "underage",
    "minor explicit",
)
DEFAULT_CONTENT_GATE_CONFIG = ContentGateConfig()


def assess_story(
    story: StoryRecord,
    *,
    existing_stories: Iterable[StoryRecord] = (),
    config: ContentGateConfig | None = None,
    created_at: datetime | None = None,
) -> ContentGateRecord:
    """Assess a story and return a reproducible Phase 8 content gate record."""
    gate_config = DEFAULT_CONTENT_GATE_CONFIG if config is None else config
    timestamp = _utc_timestamp(created_at)
    tokens = _tokens(story.normalized_text)
    token_set = frozenset(tokens)
    duplicate_matches = _duplicate_matches(story, token_set, existing_stories, gate_config)
    warnings = _content_warnings(story.normalized_text)
    estimated_seconds = _estimated_duration_seconds(len(tokens), gate_config.words_per_minute)
    duration_suitable = (
        gate_config.min_duration_seconds <= estimated_seconds <= gate_config.max_duration_seconds
    )
    quality_score = _quality_score(
        word_count=len(tokens),
        sentence_count=_sentence_count(story.normalized_text),
        duration_suitable=duration_suitable,
        duplicate_matches=duplicate_matches,
        warnings=warnings,
        config=gate_config,
    )
    reject_reasons = _reject_reasons(
        quality_score=quality_score,
        duration_suitable=duration_suitable,
        duplicate_matches=duplicate_matches,
        warnings=warnings,
        config=gate_config,
    )
    review_flags = _review_flags(
        quality_score=quality_score,
        duplicate_matches=duplicate_matches,
        warnings=warnings,
        config=gate_config,
    )
    decision = _decision(
        quality_score=quality_score,
        reject_reasons=reject_reasons,
        review_flags=review_flags,
        config=gate_config,
    )
    normalized_fingerprint = _normalized_fingerprint(story.normalized_text)
    token_fingerprint = _token_fingerprint(tokens)
    gate_id = stable_gate_id(
        story_id=story.story_id,
        source_content_sha256=story.source.content_sha256,
        token_fingerprint=token_fingerprint,
        config=gate_config,
    )
    return ContentGateRecord(
        gate_id=gate_id,
        story_id=story.story_id,
        source_content_sha256=story.source.content_sha256,
        created_at=timestamp,
        normalized_fingerprint=normalized_fingerprint,
        token_fingerprint=token_fingerprint,
        quality_score=quality_score,
        estimated_duration_seconds=estimated_seconds,
        duration_suitable=duration_suitable,
        duplicate_matches=duplicate_matches,
        warnings=warnings,
        reject_reasons=reject_reasons,
        review_flags=review_flags,
        decision=decision,
        config=gate_config,
    )


def build_override_event(
    *,
    decision: ContentGateDecision,
    reason: str,
    reviewer: str,
    created_at: datetime | None = None,
) -> OverrideEvent:
    """Create a validated manual override event."""
    cleaned_reason = reason.strip()
    cleaned_reviewer = reviewer.strip()
    if not cleaned_reason:
        raise UserInputError("Override reason must not be empty.")
    if not cleaned_reviewer:
        raise UserInputError("Override reviewer must not be empty.")
    return OverrideEvent(
        decision=decision,
        reason=cleaned_reason,
        reviewer=cleaned_reviewer,
        created_at=_utc_timestamp(created_at),
    )


def stable_gate_id(
    *,
    story_id: str,
    source_content_sha256: str,
    token_fingerprint: str,
    config: ContentGateConfig,
) -> str:
    """Build a stable gate ID from the assessed content and thresholds."""
    payload = "\n".join(
        [story_id, source_content_sha256, token_fingerprint, repr(sorted(config.to_dict().items()))]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"gate_{digest[:16]}"


def _duplicate_matches(
    story: StoryRecord,
    token_set: frozenset[str],
    existing_stories: Iterable[StoryRecord],
    config: ContentGateConfig,
) -> tuple[DuplicateMatch, ...]:
    matches: list[DuplicateMatch] = []
    for other in existing_stories:
        if other.story_id == story.story_id:
            continue
        if other.source.content_sha256 == story.source.content_sha256:
            matches.append(
                DuplicateMatch(
                    story_id=other.story_id,
                    kind=DuplicateKind.EXACT,
                    similarity=1.0,
                    reason="Content SHA-256 matches an existing story.",
                )
            )
            continue
        other_tokens = frozenset(_tokens(other.normalized_text))
        similarity = _jaccard(token_set, other_tokens)
        if similarity >= config.near_duplicate_threshold:
            matches.append(
                DuplicateMatch(
                    story_id=other.story_id,
                    kind=DuplicateKind.NEAR,
                    similarity=round(similarity, 4),
                    reason="Token-set similarity meets the near-duplicate threshold.",
                )
            )
    return tuple(sorted(matches, key=lambda match: (-match.similarity, match.story_id)))


def _quality_score(
    *,
    word_count: int,
    sentence_count: int,
    duration_suitable: bool,
    duplicate_matches: Sequence[DuplicateMatch],
    warnings: Sequence[ContentWarning],
    config: ContentGateConfig,
) -> QualityScore:
    length_score = _length_score(word_count, config)
    structure_score = 20 if sentence_count >= 2 else 12 if sentence_count == 1 else 0
    readability_score = 15 if word_count >= config.min_words and sentence_count > 0 else 7
    originality_score = _originality_score(duplicate_matches)
    safety_score = max(
        0, 10 - sum(4 for warning in warnings if warning.severity != WarningSeverity.INFO)
    )
    if not duration_suitable:
        length_score = max(0, length_score - 8)
    total = min(
        100, length_score + structure_score + readability_score + originality_score + safety_score
    )
    explanation = (
        f"{word_count} words, {sentence_count} sentence(s), "
        f"{len(duplicate_matches)} duplicate signal(s), {len(warnings)} warning(s)."
    )
    return QualityScore(
        total=total,
        length_score=length_score,
        structure_score=structure_score,
        readability_score=readability_score,
        originality_score=originality_score,
        safety_score=safety_score,
        word_count=word_count,
        sentence_count=sentence_count,
        explanation=explanation,
    )


def _content_warnings(text: str) -> tuple[ContentWarning, ...]:
    lower_text = text.lower()
    warnings: list[ContentWarning] = []
    if _EMAIL_PATTERN.search(text) or _PHONE_PATTERN.search(text) or _HANDLE_PATTERN.search(text):
        warnings.append(
            ContentWarning(
                code="private_contact",
                category="privacy",
                severity=WarningSeverity.REVIEW,
                message="Story contains contact details or social handles that require review.",
            )
        )
    if any(term in lower_text for term in SELF_HARM_TERMS):
        warnings.append(
            ContentWarning(
                code="self_harm_reference",
                category="policy",
                severity=WarningSeverity.REVIEW,
                message="Story references self-harm or suicide and requires human review.",
            )
        )
    if any(term in lower_text for term in VIOLENCE_TERMS):
        warnings.append(
            ContentWarning(
                code="violence_reference",
                category="policy",
                severity=WarningSeverity.REVIEW,
                message="Story references violence and requires human review.",
            )
        )
    if any(term in lower_text for term in MINOR_SAFETY_TERMS):
        warnings.append(
            ContentWarning(
                code="minor_safety_reference",
                category="policy",
                severity=WarningSeverity.REJECT,
                message=(
                    "Story contains minor-safety language and is rejected pending manual override."
                ),
            )
        )
    return tuple(warnings)


def _reject_reasons(
    *,
    quality_score: QualityScore,
    duration_suitable: bool,
    duplicate_matches: Sequence[DuplicateMatch],
    warnings: Sequence[ContentWarning],
    config: ContentGateConfig,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if any(match.kind is DuplicateKind.EXACT for match in duplicate_matches):
        reasons.append("exact_duplicate")
    if quality_score.total < config.reject_below_score:
        reasons.append("quality_score_below_reject_threshold")
    if not duration_suitable:
        reasons.append("duration_outside_allowed_range")
    return tuple(reasons)


def _review_flags(
    *,
    quality_score: QualityScore,
    duplicate_matches: Sequence[DuplicateMatch],
    warnings: Sequence[ContentWarning],
    config: ContentGateConfig,
) -> tuple[str, ...]:
    flags: list[str] = []
    if any(match.kind is DuplicateKind.NEAR for match in duplicate_matches):
        flags.append("near_duplicate")
    flags.extend(warning.code for warning in warnings)
    if quality_score.total < config.auto_approve_min_score:
        flags.append("quality_score_below_auto_approve_threshold")
    return tuple(dict.fromkeys(flags))


def _decision(
    *,
    quality_score: QualityScore,
    reject_reasons: Sequence[str],
    review_flags: Sequence[str],
    config: ContentGateConfig,
) -> ContentGateDecision:
    if reject_reasons:
        return ContentGateDecision.REJECTED
    if review_flags or quality_score.total < config.auto_approve_min_score:
        return ContentGateDecision.NEEDS_REVIEW
    return ContentGateDecision.APPROVED


def _length_score(word_count: int, config: ContentGateConfig) -> int:
    if config.min_words <= word_count <= config.max_words:
        return 35
    if word_count < config.min_words:
        return max(0, math.floor(35 * (word_count / config.min_words)))
    overage = word_count - config.max_words
    return max(0, 35 - math.ceil(overage / 25))


def _originality_score(duplicate_matches: Sequence[DuplicateMatch]) -> int:
    if any(match.kind is DuplicateKind.EXACT for match in duplicate_matches):
        return 0
    if duplicate_matches:
        return 8
    return 20


def _sentence_count(text: str) -> int:
    return max(1, len([match for match in _SENTENCE_PATTERN.finditer(text)])) if text.strip() else 0


def _estimated_duration_seconds(word_count: int, words_per_minute: int) -> int:
    if word_count == 0:
        return 0
    return max(1, round((word_count / words_per_minute) * 60))


def _normalized_fingerprint(text: str) -> str:
    compact = " ".join(text.lower().split())
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def _token_fingerprint(tokens: Sequence[str]) -> str:
    compact = " ".join(tokens)
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(match.group(0).lower() for match in _WORD_PATTERN.finditer(text))


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _utc_timestamp(value: datetime | None) -> str:
    timestamp = datetime.now(UTC) if value is None else value.astimezone(UTC)
    return timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
