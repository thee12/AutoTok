# Publishing

Phase 11 adds an official publishing path for approved render packages through
TikTok's Content Posting API. Publishing is still human-gated and local-first:
AutoTok will not upload anything unless a render package has been approved in
the review workflow and the command includes both `--execute` and `--confirm`.

## Verified TikTok Capability

Verified against official TikTok developer documentation on 2026-07-01:

- Direct posting is supported through
  `https://open.tiktokapis.com/v2/post/publish/video/init/`.
- Direct Post requires the `video.publish` scope and a user access token.
- Local file upload uses the returned `upload_url`; pull-from-URL uses a
  public `video_url`.
- Publish status is fetched through
  `https://open.tiktokapis.com/v2/post/publish/status/fetch/`.
- OAuth authorization-code exchange and refresh use
  `https://open.tiktokapis.com/v2/oauth/token/`.
- TikTok Direct Post scheduling is not implemented because the official docs
  verified for Phase 11 do not expose a supported scheduling field.

Official references:

- https://developers.tiktok.com/doc/content-posting-api-get-started/
- https://developers.tiktok.com/doc/content-posting-api-reference-direct-post/
- https://developers.tiktok.com/doc/content-posting-api-reference-get-video-status/
- https://developers.tiktok.com/doc/oauth-user-access-token-management/

## Configuration

Secrets are supplied through environment variables or a local ignored `.env`
file. Publication records and CLI output redact token and secret fields.

```text
AUTOTOK_TIKTOK_CLIENT_KEY=
AUTOTOK_TIKTOK_CLIENT_SECRET=
AUTOTOK_TIKTOK_ACCESS_TOKEN=
AUTOTOK_TIKTOK_REFRESH_TOKEN=
AUTOTOK_TIKTOK_TIMEOUT_SECONDS=30
```

## Commands

Prepare a dry run for an approved render package:

```bash
autotok publish tiktok render_0123456789abcdef
```

Execute a real Direct Post publish:

```bash
autotok publish tiktok render_0123456789abcdef --execute --confirm
```

Inspect local publication state:

```bash
autotok publish status render_0123456789abcdef
```

Fetch official TikTok status for a submitted publish:

```bash
autotok publish status render_0123456789abcdef --fetch
```

Build credential-safe OAuth request previews:

```bash
autotok publish token exchange --code AUTH_CODE --redirect-uri https://example.com/callback
autotok publish token refresh
```

Add `--execute` to token commands only when configured credentials should be
sent to TikTok. Responses are redacted before printing; refreshed tokens must be
stored by the operator in local secret storage.

## Local Records

Publication records are stored under:

```text
data/publications/<render_id>/tiktok/publication.json
```

Each record contains provider capability verification, the approved review
timestamp, redacted dry-run or provider-response audit events, provider publish
ID when submitted, and the latest mapped status. AutoTok prevents duplicate real
submissions once a render/provider pair has been submitted, is processing, or is
published.
