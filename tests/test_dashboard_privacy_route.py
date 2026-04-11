"""
AC-12: Dashboard SaaS mode serves /privacy HTTP 200.

Verifies:
  - GET /privacy returns HTTP 200 in SaaS mode
  - Response contains HTML content
  - Privacy page contains expected privacy policy text
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
    """Create a single-user dashboard app."""
    from hedwig.dashboard.app import create_app
    return create_app(saas_mode=False)


@pytest.mark.asyncio
async def test_privacy_route_returns_200(saas_app):
    """GET /privacy must return HTTP 200 in SaaS mode."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/privacy")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


@pytest.mark.asyncio
async def test_privacy_route_is_html(saas_app):
    """Privacy page must return HTML content."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/privacy")
        content_type = resp.headers.get("content-type", "")
        assert "text/html" in content_type, f"Expected HTML, got {content_type}"


@pytest.mark.asyncio
async def test_privacy_page_contains_policy_text(saas_app):
    """Privacy page must contain privacy policy content."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/privacy")
        body = resp.text.lower()
        assert "privacy" in body, "Privacy page missing 'privacy' text"
        assert "data" in body or "information" in body or "collect" in body, \
            "Privacy page missing data/information collection language"


@pytest.mark.asyncio
async def test_privacy_route_not_exposed_outside_saas_mode(single_user_app):
    """GET /privacy must not be available when SaaS mode is disabled."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=single_user_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/privacy")
        assert resp.status_code == 404, f"Expected 404 outside SaaS mode, got {resp.status_code}"
