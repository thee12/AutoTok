from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autotok.audio_storage import AudioStore
from autotok.ingestion import build_manual_text_record
from autotok.media_selection import build_background_media_record, select_background_clip
from autotok.media_storage import MediaStore
from autotok.render import build_render_spec, render_video_package
from autotok.render_storage import RenderStore
from autotok.review_api import MP4_CONTENT_TYPE, ReviewApi
from autotok.review_models import ReviewPackageStatus
from autotok.review_storage import ReviewStore
from autotok.script_storage import ScriptStore
from autotok.storage import StoryStore
from autotok.subtitle_storage import SubtitleStore
from autotok.subtitles import ApproximateAudioDurationStrategy, build_subtitle_document
from autotok.transform import DeterministicScriptTransformer
from autotok.tts import LocalWavTtsProvider, build_tts_audio_record
from tests.test_phase6_helpers import (
    create_fake_ffmpeg,
    create_fake_ffprobe,
)


def test_review_store_creates_and_updates_review_package(tmp_path: Path) -> None:
    render_id = _create_render(tmp_path)
    store = ReviewStore(tmp_path / "data")

    package = store.ensure_for_render(render_id)
    edited = store.update_metadata(
        render_id,
        title="A tighter title",
        caption="A caption for review.",
        hashtags=("autotok", "#review"),
    )
    scripted = store.update_script(
        render_id,
        hook="New hook",
        body="New body",
        outro="New outro",
    )
    approved = store.approve(render_id)

    assert package.status is ReviewPackageStatus.PENDING
    assert package.render_id == render_id
    assert edited.metadata.title == "A tighter title"
    assert edited.metadata.hashtags == ("#autotok", "#review")
    assert scripted.script.full_text == "New hook\n\nNew body\n\nNew outro"
    assert approved.status is ReviewPackageStatus.APPROVED
    assert approved.approved_at is not None
    assert [event.event_type.value for event in approved.audit_events] == [
        "created",
        "metadata_edited",
        "script_edited",
        "approved",
    ]


def test_review_store_rejects_and_records_regeneration_request(tmp_path: Path) -> None:
    render_id = _create_render(tmp_path)
    store = ReviewStore(tmp_path / "data")
    store.ensure_for_render(render_id)

    rejected = store.reject(render_id, reason="Opening hook needs work.")
    requested = store.request_regeneration(
        render_id,
        stage_name="render",
        reason="Subtitles need a visual pass.",
    )

    assert rejected.status is ReviewPackageStatus.REJECTED
    assert rejected.rejected_at is not None
    assert requested.status is ReviewPackageStatus.CHANGES_REQUESTED
    assert requested.regeneration_requests[0].stage_name == "render"
    assert requested.regeneration_requests[0].reason == "Subtitles need a visual pass."

    with pytest.raises(Exception, match="Regeneration stage"):
        store.request_regeneration(render_id, stage_name="publish", reason="Nope")


def test_review_api_routes_and_media_preview(tmp_path: Path) -> None:
    render_id = _create_render(tmp_path)
    api = ReviewApi(tmp_path / "data")

    health = _json(api.handle("GET", "/api/health"))
    created = _json(api.handle("POST", f"/api/reviews/render/{render_id}", b"{}"))
    detail = _json(api.handle("GET", f"/api/reviews/{render_id}"))
    metadata = _json(
        api.handle(
            "PATCH",
            f"/api/reviews/{render_id}/metadata",
            json.dumps(
                {"title": "Reviewed", "caption": "Ready", "hashtags": "autotok local"}
            ).encode("utf-8"),
        )
    )
    scripted = _json(
        api.handle(
            "PATCH",
            f"/api/reviews/{render_id}/script",
            json.dumps({"hook": "Hook", "body": "Body", "outro": "Outro"}).encode("utf-8"),
        )
    )
    approved = _json(api.handle("POST", f"/api/reviews/{render_id}/approve", b"{}"))
    media = api.media_response(f"/media/render/{render_id}/output.mp4")

    assert health["phase"] == 10
    assert created["review"]["render_id"] == render_id
    assert detail["review"]["status"] == "pending_review"
    assert metadata["review"]["metadata"]["hashtags"] == ["#autotok", "#local"]
    assert scripted["review"]["script"]["body"] == "Body"
    assert approved["review"]["status"] == "approved"
    assert media.status == 200
    assert media.content_type == MP4_CONTENT_TYPE
    assert media.body == b"rendered mp4 bytes"


def test_review_api_reports_route_and_validation_errors(tmp_path: Path) -> None:
    render_id = _create_render(tmp_path)
    api = ReviewApi(tmp_path / "data")
    api.handle("POST", f"/api/reviews/render/{render_id}", b"{}")

    missing = _json_response(api.handle("GET", "/api/not-real"))
    invalid = _json_response(
        api.handle(
            "POST",
            f"/api/reviews/{render_id}/regenerate",
            json.dumps({"stage_name": "publish", "reason": "No"}).encode("utf-8"),
        )
    )

    assert missing[0] == 404
    assert "not found" in missing[1]["error"]
    assert invalid[0] == 400
    assert "Regeneration stage" in invalid[1]["error"]


def _create_render(tmp_path: Path) -> str:
    data_dir = tmp_path / "data"
    story = build_manual_text_record(
        "A review dashboard story with enough material for a local render package."
    )
    StoryStore(data_dir).save(story)
    script = DeterministicScriptTransformer().transform(story).approve("2026-06-30T12:00:00Z")
    stored_script = ScriptStore(data_dir).save(script, before_text=story.normalized_text)
    audio_record, audio_path = build_tts_audio_record(
        stored_script.record,
        provider=LocalWavTtsProvider(),
    )
    audio = AudioStore(data_dir).save(audio_record, source_audio_path=audio_path)
    subtitle_document = build_subtitle_document(
        script=stored_script.record,
        audio=audio.record,
        timing_strategy=ApproximateAudioDurationStrategy(),
    )
    subtitle = SubtitleStore(data_dir).save(subtitle_document)
    media_file = tmp_path / "review-background.mp4"
    media_file.write_bytes(b"authorized review background media")
    media_probe = create_fake_ffprobe(tmp_path, width=1080, height=1920, duration=30.0)
    media_record = build_background_media_record(
        media_path=media_file,
        license_note="Synthetic authorized review media.",
        tags=("review",),
        ffprobe_command=[str(media_probe)],
    )
    media_store = MediaStore(data_dir)
    media = media_store.save_media(media_record, source_media_path=media_file)
    clip_record = select_background_clip(
        [media.record],
        target_duration_seconds=audio.record.metadata.duration_seconds + 1,
        seed=4,
        required_tags=("review",),
    )
    clip = media_store.save_clip(clip_record)
    ffmpeg = create_fake_ffmpeg(tmp_path)
    render_probe = create_fake_ffprobe(tmp_path, width=1080, height=1920, duration=30.0)
    spec = build_render_spec(audio=audio, subtitle=subtitle, media=media, clip=clip)
    stored = render_video_package(
        store=RenderStore(data_dir),
        spec=spec,
        subtitle=subtitle,
        ffmpeg_command=[str(ffmpeg)],
        ffprobe_command=[str(render_probe)],
    )
    return stored.manifest.render_id


def _json(response: Any) -> dict[str, Any]:
    assert response.status in {200, 201}
    payload = json.loads(response.body.decode("utf-8"))
    assert isinstance(payload, dict)
    return payload


def _json_response(response: Any) -> tuple[int, dict[str, Any]]:
    payload = json.loads(response.body.decode("utf-8"))
    assert isinstance(payload, dict)
    return response.status, payload
