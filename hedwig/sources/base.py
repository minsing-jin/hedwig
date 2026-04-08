from __future__ import annotations

import abc
from calendar import timegm
from datetime import datetime, timezone
from typing import ClassVar, Optional

import feedparser
import httpx

from hedwig.models import FetchMethod, Platform, RawPost, SourcePluginType


class Source(abc.ABC):
    """Base class for all signal source plugins."""

    # Subclasses set these as class-level metadata
    platform: ClassVar[Platform]
    plugin_id: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    plugin_type: ClassVar[SourcePluginType] = SourcePluginType.BUILTIN
    fetch_method: ClassVar[FetchMethod] = FetchMethod.API
    default_limit: ClassVar[int] = 50

    @abc.abstractmethod
    async def fetch(self, limit: int = 50) -> list[RawPost]:
        ...

    @classmethod
    def metadata(cls) -> dict:
        return {
            "plugin_id": cls.plugin_id or cls.__name__,
            "platform": cls.platform.value,
            "display_name": cls.display_name or cls.__name__,
            "plugin_type": cls.plugin_type.value,
            "fetch_method": cls.fetch_method.value,
            "default_limit": cls.default_limit,
        }


class RSSSource(Source):
    """Base class for RSS-feed-based sources. Handles common RSS parsing."""

    fetch_method: ClassVar[FetchMethod] = FetchMethod.RSS
    feeds: ClassVar[list[tuple[str, str]]] = []  # [(url, author_label)]
    entries_per_feed: ClassVar[int] = 5

    def __init__(self, feeds: Optional[list[tuple[str, str]]] = None):
        if feeds is not None:
            self._feeds = feeds
        else:
            self._feeds = self.__class__.feeds

    async def fetch(self, limit: int = 50) -> list[RawPost]:
        posts: list[RawPost] = []
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            for feed_url, author in self._feeds:
                try:
                    resp = await client.get(feed_url)
                    if resp.status_code != 200:
                        continue
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[: self.entries_per_feed]:
                        post = self._parse_entry(entry, author)
                        if post:
                            posts.append(post)
                except Exception:
                    continue
        return posts[:limit]

    def _parse_entry(self, entry: dict, author: str) -> Optional[RawPost]:
        published = datetime.now(tz=timezone.utc)
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published = datetime.fromtimestamp(
                timegm(entry.published_parsed), tz=timezone.utc
            )
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            published = datetime.fromtimestamp(
                timegm(entry.updated_parsed), tz=timezone.utc
            )

        return RawPost(
            platform=self.__class__.platform,
            external_id=entry.get("id", entry.get("link", "")),
            title=entry.get("title", "")[:200],
            url=entry.get("link", ""),
            content=entry.get("summary", "")[:2000],
            author=author,
            published_at=published,
        )


# ---------------------------------------------------------------------------
# Plugin registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, type[Source]] = {}


def register_source(cls: type[Source]) -> type[Source]:
    """Decorator to register a source plugin."""
    key = cls.plugin_id or cls.__name__
    _REGISTRY[key] = cls
    return cls


def get_registered_sources() -> dict[str, type[Source]]:
    return dict(_REGISTRY)


def get_source(plugin_id: str) -> type[Source] | None:
    return _REGISTRY.get(plugin_id)


def create_source(plugin_id: str, **kwargs) -> Source | None:
    cls = _REGISTRY.get(plugin_id)
    if cls is None:
        return None
    return cls(**kwargs)


class CustomRSSSource(RSSSource):
    """User-added custom RSS source. Created at runtime, not via decorator."""

    platform = Platform.CUSTOM
    plugin_type = SourcePluginType.CUSTOM
    display_name = "Custom RSS"

    def __init__(self, plugin_id: str, feeds: list[tuple[str, str]], display_name: str = ""):
        super().__init__(feeds=feeds)
        self._plugin_id = plugin_id
        if display_name:
            self._display_name = display_name

    @classmethod
    def metadata(cls) -> dict:
        return {
            "plugin_id": "custom_rss",
            "platform": Platform.CUSTOM.value,
            "display_name": "Custom RSS",
            "plugin_type": SourcePluginType.CUSTOM.value,
            "fetch_method": FetchMethod.RSS.value,
            "default_limit": 50,
        }
