"""AC-22: rendered billing page references Free, Pro, and Team tiers."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VISIBLE_TIER_RE = re.compile(r">\s*(free|pro|team)\s*<", re.IGNORECASE)


@pytest.fixture
def saas_app():
    """Create a SaaS-mode dashboard app."""
    from hedwig.dashboard.app import create_app

    return create_app(saas_mode=True)


@pytest.mark.asyncio
async def test_billing_page_references_all_three_tiers(saas_app):
    """GET /billing must render visible Free, Pro, and Team tier labels."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/billing")

    assert response.status_code == 200

    visible_tiers = {match.group(1).lower() for match in VISIBLE_TIER_RE.finditer(response.text)}
    assert {"free", "pro", "team"}.issubset(visible_tiers), (
        f"Rendered billing page missing tier labels: expected free/pro/team, got {sorted(visible_tiers)}"
    )
