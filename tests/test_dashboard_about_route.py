"""
AC-13: Dashboard SaaS mode serves /about HTTP 200.

Verifies:
  - GET /about returns HTTP 200 in SaaS mode
  - Response contains HTML content
  - About page contains expected descriptive text
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
async def test_about_route_returns_200(saas_app):
    """GET /about must return HTTP 200 in SaaS mode."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/about")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


@pytest.mark.asyncio
async def test_about_route_is_html(saas_app):
    """About page must return HTML content."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/about")
        content_type = resp.headers.get("content-type", "")
        assert "text/html" in content_type, f"Expected HTML, got {content_type}"


@pytest.mark.asyncio
async def test_about_page_contains_descriptive_text(saas_app):
    """About page must contain descriptive content about Hedwig."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/about")
        body = resp.text.lower()
        assert "hedwig" in body, "About page missing 'hedwig' text"
        assert "signal" in body or "radar" in body or "onboarding" in body, \
            "About page missing descriptive content about the product"


def test_about_route_registered_in_saas_mode(saas_app):
    """/about route must be registered in SaaS mode."""
    routes = [r.path for r in saas_app.routes if hasattr(r, "path")]
    assert "/about" in routes, "/about route not registered in SaaS mode"


@pytest.mark.asyncio
async def test_about_route_not_exposed_outside_saas_mode(single_user_app):
    """GET /about must not be available when SaaS mode is disabled."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=single_user_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/about")
        assert resp.status_code == 404, f"Expected 404 outside SaaS mode, got {resp.status_code}"
