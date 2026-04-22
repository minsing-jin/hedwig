"""Podcast RSS source (v3, Phase 5) — multimodal input path.

Fetches recent episodes from configured podcast RSS feeds and emits each
episode as a RawPost with:
  - title = episode title
  - content = show notes / description (+ transcript when available)
  - url = episode webpage / audio URL

Transcription (yt-dlp + whisper) is **not yet wired**; this source ships
with the fetch path complete and transcript enrichment as a TODO. Users
with whisper available can set HEDWIG_PODCAST_TRANSCRIBE=1 to opt in once
the hook is implemented.
"""
from __future__ import annotations

import logging
import os
from calendar import timegm
from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx

from hedwig.models import FetchMethod, Platform, RawPost
from hedwig.sources.base import Source, register_source

logger = logging.getLogger(__name__)


DEFAULT_FEEDS: list[tuple[str, str]] = [
    # (feed_url, show_title)
    # Intentionally empty by default — user populates via HEDWIG_PODCAST_FEEDS env
    # or programmatic override. Keeping this list empty in-repo avoids arbitrary
    # third-party defaults.
]


def _parse_feeds_env() -> list[tuple[str, str]]:
    """Parse HEDWIG_PODCAST_FEEDS='url|name, url|name, ...' into feed list."""
    raw = os.getenv("HEDWIG_PODCAST_FEEDS", "").strip()
    if not raw:
        return []
    out = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "|" in chunk:
            url, name = chunk.split("|", 1)
        else:
            url, name = chunk, chunk
        out.append((url.strip(), name.strip()))
    return out


@register_source
class PodcastSource(Source):
    """RSS-based podcast source. Multimodal — content flows back as text."""
    platform = Platform.PODCAST
    plugin_id = "podcast"
    display_name = "Podcasts (RSS)"
    fetch_method = FetchMethod.RSS
    default_limit = 20

    def __init__(self, feeds: Optional[list[tuple[str, str]]] = None):
        self._feeds = feeds if feeds is not None else (DEFAULT_FEEDS + _parse_feeds_env())

    async def fetch(self, limit: int = 20) -> list[RawPost]:
        if not self._feeds:
            return []
        posts: list[RawPost] = []
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            for feed_url, show_title in self._feeds:
                try:
                    resp = await client.get(feed_url)
                    if resp.status_code != 200:
                        continue
                    parsed = feedparser.parse(resp.text)
                    for entry in parsed.entries[:5]:
                        posts.append(self._parse_episode(entry, show_title))
                except Exception as e:
                    logger.debug("podcast feed %s failed: %s", feed_url, e)
                    continue

        # Optional transcription pass — only runs when env flag + OpenAI key are set
        if os.getenv("HEDWIG_PODCAST_TRANSCRIBE") == "1":
            try:
                from hedwig.sources._transcribe import enrich_podcast_post
                import asyncio as _asyncio
                enriched = await _asyncio.gather(
                    *(enrich_podcast_post(p) for p in posts), return_exceptions=True,
                )
                posts = [
                    p if isinstance(p, RawPost) else orig
                    for p, orig in zip(enriched, posts)
                ]
            except Exception as e:
                logger.debug("podcast transcription batch failed: %s", e)

        return posts[:limit]

    def _parse_episode(self, entry, show_title: str) -> RawPost:
        published = datetime.now(tz=timezone.utc)
        if getattr(entry, "published_parsed", None):
            published = datetime.fromtimestamp(timegm(entry.published_parsed), tz=timezone.utc)
        elif getattr(entry, "updated_parsed", None):
            published = datetime.fromtimestamp(timegm(entry.updated_parsed), tz=timezone.utc)

        description = (entry.get("description") or entry.get("summary") or "")[:4000]
        audio_url = ""
        for link in entry.get("enclosures", []) or []:
            if link.get("type", "").startswith("audio/"):
                audio_url = link.get("href", "")
                break

        external_id = entry.get("id") or entry.get("guid") or entry.get("link") or entry.get("title", "")
        return RawPost(
            platform=Platform.PODCAST,
            external_id=f"podcast:{external_id[:120]}",
            title=f"🎙 {show_title}: {entry.get('title', '(untitled)')}",
            url=entry.get("link") or audio_url,
            content=description,
            author=show_title,
            score=0,
            comments_count=0,
            published_at=published,
            extra={
                "medium": "podcast",
                "audio_url": audio_url,
                "transcribe": os.getenv("HEDWIG_PODCAST_TRANSCRIBE") == "1",
            },
        )
