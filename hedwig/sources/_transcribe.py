"""Audio transcription helper for the podcast source (v3, post-Phase completion).

Uses OpenAI's hosted Whisper endpoint (``audio.transcriptions.create``) so
users don't need a local whisper install. Caches results on disk keyed by
audio URL hash so a re-downloaded episode isn't re-billed.

Enable per-post by setting ``post.extra["transcribe"] = True`` AND
``HEDWIG_PODCAST_TRANSCRIBE=1`` AND OPENAI_API_KEY.
"""
from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from pathlib import Path

import httpx

from hedwig.config import OPENAI_API_KEY
from hedwig.models import RawPost

logger = logging.getLogger(__name__)


CACHE_DIR = Path(os.getenv(
    "HEDWIG_TRANSCRIPT_CACHE",
    str(Path.home() / ".hedwig" / "transcripts"),
))
TRANSCRIBE_MODEL = os.getenv("HEDWIG_TRANSCRIBE_MODEL", "whisper-1")
MAX_AUDIO_BYTES = 24 * 1024 * 1024  # OpenAI limit is 25MB


def _cache_path(audio_url: str) -> Path:
    key = hashlib.sha1(audio_url.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{key}.txt"


async def transcribe_url(audio_url: str) -> str | None:
    """Download the audio and return its transcript, or None on any failure."""
    if not audio_url or not OPENAI_API_KEY:
        return None
    if os.getenv("HEDWIG_PODCAST_TRANSCRIBE") != "1":
        return None

    cache_file = _cache_path(audio_url)
    if cache_file.exists():
        try:
            return cache_file.read_text(encoding="utf-8")
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(audio_url)
            if resp.status_code != 200:
                logger.debug("transcribe: status %s for %s", resp.status_code, audio_url)
                return None
            data = resp.content
    except Exception as e:
        logger.debug("transcribe download failed: %s", e)
        return None

    if len(data) > MAX_AUDIO_BYTES:
        logger.debug("transcribe: audio too large (%d B) for %s", len(data), audio_url)
        return None

    # Write to a temp file — OpenAI SDK needs a filename suffix it recognizes
    suffix = Path(audio_url.split("?", 1)[0]).suffix or ".mp3"
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return None

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)

    try:
        with open(tmp_path, "rb") as audio_file:
            tr = await client.audio.transcriptions.create(
                model=TRANSCRIBE_MODEL,
                file=audio_file,
            )
        text = getattr(tr, "text", None) or ""
    except Exception as e:
        logger.warning("transcribe API failed: %s", e)
        text = ""
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass

    if not text:
        return None

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(text, encoding="utf-8")
    except Exception:
        pass
    return text


async def enrich_podcast_post(post: RawPost) -> RawPost:
    """Attach transcript to a podcast post's content when available."""
    if post.extra.get("medium") != "podcast":
        return post
    audio_url = post.extra.get("audio_url") or ""
    transcript = await transcribe_url(audio_url)
    if not transcript:
        return post
    snippet = transcript[:4000]
    if snippet and snippet not in post.content:
        post.content = (post.content + "\n\n---\nTranscript:\n" + snippet)[:5000]
        post.extra["has_transcript"] = True
    return post
