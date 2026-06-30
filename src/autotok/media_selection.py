"""Background media cataloging and deterministic segment selection."""

from __future__ import annotations

import hashlib
import random
import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from autotok.errors import UserInputError
from autotok.media_models import BackgroundMediaRecord, ClipPreparationRecord, MediaOrientation
from autotok.media_probe import probe_video_media

DEFAULT_SELECTION_SEED = 0
DEFAULT_RECENT_AVOIDANCE_LIMIT = 5
MIN_TARGET_DURATION_SECONDS = 0.5
_TAG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def build_background_media_record(
    *,
    media_path: Path,
    license_note: str,
    usage_note: str | None = None,
    tags: Sequence[str] = (),
    ffprobe_command: Sequence[str] | None = None,
    created_at: datetime | None = None,
) -> BackgroundMediaRecord:
    """Probe and build a catalog record for an authorized background clip."""
    clean_license_note = license_note.strip()
    if not clean_license_note:
        raise UserInputError("A license or authorization note is required for background media.")
    normalized_tags = normalize_tags(tags)
    metadata = probe_video_media(media_path, ffprobe_command=ffprobe_command)
    media_id = stable_media_id(
        content_sha256=metadata.content_sha256,
        license_note=clean_license_note,
        tags=normalized_tags,
    )
    return BackgroundMediaRecord(
        media_id=media_id,
        created_at=_utc_timestamp(created_at),
        original_filename=media_path.name,
        source_path=str(media_path.expanduser()),
        license_note=clean_license_note,
        usage_note=usage_note.strip() if usage_note is not None and usage_note.strip() else None,
        tags=normalized_tags,
        metadata=metadata,
    )


def select_background_clip(
    media_records: Sequence[BackgroundMediaRecord],
    *,
    target_duration_seconds: float,
    seed: int = DEFAULT_SELECTION_SEED,
    orientation: MediaOrientation | None = None,
    required_tags: Sequence[str] = (),
    recent_media_ids: Sequence[str] = (),
    created_at: datetime | None = None,
) -> ClipPreparationRecord:
    """Select a deterministic valid media segment for a target duration."""
    target_duration = round(float(target_duration_seconds), 3)
    if target_duration < MIN_TARGET_DURATION_SECONDS:
        raise UserInputError("target_seconds must be at least 0.5 seconds.")
    tags = normalize_tags(required_tags)
    candidates = sorted(
        (
            record
            for record in media_records
            if record.metadata.duration_seconds >= target_duration
            and (orientation is None or record.metadata.orientation is orientation)
            and set(tags).issubset(record.tags)
        ),
        key=lambda record: record.media_id,
    )
    if not candidates:
        raise UserInputError(
            "No cataloged background media matches the requested duration, tags, and orientation."
        )

    recent_set = set(recent_media_ids)
    non_recent = [record for record in candidates if record.media_id not in recent_set]
    eligible = non_recent or candidates
    rng = random.Random(seed)
    selected = eligible[rng.randrange(len(eligible))]
    max_start = max(0.0, selected.metadata.duration_seconds - target_duration)
    start_seconds = round(rng.uniform(0.0, max_start), 3) if max_start > 0 else 0.0
    end_seconds = round(start_seconds + target_duration, 3)
    requested_orientation = orientation.value if orientation is not None else "any"
    clip_id = stable_clip_id(
        media_id=selected.media_id,
        target_duration_seconds=target_duration,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        seed=seed,
        required_tags=tags,
        requested_orientation=requested_orientation,
    )
    return ClipPreparationRecord(
        clip_id=clip_id,
        media_id=selected.media_id,
        created_at=_utc_timestamp(created_at),
        target_duration_seconds=target_duration,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        seed=seed,
        requested_orientation=requested_orientation,
        required_tags=tags,
        avoided_recent_media_ids=tuple(recent_media_ids),
    )


def recent_media_ids_from_clips(
    clips: Iterable[ClipPreparationRecord],
    *,
    limit: int = DEFAULT_RECENT_AVOIDANCE_LIMIT,
) -> tuple[str, ...]:
    """Return the most recent selected media IDs for avoidance."""
    if limit <= 0:
        return ()
    ordered = sorted(clips, key=lambda clip: clip.created_at, reverse=True)
    media_ids: list[str] = []
    for clip in ordered:
        if clip.media_id not in media_ids:
            media_ids.append(clip.media_id)
        if len(media_ids) >= limit:
            break
    return tuple(media_ids)


def normalize_tags(tags: Sequence[str]) -> tuple[str, ...]:
    """Normalize and validate media tags."""
    normalized: list[str] = []
    for tag in tags:
        clean = tag.strip().lower()
        if not clean:
            continue
        if _TAG_PATTERN.fullmatch(clean) is None:
            raise UserInputError(
                "Tags must use lowercase letters, numbers, underscores, or hyphens."
            )
        if clean not in normalized:
            normalized.append(clean)
    return tuple(sorted(normalized))


def stable_media_id(*, content_sha256: str, license_note: str, tags: Sequence[str]) -> str:
    """Build a stable media ID from content and authorization metadata."""
    payload = "\n".join([content_sha256, license_note.strip(), *tags]).encode("utf-8")
    return f"media_{hashlib.sha256(payload).hexdigest()[:16]}"


def stable_clip_id(
    *,
    media_id: str,
    target_duration_seconds: float,
    start_seconds: float,
    end_seconds: float,
    seed: int,
    required_tags: Sequence[str],
    requested_orientation: str,
) -> str:
    """Build a stable clip-preparation ID from selection inputs."""
    payload = "\n".join(
        [
            media_id,
            f"{target_duration_seconds:.3f}",
            f"{start_seconds:.3f}",
            f"{end_seconds:.3f}",
            str(seed),
            requested_orientation,
            *required_tags,
        ]
    ).encode("utf-8")
    return f"clip_{hashlib.sha256(payload).hexdigest()[:16]}"


def _utc_timestamp(value: datetime | None) -> str:
    timestamp = datetime.now(UTC) if value is None else value.astimezone(UTC)
    return timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
