"""
AC-11: Dashboard SaaS mode serves /terms HTTP 200.

Verifies:
  - GET /terms returns HTTP 200 in SaaS mode
  - Response contains HTML content
  - Terms page contains expected legal text
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
async def test_terms_route_returns_200(saas_app):
    """GET /terms must return HTTP 200 in SaaS mode."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/terms")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


@pytest.mark.asyncio
async def test_terms_route_is_html(saas_app):
    """Terms page must return HTML content."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/terms")
        content_type = resp.headers.get("content-type", "")
        assert "text/html" in content_type, f"Expected HTML, got {content_type}"


@pytest.mark.asyncio
async def test_terms_page_contains_legal_text(saas_app):
    """Terms page must contain terms of service content."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/terms")
        body = resp.text.lower()
        assert "terms" in body, "Terms page missing 'terms' text"
        assert "service" in body or "agreement" in body or "agree" in body, \
            "Terms page missing legal agreement language"
