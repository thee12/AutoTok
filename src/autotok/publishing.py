"""Local manual-upload publishing handoff workflows."""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from autotok.config import AppConfig
from autotok.errors import PersistenceError, UserInputError
from autotok.publishing_models import (
    ManualUploadPackage,
    PublicationAuditEvent,
    PublicationEventType,
    PublicationRecord,
    PublicationResult,
    PublicationStatus,
    PublishingProvider,
    TikTokManualUploadOptions,
)
from autotok.publishing_storage import PublicationStore, new_id, utc_timestamp
from autotok.render_storage import RenderStore, StoredRender
from autotok.review_models import ReviewPackage, ReviewPackageStatus
from autotok.review_storage import ReviewStore

MANUAL_UPLOAD_DIRNAME = "manual_upload"
MANUAL_VIDEO_FILENAME = "video.mp4"
CAPTION_FILENAME = "caption.txt"
METADATA_FILENAME = "metadata.json"
INSTRUCTIONS_FILENAME = "instructions.md"


def prepare_tiktok_publication(
    *,
    config: AppConfig,
    render_id: str,
    options: TikTokManualUploadOptions,
) -> PublicationResult:
    """Prepare a local TikTok manual-upload package for an approved render."""
    render = RenderStore(config.data_dir).load(render_id)
    review = ReviewStore(config.data_dir).load(render_id)
    if review.status is not ReviewPackageStatus.APPROVED or review.approved_at is None:
        raise UserInputError(
            "Render package must be approved in `autotok review` before preparing a TikTok upload."
        )

    store = PublicationStore(config.data_dir)
    existing = (
        store.load(render_id, PublishingProvider.TIKTOK).record
        if store.exists(render_id, PublishingProvider.TIKTOK)
        else None
    )
    package = _write_manual_upload_package(
        config=config,
        render=render,
        review=review,
        options=options,
    )
    timestamp = utc_timestamp()
    if existing is None:
        record = PublicationRecord(
            publication_id=new_id("publication"),
            render_id=render_id,
            provider=PublishingProvider.TIKTOK,
            status=PublicationStatus.EXPORT_READY,
            created_at=timestamp,
            updated_at=timestamp,
            approved_review_at=review.approved_at,
            render_output_path=str(render.paths.output_path),
            manual_options=options,
            upload_package=package,
        )
        created = True
    else:
        record = replace(existing, manual_options=options)
        created = False

    event = _event(
        PublicationEventType.EXPORT_PREPARED,
        message="TikTok manual upload package prepared.",
        metadata={"package": package.to_dict(), "manual_options": options.to_dict()},
    )
    record = record.with_event(
        event,
        status=PublicationStatus.EXPORT_READY,
        upload_package=package,
    )
    stored = store.save(record, created=created)
    return PublicationResult(record=stored.record, package=package)


def record_manual_tiktok_publish(
    *,
    config: AppConfig,
    render_id: str,
    url: str | None = None,
) -> PublicationRecord:
    """Mark a TikTok package as manually published after the operator uploads it."""
    store = PublicationStore(config.data_dir)
    record = store.load(render_id, PublishingProvider.TIKTOK).record
    event = _event(
        PublicationEventType.MANUAL_STATUS_RECORDED,
        message="Operator recorded a manual TikTok publish.",
        metadata={"url": url} if url else {},
    )
    updated = record.with_event(
        event,
        status=PublicationStatus.MANUALLY_PUBLISHED,
        manual_publish_url=url,
    )
    return store.save(updated).record


def _write_manual_upload_package(
    *,
    config: AppConfig,
    render: StoredRender,
    review: ReviewPackage,
    options: TikTokManualUploadOptions,
) -> ManualUploadPackage:
    output_path = render.paths.output_path
    if not output_path.exists() or not output_path.is_file():
        raise UserInputError(f"Rendered video file is not readable: {output_path}")

    package_dir = (
        config.data_dir
        / "publications"
        / render.manifest.render_id
        / PublishingProvider.TIKTOK.value
        / MANUAL_UPLOAD_DIRNAME
    )
    video_path = package_dir / MANUAL_VIDEO_FILENAME
    caption_path = package_dir / CAPTION_FILENAME
    metadata_path = package_dir / METADATA_FILENAME
    instructions_path = package_dir / INSTRUCTIONS_FILENAME

    title = review.metadata.title.strip() or f"AutoTok render {render.manifest.render_id}"
    hashtags = review.metadata.hashtags
    caption = _caption_text(review)
    metadata = {
        "provider": PublishingProvider.TIKTOK.value,
        "mode": "manual_upload",
        "render_id": render.manifest.render_id,
        "source_video_path": str(output_path),
        "video_path": str(video_path),
        "title": title,
        "caption": caption,
        "hashtags": list(hashtags),
        "manual_options": options.to_dict(),
        "safety": {
            "api_upload_disabled": True,
            "requires_operator_upload": True,
            "requires_operator_final_publish_click": True,
        },
    }

    try:
        package_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output_path, video_path)
        caption_path.write_text(caption + "\n", encoding="utf-8")
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        instructions_path.write_text(
            _instructions_text(
                title=title, caption=caption, video_path=video_path, options=options
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        raise PersistenceError(
            f"Could not write TikTok manual upload package for {render.manifest.render_id}."
        ) from exc

    return ManualUploadPackage(
        package_dir=str(package_dir),
        video_path=str(video_path),
        caption_path=str(caption_path),
        metadata_path=str(metadata_path),
        instructions_path=str(instructions_path),
        title=title,
        caption=caption,
        hashtags=hashtags,
    )


def _caption_text(review: ReviewPackage) -> str:
    parts = [review.metadata.caption.strip(), " ".join(review.metadata.hashtags).strip()]
    caption = " ".join(part for part in parts if part)
    return caption or "Generated with AutoTok."


def _instructions_text(
    *,
    title: str,
    caption: str,
    video_path: Path,
    options: TikTokManualUploadOptions,
) -> str:
    duet = "off" if options.disable_duet else "operator choice"
    comments = "off" if options.disable_comment else "operator choice"
    stitch = "off" if options.disable_stitch else "operator choice"
    return f"""# TikTok Manual Upload Package

AutoTok does not upload or publish this video through TikTok APIs. Use these files to
manual publish from your own TikTok account.

## Files

- Video: `{video_path}`
- Caption: `caption.txt`
- Metadata: `metadata.json`

## Suggested TikTok Fields

Title:
{title}

Caption:
{caption}

Suggested settings:
- Privacy: {options.privacy_level}
- Duet: {duet}
- Comments: {comments}
- Stitch: {stitch}
- Cover timestamp: {options.cover_timestamp_ms} ms

## Manual Steps

1. Open TikTok in your browser or the TikTok app.
2. Start a normal manual upload from your own account.
3. Select `video.mp4` from this package.
4. Paste the caption from `caption.txt`.
5. Review all TikTok settings, copyright prompts, synthetic-media prompts,
   privacy, and audience fields yourself.
6. Click TikTok's final publish/post button only when you are satisfied.

No TikTok access token, API scope, Direct Post request, or automated publish
action is used by AutoTok in this workflow.
"""


def _event(
    event_type: PublicationEventType,
    *,
    message: str,
    metadata: Mapping[str, Any] | None = None,
) -> PublicationAuditEvent:
    return PublicationAuditEvent(
        event_id=new_id("event"),
        event_type=event_type,
        created_at=utc_timestamp(),
        message=message,
        metadata={} if metadata is None else dict(metadata),
    )
