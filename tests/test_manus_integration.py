from __future__ import annotations

import json

import httpx
import pytest


def test_manus_config_defaults_disabled(monkeypatch):
    for key in (
        "HEDWIG_MANUS_ENABLED",
        "MANUS_API_KEY",
        "MANUS_API_BASE_URL",
        "MANUS_AGENT_PROFILE",
        "MANUS_PROJECT_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    from hedwig.integrations.manus import ManusConfig
    cfg = ManusConfig.from_env()

    assert cfg.ready is False
    assert "disabled" in (cfg.readiness_error() or "")
    assert cfg.base_url == "https://api.manus.ai"


@pytest.mark.asyncio
async def test_manus_client_create_task_uses_v2_headers_and_payload():
    from hedwig.integrations.manus import ManusClient, ManusConfig

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"id": "task_123", "status": "created"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        cfg = ManusConfig(
            enabled=True,
            api_key="manus_test_key",
            base_url="https://api.manus.ai",
            agent_profile="manus-1.6",
            project_id="proj_1",
        )
        client = ManusClient(config=cfg, http_client=http_client)
        result = await client.create_task("Research this", title="Hedwig task")

    assert result["ok"] is True
    assert captured["url"] == "https://api.manus.ai/v2/task.create"
    assert captured["headers"]["x-manus-api-key"] == "manus_test_key"
    assert captured["payload"]["message"]["content"] == [{"type": "text", "text": "Research this"}]
    assert captured["payload"]["title"] == "Hedwig task"
    assert captured["payload"]["agent_profile"] == "manus-1.6"
    assert captured["payload"]["project_id"] == "proj_1"


@pytest.mark.asyncio
async def test_manus_client_list_messages_uses_v2_method_endpoint():
    from hedwig.integrations.manus import ManusClient, ManusConfig

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"messages": [{"type": "text", "text": "done"}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        cfg = ManusConfig(enabled=True, api_key="manus_test_key")
        client = ManusClient(config=cfg, http_client=http_client)
        result = await client.list_messages("task_123", limit=3)

    assert result["ok"] is True
    assert captured["url"] == (
        "https://api.manus.ai/v2/task.listMessages?task_id=task_123&limit=3&order=desc"
    )
    assert captured["headers"]["x-manus-api-key"] == "manus_test_key"


def test_available_tools_hide_manus_until_enabled(monkeypatch):
    monkeypatch.delenv("HEDWIG_MANUS_ENABLED", raising=False)
    monkeypatch.delenv("MANUS_API_KEY", raising=False)
    from hedwig.chat.tools import available_tool_schemas

    names = {s["function"]["name"] for s in available_tool_schemas()}
    assert "delegate_to_manus" not in names

    monkeypatch.setenv("HEDWIG_MANUS_ENABLED", "1")
    monkeypatch.setenv("MANUS_API_KEY", "manus_test_key")
    names = {s["function"]["name"] for s in available_tool_schemas()}
    assert "delegate_to_manus" in names


@pytest.mark.asyncio
async def test_delegate_to_manus_requires_advanced_enable(monkeypatch):
    monkeypatch.delenv("HEDWIG_MANUS_ENABLED", raising=False)
    monkeypatch.delenv("MANUS_API_KEY", raising=False)

    from hedwig.chat.tools import call_tool
    result = await call_tool("delegate_to_manus", {"prompt": "do this"})

    assert result["ok"] is False
    assert "disabled" in result["error"]


def test_setup_exposes_manus_advanced_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.chdir(tmp_path)

    from fastapi.testclient import TestClient
    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    assert "HEDWIG_MANUS_ENABLED" in resp.text
    assert "MANUS_API_KEY" in resp.text
    assert "Optional" in resp.text and "Advanced Keys" in resp.text
