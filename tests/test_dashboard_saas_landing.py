"""
AC-4: Dashboard SaaS mode starts and serves the landing page HTTP 200.

Verifies:
  - create_app(saas_mode=True) succeeds without errors
  - GET /landing returns HTTP 200 with HTML content
  - Landing page contains key marketing elements (brand, CTA, pricing)
  - Static CSS assets referenced by landing page are served correctly
  - SaaS auth routes (signup, login) are registered and return 200
  - Non-SaaS mode does NOT expose the /landing route
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
# Test: app creation
# ---------------------------------------------------------------------------


def test_saas_app_creates_successfully(saas_app):
    """SaaS app should be created without errors."""
    assert saas_app is not None
    assert saas_app.title == "Hedwig Dashboard"
    assert saas_app.state.saas_mode is True


def test_single_user_app_creates_successfully(single_user_app):
    """Single-user app should be created without errors."""
    assert single_user_app is not None
    assert single_user_app.state.saas_mode is False


# ---------------------------------------------------------------------------
# Test: landing page HTTP 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_landing_page_returns_200(saas_app):
    """GET /landing must return HTTP 200."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/landing")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


@pytest.mark.asyncio
async def test_landing_page_is_html(saas_app):
    """Landing page must return HTML content."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/landing")
        content_type = resp.headers.get("content-type", "")
        assert "text/html" in content_type, f"Expected HTML, got {content_type}"


@pytest.mark.asyncio
async def test_landing_page_contains_brand(saas_app):
    """Landing page must contain the Hedwig brand name."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/landing")
        body = resp.text
        assert "Hedwig" in body, "Landing page missing 'Hedwig' brand"


@pytest.mark.asyncio
async def test_landing_page_contains_cta(saas_app):
    """Landing page must contain signup call-to-action."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/landing")
        body = resp.text.lower()
        assert "/signup" in body, "Landing page missing signup CTA link"


@pytest.mark.asyncio
async def test_landing_page_contains_pricing(saas_app):
    """Landing page must contain pricing section."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/landing")
        body = resp.text
        assert "pricing" in body.lower(), "Landing page missing pricing section"
        assert "$19" in body, "Landing page missing Pro price"
        assert "$49" in body, "Landing page missing Team price"


# ---------------------------------------------------------------------------
# Test: static CSS assets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_static_style_css_served(saas_app):
    """Static style.css must be served (referenced by landing.html)."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/static/style.css")
        assert resp.status_code == 200, f"style.css returned {resp.status_code}"


@pytest.mark.asyncio
async def test_static_landing_css_served(saas_app):
    """Static landing.css must be served (referenced by landing.html)."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/static/landing.css")
        assert resp.status_code == 200, f"landing.css returned {resp.status_code}"


# ---------------------------------------------------------------------------
# Test: SaaS routes are registered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signup_page_returns_200(saas_app):
    """GET /signup must return HTTP 200 in SaaS mode."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/signup")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_login_page_returns_200(saas_app):
    """GET /login must return HTTP 200 in SaaS mode."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/login")
        assert resp.status_code == 200


def test_saas_routes_registered(saas_app):
    """SaaS mode must register landing, signup, login, auth, and billing routes."""
    routes = [r.path for r in saas_app.routes if hasattr(r, "path")]
    for expected in ("/landing", "/signup", "/login", "/auth/signup", "/auth/login", "/billing/checkout"):
        assert expected in routes, f"Route {expected} not registered in SaaS mode"


# ---------------------------------------------------------------------------
# Test: non-SaaS mode does NOT expose landing
# ---------------------------------------------------------------------------


def test_non_saas_mode_no_landing_route(single_user_app):
    """Non-SaaS mode must NOT register the /landing route."""
    routes = [r.path for r in single_user_app.routes if hasattr(r, "path")]
    assert "/landing" not in routes, "/landing should not exist in single-user mode"
    assert "/signup" not in routes, "/signup should not exist in single-user mode"
    assert "/login" not in routes, "/login should not exist in single-user mode"
