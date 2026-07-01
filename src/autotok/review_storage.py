"""Filesystem-backed review package storage for Phase 10."""

from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autotok.audio_storage import AudioStore
from autotok.errors import PersistenceError, UserInputError
from autotok.render_storage import RenderStore
from autotok.review_models import (
    RegenerationRequest,
    ReviewAuditEvent,
    ReviewEventType,
    ReviewMetadata,
    ReviewPackage,
    ReviewPackageStatus,
    ReviewScriptSnapshot,
)
from autotok.script_storage import ScriptStore
from autotok.storage import StoryStore
from autotok.subtitle_storage import SubtitleStore

DEFAULT_REVIEWER = "local_reviewer"
REVIEW_DIRNAME = "reviews"
REVIEW_RECORD_FILENAME = "review.json"
ALLOWED_REGENERATION_STAGES = {
    "transform",
    "narrate",
    "subtitle",
    "select_clip",
    "render",
}


class ReviewStore:
    """Store and update local review package state."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.reviews_dir = data_dir / REVIEW_DIRNAME

    def ensure_for_render(
        self, render_id: str, *, reviewer: str = DEFAULT_REVIEWER
    ) -> ReviewPackage:
        """Load or create review state for a render package."""
        existing_path = self._record_path(render_id)
        if existing_path.exists():
            return self.load(render_id)
        render = RenderStore(self.data_dir).load(render_id)
        script = ScriptStore(self.data_dir).load(render.manifest.spec.script_id).record
        timestamp = _utc_timestamp()
        package = ReviewPackage(
            render_id=render.manifest.render_id,
            story_id=render.manifest.spec.story_id,
            script_id=render.manifest.spec.script_id,
            audio_id=render.manifest.spec.audio_id,
            subtitle_id=render.manifest.spec.subtitle_id,
            clip_id=render.manifest.spec.clip_id,
            output_path=str(render.paths.output_path),
            created_at=timestamp,
            updated_at=timestamp,
            script=ReviewScriptSnapshot(
                hook=script.sections.hook,
                body=script.sections.body,
                outro=script.sections.outro,
            ),
        ).with_event(
            _event(
                ReviewEventType.CREATED,
                reviewer=reviewer,
                message="Review package created from render manifest.",
                metadata={"render_id": render.manifest.render_id},
            )
        )
        self.save(package)
        return package

    def load(self, render_id: str) -> ReviewPackage:
        """Load review state for a render package."""
        record_path = self._record_path(render_id)
        if not record_path.exists():
            raise UserInputError(f"Review package was not found: {render_id}")
        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Review package JSON must be an object.")
            return ReviewPackage.from_dict(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PersistenceError(f"Could not load review package: {render_id}") from exc

    def save(self, package: ReviewPackage) -> ReviewPackage:
        """Persist one review package."""
        record_path = self._record_path(package.render_id)
        try:
            record_path.parent.mkdir(parents=True, exist_ok=True)
            _write_json(record_path, package.to_dict())
        except OSError as exc:
            raise PersistenceError(f"Could not write review package: {package.render_id}") from exc
        return package

    def list(self) -> tuple[ReviewPackage, ...]:
        """List review packages in deterministic render ID order."""
        packages: list[ReviewPackage] = []
        for render_id in _available_render_ids(self.data_dir):
            packages.append(self.ensure_for_render(render_id))
        if self.reviews_dir.exists():
            for record_path in sorted(self.reviews_dir.glob("render_*/review.json")):
                render_id = record_path.parent.name
                if render_id not in {package.render_id for package in packages}:
                    packages.append(self.load(render_id))
        return tuple(sorted(packages, key=lambda package: package.render_id))

    def update_script(
        self,
        render_id: str,
        *,
        hook: str,
        body: str,
        outro: str,
        reviewer: str = DEFAULT_REVIEWER,
    ) -> ReviewPackage:
        """Update editable script text for a review package."""
        script = ReviewScriptSnapshot(hook=hook.strip(), body=body.strip(), outro=outro.strip())
        if not script.full_text.strip():
            raise UserInputError("Review script text must not be empty.")
        package = self.load(render_id)
        event = _event(
            ReviewEventType.SCRIPT_EDITED,
            reviewer=reviewer,
            message="Editable script text updated.",
            metadata={"script_id": package.script_id},
        )
        updated = replace(
            package.with_event(event),
            script=script,
            status=ReviewPackageStatus.PENDING,
            approved_at=None,
            rejected_at=None,
        )
        return self.save(updated)

    def update_metadata(
        self,
        render_id: str,
        *,
        title: str,
        caption: str,
        hashtags: tuple[str, ...],
        reviewer: str = DEFAULT_REVIEWER,
    ) -> ReviewPackage:
        """Update editable export metadata for a review package."""
        metadata = ReviewMetadata.from_dict(
            {"title": title.strip(), "caption": caption.strip(), "hashtags": list(hashtags)}
        )
        package = self.load(render_id)
        event = _event(
            ReviewEventType.METADATA_EDITED,
            reviewer=reviewer,
            message="Export metadata updated.",
            metadata={"render_id": render_id},
        )
        updated = replace(package.with_event(event), metadata=metadata)
        return self.save(updated)

    def approve(self, render_id: str, *, reviewer: str = DEFAULT_REVIEWER) -> ReviewPackage:
        """Mark a review package approved for export."""
        package = self.load(render_id)
        timestamp = _utc_timestamp()
        event = _event(
            ReviewEventType.APPROVED,
            reviewer=reviewer,
            message="Review package approved for export.",
            created_at=timestamp,
            metadata={"render_id": render_id},
        )
        updated = replace(
            package.with_event(event),
            status=ReviewPackageStatus.APPROVED,
            approved_at=timestamp,
            rejected_at=None,
        )
        return self.save(updated)

    def reject(
        self,
        render_id: str,
        *,
        reason: str,
        reviewer: str = DEFAULT_REVIEWER,
    ) -> ReviewPackage:
        """Reject a review package with an audit reason."""
        cleaned_reason = reason.strip()
        if not cleaned_reason:
            raise UserInputError("A rejection reason is required.")
        package = self.load(render_id)
        timestamp = _utc_timestamp()
        event = _event(
            ReviewEventType.REJECTED,
            reviewer=reviewer,
            message=cleaned_reason,
            created_at=timestamp,
            metadata={"render_id": render_id},
        )
        updated = replace(
            package.with_event(event),
            status=ReviewPackageStatus.REJECTED,
            approved_at=None,
            rejected_at=timestamp,
        )
        return self.save(updated)

    def request_regeneration(
        self,
        render_id: str,
        *,
        stage_name: str,
        reason: str,
        reviewer: str = DEFAULT_REVIEWER,
    ) -> ReviewPackage:
        """Record a request to regenerate a pipeline stage."""
        cleaned_stage = stage_name.strip()
        cleaned_reason = reason.strip()
        if cleaned_stage not in ALLOWED_REGENERATION_STAGES:
            allowed = ", ".join(sorted(ALLOWED_REGENERATION_STAGES))
            raise UserInputError(f"Regeneration stage must be one of: {allowed}.")
        if not cleaned_reason:
            raise UserInputError("A regeneration reason is required.")
        package = self.load(render_id)
        timestamp = _utc_timestamp()
        request = RegenerationRequest(
            request_id=_new_id("regen"),
            stage_name=cleaned_stage,
            reason=cleaned_reason,
            requested_by=reviewer.strip() or DEFAULT_REVIEWER,
            requested_at=timestamp,
        )
        event = _event(
            ReviewEventType.REGENERATION_REQUESTED,
            reviewer=reviewer,
            message=cleaned_reason,
            created_at=timestamp,
            metadata={"stage_name": cleaned_stage},
        )
        updated = replace(
            package.with_event(event),
            status=ReviewPackageStatus.CHANGES_REQUESTED,
            approved_at=None,
            rejected_at=None,
            regeneration_requests=(*package.regeneration_requests, request),
        )
        return self.save(updated)

    def details(self, render_id: str) -> dict[str, object]:
        """Build an API-ready review package detail object."""
        package = self.ensure_for_render(render_id)
        render = RenderStore(self.data_dir).load(render_id)
        story = StoryStore(self.data_dir).load(package.story_id).record
        script = ScriptStore(self.data_dir).load(package.script_id).record
        audio = AudioStore(self.data_dir).load(package.audio_id).record
        subtitle = SubtitleStore(self.data_dir).load(package.subtitle_id).document
        return {
            "review": package.to_dict(),
            "render": render.manifest.to_dict(),
            "story": story.to_dict(),
            "source_preview": _preview(story.normalized_text, limit=260),
            "original_script": script.to_dict(),
            "audio": audio.to_dict(),
            "subtitle": subtitle.to_dict(),
            "media": {
                "video_url": f"/media/render/{render_id}/output.mp4",
                "output_path": str(render.paths.output_path),
            },
        }

    def _record_path(self, render_id: str) -> Path:
        return self.reviews_dir / render_id / REVIEW_RECORD_FILENAME


def _available_render_ids(data_dir: Path) -> tuple[str, ...]:
    renders_dir = data_dir / "renders"
    if not renders_dir.exists():
        return ()
    return tuple(
        sorted(
            path.name for path in renders_dir.glob("render_*") if (path / "manifest.json").exists()
        )
    )


def _event(
    event_type: ReviewEventType,
    *,
    reviewer: str,
    message: str,
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> ReviewAuditEvent:
    return ReviewAuditEvent(
        event_id=_new_id("event"),
        event_type=event_type,
        created_at=created_at or _utc_timestamp(),
        reviewer=reviewer.strip() or DEFAULT_REVIEWER,
        message=message,
        metadata={} if metadata is None else metadata,
    )


def _preview(text: str, *, limit: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3]}..."


def _write_json(path: Path, payload: dict[str, object]) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"
