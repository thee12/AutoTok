"""Local HTTP server for the Phase 10 review dashboard."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final

from autotok.review_api import ApiResponse, ReviewApi

DEFAULT_REVIEW_HOST: Final[str] = "127.0.0.1"
DEFAULT_REVIEW_PORT: Final[int] = 8765


class ReviewRequestHandler(BaseHTTPRequestHandler):
    """HTTP adapter around the pure ReviewApi router."""

    api: ReviewApi

    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        """Handle GET requests."""
        if self.path.startswith("/media/render/"):
            self._send(self.api.media_response(self.path))
            return
        self._send(self.api.handle("GET", self.path))

    def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
        """Handle POST requests."""
        self._send(self.api.handle("POST", self.path, self._read_body()))

    def do_PATCH(self) -> None:  # noqa: N802 - stdlib callback name
        """Handle PATCH requests."""
        self._send(self.api.handle("PATCH", self.path, self._read_body()))

    def log_message(self, format: str, *args: object) -> None:
        """Silence default request logging for a quieter local CLI server."""

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length > 0 else b""

    def _send(self, response: ApiResponse) -> None:
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(response.body)


def build_review_server(
    data_dir: Path,
    *,
    host: str = DEFAULT_REVIEW_HOST,
    port: int = DEFAULT_REVIEW_PORT,
) -> ThreadingHTTPServer:
    """Build a local review dashboard server."""

    class BoundReviewRequestHandler(ReviewRequestHandler):
        api = ReviewApi(data_dir)

    return ThreadingHTTPServer((host, port), BoundReviewRequestHandler)


def serve_review_dashboard(
    data_dir: Path,
    *,
    host: str = DEFAULT_REVIEW_HOST,
    port: int = DEFAULT_REVIEW_PORT,
) -> None:
    """Serve the local review dashboard until interrupted."""
    server = build_review_server(data_dir, host=host, port=port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
