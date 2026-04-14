from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import feedparser
import pytest

from hedwig.sources import youtube as youtube_mod
from hedwig.sources.youtube import YouTubeSource


def _make_rss_entry() -> feedparser.FeedParserDict:
    return feedparser.FeedParserDict(
        {
            "yt_videoid": "abc123",
            "id": "video-entry-id",
            "title": "Agent update",
            "link": "https://www.youtube.com/watch?v=abc123",
            "summary": "Summary body",
            "published_parsed": time.gmtime(1_712_674_800),
        }
    )


def _mock_youtube_rss(entry: feedparser.FeedParserDict):
    return patch("hedwig.sources.youtube.feedparser.parse", return_value=SimpleNamespace(entries=[entry]))


def _mock_http_client():
    return patch("hedwig.sources.youtube.httpx.AsyncClient")


def test_download_video_transcript_uses_yt_dlp_and_parses_vtt(monkeypatch):
    source = YouTubeSource(channels=[])
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, capture_output, text, timeout, check):
        captured["cmd"] = cmd
        output_template = Path(cmd[cmd.index("--output") + 1])
        transcript_path = output_template.parent / "abc123.en.vtt"
        transcript_path.write_text(
            "\n".join(
                [
                    "WEBVTT",
                    "",
                    "00:00:00.000 --> 00:00:01.000",
                    "Hello",
                    "",
                    "00:00:01.000 --> 00:00:02.000",
                    "Hello",
                    "world",
                ]
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        youtube_mod,
        "subprocess",
        SimpleNamespace(run=fake_run),
        raising=False,
    )

    transcript = source._download_video_transcript(
        "https://www.youtube.com/watch?v=abc123",
        timeout=3.0,
    )

    assert transcript == "Hello world"
    assert captured["cmd"][0] == "yt-dlp"
    assert "--write-subs" in captured["cmd"]
    assert "--write-auto-subs" in captured["cmd"]
    assert "--skip-download" in captured["cmd"]


@pytest.mark.asyncio
async def test_fetch_appends_transcript_to_youtube_post_content():
    source = YouTubeSource(channels=[("channel-1", "Test Channel")])
    entry = _make_rss_entry()

    with _mock_http_client() as MockClient, _mock_youtube_rss(entry):
        instance = AsyncMock()
        response = AsyncMock()
        response.status_code = 200
        response.text = "<rss />"
        instance.get.return_value = response
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        with patch.object(
            YouTubeSource,
            "_fetch_video_transcript",
            new=AsyncMock(return_value="Transcript line one. Transcript line two."),
            create=True,
        ):
            posts = await source.fetch(limit=1)

    assert len(posts) == 1
    assert posts[0].content == (
        "Summary body\n\nTranscript:\nTranscript line one. Transcript line two."
    )


@pytest.mark.asyncio
async def test_fetch_keeps_rss_summary_when_transcript_unavailable():
    source = YouTubeSource(channels=[("channel-1", "Test Channel")])
    entry = _make_rss_entry()

    with _mock_http_client() as MockClient, _mock_youtube_rss(entry):
        instance = AsyncMock()
        response = AsyncMock()
        response.status_code = 200
        response.text = "<rss />"
        instance.get.return_value = response
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        with patch.object(
            YouTubeSource,
            "_fetch_video_transcript",
            new=AsyncMock(return_value=""),
            create=True,
        ):
            posts = await source.fetch(limit=1)

    assert len(posts) == 1
    assert posts[0].content == "Summary body"
