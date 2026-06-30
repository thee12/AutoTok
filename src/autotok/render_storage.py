"""Filesystem storage for Phase 6 render packages."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autotok.errors import PersistenceError, UserInputError
from autotok.render_models import RenderManifest, RenderSpec

RENDER_ID_PATTERN = re.compile(r"^render_[a-f0-9]{16}$")


@dataclass(frozen=True, slots=True)
class RenderPaths:
    """Filesystem paths for a render package."""

    render_dir: Path
    work_dir: Path
    output_path: Path
    manifest_path: Path
    spec_path: Path
    subtitle_ass_path: Path


@dataclass(frozen=True, slots=True)
class StoredRender:
    """A stored render manifest and artifact paths."""

    manifest: RenderManifest
    paths: RenderPaths
    created: bool = False


class RenderStore:
    """Store Phase 6 render packages in the local workspace."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.renders_dir = data_dir / "renders"

    def paths_for(self, spec: RenderSpec) -> RenderPaths:
        """Return artifact paths for a render specification."""
        _validate_render_id(spec.render_id)
        render_dir = self.renders_dir / spec.render_id
        work_dir = render_dir / "work"
        return RenderPaths(
            render_dir=render_dir,
            work_dir=work_dir,
            output_path=render_dir / spec.output_filename,
            manifest_path=render_dir / "manifest.json",
            spec_path=render_dir / "render_spec.json",
            subtitle_ass_path=work_dir / "subtitles.ass",
        )

    def save_spec(self, spec: RenderSpec) -> RenderPaths:
        """Create directories and write a render spec."""
        paths = self.paths_for(spec)
        try:
            paths.work_dir.mkdir(parents=True, exist_ok=True)
            _write_json(paths.spec_path, spec.to_dict())
        except OSError as exc:
            raise PersistenceError(f"Could not write render spec for {spec.render_id}.") from exc
        return paths

    def save_manifest(
        self, manifest: RenderManifest, paths: RenderPaths, *, created: bool
    ) -> StoredRender:
        """Persist a completed render manifest."""
        try:
            _write_json(paths.manifest_path, manifest.to_dict())
        except OSError as exc:
            raise PersistenceError(
                f"Could not write render manifest for {manifest.render_id}."
            ) from exc
        return StoredRender(manifest=manifest, paths=paths, created=created)

    def load(self, render_id: str) -> StoredRender:
        """Load a completed render package by ID."""
        _validate_render_id(render_id)
        render_dir = self.renders_dir / render_id
        manifest_path = render_dir / "manifest.json"
        if not manifest_path.exists():
            raise UserInputError(f"Render manifest was not found: {render_id}")
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Render manifest JSON must be an object.")
            manifest = RenderManifest.from_dict(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PersistenceError(f"Could not load render manifest: {render_id}") from exc
        paths = self.paths_for(manifest.spec)
        return StoredRender(manifest=manifest, paths=paths, created=False)


def _validate_render_id(render_id: str) -> None:
    if RENDER_ID_PATTERN.fullmatch(render_id) is None:
        raise UserInputError(
            "Render ID must look like render_ followed by 16 lowercase hexadecimal characters."
        )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)
