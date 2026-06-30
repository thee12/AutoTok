"""Source adapters for approved Phase 7 discovery."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from autotok.errors import ProviderError, ProviderRateLimitError, UserInputError
from autotok.source_models import (
    DiscoveredSourcePost,
    SourceDiscoveryRun,
    SourceProvider,
    build_discovered_post,
    build_discovery_id,
)

REDDIT_API_BASE_URL = "https://oauth.reddit.com"
REDDIT_ALLOWED_SORTS = frozenset({"hot", "new", "top", "rising"})
REDDIT_MAX_LIMIT = 100
REDDIT_MAX_PAGES = 10
REDDIT_REMOVED_MARKERS = frozenset({"[deleted]", "[removed]"})
DEFAULT_REDDIT_TIMEOUT_SECONDS = 20


@dataclass(frozen=True, slots=True)
class HttpJsonResponse:
    """JSON HTTP response returned by a source adapter client."""

    payload: dict[str, object]
    headers: dict[str, str]
    status_code: int


class JsonHttpClient(Protocol):
    """Minimal HTTP client protocol used by source adapters."""

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: int,
    ) -> HttpJsonResponse:
        """Fetch JSON from a URL."""
        ...


class CachedRetrievalProtocol(Protocol):
    """Cached raw retrieval response used by the adapter."""

    @property
    def payload(self) -> dict[str, object]:
        """Cached JSON payload."""
        ...

    @property
    def headers(self) -> dict[str, str]:
        """Cached response headers."""
        ...


class RetrievalCache(Protocol):
    """Protocol for a raw retrieval cache."""

    def load(self, cache_key: str) -> CachedRetrievalProtocol | None:
        """Load a cached response by cache key."""
        ...

    def save(
        self,
        cache_key: str,
        *,
        payload: dict[str, object],
        headers: dict[str, str],
        url: str,
        cached_at: str,
    ) -> Path:
        """Save a raw response and return its path."""
        ...


@dataclass(frozen=True, slots=True)
class RedditDiscoveryConfig:
    """Configuration for Reddit Data API discovery."""

    subreddit: str
    sort: str = "hot"
    limit: int = 25
    max_pages: int = 1
    user_agent: str = "AutoTok/0.1 local-source-ingestion"
    oauth_token: str | None = None
    timeout_seconds: int = DEFAULT_REDDIT_TIMEOUT_SECONDS
    use_cache: bool = True

    def validate(self, *, require_auth: bool = True) -> None:
        """Validate Reddit discovery configuration."""
        if not _valid_subreddit_name(self.subreddit):
            raise UserInputError(
                "Subreddit must be 2-21 characters using only letters, numbers, and underscores."
            )
        if self.sort not in REDDIT_ALLOWED_SORTS:
            allowed = ", ".join(sorted(REDDIT_ALLOWED_SORTS))
            raise UserInputError(f"Reddit sort must be one of: {allowed}.")
        if self.limit <= 0 or self.limit > REDDIT_MAX_LIMIT:
            raise UserInputError(f"Reddit limit must be between 1 and {REDDIT_MAX_LIMIT}.")
        if self.max_pages <= 0 or self.max_pages > REDDIT_MAX_PAGES:
            raise UserInputError(f"Reddit max pages must be between 1 and {REDDIT_MAX_PAGES}.")
        if self.timeout_seconds <= 0:
            raise UserInputError("Reddit timeout seconds must be greater than zero.")
        if not self.user_agent.strip():
            raise UserInputError("Reddit user agent must not be empty.")
        if require_auth and not self.oauth_token:
            raise UserInputError(
                "Reddit discovery requires AUTOTOK_REDDIT_OAUTH_TOKEN or a --fixture-json file."
            )


@dataclass(frozen=True, slots=True)
class RedditDiscoveryResult:
    """Filtered Reddit discovery output plus raw pages for local storage."""

    run: SourceDiscoveryRun
    raw_pages: tuple[dict[str, object], ...]


class StdlibJsonHttpClient:
    """Small standard-library JSON HTTP client for source adapters."""

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: int,
    ) -> HttpJsonResponse:
        """Fetch a JSON object with a timeout and map HTTP errors."""
        request = urllib.request.Request(url, headers=dict(headers), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read()
                payload = _json_object(raw, context=url)
                response_headers = {key.lower(): value for key, value in response.headers.items()}
                return HttpJsonResponse(
                    payload=payload,
                    headers=response_headers,
                    status_code=response.status,
                )
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise ProviderRateLimitError(
                    "Reddit rate limit reached. Wait for the Retry-After or x-ratelimit-reset "
                    "window before retrying."
                ) from exc
            raise ProviderError(f"Reddit request failed with HTTP status {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Reddit request failed: {exc.reason}.") from exc
        except TimeoutError as exc:
            raise ProviderError("Reddit request timed out.") from exc


class RedditDataApiAdapter:
    """Discover public posts through Reddit's authenticated Data API."""

    def __init__(self, http_client: JsonHttpClient | None = None) -> None:
        self.http_client = StdlibJsonHttpClient() if http_client is None else http_client

    def discover(
        self,
        config: RedditDiscoveryConfig,
        *,
        cache: RetrievalCache | None = None,
        now: datetime | None = None,
    ) -> RedditDiscoveryResult:
        """Fetch, filter, and package Reddit posts for local import."""
        config.validate(require_auth=True)
        created_at = _utc_timestamp(now)
        raw_pages: list[dict[str, object]] = []
        rate_limits: list[Mapping[str, object]] = []
        posts: list[DiscoveredSourcePost] = []
        after: str | None = None
        cache_hits = 0
        pages_requested = 0

        for _page_number in range(1, config.max_pages + 1):
            url = _reddit_listing_url(config, after=after)
            cache_key = _cache_key("reddit", url)
            cached = cache.load(cache_key) if cache is not None and config.use_cache else None
            if cached is None:
                response = self.http_client.get_json(
                    url,
                    headers=_reddit_headers(config),
                    timeout_seconds=config.timeout_seconds,
                )
                payload = response.payload
                headers = response.headers
                if cache is not None and config.use_cache:
                    cache.save(
                        cache_key,
                        payload=payload,
                        headers=headers,
                        url=url,
                        cached_at=created_at,
                    )
            else:
                payload = cached.payload
                headers = cached.headers
                cache_hits += 1

            pages_requested += 1
            raw_pages.append(payload)
            rate_limits.append(_rate_limit_snapshot(headers))
            posts.extend(_posts_from_listing(payload, config=config, retrieved_at=created_at))
            after = _next_after(payload)
            if after is None or _remaining_requests(headers) <= 0:
                break

        query: dict[str, object] = {
            "subreddit": config.subreddit,
            "sort": config.sort,
            "limit": config.limit,
            "max_pages": config.max_pages,
        }
        discovery_id = build_discovery_id(SourceProvider.REDDIT, query, posts)
        run = SourceDiscoveryRun(
            discovery_id=discovery_id,
            provider=SourceProvider.REDDIT,
            created_at=created_at,
            query=query,
            posts=tuple(posts),
            request={
                "api_base_url": REDDIT_API_BASE_URL,
                "auth": "oauth_bearer",
                "user_agent": config.user_agent,
                "cached": config.use_cache,
            },
            pagination={"pages_requested": pages_requested, "next_after": after},
            rate_limits=tuple(rate_limits),
            cache_hits=cache_hits,
        )
        return RedditDiscoveryResult(run=run, raw_pages=tuple(raw_pages))


def discover_reddit_from_fixture(
    fixture_path: Path,
    config: RedditDiscoveryConfig,
    *,
    now: datetime | None = None,
) -> RedditDiscoveryResult:
    """Build a Reddit discovery run from a local fixture JSON file."""
    config.validate(require_auth=False)
    created_at = _utc_timestamp(now)
    payload = _read_json_fixture(fixture_path)
    posts = tuple(_posts_from_listing(payload, config=config, retrieved_at=created_at))
    query: dict[str, object] = {
        "subreddit": config.subreddit,
        "sort": config.sort,
        "limit": config.limit,
        "max_pages": 1,
        "fixture": str(fixture_path),
    }
    discovery_id = build_discovery_id(SourceProvider.REDDIT, query, posts)
    run = SourceDiscoveryRun(
        discovery_id=discovery_id,
        provider=SourceProvider.REDDIT,
        created_at=created_at,
        query=query,
        posts=posts,
        request={"source": "fixture", "auth": "not_used"},
        pagination={"pages_requested": 1, "next_after": _next_after(payload)},
        rate_limits=(),
        cache_hits=0,
    )
    return RedditDiscoveryResult(run=run, raw_pages=(payload,))


def _posts_from_listing(
    payload: Mapping[str, object],
    *,
    config: RedditDiscoveryConfig,
    retrieved_at: str,
) -> tuple[DiscoveredSourcePost, ...]:
    data = _required_mapping(payload.get("data"), "listing data")
    children = data.get("children")
    if not isinstance(children, list):
        raise ProviderError("Reddit listing response did not include a children list.")
    posts: list[DiscoveredSourcePost] = []
    for child in children:
        child_data = _required_mapping(child, "listing child")
        post_data = _required_mapping(child_data.get("data"), "post data")
        if bool(post_data.get("over_18")):
            continue
        source_id = _post_source_id(post_data)
        raw_title = _optional_str(post_data.get("title"))
        raw_body = _optional_str(post_data.get("selftext"))
        if _is_removed_marker(raw_title) or _is_removed_marker(raw_body):
            continue
        title = _clean_reddit_text(raw_title)
        body = _clean_reddit_text(raw_body)
        if not title and not body:
            continue
        permalink = _optional_str(post_data.get("permalink"))
        source_url = _source_url_from_permalink(permalink)
        post = build_discovered_post(
            provider=SourceProvider.REDDIT,
            source_id=source_id,
            source_url=source_url,
            title=title,
            body=body,
            retrieved_at=retrieved_at,
            source_label=f"r/{config.subreddit}",
            permalink=permalink,
        )
        if post is not None:
            posts.append(post)
    return tuple(posts)


def _reddit_listing_url(config: RedditDiscoveryConfig, *, after: str | None) -> str:
    params: dict[str, str] = {"limit": str(config.limit), "raw_json": "1"}
    if after is not None:
        params["after"] = after
    encoded_subreddit = urllib.parse.quote(config.subreddit, safe="")
    encoded_sort = urllib.parse.quote(config.sort, safe="")
    query = urllib.parse.urlencode(params)
    return f"{REDDIT_API_BASE_URL}/r/{encoded_subreddit}/{encoded_sort}?{query}"


def _reddit_headers(config: RedditDiscoveryConfig) -> dict[str, str]:
    if config.oauth_token is None:
        raise UserInputError("Reddit OAuth token is required for live discovery.")
    return {
        "Authorization": f"Bearer {config.oauth_token}",
        "User-Agent": config.user_agent,
        "Accept": "application/json",
    }


def _read_json_fixture(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.expanduser().read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise UserInputError(f"Could not read Reddit fixture JSON: {path}") from exc
    except json.JSONDecodeError as exc:
        raise UserInputError(f"Reddit fixture must be valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise UserInputError("Reddit fixture JSON must be an object.")
    return payload


def _json_object(raw: bytes, *, context: str) -> dict[str, object]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError(f"Source response was not valid UTF-8 JSON: {context}") from exc
    if not isinstance(payload, dict):
        raise ProviderError(f"Source response JSON must be an object: {context}")
    return payload


def _next_after(payload: Mapping[str, object]) -> str | None:
    data = _required_mapping(payload.get("data"), "listing data")
    return _optional_str(data.get("after"))


def _post_source_id(post_data: Mapping[str, object]) -> str:
    name = _optional_str(post_data.get("name"))
    if name is not None:
        return name
    post_id = _optional_str(post_data.get("id"))
    if post_id is None:
        raise ProviderError("Reddit post response is missing id/name.")
    return f"t3_{post_id}"


def _clean_reddit_text(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip()


def _is_removed_marker(value: str | None) -> bool:
    return value is not None and value.strip().lower() in REDDIT_REMOVED_MARKERS


def _source_url_from_permalink(permalink: str | None) -> str:
    if permalink is None:
        return "https://www.reddit.com/"
    if permalink.startswith("/"):
        return f"https://www.reddit.com{permalink}"
    return permalink


def _rate_limit_snapshot(headers: Mapping[str, str]) -> Mapping[str, object]:
    snapshot: dict[str, object] = {}
    for key in ("x-ratelimit-used", "x-ratelimit-remaining", "x-ratelimit-reset", "retry-after"):
        value = headers.get(key)
        if value is not None:
            snapshot[key] = value
    return snapshot


def _remaining_requests(headers: Mapping[str, str]) -> float:
    value = headers.get("x-ratelimit-remaining")
    if value is None:
        return 1.0
    try:
        return float(value)
    except ValueError:
        return 1.0


def _cache_key(provider: str, url: str) -> str:
    payload = {"provider": provider, "url": url}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _valid_subreddit_name(value: str) -> bool:
    if len(value) < 2 or len(value) > 21:
        return False
    return all(character.isalnum() or character == "_" for character in value)


def _required_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ProviderError(f"Reddit {name} must be an object.")
    return value


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    return value


def _utc_timestamp(value: datetime | None) -> str:
    timestamp = datetime.now(UTC) if value is None else value.astimezone(UTC)
    return timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
