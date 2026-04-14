from __future__ import annotations

import asyncio
import html
import re
import subprocess
import tempfile
from calendar import timegm
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import httpx

from hedwig.models import FetchMethod, Platform, RawPost
from hedwig.sources.base import Source, register_source

AI_YOUTUBE_CHANNELS = [
    ("UCbfYPyITQ-7l4upoX8nvctg", "Two Minute Papers"),
    ("UCWN3xxRkmTPphYit_FYl6Ag", "AI Explained"),
    ("UCZHmQk67mSJgfCCTn7xBfew", "Bycloud"),
    ("UCMLtBahI5DMrt0NPvDSoIRQ", "Machine Learning Street Talk"),
    ("UCKlA7JlBEFMuAbBpYFkKsdg", "Matt Wolfe"),
    ("UCbRP3c757lWg9M-U7TyEkXA", "Yannic Kilcher"),
    ("UCVhQ2NnY5Rskt6UjCFkNq-A", "AI Jason"),
    ("UCwBmNDEDLnVn2fRYHnaBaOg", "The AI Advantage"),
    ("UCM548bIwKK-m5FkKKJcBQhg", "Wes Roth"),
]

TRANSCRIPT_MAX_CONCURRENCY = 8
TRANSCRIPT_TIMEOUT_SECONDS = 5.0
MAX_CONTENT_LENGTH = 5000
TRANSCRIPT_LABEL = "Transcript:"


@register_source
class YouTubeSource(Source):
    """AI videos from YouTube channels via RSS."""
    platform = Platform.YOUTUBE
    plugin_id = "youtube"
    display_name = "YouTube"
    fetch_method = FetchMethod.RSS

    def __init__(self, channels: list[tuple[str, str]] | None = None):
        self.channels = channels or AI_YOUTUBE_CHANNELS

    async def fetch(self, limit: int = 30) -> list[RawPost]:
        posts: list[RawPost] = []
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            for channel_id, channel_name in self.channels:
                try:
                    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                    resp = await client.get(rss_url)
                    if resp.status_code != 200:
                        continue
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:3]:
                        published = datetime.now(tz=timezone.utc)
                        if hasattr(entry, "published_parsed") and entry.published_parsed:
                            published = datetime.fromtimestamp(
                                timegm(entry.published_parsed), tz=timezone.utc
                            )
                        description = ""
                        if hasattr(entry, "media_group"):
                            for mg in entry.media_group:
                                if hasattr(mg, "content"):
                                    description = mg.get("content", "")
                        if not description:
                            description = entry.get("summary", "")
                        posts.append(RawPost(
                            platform=Platform.YOUTUBE,
                            external_id=entry.get("yt_videoid", entry.get("id", "")),
                            title=entry.get("title", ""),
                            url=entry.get("link", ""),
                            content=description[:2000],
                            author=channel_name,
                            published_at=published,
                            extra={"channel_id": channel_id},
                        ))
                except Exception:
                    continue
        selected_posts = posts[:limit]
        await self._enrich_posts_with_transcripts(selected_posts)
        return selected_posts

    async def _enrich_posts_with_transcripts(self, posts: list[RawPost]) -> None:
        if not posts:
            return

        semaphore = asyncio.Semaphore(min(TRANSCRIPT_MAX_CONCURRENCY, len(posts)))

        async def enrich(post: RawPost) -> None:
            async with semaphore:
                transcript = await self._fetch_video_transcript(post.url)
                if transcript:
                    post.content = self._append_transcript(post.content, transcript)

        await asyncio.gather(*(enrich(post) for post in posts))

    async def _fetch_video_transcript(
        self,
        url: str,
        timeout: float = TRANSCRIPT_TIMEOUT_SECONDS,
    ) -> str:
        if not url:
            return ""
        return await asyncio.to_thread(self._download_video_transcript, url, timeout)

    def _download_video_transcript(self, url: str, timeout: float) -> str:
        try:
            with tempfile.TemporaryDirectory(prefix="hedwig-ytdlp-") as temp_dir:
                output_template = str(Path(temp_dir) / "%(id)s")
                result = subprocess.run(
                    [
                        "yt-dlp",
                        "--skip-download",
                        "--write-subs",
                        "--write-auto-subs",
                        "--sub-langs",
                        "en.*,en",
                        "--sub-format",
                        "vtt",
                        "--output",
                        output_template,
                        url,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                if result.returncode != 0:
                    return ""

                for transcript_path in sorted(Path(temp_dir).glob("*.vtt")):
                    transcript_text = transcript_path.read_text(
                        encoding="utf-8",
                        errors="ignore",
                    )
                    transcript = self._parse_vtt_transcript(transcript_text)
                    if transcript:
                        return transcript
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            return ""

        return ""

    def _parse_vtt_transcript(self, transcript: str) -> str:
        parts: list[str] = []
        previous = ""

        for raw_line in transcript.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line in {"WEBVTT", TRANSCRIPT_LABEL}:
                continue
            if line.startswith(("Kind:", "Language:", "NOTE", "STYLE", "REGION")):
                continue
            if "-->" in line or line.isdigit():
                continue

            line = re.sub(r"<[^>]+>", "", line)
            line = html.unescape(line).strip()
            if not line or line == previous:
                continue

            parts.append(line)
            previous = line

        return " ".join(parts)

    def _append_transcript(self, content: str, transcript: str) -> str:
        if not transcript:
            return content[:MAX_CONTENT_LENGTH]

        if content:
            combined = f"{content}\n\n{TRANSCRIPT_LABEL}\n{transcript}"
        else:
            combined = f"{TRANSCRIPT_LABEL}\n{transcript}"
        return combined[:MAX_CONTENT_LENGTH]
