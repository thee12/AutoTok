from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from autotok.errors import UserInputError
from autotok.models import SourceType
from autotok.source_adapters import (
    HttpJsonResponse,
    RedditDataApiAdapter,
    RedditDiscoveryConfig,
    discover_reddit_from_fixture,
)
from autotok.source_ingestion import build_source_post_record
from autotok.source_models import SourceProvider
from autotok.source_storage import SourceDiscoveryStore, SourceRetrievalCache
from autotok.storage import StoryStore

FIXTURE = Path("tests/fixtures/reddit_listing.json")
FIXED_TIME = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


class FakeRedditClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.urls: list[str] = []

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: int,
    ) -> HttpJsonResponse:
        self.urls.append(url)
        assert headers["Authorization"] == "Bearer token"
        assert headers["User-Agent"] == "AutoTok tests"
        assert timeout_seconds == 7
        return HttpJsonResponse(
            payload=self.payload,
            headers={"x-ratelimit-remaining": "12", "x-ratelimit-reset": "600"},
            status_code=200,
        )


def test_reddit_fixture_discovery_filters_unusable_posts() -> None:
    result = discover_reddit_from_fixture(
        FIXTURE,
        RedditDiscoveryConfig(subreddit="autotok_test", limit=25),
        now=FIXED_TIME,
    )

    assert result.run.provider is SourceProvider.REDDIT
    assert result.run.created_at == "2026-06-30T12:00:00Z"
    assert [post.source_id for post in result.run.posts] == ["t3_abc123", "t3_def456"]
    assert result.run.posts[0].source_url.startswith("https://www.reddit.com/r/autotok_test")
    assert result.run.posts[0].story_text.startswith("A public approved story")
    assert result.raw_pages[0]["kind"] == "Listing"


def test_reddit_live_adapter_uses_auth_headers_and_cache(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8-sig"))
    fake_client = FakeRedditClient(payload)
    adapter = RedditDataApiAdapter(fake_client)
    config = RedditDiscoveryConfig(
        subreddit="autotok_test",
        sort="hot",
        limit=2,
        max_pages=1,
        user_agent="AutoTok tests",
        oauth_token="token",
        timeout_seconds=7,
    )
    cache = SourceRetrievalCache(tmp_path / "data", SourceProvider.REDDIT)

    first = adapter.discover(config, cache=cache, now=FIXED_TIME)
    second = adapter.discover(config, cache=cache, now=FIXED_TIME)

    fake = fake_client
    assert isinstance(fake, FakeRedditClient)
    assert len(fake.urls) == 1
    assert first.run.cache_hits == 0
    assert second.run.cache_hits == 1
    assert second.run.rate_limits[0]["x-ratelimit-remaining"] == "12"


def test_reddit_live_adapter_requires_oauth_without_fixture() -> None:
    adapter = RedditDataApiAdapter(FakeRedditClient({"data": {"children": []}}))
    config = RedditDiscoveryConfig(subreddit="autotok_test", oauth_token=None)

    with pytest.raises(UserInputError, match="AUTOTOK_REDDIT_OAUTH_TOKEN"):
        adapter.discover(config, now=FIXED_TIME)


def test_source_discovery_store_and_import_to_story_store(tmp_path: Path) -> None:
    result = discover_reddit_from_fixture(
        FIXTURE,
        RedditDiscoveryConfig(subreddit="autotok_test", limit=25),
        now=FIXED_TIME,
    )
    discovery_store = SourceDiscoveryStore(tmp_path / "data")

    stored_discovery = discovery_store.save(result.run, raw_pages=result.raw_pages)
    loaded_discovery = discovery_store.load(stored_discovery.record.discovery_id)
    post = loaded_discovery.record.posts[0]
    story = build_source_post_record(post, imported_at=FIXED_TIME)
    stored_story = StoryStore(tmp_path / "data").save(story)

    assert stored_discovery.created is True
    assert loaded_discovery.raw_page_paths[0].exists()
    assert stored_story.record.source.source_type is SourceType.REDDIT_POST
    assert stored_story.record.source.source_identifier == "t3_abc123"
    assert stored_story.record.source.source_url == post.source_url
    assert stored_story.record.source.retrieved_at == "2026-06-30T12:00:00Z"
    assert stored_story.record.normalized_text.startswith("A public approved story")
