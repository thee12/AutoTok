# Publishing

AutoTok publishing is a local manual handoff for TikTok. It prepares the video,
caption, metadata, and operator instructions on disk, then the user manually
uploads and publishes from their own TikTok account.

AutoTok does not use TikTok Login Kit, OAuth tokens, Content Posting API, Direct
Post, browser automation, or any other platform API for publishing. You remain in
control of TikTok's upload screen and final publish button.

## Scope

In scope:

- approved render packages only
- TikTok manual upload packages
- copied `video.mp4`, `caption.txt`, `metadata.json`, and `instructions.md`
- local publication records and audit events
- manual status recording after you publish yourself

Out of scope:

- API upload or Direct Post
- Login Kit, OAuth, access tokens, refresh tokens, scopes, or app review
- scheduling
- YouTube, Shorts, Instagram, or other platforms
- engagement automation such as likes, comments, follows, or messages

## Commands

Prepare a TikTok manual upload package for an approved render:

```bash
autotok publish tiktok render_0123456789abcdef
```

Inspect the local publication record:

```bash
autotok publish status render_0123456789abcdef
```

After you manually upload and publish in TikTok, record that local status:

```bash
autotok publish mark render_0123456789abcdef --url https://www.tiktok.com/@you/video/123
```

The `--url` value is optional. It is stored only in the local publication record.

## Local Files

Publication records are stored under:

```text
data/publications/<render_id>/tiktok/publication.json
```

Manual upload package files are stored under:

```text
data/publications/<render_id>/tiktok/manual_upload/
```

The package contains:

- `video.mp4`: the rendered portrait video copied from the render package
- `caption.txt`: the suggested caption and hashtags
- `metadata.json`: local provenance, review settings, and safety flags
- `instructions.md`: step-by-step manual TikTok upload notes

## Manual TikTok Upload Flow

1. Approve the render in `autotok review` or the local review dashboard.
2. Run `autotok publish tiktok <render_id>`.
3. Open TikTok in your browser or the TikTok app.
4. Start a normal manual upload from your own account.
5. Select `video.mp4` from the manual upload package.
6. Paste the caption from `caption.txt`.
7. Review TikTok's copyright, synthetic-media, privacy, audience, and safety prompts yourself.
8. Click TikTok's final publish/post button only when you are satisfied.
9. Optionally run `autotok publish mark <render_id> --url <posted-url>`.
