"""
AC-9: Dashboard SaaS mode serves /ko (Korean landing) HTTP 200.

Verifies:
  - GET /ko returns HTTP 200 in SaaS mode
  - Response is HTML with Korean content
  - Korean landing page contains Hedwig brand
  - /ko is NOT registered in non-SaaS mode
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
# Test: /ko returns HTTP 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ko_landing_returns_200(saas_app):
    """GET /ko must return HTTP 200 in SaaS mode."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/ko")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


@pytest.mark.asyncio
async def test_ko_landing_is_html(saas_app):
    """Korean landing page must return HTML content."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/ko")
        content_type = resp.headers.get("content-type", "")
        assert "text/html" in content_type, f"Expected HTML, got {content_type}"


@pytest.mark.asyncio
async def test_ko_landing_contains_hedwig_brand(saas_app):
    """Korean landing page must contain Hedwig brand."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/ko")
        body = resp.text
        assert "Hedwig" in body or "hedwig" in body.lower(), \
            "Korean landing page missing Hedwig brand"


@pytest.mark.asyncio
async def test_ko_landing_contains_korean_text(saas_app):
    """Korean landing page must contain Korean language content."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/ko")
        body = resp.text
        stable_korean_phrases = (
            "개인을 위한 알고리즘 주권",
            "무료로 시작",
            "시작하기",
        )
        assert 'lang="ko"' in body, "Korean landing missing lang='ko' attribute"
        assert any(phrase in body for phrase in stable_korean_phrases), (
            "Korean landing page missing stable Korean copy"
        )


@pytest.mark.asyncio
async def test_ko_landing_has_signup_cta(saas_app):
    """Korean landing page must contain signup CTA link."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/ko")
        body = resp.text.lower()
        assert "/signup" in body, "Korean landing page missing /signup CTA"


# ---------------------------------------------------------------------------
# Test: /ko route registered only in SaaS mode
# ---------------------------------------------------------------------------


def test_ko_route_registered_in_saas_mode(saas_app):
    """/ko route must be registered in SaaS mode."""
    routes = [r.path for r in saas_app.routes if hasattr(r, "path")]
    assert "/ko" in routes, "/ko route not registered in SaaS mode"


def test_ko_route_not_in_single_user_mode(single_user_app):
    """/ko route must NOT be registered in single-user mode."""
    routes = [r.path for r in single_user_app.routes if hasattr(r, "path")]
    assert "/ko" not in routes, "/ko should not exist in single-user mode"
