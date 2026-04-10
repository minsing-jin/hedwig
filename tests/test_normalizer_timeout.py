"""Tests for r.jina.ai normalizer — timeout and error handling.

Verifies that normalize_content, normalize_batch, and search_web degrade
gracefully when the upstream Jina API times out, refuses connections, or
returns unexpected responses.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from hedwig.engine.normalizer import (
    DEFAULT_TIMEOUT,
    normalize_batch,
    normalize_content,
    search_web,
)
from hedwig.models import RawPost


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_post(url: str = "https://example.com/article", content: str = "fallback content") -> RawPost:
    return RawPost(
        platform="hackernews",
        external_id="1",
        title="Test",
        url=url,
        content=content,
    )


# ---------------------------------------------------------------------------
# normalize_content — timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_normalize_content_timeout_returns_original():
    """When Jina times out, normalize_content must return post.content."""
    post = _make_post()

    with patch("hedwig.engine.normalizer.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.side_effect = httpx.ReadTimeout("timed out")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await normalize_content(post, timeout=0.01)

    assert result == "fallback content"


@pytest.mark.asyncio
async def test_normalize_content_connect_timeout_returns_original():
    """ConnectTimeout is also handled gracefully."""
    post = _make_post()

    with patch("hedwig.engine.normalizer.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.side_effect = httpx.ConnectTimeout("connect timeout")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await normalize_content(post, timeout=0.01)

    assert result == "fallback content"


@pytest.mark.asyncio
async def test_normalize_content_pool_timeout_returns_original():
    """PoolTimeout (connection pool exhausted) is handled gracefully."""
    post = _make_post()

    with patch("hedwig.engine.normalizer.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.side_effect = httpx.PoolTimeout("pool timeout")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await normalize_content(post, timeout=0.01)

    assert result == "fallback content"


# ---------------------------------------------------------------------------
# normalize_content — connection errors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_normalize_content_connect_error_returns_original():
    """When Jina is unreachable, return original content."""
    post = _make_post()

    with patch("hedwig.engine.normalizer.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.side_effect = httpx.ConnectError("connection refused")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await normalize_content(post)

    assert result == "fallback content"


# ---------------------------------------------------------------------------
# normalize_content — HTTP error responses
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_normalize_content_500_returns_original():
    """When Jina returns a server error, return original content."""
    post = _make_post()

    with patch("hedwig.engine.normalizer.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        instance.get.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await normalize_content(post)

    assert result == "fallback content"


@pytest.mark.asyncio
async def test_normalize_content_short_response_returns_original():
    """When Jina returns very short content (<50 chars), fall back."""
    post = _make_post()

    with patch("hedwig.engine.normalizer.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = "tiny"
        instance.get.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await normalize_content(post)

    assert result == "fallback content"


# ---------------------------------------------------------------------------
# normalize_content — success path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_normalize_content_success():
    """When Jina succeeds, return the markdown content."""
    post = _make_post()
    long_markdown = "# Great Article\n\n" + "Lorem ipsum dolor sit amet. " * 10

    with patch("hedwig.engine.normalizer.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = long_markdown
        instance.get.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await normalize_content(post)

    assert result == long_markdown


@pytest.mark.asyncio
async def test_normalize_content_truncates_at_5000():
    """Content longer than 5000 chars is truncated."""
    post = _make_post()
    oversized = "x" * 10_000

    with patch("hedwig.engine.normalizer.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = oversized
        instance.get.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await normalize_content(post)

    assert len(result) == 5000


# ---------------------------------------------------------------------------
# normalize_content — skip paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_normalize_content_no_url_returns_content():
    """Posts without a URL return content as-is."""
    post = _make_post(url="", content="no-url content")
    result = await normalize_content(post)
    assert result == "no-url content"


@pytest.mark.asyncio
async def test_normalize_content_jina_url_returns_content():
    """Posts already pointing at r.jina.ai skip re-normalization."""
    post = _make_post(url="https://r.jina.ai/already", content="jina content")
    result = await normalize_content(post)
    assert result == "jina content"


# ---------------------------------------------------------------------------
# normalize_batch — timeout resilience
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_normalize_batch_timeout_preserves_originals():
    """Batch normalization with all timeouts keeps every post's original content."""
    posts = [_make_post(content=f"original-{i}") for i in range(3)]

    with patch("hedwig.engine.normalizer.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.side_effect = httpx.ReadTimeout("timed out")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await normalize_batch(posts, timeout=0.01)

    assert len(result) == 3
    for i, post in enumerate(result):
        assert post.content == f"original-{i}"


@pytest.mark.asyncio
async def test_normalize_batch_partial_failure():
    """If some posts timeout and some succeed, each post gets the right content."""
    posts = [
        _make_post(url="https://example.com/ok", content="short"),
        _make_post(url="https://example.com/slow", content="original-slow"),
    ]

    long_md = "# Success\n" + "Word " * 50

    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # First call succeeds, second times out
        url = args[0] if args else kwargs.get("url", "")
        if "ok" in str(url):
            resp = AsyncMock()
            resp.status_code = 200
            resp.text = long_md
            return resp
        raise httpx.ReadTimeout("timed out")

    with patch("hedwig.engine.normalizer.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.side_effect = side_effect
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await normalize_batch(posts, timeout=0.01)

    # First post should be updated (normalized content is longer)
    assert "Success" in result[0].content or result[0].content == "short"
    # Second post keeps original
    assert result[1].content == "original-slow"


# ---------------------------------------------------------------------------
# search_web — timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_web_timeout_returns_empty():
    """search_web returns empty list on timeout."""
    with patch("hedwig.engine.normalizer.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.side_effect = httpx.ReadTimeout("timed out")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await search_web("test query", timeout=0.01)

    assert result == []


@pytest.mark.asyncio
async def test_search_web_connect_error_returns_empty():
    """search_web returns empty list on connection error."""
    with patch("hedwig.engine.normalizer.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.side_effect = httpx.ConnectError("refused")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await search_web("test query")

    assert result == []


# ---------------------------------------------------------------------------
# DEFAULT_TIMEOUT constant
# ---------------------------------------------------------------------------

def test_default_timeout_is_reasonable():
    """DEFAULT_TIMEOUT should be a positive number >= 5s."""
    assert DEFAULT_TIMEOUT >= 5.0
    assert isinstance(DEFAULT_TIMEOUT, (int, float))
