"""Official publishing adapters and workflows for Phase 11."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from autotok.config import AppConfig
from autotok.errors import ConfigurationError, ProviderError, ProviderRateLimitError, UserInputError
from autotok.publishing_models import (
    PublicationAuditEvent,
    PublicationEventType,
    PublicationRecord,
    PublicationResult,
    PublicationStatus,
    PublishingProvider,
    PublishSourceType,
    TikTokCapability,
    TikTokDirectPostOptions,
)
from autotok.publishing_storage import PublicationStore, new_id, utc_timestamp
from autotok.render_storage import RenderStore, StoredRender
from autotok.review_models import ReviewPackage, ReviewPackageStatus
from autotok.review_storage import ReviewStore

TIKTOK_INIT_ENDPOINT = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_STATUS_ENDPOINT = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
TIKTOK_TOKEN_ENDPOINT = "https://open.tiktokapis.com/v2/oauth/token/"
DEFAULT_UPLOAD_CHUNK_SIZE = 10 * 1024 * 1024
NON_DUPLICABLE_STATUSES = {
    PublicationStatus.SUBMITTED,
    PublicationStatus.PROCESSING,
    PublicationStatus.PUBLISHED,
}
SECRET_KEYS = {
    "access_token",
    "refresh_token",
    "client_secret",
    "authorization",
    "Authorization",
}


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """A minimal HTTP response object used by provider adapters."""

    status: int
    body: bytes
    headers: Mapping[str, str]


class HttpTransport(Protocol):
    """Transport protocol so tests can avoid real network access."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None = None,
        timeout_seconds: int,
    ) -> HttpResponse:
        """Send one HTTP request."""


class UrllibHttpTransport:
    """Standard-library HTTP transport."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None = None,
        timeout_seconds: int,
    ) -> HttpResponse:
        """Send one HTTP request with urllib."""
        request = Request(url=url, data=body, headers=dict(headers), method=method)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return HttpResponse(
                    status=int(response.status),
                    body=response.read(),
                    headers={str(key): str(value) for key, value in response.headers.items()},
                )
        except HTTPError as exc:
            return HttpResponse(
                status=int(exc.code),
                body=exc.read(),
                headers={str(key): str(value) for key, value in exc.headers.items()},
            )
        except URLError as exc:
            raise ProviderError(
                f"TikTok request failed before receiving a response: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class TikTokTokenRequest:
    """Redactable OAuth token request description."""

    url: str
    form: Mapping[str, str]

    def body(self) -> bytes:
        """Return form-encoded request body."""
        return urlencode(dict(self.form)).encode("utf-8")

    def redacted(self) -> dict[str, object]:
        """Return a credential-safe request preview."""
        return {"url": self.url, "form": redact_mapping(self.form)}


class TikTokContentPostingAdapter:
    """TikTok Content Posting API adapter using official documented endpoints."""

    def __init__(
        self,
        config: AppConfig,
        *,
        transport: HttpTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = UrllibHttpTransport() if transport is None else transport
        self.capability = TikTokCapability()

    def dry_run_payload(
        self,
        render: StoredRender,
        review: ReviewPackage,
        options: TikTokDirectPostOptions,
    ) -> dict[str, object]:
        """Build the credential-free Direct Post request preview."""
        return {
            "provider": PublishingProvider.TIKTOK.value,
            "endpoint": TIKTOK_INIT_ENDPOINT,
            "required_scope": self.capability.required_scope,
            "request": redact_mapping(self._direct_post_payload(render, review, options)),
            "capability": self.capability.to_dict(),
        }

    def publish(
        self,
        render: StoredRender,
        review: ReviewPackage,
        options: TikTokDirectPostOptions,
    ) -> Mapping[str, Any]:
        """Initialize a TikTok Direct Post publish and upload file data when needed."""
        token = self.config.tiktok_access_token
        if token is None:
            raise ConfigurationError(
                "AUTOTOK_TIKTOK_ACCESS_TOKEN is required for --execute publishing."
            )
        payload = self._direct_post_payload(render, review, options)
        response = self._json_request(
            "POST",
            TIKTOK_INIT_ENDPOINT,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            body=json.dumps(payload).encode("utf-8"),
        )
        upload_url = _nested_str(response, "data", "upload_url")
        if options.source_type is PublishSourceType.FILE_UPLOAD and upload_url:
            self._upload_file(upload_url, Path(render.paths.output_path), token)
        return response

    def fetch_status(self, publish_id: str) -> Mapping[str, Any]:
        """Fetch TikTok publish status for a submitted publish ID."""
        token = self.config.tiktok_access_token
        if token is None:
            raise ConfigurationError(
                "AUTOTOK_TIKTOK_ACCESS_TOKEN is required to fetch TikTok publish status."
            )
        return self._json_request(
            "POST",
            TIKTOK_STATUS_ENDPOINT,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            body=json.dumps({"publish_id": publish_id}).encode("utf-8"),
        )

    def exchange_token(self, code: str, redirect_uri: str) -> Mapping[str, Any]:
        """Exchange an OAuth authorization code for a user access token."""
        request = build_tiktok_token_exchange_request(self.config, code, redirect_uri)
        return self._json_request(
            "POST",
            request.url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=request.body(),
        )

    def refresh_token(self) -> Mapping[str, Any]:
        """Refresh a TikTok user access token."""
        request = build_tiktok_token_refresh_request(self.config)
        return self._json_request(
            "POST",
            request.url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=request.body(),
        )

    def _direct_post_payload(
        self,
        render: StoredRender,
        review: ReviewPackage,
        options: TikTokDirectPostOptions,
    ) -> dict[str, object]:
        title = review.metadata.title.strip() or f"AutoTok render {render.manifest.render_id}"
        description = " ".join(
            part
            for part in (
                review.metadata.caption.strip(),
                " ".join(review.metadata.hashtags),
            )
            if part
        )
        payload: dict[str, object] = {
            "post_info": {
                "title": title,
                "description": description,
                "privacy_level": options.privacy_level,
                "disable_duet": options.disable_duet,
                "disable_comment": options.disable_comment,
                "disable_stitch": options.disable_stitch,
                "video_cover_timestamp_ms": options.cover_timestamp_ms,
            },
            "source_info": _source_info(render, options),
        }
        return payload

    def _json_request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> Mapping[str, Any]:
        response = self.transport.request(
            method,
            url,
            headers=headers,
            body=body,
            timeout_seconds=self.config.tiktok_timeout_seconds,
        )
        if response.status == 429:
            raise ProviderRateLimitError("TikTok API reported a rate limit. Retry later.")
        payload = _decode_json_response(response)
        if response.status >= 400:
            raise ProviderError(
                f"TikTok API request failed with HTTP {response.status}: {redact_mapping(payload)}"
            )
        return payload

    def _upload_file(self, upload_url: str, video_path: Path, token: str) -> None:
        total_size = video_path.stat().st_size
        chunk_size = min(total_size, DEFAULT_UPLOAD_CHUNK_SIZE) if total_size > 0 else total_size
        with video_path.open("rb") as video_file:
            start = 0
            while start < total_size:
                chunk = video_file.read(chunk_size)
                end = start + len(chunk) - 1
                response = self.transport.request(
                    "PUT",
                    upload_url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start}-{end}/{total_size}",
                    },
                    body=chunk,
                    timeout_seconds=self.config.tiktok_timeout_seconds,
                )
                if response.status == 429:
                    raise ProviderRateLimitError(
                        "TikTok upload reported a rate limit. Retry later."
                    )
                if response.status >= 400:
                    payload = _decode_json_response(response)
                    raise ProviderError(
                        "TikTok upload failed "
                        f"with HTTP {response.status}: {redact_mapping(payload)}"
                    )
                start = end + 1


def prepare_tiktok_publication(
    *,
    config: AppConfig,
    render_id: str,
    options: TikTokDirectPostOptions,
    execute: bool = False,
    confirmed: bool = False,
    scheduled_at: str | None = None,
    transport: HttpTransport | None = None,
) -> PublicationResult:
    """Create a dry-run record or execute an approved TikTok Direct Post publish."""
    if scheduled_at is not None:
        raise UserInputError(
            "TikTok Direct Post scheduling is not supported by the official docs verified for "
            "Phase 11; omit --publish-at and publish immediately after approval."
        )
    if execute and not confirmed:
        raise UserInputError("Real publishing requires both --execute and --confirm.")

    render = RenderStore(config.data_dir).load(render_id)
    review = ReviewStore(config.data_dir).load(render_id)
    if review.status is not ReviewPackageStatus.APPROVED or review.approved_at is None:
        raise UserInputError(
            "Render package must be approved in `autotok review` before publishing."
        )

    store = PublicationStore(config.data_dir)
    existing = (
        store.load(render_id, PublishingProvider.TIKTOK).record
        if store.exists(render_id, PublishingProvider.TIKTOK)
        else None
    )
    if existing is not None and existing.status in NON_DUPLICABLE_STATUSES:
        return PublicationResult(record=existing, dry_run=not execute, duplicate_prevented=True)

    adapter = TikTokContentPostingAdapter(config, transport=transport)
    timestamp = utc_timestamp()
    if existing is None:
        record = PublicationRecord(
            publication_id=new_id("publication"),
            render_id=render_id,
            provider=PublishingProvider.TIKTOK,
            status=PublicationStatus.DRY_RUN_READY,
            created_at=timestamp,
            updated_at=timestamp,
            approved_review_at=review.approved_at,
            render_output_path=str(render.paths.output_path),
            request_options=options,
        )
        created = True
    else:
        record = existing
        created = False

    if not execute:
        event = _event(
            PublicationEventType.DRY_RUN,
            message="TikTok Direct Post dry run prepared.",
            metadata=adapter.dry_run_payload(render, review, options),
        )
        record = record.with_event(event, status=PublicationStatus.DRY_RUN_READY)
        stored = store.save(record, created=created)
        return PublicationResult(record=stored.record, dry_run=True)

    response = adapter.publish(render, review, options)
    publish_id = _nested_str(response, "data", "publish_id")
    if publish_id is None:
        raise ProviderError("TikTok publish response did not include data.publish_id.")
    event = _event(
        PublicationEventType.SUBMITTED,
        message="TikTok Direct Post publish submitted.",
        metadata={"provider_response": redact_mapping(response)},
    )
    record = record.with_event(
        event,
        status=PublicationStatus.SUBMITTED,
        publish_id=publish_id,
        last_status_payload=response,
    )
    stored = store.save(record, created=created)
    return PublicationResult(record=stored.record, dry_run=False, provider_response=response)


def fetch_tiktok_publication_status(
    *,
    config: AppConfig,
    render_id: str,
    transport: HttpTransport | None = None,
) -> PublicationResult:
    """Fetch provider status for an already-submitted TikTok publication."""
    store = PublicationStore(config.data_dir)
    record = store.load(render_id, PublishingProvider.TIKTOK).record
    if record.publish_id is None:
        raise UserInputError("Publication record does not have a TikTok publish_id yet.")
    adapter = TikTokContentPostingAdapter(config, transport=transport)
    response = adapter.fetch_status(record.publish_id)
    status = map_tiktok_status(response)
    event = _event(
        PublicationEventType.STATUS_FETCHED,
        message="TikTok publish status fetched.",
        metadata={"provider_response": redact_mapping(response)},
    )
    updated = record.with_event(event, status=status, last_status_payload=response)
    stored = store.save(updated)
    return PublicationResult(record=stored.record, dry_run=False, provider_response=response)


def build_tiktok_token_exchange_request(
    config: AppConfig,
    code: str,
    redirect_uri: str,
) -> TikTokTokenRequest:
    """Build the official TikTok OAuth authorization-code request."""
    if config.tiktok_client_key is None or config.tiktok_client_secret is None:
        raise ConfigurationError(
            "AUTOTOK_TIKTOK_CLIENT_KEY and AUTOTOK_TIKTOK_CLIENT_SECRET are required."
        )
    return TikTokTokenRequest(
        url=TIKTOK_TOKEN_ENDPOINT,
        form={
            "client_key": config.tiktok_client_key,
            "client_secret": config.tiktok_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )


def build_tiktok_token_refresh_request(config: AppConfig) -> TikTokTokenRequest:
    """Build the official TikTok OAuth refresh-token request."""
    if config.tiktok_client_key is None or config.tiktok_client_secret is None:
        raise ConfigurationError(
            "AUTOTOK_TIKTOK_CLIENT_KEY and AUTOTOK_TIKTOK_CLIENT_SECRET are required."
        )
    if config.tiktok_refresh_token is None:
        raise ConfigurationError("AUTOTOK_TIKTOK_REFRESH_TOKEN is required.")
    return TikTokTokenRequest(
        url=TIKTOK_TOKEN_ENDPOINT,
        form={
            "client_key": config.tiktok_client_key,
            "client_secret": config.tiktok_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": config.tiktok_refresh_token,
        },
    )


def map_tiktok_status(response: Mapping[str, Any]) -> PublicationStatus:
    """Map a TikTok status response into AutoTok's publication lifecycle."""
    status = str(_nested_str(response, "data", "status") or "").upper()
    fail_reason = str(_nested_str(response, "data", "fail_reason") or "").lower()
    if status in {"PUBLISH_COMPLETE", "PUBLICLY_AVAILABLE"}:
        return PublicationStatus.PUBLISHED
    if status in {"FAILED", "PUBLISH_FAILED"} or fail_reason:
        return PublicationStatus.FAILED
    return PublicationStatus.PROCESSING


def redact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively redact secret-looking fields from a mapping."""
    redacted: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        if key_text in SECRET_KEYS or "token" in key_text.lower() or "secret" in key_text.lower():
            redacted[key_text] = "[REDACTED]" if item else item
        elif isinstance(item, Mapping):
            redacted[key_text] = redact_mapping(item)
        elif isinstance(item, list):
            redacted[key_text] = [
                redact_mapping(child) if isinstance(child, Mapping) else child for child in item
            ]
        else:
            redacted[key_text] = item
    return redacted


def _source_info(render: StoredRender, options: TikTokDirectPostOptions) -> dict[str, object]:
    if options.source_type is PublishSourceType.PULL_FROM_URL:
        if options.video_url is None or not options.video_url.strip():
            raise UserInputError("--video-url is required when --source pull_from_url is used.")
        return {"source": options.source_type.value, "video_url": options.video_url}
    output_path = render.paths.output_path
    try:
        size = output_path.stat().st_size
    except OSError as exc:
        raise UserInputError(f"Rendered video file is not readable: {output_path}") from exc
    chunk_size = min(size, DEFAULT_UPLOAD_CHUNK_SIZE) if size > 0 else DEFAULT_UPLOAD_CHUNK_SIZE
    return {
        "source": options.source_type.value,
        "video_size": size,
        "chunk_size": chunk_size,
        "total_chunk_count": max(1, (size + chunk_size - 1) // chunk_size),
    }


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


def _decode_json_response(response: HttpResponse) -> Mapping[str, Any]:
    if not response.body:
        return {}
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError("TikTok API returned a non-JSON response.") from exc
    if not isinstance(payload, Mapping):
        raise ProviderError("TikTok API returned a non-object JSON response.")
    return dict(payload)


def _nested_str(payload: Mapping[str, Any], first: str, second: str) -> str | None:
    nested = payload.get(first)
    if not isinstance(nested, Mapping):
        return None
    value = nested.get(second)
    return value if isinstance(value, str) and value else None
