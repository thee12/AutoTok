from __future__ import annotations

from datetime import UTC, datetime

import pytest

from autotok.content_gate_models import ContentGateDecision, DuplicateKind, WarningSeverity
from autotok.content_gates import assess_story, build_override_event
from autotok.ingestion import build_manual_text_record
from autotok.models import StoryRecord

FIXED_TIME = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


def test_assess_story_approves_good_original_story() -> None:
    story = build_manual_text_record(
        "I opened the bakery before sunrise. The ovens failed, but the neighbors brought "
        "extension cords and helped us finish every order before the wedding started.",
        imported_at=FIXED_TIME,
    )

    record = assess_story(story, created_at=FIXED_TIME)

    assert record.decision is ContentGateDecision.APPROVED
    assert record.effective_decision is ContentGateDecision.APPROVED
    assert record.quality_score.total >= 75
    assert record.duplicate_matches == ()
    assert record.reject_reasons == ()
    assert record.created_at == "2026-06-30T12:00:00Z"


def test_assess_story_rejects_exact_duplicate() -> None:
    story = build_manual_text_record(
        "The same story happened twice during a long neighborhood meeting. It had enough "
        "details, sentences, and practical context to pass the default duration gate safely.",
        imported_at=FIXED_TIME,
    )

    record = assess_story(story, existing_stories=(story,), created_at=FIXED_TIME)

    assert record.decision is ContentGateDecision.APPROVED

    duplicate = StoryRecord(
        story_id="story_ffffffffffffffff",
        source=story.source,
        original_text=story.original_text,
        normalized_text=story.normalized_text,
    )
    duplicate_record = assess_story(duplicate, existing_stories=(story,), created_at=FIXED_TIME)

    assert duplicate_record.decision is ContentGateDecision.REJECTED
    assert duplicate_record.duplicate_matches[0].kind is DuplicateKind.EXACT
    assert "exact_duplicate" in duplicate_record.reject_reasons


def test_assess_story_flags_near_duplicate_for_review() -> None:
    original = build_manual_text_record(
        "A neighbor found my missing keys under the blue porch mat after a storm passed, "
        "then brought warm tea while everyone searched the driveway together.",
        imported_at=FIXED_TIME,
    )
    candidate = build_manual_text_record(
        "A neighbor found my missing keys under the blue porch mat after the storm passed, "
        "then brought tea while everyone searched the driveway together.",
        imported_at=FIXED_TIME,
    )

    record = assess_story(candidate, existing_stories=(original,), created_at=FIXED_TIME)

    assert record.decision is ContentGateDecision.NEEDS_REVIEW
    assert record.duplicate_matches[0].kind is DuplicateKind.NEAR
    assert "near_duplicate" in record.review_flags


def test_assess_story_adds_privacy_and_policy_warnings() -> None:
    story = build_manual_text_record(
        "Email reader@example.com after the shooting report. This synthetic fixture needs "
        "careful review because the story includes enough context, details, and "
        "plain-language narration material for duration suitability.",
        imported_at=FIXED_TIME,
    )

    record = assess_story(story, created_at=FIXED_TIME)

    assert record.decision is ContentGateDecision.NEEDS_REVIEW
    assert {warning.code for warning in record.warnings} == {
        "private_contact",
        "violence_reference",
    }
    assert all(warning.severity is WarningSeverity.REVIEW for warning in record.warnings)


def test_override_event_changes_effective_decision() -> None:
    story = build_manual_text_record("Too short.", imported_at=FIXED_TIME)
    record = assess_story(story, created_at=FIXED_TIME)
    event = build_override_event(
        decision=ContentGateDecision.APPROVED,
        reason="Reviewed locally for a test fixture.",
        reviewer="tester",
        created_at=FIXED_TIME,
    )

    updated = record.with_override(event)

    assert record.effective_decision is not ContentGateDecision.APPROVED
    assert updated.effective_decision is ContentGateDecision.APPROVED
    assert updated.override_events[0].reviewer == "tester"


def test_override_event_rejects_empty_reason() -> None:
    with pytest.raises(Exception, match="reason"):
        build_override_event(
            decision=ContentGateDecision.APPROVED,
            reason=" ",
            reviewer="tester",
            created_at=FIXED_TIME,
        )
