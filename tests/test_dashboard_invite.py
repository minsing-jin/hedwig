"""
AC-8: Dashboard SaaS mode serves /invite route HTTP 200.

Verifies:
  - GET /invite returns HTTP 200 in SaaS mode
  - Response is HTML containing invite-related content
  - Invite link is present in the page
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


@pytest.mark.asyncio
async def test_invite_route_returns_200(saas_app):
    """GET /invite must return HTTP 200 in SaaS mode."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/invite")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


@pytest.mark.asyncio
async def test_invite_route_returns_html(saas_app):
    """GET /invite must return HTML content."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/invite")
        content_type = resp.headers.get("content-type", "")
        assert "text/html" in content_type, f"Expected HTML, got {content_type}"


@pytest.mark.asyncio
async def test_invite_page_contains_invite_link(saas_app):
    """Invite page must contain an invite link input."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/invite")
        body = resp.text
        assert "invite-link" in body, "Invite page missing invite link element"
        assert "signup?ref=" in body, "Invite page missing referral link"


@pytest.mark.asyncio
async def test_invite_page_contains_share_buttons(saas_app):
    """Invite page must contain share buttons (X/Twitter, Email)."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/invite")
        body = resp.text
        assert "twitter.com" in body or "x.com" in body, "Missing X/Twitter share button"
        assert "mailto:" in body, "Missing email share button"


def test_invite_route_registered(saas_app):
    """SaaS mode must register the /invite route."""
    routes = [r.path for r in saas_app.routes if hasattr(r, "path")]
    assert "/invite" in routes, "Route /invite not registered in SaaS mode"
