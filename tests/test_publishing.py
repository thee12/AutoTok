from __future__ import annotations

import json
from pathlib import Path

import pytest

from autotok.cli import main
from autotok.config import AppConfig
from autotok.errors import UserInputError
from autotok.publishing import prepare_tiktok_publication, record_manual_tiktok_publish
from autotok.publishing_models import (
    PublicationStatus,
    PublishingProvider,
    TikTokManualUploadOptions,
)
from autotok.publishing_storage import PublicationStore
from autotok.review_storage import ReviewStore
from tests.test_review import _create_render


def test_tiktok_manual_upload_requires_approved_review_and_writes_package(tmp_path: Path) -> None:
    render_id = _create_render(tmp_path)
    data_dir = tmp_path / "data"
    config = AppConfig(data_dir=data_dir)
    review_store = ReviewStore(data_dir)

    review_store.ensure_for_render(render_id)
    with pytest.raises(UserInputError, match="approved"):
        prepare_tiktok_publication(
            config=config,
            render_id=render_id,
            options=TikTokManualUploadOptions(),
        )

    review_store.update_metadata(
        render_id,
        title="A reviewed title",
        caption="Manual caption",
        hashtags=("#manual",),
    )
    review_store.approve(render_id)

    result = prepare_tiktok_publication(
        config=config,
        render_id=render_id,
        options=TikTokManualUploadOptions(disable_comment=True),
    )

    stored = PublicationStore(data_dir).load(render_id, PublishingProvider.TIKTOK)
    package = result.package
    metadata = json.loads(Path(package.metadata_path).read_text(encoding="utf-8"))

    assert result.record.status is PublicationStatus.EXPORT_READY
    assert stored.record.status is PublicationStatus.EXPORT_READY
    assert Path(package.video_path).read_bytes()
    assert Path(package.caption_path).read_text(encoding="utf-8").strip() == (
        "Manual caption #manual"
    )
    assert Path(package.instructions_path).exists()
    assert metadata["mode"] == "manual_upload"
    assert metadata["safety"]["api_upload_disabled"] is True
    assert metadata["safety"]["requires_operator_final_publish_click"] is True
    assert stored.record.audit_events[-1].event_type.value == "export_prepared"
    assert "access_token" not in json.dumps(result.to_dict())


def test_tiktok_manual_upload_reprepare_refreshes_package_without_api_duplicate_state(
    tmp_path: Path,
) -> None:
    render_id = _approved_render(tmp_path)
    config = AppConfig(data_dir=tmp_path / "data")

    first = prepare_tiktok_publication(
        config=config,
        render_id=render_id,
        options=TikTokManualUploadOptions(),
    )
    second = prepare_tiktok_publication(
        config=config,
        render_id=render_id,
        options=TikTokManualUploadOptions(disable_stitch=True),
    )

    assert first.record.publication_id == second.record.publication_id
    assert second.record.status is PublicationStatus.EXPORT_READY
    assert second.record.manual_options.disable_stitch is True
    assert second.duplicate_prevented is False
    assert [event.event_type.value for event in second.record.audit_events] == [
        "export_prepared",
        "export_prepared",
    ]


def test_record_manual_tiktok_publish_marks_local_status(tmp_path: Path) -> None:
    render_id = _approved_render(tmp_path)
    config = AppConfig(data_dir=tmp_path / "data")
    prepare_tiktok_publication(
        config=config,
        render_id=render_id,
        options=TikTokManualUploadOptions(),
    )

    record = record_manual_tiktok_publish(
        config=config,
        render_id=render_id,
        url="https://www.tiktok.com/@me/video/123",
    )

    assert record.status is PublicationStatus.MANUALLY_PUBLISHED
    assert record.manual_publish_url == "https://www.tiktok.com/@me/video/123"
    assert record.audit_events[-1].event_type.value == "manual_status_recorded"


def test_publish_cli_creates_tiktok_manual_upload_package(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    render_id = _approved_render(tmp_path)
    data_dir = tmp_path / "data"

    exit_code = main(["--data-dir", str(data_dir), "publish", "tiktok", render_id, "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["manual_upload"] is True
    assert payload["publication"]["status"] == "export_ready"
    assert Path(payload["package"]["instructions_path"]).exists()


def test_publish_cli_marks_manual_tiktok_publish(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    render_id = _approved_render(tmp_path)
    data_dir = tmp_path / "data"
    prepare_tiktok_publication(
        config=AppConfig(data_dir=data_dir),
        render_id=render_id,
        options=TikTokManualUploadOptions(),
    )

    exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "publish",
            "mark",
            render_id,
            "--url",
            "https://www.tiktok.com/@me/video/123",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "manually_published"
    assert payload["manual_publish_url"] == "https://www.tiktok.com/@me/video/123"


def _approved_render(tmp_path: Path) -> str:
    render_id = _create_render(tmp_path)
    store = ReviewStore(tmp_path / "data")
    store.ensure_for_render(render_id)
    store.update_metadata(
        render_id,
        title="A reviewed title",
        caption="Reviewed caption",
        hashtags=("#autotok",),
    )
    store.approve(render_id)
    return render_id
