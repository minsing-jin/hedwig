"""Coverage for /chat + Jina trafilatura fallback + UX changes."""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    import hedwig.config as _cfg
    _cfg._ALGORITHM_VERSION_SEEDED = False
    yield tmp_path


# --- Bug fix: feedback no longer 500s -------------------------------

def test_feedback_endpoint_no_longer_500s(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.demo_seed import seed_demo
    seed_demo(reset=True)
    client = TestClient(create_app())
    resp = client.post("/feedback/demo-0/up")
    assert resp.status_code == 200
    assert resp.json().get("ok") is True


def test_save_feedback_accepts_user_id_kwarg(tmp_env):
    from hedwig.feedback import FeedbackCollector
    from hedwig.models import VoteType
    from hedwig.storage import save_feedback
    fb = FeedbackCollector().from_direct(signal_id="x", vote=VoteType.UP)
    # local backend ignores user_id but must accept it
    assert save_feedback(fb, user_id="anything") is True
    assert save_feedback(fb, user_id=None) is True


# --- Chat — conversations + messages CRUD --------------------------

def test_create_and_list_conversations(tmp_env):
    from hedwig.storage import (
        append_chat_message,
        create_conversation,
        list_conversations,
        get_chat_messages,
    )
    create_conversation("c1", title="My chat")
    append_chat_message("c1", "user", "hello")
    append_chat_message("c1", "assistant", "hi there")
    convos = list_conversations()
    assert any(c["id"] == "c1" for c in convos)
    msgs = get_chat_messages("c1")
    assert [m["role"] for m in msgs] == ["user", "assistant"]


def test_chat_page_renders(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/chat")
    assert resp.status_code == 200
    assert "chat-shell" in resp.text
    # Chat page now streams via /chat/stream (SSE) — /chat/message remains a
    # supported fallback endpoint registered server-side.
    assert "/chat/stream" in resp.text


def test_chat_message_endpoint_no_openai_key(tmp_env, monkeypatch):
    """Without an OPENAI_API_KEY the endpoint must persist a graceful fallback message."""
    monkeypatch.setattr("hedwig.chat.router.OPENAI_API_KEY", "")
    from hedwig.dashboard.app import create_app
    from hedwig.storage import get_chat_messages
    client = TestClient(create_app())
    resp = client.post("/chat/message", json={
        "conversation_id": "c-test", "message": "hello",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "OpenAI API" in data["answer"]
    msgs = get_chat_messages("c-test")
    assert any(m["role"] == "user" and m["content"] == "hello" for m in msgs)
    assert any(m["role"] == "assistant" for m in msgs)


def test_chat_tools_search_signals(tmp_env):
    from hedwig.dashboard.demo_seed import seed_demo
    from hedwig.chat.tools import t_search_signals
    seed_demo(reset=True)
    out = t_search_signals(query="agent", limit=5)
    assert "items" in out
    assert isinstance(out["items"], list)


def test_chat_tools_get_status(tmp_env):
    from hedwig.chat.tools import t_get_status
    out = t_get_status()
    assert "exit_conditions" in out
    assert len(out["exit_conditions"]) == 4


def test_chat_tools_propose_criteria_no_key(tmp_env, monkeypatch):
    monkeypatch.setattr("hedwig.config.OPENAI_API_KEY", "")
    monkeypatch.setattr("hedwig.onboarding.nl_editor.OPENAI_API_KEY", "")
    from hedwig.chat.tools import t_propose_criteria
    out = asyncio.run(t_propose_criteria(intent="agent 위주로"))
    assert out["ok"] is False
    assert "OPENAI_API_KEY" in out.get("error", "")


def test_chat_tools_call_dispatcher(tmp_env):
    from hedwig.chat.tools import call_tool
    out = asyncio.run(call_tool("get_status", {}))
    assert "exit_conditions" in out
    err = asyncio.run(call_tool("nope", {}))
    assert "unknown tool" in err.get("error", "")


# --- Jina trafilatura fallback -----------------------------------

def test_normalizer_falls_back_to_trafilatura(monkeypatch):
    """When Jina returns 429, fetch_clean_markdown should try trafilatura."""
    import httpx
    from hedwig.engine import normalizer

    class _Resp:
        def __init__(self, status_code, text=""):
            self.status_code = status_code
            self.text = text

    class _Client:
        def __init__(self, *a, **kw): self._calls = 0
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None):
            # First call: Jina 429. Second call: trafilatura's HTTP fetch.
            if "r.jina.ai" in url:
                return _Resp(429, "Too Many Requests")
            return _Resp(200, "<html><body><h1>Hello</h1><p>Body text — long enough.</p></body></html>")

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    monkeypatch.setattr(
        normalizer, "_trafilatura_extract",
        AsyncMock(return_value="# Hello\n\nBody text — long enough."),
    )
    out = asyncio.run(normalizer.fetch_clean_markdown("https://example.com/a"))
    assert out is not None
    assert "Hello" in out


# --- UX: GeekNews-style headline+toggle ----------------------------

def test_brief_page_uses_headline_card(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.storage import save_briefing
    save_briefing(
        "daily",
        "### 🔴 즉시 주목\n- BIG_HEADLINE_MARKER\n\n### 🎯 기회\n- opp1",
        signal_count=5,
    )
    client = TestClient(create_app())
    resp = client.get("/brief?cycle=daily")
    assert resp.status_code == 200
    assert "headline-card" in resp.text
    assert "BIG_HEADLINE_MARKER" in resp.text


def test_signals_page_uses_headline_card(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.demo_seed import seed_demo
    seed_demo(reset=True)
    client = TestClient(create_app())
    resp = client.get("/signals")
    assert resp.status_code == 200
    assert "headline-card" in resp.text


def test_v3_css_loaded_on_every_page(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/")
    assert "/static/v3.css" in resp.text


def test_v3_css_file_exists():
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "hedwig/dashboard/static/v3.css"
    assert p.exists()
    assert "headline-card" in p.read_text()


def test_chat_nav_link_present(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/")
    assert 'href="/chat"' in resp.text
