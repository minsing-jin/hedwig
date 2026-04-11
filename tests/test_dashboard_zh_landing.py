"""
AC-10: Dashboard SaaS mode serves /zh (Chinese landing) HTTP 200.

Verifies:
  - GET /zh returns HTTP 200 in SaaS mode
  - Response is HTML with Chinese content
  - Chinese landing page contains Hedwig brand
  - /zh is NOT registered in non-SaaS mode
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def saas_app():
    """Create a SaaS-mode dashboard app."""
    from hedwig.dashboard.app import create_app
    return create_app(saas_mode=True)


@pytest.fixture
def single_user_app():
    """Create a single-user (non-SaaS) dashboard app."""
    from hedwig.dashboard.app import create_app
    return create_app(saas_mode=False)


# ---------------------------------------------------------------------------
# Test: /zh returns HTTP 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zh_landing_returns_200(saas_app):
    """GET /zh must return HTTP 200 in SaaS mode."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/zh")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


@pytest.mark.asyncio
async def test_zh_landing_is_html(saas_app):
    """Chinese landing page must return HTML content."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/zh")
        content_type = resp.headers.get("content-type", "")
        assert "text/html" in content_type, f"Expected HTML, got {content_type}"


@pytest.mark.asyncio
async def test_zh_landing_contains_hedwig_brand(saas_app):
    """Chinese landing page must contain Hedwig brand."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/zh")
        body = resp.text
        assert "Hedwig" in body or "hedwig" in body.lower(), \
            "Chinese landing page missing Hedwig brand"


@pytest.mark.asyncio
async def test_zh_landing_contains_chinese_text(saas_app):
    """Chinese landing page must contain Chinese language content."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/zh")
        body = resp.text
        stable_chinese_phrases = (
            "个人算法主权",
            "免费开始",
            "开始",
        )
        assert 'lang="zh"' in body, "Chinese landing missing lang='zh' attribute"
        assert any(phrase in body for phrase in stable_chinese_phrases), (
            "Chinese landing page missing stable Chinese copy"
        )


@pytest.mark.asyncio
async def test_zh_landing_has_signup_cta(saas_app):
    """Chinese landing page must contain signup CTA link."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/zh")
        body = resp.text.lower()
        assert "/signup" in body, "Chinese landing page missing /signup CTA"


# ---------------------------------------------------------------------------
# Test: /zh route registered only in SaaS mode
# ---------------------------------------------------------------------------


def test_zh_route_registered_in_saas_mode(saas_app):
    """/zh route must be registered in SaaS mode."""
    routes = [r.path for r in saas_app.routes if hasattr(r, "path")]
    assert "/zh" in routes, "/zh route not registered in SaaS mode"


def test_zh_route_not_in_single_user_mode(single_user_app):
    """/zh route must NOT be registered in single-user mode."""
    routes = [r.path for r in single_user_app.routes if hasattr(r, "path")]
    assert "/zh" not in routes, "/zh should not exist in single-user mode"
