"""Robustness tests for chat (force-summary) + save_feedback signature."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    import hedwig.config as _cfg
    _cfg._ALGORITHM_VERSION_SEEDED = False
    yield tmp_path


# --- save_feedback signature defense -------------------------------

def test_save_feedback_absorbs_unknown_kwargs(tmp_env):
    """**_kwargs absorption — even a future kwarg won't TypeError."""
    from hedwig.feedback import FeedbackCollector
    from hedwig.models import VoteType
    from hedwig.storage import save_feedback
    fb = FeedbackCollector().from_direct(signal_id="x", vote=VoteType.UP)
    # These all must work without raising
    assert save_feedback(fb) is True
    assert save_feedback(fb, user_id=None) is True
    assert save_feedback(fb, user_id="x") is True
    # Future signature drift simulation:
    assert save_feedback(fb, user_id="x", tenant_id="future") is True
    assert save_feedback(fb, future_kwarg=42) is True


def test_feedback_endpoint_works_when_user_id_is_none(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.demo_seed import seed_demo
    seed_demo(reset=True)
    client = TestClient(create_app())
    resp = client.post("/feedback/demo-0/up")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# --- Chat force summary on empty content --------------------------

def test_chat_forces_summary_when_assistant_empty(tmp_env, monkeypatch):
    """If the LLM returns empty content after tool calls, the router must
    issue one extra summarization request rather than persisting nothing."""
    from hedwig.chat import router as router_mod

    # Build a fake AsyncOpenAI client where chat.completions.create returns:
    #   1st call → tool_calls + empty content
    #   2nd call (force-summary) → natural text
    call_count = {"n": 0}

    class _ToolFunc:
        def __init__(self):
            self.name = "get_status"
            self.arguments = "{}"

    class _ToolCall:
        def __init__(self):
            self.id = "tc-1"
            self.function = _ToolFunc()

    class _Msg:
        def __init__(self, content="", tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls

    class _Choice:
        def __init__(self, msg):
            self.message = msg

    class _Resp:
        def __init__(self, choices):
            self.choices = choices

    async def _fake_create(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # Tool call with empty content
            return _Resp([_Choice(_Msg(content="", tool_calls=[_ToolCall()]))])
        if call_count["n"] == 2:
            # Loop iteration 2: empty content (no tool calls) — triggers
            # the force-summary path
            return _Resp([_Choice(_Msg(content="", tool_calls=None))])
        # Force-summary call
        return _Resp([_Choice(_Msg(
            content="✅ exit_conditions 4개 모두 진행 중입니다.",
            tool_calls=None,
        ))])

    fake_client = MagicMock()
    fake_client.chat.completions.create = _fake_create

    class _FakeAsyncOpenAI:
        def __init__(self, *a, **kw): pass
        def __new__(cls, *a, **kw):
            return fake_client

    # Patch the symbol the router imports
    import openai
    monkeypatch.setattr(openai, "AsyncOpenAI", _FakeAsyncOpenAI)
    monkeypatch.setattr(router_mod, "OPENAI_API_KEY", "sk-fake")

    result = asyncio.run(router_mod.handle_user_message("conv-test", "상태 알려줘"))
    answer = result["answer"]
    assert answer
    # Force-summary message should have surfaced
    assert "exit_conditions" in answer or "진행" in answer


def test_chat_router_no_key_returns_korean_message(tmp_env, monkeypatch):
    from hedwig.chat import router as router_mod
    monkeypatch.setattr(router_mod, "OPENAI_API_KEY", "")
    result = asyncio.run(router_mod.handle_user_message("conv-test", "hi"))
    assert "OpenAI API" in result["answer"]


# --- Parallel collection sanity --------------------------------

def test_collect_all_uses_asyncio_gather():
    """The actual function we tell the user is parallel must use gather."""
    from pathlib import Path
    body = (Path(__file__).resolve().parents[1] / "hedwig/main.py").read_text()
    assert "async def collect_all" in body
    # confirm asyncio.gather is reached within collect_all body (~80 lines)
    start = body.index("async def collect_all")
    snippet = body[start:start + 2500]
    assert "asyncio.gather" in snippet


def test_agent_collector_uses_asyncio_gather():
    """The agent-driven collection path is also parallel."""
    from pathlib import Path
    body = (Path(__file__).resolve().parents[1]
             / "hedwig/engine/agent_collector.py").read_text()
    assert "asyncio.gather" in body
