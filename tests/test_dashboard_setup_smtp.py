"""
SMTP setup wizard coverage.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def single_user_app():
    from hedwig.dashboard.app import create_app

    return create_app(saas_mode=False)


def test_env_manager_accepts_standalone_smtp_delivery(tmp_path):
    """SMTP host + from address should satisfy setup readiness on their own."""
    from hedwig.dashboard.env_manager import EnvManager

    mgr = EnvManager(env_path=tmp_path / ".env")
    mgr.save(
        {
            "OPENAI_API_KEY": "sk-test",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_KEY": "service-role-key",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_FROM": "alerts@example.com",
        }
    )

    status = mgr.get_status()

    assert status["smtp_configured"] is True
    assert status["delivery_ok"] is True
    assert status["ready"] is True


@pytest.mark.asyncio
async def test_setup_page_exposes_smtp_delivery_fields(single_user_app):
    """GET /setup should expose SMTP fields alongside Slack and Discord."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=single_user_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/setup")

    body = resp.text
    assert resp.status_code == 200
    assert "Slack, Discord, or SMTP email" in body
    assert "SMTP Email" in body
    assert "SMTP Host" in body
    assert "SMTP Port" in body
    assert "SMTP Username" in body
    assert "SMTP Password" in body
    assert "SMTP From Address" in body
    assert "checks SMTP connectivity" in body
