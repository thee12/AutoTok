from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from autotok.errors import UserInputError
from autotok.media_models import BackgroundMediaRecord, MediaOrientation
from autotok.media_probe import metadata_from_ffprobe
from autotok.media_selection import (
    build_background_media_record,
    recent_media_ids_from_clips,
    select_background_clip,
)
from autotok.media_storage import MediaStore

FIXED_TIME = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


def test_metadata_from_ffprobe_builds_valid_video_metadata(tmp_path: Path) -> None:
    media_path = tmp_path / "portrait.mp4"
    media_path.write_bytes(b"synthetic video bytes")

    metadata = metadata_from_ffprobe(ffprobe_payload(width=1080, height=1920), media_path)

    assert metadata.duration_seconds == 14.5
    assert metadata.frame_rate_fps == 30.0
    assert metadata.orientation is MediaOrientation.PORTRAIT
    assert metadata.content_sha256
    assert metadata.file_size_bytes == len(b"synthetic video bytes")


def test_build_media_record_requires_license_note(tmp_path: Path) -> None:
    media_path = tmp_path / "clip.mp4"
    media_path.write_bytes(b"synthetic video bytes")

    with pytest.raises(UserInputError, match="license"):
        build_background_media_record(
            media_path=media_path,
            license_note=" ",
            ffprobe_command=fake_probe_command(tmp_path),
        )


def test_media_store_saves_media_and_clip_selection(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    media_path = tmp_path / "clip.mp4"
    media_path.write_bytes(b"synthetic video bytes")
    record = build_background_media_record(
        media_path=media_path,
        license_note="User-owned gameplay capture.",
        usage_note="Quiet background clip.",
        tags=("Gameplay", "Calm"),
        ffprobe_command=fake_probe_command(tmp_path),
        created_at=FIXED_TIME,
    )
    store = MediaStore(data_dir)

    stored = store.save_media(record, source_media_path=media_path)
    repeated = store.save_media(record, source_media_path=media_path)
    clip = select_background_clip(
        store.list_media(),
        target_duration_seconds=5.0,
        seed=11,
        orientation=MediaOrientation.PORTRAIT,
        required_tags=("gameplay",),
        created_at=FIXED_TIME,
    )
    stored_clip = store.save_clip(clip)

    assert stored.created is True
    assert repeated.created is False
    assert stored.media_path.exists()
    assert stored.record.tags == ("calm", "gameplay")
    assert stored_clip.record.media_id == record.media_id
    assert stored_clip.record.duration_seconds == 5.0
    assert store.load_clip(clip.clip_id).record == clip


def test_selection_avoids_recent_media_when_alternative_exists(tmp_path: Path) -> None:
    first = media_record(tmp_path, "first.mp4", width=1080, height=1920, created_at=FIXED_TIME)
    second = media_record(tmp_path, "second.mp4", width=1080, height=1920, created_at=FIXED_TIME)
    previous = select_background_clip(
        [first],
        target_duration_seconds=4.0,
        seed=1,
        created_at=FIXED_TIME,
    )

    selected = select_background_clip(
        [first, second],
        target_duration_seconds=4.0,
        seed=1,
        recent_media_ids=recent_media_ids_from_clips([previous]),
        created_at=FIXED_TIME,
    )

    assert selected.media_id == second.media_id
    assert selected.media_id != previous.media_id


def test_selection_rejects_unsuitable_duration_or_tags(tmp_path: Path) -> None:
    record = media_record(tmp_path, "short.mp4", width=1920, height=1080, duration=3.0)

    with pytest.raises(UserInputError, match="No cataloged"):
        select_background_clip(
            [record],
            target_duration_seconds=5.0,
            orientation=MediaOrientation.PORTRAIT,
            required_tags=("gameplay",),
        )


def media_record(
    tmp_path: Path,
    filename: str,
    *,
    width: int,
    height: int,
    duration: float = 12.0,
    created_at: datetime | None = None,
) -> BackgroundMediaRecord:
    media_path = tmp_path / filename
    media_path.write_bytes(f"synthetic {filename}".encode())
    return build_background_media_record(
        media_path=media_path,
        license_note="User-owned gameplay capture.",
        tags=("gameplay",),
        ffprobe_command=fake_probe_command(tmp_path, width=width, height=height, duration=duration),
        created_at=created_at,
    )


def fake_probe_command(
    tmp_path: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    duration: float = 14.5,
) -> list[str]:
    script = tmp_path / f"fake_ffprobe_{width}_{height}_{duration}.py"
    script.write_text(
        "import json\n"
        "print(json.dumps("
        f"{json.dumps(ffprobe_payload(width=width, height=height, duration=duration))}"
        "))\n",
        encoding="utf-8",
    )
    import sys

    return [sys.executable, str(script)]


def ffprobe_payload(*, width: int, height: int, duration: float = 14.5) -> dict[str, object]:
    return {
        "format": {"duration": str(duration), "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": width,
                "height": height,
                "avg_frame_rate": "30/1",
            }
        ],
    }
