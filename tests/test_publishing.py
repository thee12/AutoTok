from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from autotok.cli import main
from autotok.config import AppConfig, ConfigError
from autotok.publishing import (
    HttpResponse,
    build_tiktok_token_exchange_request,
    fetch_tiktok_publication_status,
    prepare_tiktok_publication,
)
from autotok.publishing_models import (
    PublicationStatus,
    PublishingProvider,
    PublishSourceType,
    TikTokDirectPostOptions,
)
from autotok.publishing_storage import PublicationStore
from autotok.review_storage import ReviewStore
from tests.test_review import _create_render


class FakeTransport:
    def __init__(self, responses: list[Mapping[str, Any]]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None = None,
        timeout_seconds: int,
    ) -> HttpResponse:
        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "body": body,
                "timeout_seconds": timeout_seconds,
            }
        )
        payload = self.responses.pop(0) if self.responses else {}
        return HttpResponse(status=200, body=json.dumps(payload).encode("utf-8"), headers={})


def test_tiktok_dry_run_requires_approved_review_and_writes_audit(tmp_path: Path) -> None:
    render_id = _create_render(tmp_path)
    data_dir = tmp_path / "data"
    config = AppConfig(data_dir=data_dir)

    review_store = ReviewStore(data_dir)
    review_store.ensure_for_render(render_id)
    with pytest.raises(Exception, match="approved"):
        prepare_tiktok_publication(
            config=config,
            render_id=render_id,
            options=TikTokDirectPostOptions(),
        )

    review_store.approve(render_id)
    result = prepare_tiktok_publication(
        config=config,
        render_id=render_id,
        options=TikTokDirectPostOptions(disable_comment=True),
    )

    stored = PublicationStore(data_dir).load(render_id, PublishingProvider.TIKTOK)
    assert result.dry_run is True
    assert stored.record.status is PublicationStatus.DRY_RUN_READY
    assert stored.record.audit_events[-1].event_type.value == "dry_run"
    assert stored.record.audit_events[-1].metadata["required_scope"] == "video.publish"
    assert "access_token" not in json.dumps(stored.record.to_dict())


def test_tiktok_scheduling_is_rejected_because_official_support_is_unverified(
    tmp_path: Path,
) -> None:
    render_id = _create_render(tmp_path)

    with pytest.raises(Exception, match="scheduling is not supported"):
        prepare_tiktok_publication(
            config=AppConfig(data_dir=tmp_path / "data"),
            render_id=render_id,
            options=TikTokDirectPostOptions(),
            scheduled_at="2026-07-02T12:00:00Z",
        )


def test_tiktok_execute_uploads_and_blocks_duplicate_submission(tmp_path: Path) -> None:
    render_id = _approved_render(tmp_path)
    config = AppConfig(data_dir=tmp_path / "data", tiktok_access_token="token")
    transport = FakeTransport(
        [
            {"data": {"publish_id": "pub_123", "upload_url": "https://upload.example/video"}},
            {},
        ]
    )

    first = prepare_tiktok_publication(
        config=config,
        render_id=render_id,
        options=TikTokDirectPostOptions(),
        execute=True,
        confirmed=True,
        transport=transport,
    )
    second = prepare_tiktok_publication(
        config=config,
        render_id=render_id,
        options=TikTokDirectPostOptions(),
        execute=True,
        confirmed=True,
        transport=transport,
    )

    assert first.record.status is PublicationStatus.SUBMITTED
    assert first.record.publish_id == "pub_123"
    assert [request["method"] for request in transport.requests] == ["POST", "PUT"]
    assert transport.requests[1]["headers"]["Content-Range"].startswith("bytes 0-")
    assert second.duplicate_prevented is True
    assert second.record.publish_id == "pub_123"


def test_tiktok_pull_from_url_dry_run_records_official_source_info(tmp_path: Path) -> None:
    render_id = _approved_render(tmp_path)

    result = prepare_tiktok_publication(
        config=AppConfig(data_dir=tmp_path / "data"),
        render_id=render_id,
        options=TikTokDirectPostOptions(
            source_type=PublishSourceType.PULL_FROM_URL,
            video_url="https://cdn.example/render.mp4",
        ),
    )

    event = result.record.audit_events[-1]
    request = event.metadata["request"]
    assert request["source_info"] == {
        "source": "PULL_FROM_URL",
        "video_url": "https://cdn.example/render.mp4",
    }


def test_tiktok_token_exchange_request_redacts_secrets() -> None:
    request = build_tiktok_token_exchange_request(
        AppConfig(tiktok_client_key="client", tiktok_client_secret="secret"),
        code="auth-code",
        redirect_uri="https://local.example/callback",
    )

    redacted = request.redacted()
    form = redacted["form"]

    assert b"grant_type=authorization_code" in request.body()
    assert isinstance(form, Mapping)
    assert form["client_secret"] == "[REDACTED]"


def test_tiktok_status_fetch_updates_publication_status(tmp_path: Path) -> None:
    render_id = _approved_render(tmp_path)
    config = AppConfig(data_dir=tmp_path / "data", tiktok_access_token="token")
    execute_transport = FakeTransport(
        [
            {"data": {"publish_id": "pub_123", "upload_url": "https://upload.example/video"}},
            {},
        ]
    )
    prepare_tiktok_publication(
        config=config,
        render_id=render_id,
        options=TikTokDirectPostOptions(),
        execute=True,
        confirmed=True,
        transport=execute_transport,
    )

    status_transport = FakeTransport([{"data": {"status": "PUBLISH_COMPLETE"}}])
    result = fetch_tiktok_publication_status(
        config=config,
        render_id=render_id,
        transport=status_transport,
    )

    assert result.record.status is PublicationStatus.PUBLISHED
    assert status_transport.requests[0]["url"].endswith("/v2/post/publish/status/fetch/")


def test_publish_cli_creates_tiktok_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    render_id = _approved_render(tmp_path)
    data_dir = tmp_path / "data"

    exit_code = main(["--data-dir", str(data_dir), "publish", "tiktok", render_id, "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["dry_run"] is True
    assert payload["publication"]["status"] == "dry_run_ready"


def test_config_reads_tiktok_values_and_rejects_invalid_timeout() -> None:
    config = AppConfig.from_environment(
        {
            "AUTOTOK_TIKTOK_CLIENT_KEY": " client ",
            "AUTOTOK_TIKTOK_CLIENT_SECRET": " secret ",
            "AUTOTOK_TIKTOK_ACCESS_TOKEN": " access ",
            "AUTOTOK_TIKTOK_REFRESH_TOKEN": " refresh ",
            "AUTOTOK_TIKTOK_TIMEOUT_SECONDS": "12",
        }
    )

    assert config.tiktok_client_key == "client"
    assert config.tiktok_client_secret == "secret"
    assert config.tiktok_access_token == "access"
    assert config.tiktok_refresh_token == "refresh"
    assert config.tiktok_timeout_seconds == 12
    with pytest.raises(ConfigError, match="AUTOTOK_TIKTOK_TIMEOUT_SECONDS"):
        AppConfig.from_environment({"AUTOTOK_TIKTOK_TIMEOUT_SECONDS": "0"})


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
