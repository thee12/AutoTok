"""Local review dashboard API and static UI for Phase 10."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from autotok.errors import AutoTokError, PersistenceError, UserInputError
from autotok.review_storage import ReviewStore

JSON_CONTENT_TYPE = "application/json; charset=utf-8"
HTML_CONTENT_TYPE = "text/html; charset=utf-8"
CSS_CONTENT_TYPE = "text/css; charset=utf-8"
JS_CONTENT_TYPE = "application/javascript; charset=utf-8"
MP4_CONTENT_TYPE = "video/mp4"
MAX_JSON_BODY_BYTES = 128_000


@dataclass(frozen=True, slots=True)
class ApiResponse:
    """HTTP-ish response returned by the review API router."""

    status: int
    body: bytes
    content_type: str = JSON_CONTENT_TYPE

    @classmethod
    def json(cls, payload: Mapping[str, object], *, status: int = 200) -> ApiResponse:
        """Build a JSON API response."""
        return cls(
            status=status,
            body=json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
            content_type=JSON_CONTENT_TYPE,
        )

    @classmethod
    def text(cls, text: str, *, status: int, content_type: str) -> ApiResponse:
        """Build a text response."""
        return cls(status=status, body=text.encode("utf-8"), content_type=content_type)


class ReviewApi:
    """Route local dashboard requests to review storage operations."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.store = ReviewStore(data_dir)

    def handle(self, method: str, raw_path: str, body: bytes = b"") -> ApiResponse:
        """Handle one local dashboard request."""
        path = urlparse(raw_path).path
        try:
            return self._handle(method.upper(), path, body)
        except UserInputError as exc:
            return ApiResponse.json({"error": str(exc)}, status=400)
        except PersistenceError as exc:
            return ApiResponse.json({"error": str(exc)}, status=500)
        except AutoTokError as exc:
            return ApiResponse.json({"error": str(exc)}, status=500)

    def media_response(self, raw_path: str) -> ApiResponse:
        """Return a local rendered output file for preview playback."""
        path = urlparse(raw_path).path
        prefix = "/media/render/"
        if not path.startswith(prefix) or not path.endswith("/output.mp4"):
            return ApiResponse.json({"error": "Media route was not found."}, status=404)
        render_id = unquote(path.removeprefix(prefix).removesuffix("/output.mp4"))
        render = self.store.ensure_for_render(render_id)
        output_path = Path(render.output_path).resolve()
        data_root = self.data_dir.resolve()
        if data_root != output_path and data_root not in output_path.parents:
            return ApiResponse.json(
                {"error": "Media path is outside the data directory."}, status=403
            )
        if not output_path.exists():
            return ApiResponse.json({"error": "Rendered video output was not found."}, status=404)
        try:
            return ApiResponse(
                status=200, body=output_path.read_bytes(), content_type=MP4_CONTENT_TYPE
            )
        except OSError as exc:
            raise PersistenceError(f"Could not read rendered video output: {render_id}") from exc

    def _handle(self, method: str, path: str, body: bytes) -> ApiResponse:
        if method == "GET" and path == "/":
            return ApiResponse.text(REVIEW_HTML, status=200, content_type=HTML_CONTENT_TYPE)
        if method == "GET" and path == "/styles.css":
            return ApiResponse.text(REVIEW_CSS, status=200, content_type=CSS_CONTENT_TYPE)
        if method == "GET" and path == "/app.js":
            return ApiResponse.text(REVIEW_JS, status=200, content_type=JS_CONTENT_TYPE)
        if method == "GET" and path == "/api/health":
            return ApiResponse.json({"status": "ok", "phase": 10})
        if method == "GET" and path == "/api/reviews":
            packages = [package.to_dict() for package in self.store.list()]
            return ApiResponse.json({"reviews": packages})

        parts = [part for part in path.split("/") if part]
        if len(parts) == 3 and parts[:2] == ["api", "reviews"]:
            render_id = parts[2]
            if method == "GET":
                return ApiResponse.json(self.store.details(render_id))
        if len(parts) == 4 and parts[:3] == ["api", "reviews", "render"]:
            render_id = parts[3]
            if method == "POST":
                package = self.store.ensure_for_render(
                    render_id, reviewer=_reviewer(_json_body(body))
                )
                return ApiResponse.json({"review": package.to_dict()}, status=201)
        if len(parts) == 4 and parts[:2] == ["api", "reviews"]:
            render_id = parts[2]
            action = parts[3]
            payload = _json_body(body)
            if method == "PATCH" and action == "script":
                package = self.store.update_script(
                    render_id,
                    hook=_payload_str(payload, "hook"),
                    body=_payload_str(payload, "body"),
                    outro=_payload_str(payload, "outro"),
                    reviewer=_reviewer(payload),
                )
                return ApiResponse.json({"review": package.to_dict()})
            if method == "PATCH" and action == "metadata":
                package = self.store.update_metadata(
                    render_id,
                    title=_payload_optional_str(payload, "title"),
                    caption=_payload_optional_str(payload, "caption"),
                    hashtags=_payload_hashtags(payload),
                    reviewer=_reviewer(payload),
                )
                return ApiResponse.json({"review": package.to_dict()})
            if method == "POST" and action == "approve":
                package = self.store.approve(render_id, reviewer=_reviewer(payload))
                return ApiResponse.json({"review": package.to_dict()})
            if method == "POST" and action == "reject":
                package = self.store.reject(
                    render_id,
                    reason=_payload_str(payload, "reason"),
                    reviewer=_reviewer(payload),
                )
                return ApiResponse.json({"review": package.to_dict()})
            if method == "POST" and action == "regenerate":
                package = self.store.request_regeneration(
                    render_id,
                    stage_name=_payload_str(payload, "stage_name"),
                    reason=_payload_str(payload, "reason"),
                    reviewer=_reviewer(payload),
                )
                return ApiResponse.json({"review": package.to_dict()})
        return ApiResponse.json({"error": "Review API route was not found."}, status=404)


def _json_body(body: bytes) -> dict[str, object]:
    if not body:
        return {}
    if len(body) > MAX_JSON_BODY_BYTES:
        raise UserInputError("Review API request body is too large.")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UserInputError("Review API request body must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise UserInputError("Review API request body must be a JSON object.")
    return payload


def _reviewer(payload: Mapping[str, object]) -> str:
    return _payload_optional_str(payload, "reviewer") or "local_reviewer"


def _payload_str(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise UserInputError(f"{key} is required.")
    return value


def _payload_optional_str(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise UserInputError(f"{key} must be a string.")
    return value


def _payload_hashtags(payload: Mapping[str, object]) -> tuple[str, ...]:
    value = payload.get("hashtags", [])
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split()]
    elif isinstance(value, list):
        raw_items = []
        for item in value:
            if not isinstance(item, str):
                raise UserInputError("hashtags must contain strings.")
            raw_items.append(item)
    else:
        raise UserInputError("hashtags must be a list of strings or a space-delimited string.")
    cleaned = []
    for item in raw_items:
        text = item.strip()
        if text:
            cleaned.append(text if text.startswith("#") else f"#{text}")
    return tuple(cleaned)


REVIEW_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AutoTok Review</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <main class="shell">
    <aside class="queue" aria-label="Review queue">
      <div class="topline">
        <h1>AutoTok Review</h1>
        <button id="refresh" type="button" title="Refresh queue">Refresh</button>
      </div>
      <div id="queue" class="queue-list" aria-live="polite"></div>
    </aside>
    <section class="workspace" aria-label="Selected review package">
      <div id="error" class="error" role="alert" hidden></div>
      <div class="review-grid">
        <section class="preview-panel">
          <video id="video" controls playsinline preload="metadata"></video>
          <dl class="facts" id="facts"></dl>
        </section>
        <section class="editor-panel">
          <div class="actions">
            <button id="approve" type="button">Approve</button>
            <button id="reject" type="button">Reject</button>
            <button id="regenerate" type="button">Regenerate</button>
          </div>
          <label>Title<input id="title" type="text"></label>
          <label>Caption<textarea id="caption" rows="4"></textarea></label>
          <label>Hashtags<input id="hashtags" type="text"></label>
          <label>Hook<textarea id="hook" rows="3"></textarea></label>
          <label>Body<textarea id="body" rows="8"></textarea></label>
          <label>Outro<textarea id="outro" rows="3"></textarea></label>
          <div class="actions secondary">
            <button id="saveMeta" type="button">Save Metadata</button>
            <button id="saveScript" type="button">Save Script</button>
          </div>
        </section>
      </div>
      <section class="audit-panel">
        <h2>Audit History</h2>
        <ol id="audit"></ol>
      </section>
    </section>
  </main>
  <script src="/app.js"></script>
</body>
</html>
"""

REVIEW_CSS = """:root {
  color-scheme: light;
  font-family: Arial, sans-serif;
}
body {
  margin: 0;
  background: #f5f7f8;
  color: #172026;
}
.shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 320px 1fr;
}
.queue {
  background: #19252c;
  color: #f8fbfc;
  padding: 18px;
  overflow-y: auto;
}
.topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
h1 { font-size: 20px; margin: 0; }
button {
  border: 1px solid #82919a;
  background: #ffffff;
  color: #172026;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
}
button:hover { background: #edf2f4; }
.queue-list {
  display: grid;
  gap: 8px;
  margin-top: 18px;
}
.queue-item {
  width: 100%;
  text-align: left;
  background: #26343d;
  color: #f8fbfc;
  border-color: #3b4c56;
}
.queue-item.active { outline: 2px solid #e3ba55; }
.workspace { padding: 20px; }
.error {
  background: #ffe7df;
  border: 1px solid #b7472a;
  padding: 10px;
  border-radius: 6px;
  margin-bottom: 12px;
}
.review-grid {
  display: grid;
  grid-template-columns: minmax(280px, 420px) minmax(360px, 1fr);
  gap: 18px;
  align-items: start;
}
.preview-panel,
.editor-panel,
.audit-panel {
  background: #ffffff;
  border: 1px solid #d9e0e4;
  border-radius: 8px;
  padding: 14px;
}
video {
  width: 100%;
  aspect-ratio: 9 / 16;
  background: #101820;
  border-radius: 6px;
}
.facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 6px 10px;
  font-size: 14px;
}
.facts dt { font-weight: 700; color: #52636d; }
.editor-panel { display: grid; gap: 10px; }
label {
  display: grid;
  gap: 4px;
  font-size: 13px;
  font-weight: 700;
  color: #52636d;
}
input,
textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #bec9cf;
  border-radius: 6px;
  padding: 8px;
  font: inherit;
  color: #172026;
}
textarea { resize: vertical; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.actions.secondary { justify-content: flex-end; }
.audit-panel { margin-top: 18px; }
h2 { font-size: 16px; margin: 0 0 10px; }
ol { margin: 0; padding-left: 22px; }
li { margin-bottom: 8px; }
@media (max-width: 860px) {
  .shell { grid-template-columns: 1fr; }
  .review-grid { grid-template-columns: 1fr; }
}
"""
REVIEW_JS = """let selectedRenderId = null;
const state = { reviews: [] };
const $ = (id) => document.getElementById(id);

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

function showError(error) {
  const box = $('error');
  box.textContent = error.message || String(error);
  box.hidden = false;
}

function clearError() { $('error').hidden = true; }

async function loadQueue() {
  clearError();
  const data = await request('/api/reviews');
  state.reviews = data.reviews || [];
  const queue = $('queue');
  queue.innerHTML = '';
  for (const review of state.reviews) {
    const button = document.createElement('button');
    const activeClass = review.render_id === selectedRenderId ? ' active' : '';
    button.className = 'queue-item' + activeClass;
    button.textContent = `${review.render_id} - ${review.status}`;
    button.addEventListener('click', () => loadReview(review.render_id));
    queue.appendChild(button);
  }
  if (!selectedRenderId && state.reviews.length) {
    await loadReview(state.reviews[0].render_id);
  }
}

async function loadReview(renderId) {
  clearError();
  selectedRenderId = renderId;
  const data = await request(`/api/reviews/${renderId}`);
  const review = data.review;
  $('video').src = data.media.video_url;
  $('title').value = review.metadata.title || '';
  $('caption').value = review.metadata.caption || '';
  $('hashtags').value = (review.metadata.hashtags || []).join(' ');
  $('hook').value = review.script.hook || '';
  $('body').value = review.script.body || '';
  $('outro').value = review.script.outro || '';
  $('facts').innerHTML = [
    `<dt>Status</dt><dd>${review.status}</dd>`,
    `<dt>Story</dt><dd>${review.story_id}</dd>`,
    `<dt>Duration</dt><dd>${data.render.output_metadata.duration_seconds}s</dd>`,
    `<dt>Output</dt><dd>${data.media.output_path}</dd>`
  ].join('');
  const audit = $('audit');
  audit.innerHTML = '';
  for (const event of [...review.audit_events].reverse()) {
    const item = document.createElement('li');
    item.textContent = `${event.created_at} ${event.event_type}: ${event.message}`;
    audit.appendChild(item);
  }
  await loadQueue();
}

async function saveMetadata() {
  await request(`/api/reviews/${selectedRenderId}/metadata`, {
    method: 'PATCH',
    body: JSON.stringify({
      title: $('title').value,
      caption: $('caption').value,
      hashtags: $('hashtags').value
    })
  });
  await loadReview(selectedRenderId);
}

async function saveScript() {
  await request(`/api/reviews/${selectedRenderId}/script`, {
    method: 'PATCH',
    body: JSON.stringify({
      hook: $('hook').value,
      body: $('body').value,
      outro: $('outro').value
    })
  });
  await loadReview(selectedRenderId);
}

async function approve() {
  await request(`/api/reviews/${selectedRenderId}/approve`, {
    method: 'POST',
    body: '{}'
  });
  await loadReview(selectedRenderId);
}

async function reject() {
  const reason = prompt('Rejection reason');
  if (!reason) return;
  await request(`/api/reviews/${selectedRenderId}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason })
  });
  await loadReview(selectedRenderId);
}

async function regenerate() {
  const reason = prompt('Reason for regenerating render stage');
  if (!reason) return;
  await request(`/api/reviews/${selectedRenderId}/regenerate`, {
    method: 'POST',
    body: JSON.stringify({ stage_name: 'render', reason })
  });
  await loadReview(selectedRenderId);
}

$('refresh').addEventListener('click', () => loadQueue().catch(showError));
$('saveMeta').addEventListener('click', () => saveMetadata().catch(showError));
$('saveScript').addEventListener('click', () => saveScript().catch(showError));
$('approve').addEventListener('click', () => approve().catch(showError));
$('reject').addEventListener('click', () => reject().catch(showError));
$('regenerate').addEventListener('click', () => regenerate().catch(showError));
loadQueue().catch(showError);
"""
