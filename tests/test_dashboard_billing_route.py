"""
AC-7: Dashboard SaaS mode serves /billing route HTTP 200.

Verifies:
  - GET /billing returns HTTP 200 in SaaS mode
  - Response contains HTML content
  - Billing page references all three tiers (free, pro, team)
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
async def test_billing_route_returns_200(saas_app):
    """GET /billing must return HTTP 200 in SaaS mode."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/billing")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


@pytest.mark.asyncio
async def test_billing_route_is_html(saas_app):
    """Billing page must return HTML content."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/billing")
        content_type = resp.headers.get("content-type", "")
        assert "text/html" in content_type, f"Expected HTML, got {content_type}"


@pytest.mark.asyncio
async def test_billing_page_contains_all_tiers(saas_app):
    """Billing page must reference all available subscription tiers."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/billing")
        body = resp.text.lower()
        assert "billing" in body, "Billing page missing 'billing' text"
        for tier in ("free", "pro", "team"):
            assert tier in body, f"Billing page missing '{tier}' tier reference"


@pytest.mark.asyncio
async def test_billing_route_not_exposed_outside_saas_mode(single_user_app):
    """GET /billing must not be available when SaaS mode is disabled."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=single_user_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/billing")
        assert resp.status_code == 404, f"Expected 404 outside SaaS mode, got {resp.status_code}"
