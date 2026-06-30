from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from autotok.errors import UserInputError
from autotok.ingestion import build_manual_text_record
from autotok.script_models import ReviewStatus
from autotok.script_storage import ScriptStore
from autotok.transform import (
    DEFAULT_WORDS_PER_MINUTE,
    DeterministicScriptTransformer,
    FakeScriptTransformer,
    build_duration_budget,
    redact_private_text,
    truncate_to_words,
)

FIXED_TIME = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


def test_redact_private_text_counts_common_contact_details() -> None:
    cleaned, report = redact_private_text(
        "Email me@example.com or call 212-555-1212 and ping @local_user."
    )

    assert "me@example.com" not in cleaned
    assert "212-555-1212" not in cleaned
    assert "@local_user" not in cleaned
    assert report.email_redactions == 1
    assert report.phone_redactions == 1
    assert report.handle_redactions == 1
    assert report.total_redactions == 3


def test_duration_budget_uses_target_and_wpm() -> None:
    budget = build_duration_budget(
        "one two three four five",
        target_seconds=30,
        words_per_minute=DEFAULT_WORDS_PER_MINUTE,
    )

    assert budget.target_seconds == 30
    assert budget.max_words == 75
    assert budget.word_count == 5
    assert budget.estimated_seconds == 2


def test_duration_budget_rejects_out_of_range_target() -> None:
    with pytest.raises(UserInputError, match="Target seconds"):
        build_duration_budget("words", target_seconds=10, words_per_minute=150)


def test_truncate_to_words_prefers_sentence_boundary() -> None:
    text = "First sentence is short. Second sentence should be omitted."

    assert truncate_to_words(text, 4) == "First sentence is short."


def test_deterministic_transformer_creates_reviewable_script() -> None:
    story = build_manual_text_record(
        "Contact jane@example.com. Then the whole room went silent.",
        title="The Quiet Room",
        imported_at=FIXED_TIME,
    )

    script = DeterministicScriptTransformer().transform(
        story,
        target_seconds=45,
        created_at=FIXED_TIME,
    )

    assert script.script_id.startswith("script_")
    assert script.story_id == story.story_id
    assert script.review_status is ReviewStatus.PENDING
    assert script.created_at == "2026-06-30T12:00:00Z"
    assert script.sections.hook.startswith("This story starts with The Quiet Room")
    assert "[redacted email]" in script.full_text
    assert script.privacy_report.email_redactions == 1
    assert script.duration_budget.target_seconds == 45
    assert [step.name for step in script.transformation_steps] == [
        "baseline_clean",
        "privacy_redaction",
        "duration_budget",
        "section_structure",
    ]


def test_fake_transformer_uses_provider_interface() -> None:
    story = build_manual_text_record("A source story.", imported_at=FIXED_TIME)

    script = FakeScriptTransformer().transform(story, created_at=FIXED_TIME)

    assert script.provider_name == "fake"
    assert script.sections.body == f"Fake body for {story.story_id}."


def test_script_store_saves_and_approves_artifacts(tmp_path: Path) -> None:
    story = build_manual_text_record("A source story.", imported_at=FIXED_TIME)
    script = DeterministicScriptTransformer().transform(story, created_at=FIXED_TIME)
    store = ScriptStore(tmp_path / "data")

    stored = store.save(script, before_text=story.normalized_text)
    repeated = store.save(script, before_text=story.normalized_text)
    approved = store.approve(script.script_id, approved_at=FIXED_TIME)

    assert stored.created is True
    assert repeated.created is False
    assert stored.before_text_path.read_text(encoding="utf-8") == story.normalized_text
    assert stored.script_text_path.read_text(encoding="utf-8") == script.full_text
    assert approved.record.review_status is ReviewStatus.APPROVED
    assert approved.record.approved_at == "2026-06-30T12:00:00Z"
