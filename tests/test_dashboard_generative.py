"""
AC-6: /dashboard/generative renders the rule-based generative dashboard.
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


def test_generative_dashboard_build_layout_returns_expected_card_types():
    """The layout builder returns a stable ordered card set for the first skeleton."""
    from hedwig.dashboard.generative import GenerativeDashboard

    layout = GenerativeDashboard().build_layout(
        user_criteria={
            "interests": ["AI agents", "developer tools"],
            "projects": ["Hedwig"],
        },
        recent_signals=[
            {
                "platform": "github",
                "title": "Open-source agent launch",
                "url": "https://example.com/github",
                "relevance_score": 0.97,
                "opportunity_note": "Early integration opening for agent workflows.",
                "why_relevant": "Matches the builder workflow.",
                "collected_at": "2026-04-16T09:00:00+00:00",
            },
            {
                "platform": "youtube",
                "title": "Agent benchmark analysis",
                "url": "https://example.com/youtube",
                "relevance_score": 0.74,
                "why_relevant": "Explains the current benchmark shift.",
                "collected_at": "2026-04-16T10:00:00+00:00",
            },
        ],
        dashboard_stats={
            "total_signals": 12,
            "upvote_ratio": 0.75,
            "evolution_cycles": 4,
            "top_5_sources": [{"source": "github", "count": 7}],
            "days_active": 9,
        },
    )

    assert [card["type"] for card in layout["cards"]] == [
        "stat",
        "trend",
        "opportunity",
        "source_highlight",
    ]
    assert layout["cards"][0]["data"]["focus_summary"] == "AI agents, developer tools"
    assert layout["cards"][1]["data"]["source"] == "github"
    assert layout["cards"][2]["data"]["title"] == "Open-source agent launch"
    assert layout["cards"][3]["data"]["source"] == "github"


@pytest.mark.asyncio
async def test_dashboard_generative_route_returns_html_with_all_card_types(
    monkeypatch, single_user_app
):
    """GET /dashboard/generative returns 200 and renders one card per required type."""
    from hedwig.dashboard import app as dashboard_app
    from httpx import ASGITransport, AsyncClient

    monkeypatch.setattr(
        dashboard_app,
        "_load_criteria",
        lambda: {"interests": ["AI agents", "signal detection"]},
    )
    monkeypatch.setattr(
        dashboard_app,
        "_load_recent_signals",
        lambda limit=20: [
            {
                "platform": "github",
                "title": "GitHub agent launch",
                "url": "https://example.com/github",
                "relevance_score": 0.95,
                "opportunity_note": "Ship an integration while distribution is still open.",
                "why_relevant": "Directly relevant to the current roadmap.",
                "collected_at": "2026-04-16T09:00:00+00:00",
            },
            {
                "platform": "reddit",
                "title": "Developer feedback thread",
                "url": "https://example.com/reddit",
                "relevance_score": 0.68,
                "why_relevant": "Shows buyer pain in the open.",
                "collected_at": "2026-04-16T11:00:00+00:00",
            },
            {
                "platform": "youtube",
                "title": "State of AI agents",
                "url": "https://example.com/youtube",
                "relevance_score": 0.72,
                "why_relevant": "Useful market context.",
                "collected_at": "2026-04-15T11:00:00+00:00",
            },
        ],
    )
    monkeypatch.setattr(
        dashboard_app,
        "_load_dashboard_stats",
        lambda user_id=None: {
            "total_signals": 21,
            "upvote_ratio": 0.61,
            "evolution_cycles": 5,
            "top_5_sources": [
                {"source": "github", "count": 11},
                {"source": "youtube", "count": 4},
            ],
            "days_active": 14,
        },
    )

    transport = ASGITransport(app=single_user_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard/generative")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    for card_type in ("stat", "trend", "opportunity", "source_highlight"):
        assert f'data-card-type="{card_type}"' in resp.text


@pytest.mark.asyncio
async def test_dashboard_generative_route_escapes_embedded_layout_json(
    monkeypatch, single_user_app
):
    """Hostile signal content must stay inside the JSON script payload."""
    from hedwig.dashboard import app as dashboard_app
    from httpx import ASGITransport, AsyncClient

    hostile_title = '</script><script>alert("xss")</script>'

    monkeypatch.setattr(
        dashboard_app,
        "_load_criteria",
        lambda: {"interests": ["AI agents"]},
    )
    monkeypatch.setattr(
        dashboard_app,
        "_load_recent_signals",
        lambda limit=20: [
            {
                "platform": "github",
                "title": hostile_title,
                "url": "https://example.com/github",
                "relevance_score": 0.95,
                "opportunity_note": "Ship an integration while distribution is still open.",
                "why_relevant": "Directly relevant to the current roadmap.",
                "collected_at": "2026-04-16T09:00:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(
        dashboard_app,
        "_load_dashboard_stats",
        lambda user_id=None: {
            "total_signals": 1,
            "upvote_ratio": 1.0,
            "top_5_sources": [{"source": "github", "count": 1}],
            "days_active": 1,
        },
    )

    transport = ASGITransport(app=single_user_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard/generative")

    assert resp.status_code == 200
    assert '<script>alert("xss")</script>' not in resp.text
    assert "</script><script>" not in resp.text
    assert "\\u003c/script\\u003e\\u003cscript\\u003ealert(\\\"xss\\\")\\u003c/script\\u003e" in resp.text
