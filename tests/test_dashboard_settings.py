"""
AC-7: /settings persists source plugin toggles in local and SaaS modes.
"""
from __future__ import annotations

import json
import re
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


@pytest.fixture
def saas_app():
    from hedwig.dashboard.app import create_app

    return create_app(saas_mode=True)


def _extract_checkbox(html: str, plugin_id: str) -> str:
    pattern = (
        r'<input[^>]+type="checkbox"[^>]+name="enabled_sources"'
        rf'[^>]+value="{re.escape(plugin_id)}"[^>]*>'
    )
    match = re.search(pattern, html)
    assert match is not None, f"Missing checkbox for plugin {plugin_id}"
    return match.group(0)


def _build_fake_user_sources_client(state: list[dict]):
    class Result:
        def __init__(self, data):
            self.data = data

    class FakeTable:
        def __init__(self):
            self._select_fields: str | None = None
            self._eq_filters: list[tuple[str, object]] = []
            self._upsert_rows: list[dict] | None = None
            self._on_conflict = ""

        def select(self, fields: str):
            self._select_fields = fields
            return self

        def eq(self, field: str, value: object):
            self._eq_filters.append((field, value))
            return self

        def upsert(self, rows, on_conflict: str):
            self._upsert_rows = [dict(row) for row in rows]
            self._on_conflict = on_conflict
            return self

        def execute(self):
            if self._upsert_rows is not None:
                keys = tuple(
                    part.strip()
                    for part in self._on_conflict.split(",")
                    if part.strip()
                )
                for row in self._upsert_rows:
                    replaced = False
                    for index, existing in enumerate(state):
                        if all(existing.get(key) == row.get(key) for key in keys):
                            state[index] = dict(row)
                            replaced = True
                            break
                    if not replaced:
                        state.append(dict(row))
                return Result([dict(row) for row in self._upsert_rows])

            rows = [dict(row) for row in state]
            for field, value in self._eq_filters:
                rows = [row for row in rows if row.get(field) == value]

            if self._select_fields and self._select_fields != "*":
                columns = [
                    field.strip()
                    for field in self._select_fields.split(",")
                    if field.strip()
                ]
                rows = [
                    {field: row.get(field) for field in columns}
                    for row in rows
                ]
            return Result(rows)

    class FakeClient:
        def table(self, table_name: str):
            assert table_name == "user_sources"
            return FakeTable()

    return FakeClient()


@pytest.mark.asyncio
@pytest.mark.parametrize("saas_mode", [False, True])
async def test_settings_page_returns_200_in_single_user_and_authenticated_saas_modes(
    monkeypatch, tmp_path, saas_mode
):
    from hedwig.dashboard.app import create_app
    from hedwig.sources import settings as source_settings
    from hedwig.storage import supabase as supabase_mod
    from httpx import ASGITransport, AsyncClient

    app = create_app(saas_mode=saas_mode)

    if saas_mode:
        from hedwig.saas import auth as auth_mod

        async def fake_require_auth(request):
            return {"id": "user-123", "email": "user@example.com"}

        monkeypatch.setattr(auth_mod, "require_auth", fake_require_auth)
        monkeypatch.setattr(
            supabase_mod,
            "_get_client",
            lambda: _build_fake_user_sources_client([]),
        )
    else:
        monkeypatch.setattr(
            source_settings,
            "SOURCE_SETTINGS_PATH",
            tmp_path / "source_settings.json",
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/settings")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_settings_page_lists_registered_sources_and_saved_states(
    monkeypatch, tmp_path, single_user_app
):
    from hedwig.sources import get_registered_sources
    from hedwig.sources import settings as source_settings
    from httpx import ASGITransport, AsyncClient

    config_path = tmp_path / "source_settings.json"
    config_path.write_text(
        json.dumps(
            {
                "sources": {
                    "github_trending": True,
                    "arxiv": False,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", config_path)

    transport = ASGITransport(app=single_user_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/settings")

    assert resp.status_code == 200
    assert "Source Settings" in resp.text
    assert str(config_path) in resp.text
    assert "GitHub Trending" in resp.text
    assert "arXiv" in resp.text
    # v3 added arxiv_recsys (self-referential paper monitor) and podcast → 19
    assert len(get_registered_sources()) == 19
    assert resp.text.count('name="enabled_sources"') == 19
    for plugin_id in get_registered_sources():
        _extract_checkbox(resp.text, plugin_id)
    assert "checked" in _extract_checkbox(resp.text, "github_trending")
    assert "checked" not in _extract_checkbox(resp.text, "arxiv")


@pytest.mark.asyncio
async def test_settings_save_writes_local_source_toggle_config(
    monkeypatch, tmp_path, single_user_app
):
    from hedwig.sources import settings as source_settings
    from httpx import ASGITransport, AsyncClient

    config_path = tmp_path / "source_settings.json"
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", config_path)

    transport = ASGITransport(app=single_user_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/settings/save",
            data={"enabled_sources": ["github_trending", "youtube"]},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings?saved=1"

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["sources"]["github_trending"] is True
    assert saved["sources"]["youtube"] is True
    assert saved["sources"]["arxiv"] is False
    assert all(isinstance(value, bool) for value in saved["sources"].values())


@pytest.mark.asyncio
async def test_settings_routes_require_auth_in_saas_mode(saas_app):
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        get_resp = await client.get("/settings")
        post_resp = await client.post("/settings/save", data={})

    assert get_resp.status_code == 401
    assert get_resp.json() == {"detail": "Authentication required"}
    assert post_resp.status_code == 401
    assert post_resp.json() == {"detail": "Authentication required"}


@pytest.mark.asyncio
async def test_settings_page_loads_authenticated_saas_user_source_preferences(
    monkeypatch, saas_app
):
    from hedwig.saas import auth as auth_mod
    from hedwig.storage import supabase as supabase_mod
    from httpx import ASGITransport, AsyncClient

    state = [
        {"user_id": "user-123", "plugin_id": "github_trending", "enabled": False},
        {"user_id": "user-123", "plugin_id": "youtube", "enabled": True},
        {"user_id": "user-999", "plugin_id": "arxiv", "enabled": False},
    ]

    async def fake_require_auth(request):
        return {"id": "user-123", "email": "user@example.com"}

    monkeypatch.setattr(auth_mod, "require_auth", fake_require_auth)
    monkeypatch.setattr(
        supabase_mod,
        "_get_client",
        lambda: _build_fake_user_sources_client(state),
    )

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/settings")

    assert resp.status_code == 200
    assert "Saved to your SaaS account via Supabase." in resp.text
    assert "checked" not in _extract_checkbox(resp.text, "github_trending")
    assert "checked" in _extract_checkbox(resp.text, "youtube")
    assert "checked" in _extract_checkbox(resp.text, "arxiv")


@pytest.mark.asyncio
async def test_settings_save_persists_authenticated_saas_user_source_preferences(
    monkeypatch, saas_app
):
    from hedwig.saas import auth as auth_mod
    from hedwig.sources import get_registered_sources
    from hedwig.storage import supabase as supabase_mod
    from httpx import ASGITransport, AsyncClient

    state = [
        {"user_id": "user-999", "plugin_id": "arxiv", "enabled": False},
    ]

    async def fake_require_auth(request):
        return {"id": "user-123", "email": "user@example.com"}

    monkeypatch.setattr(auth_mod, "require_auth", fake_require_auth)
    monkeypatch.setattr(
        supabase_mod,
        "_get_client",
        lambda: _build_fake_user_sources_client(state),
    )

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/settings/save",
            data={"enabled_sources": ["github_trending", "youtube"]},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings?saved=1"

    registry = get_registered_sources()
    user_rows = [row for row in state if row["user_id"] == "user-123"]
    # v3 added arxiv_recsys + podcast → 19
    assert len(registry) == 19
    assert len(user_rows) == 19
    enabled_by_plugin = {
        row["plugin_id"]: row["enabled"]
        for row in user_rows
    }
    assert enabled_by_plugin["github_trending"] is True
    assert enabled_by_plugin["youtube"] is True
    assert enabled_by_plugin["arxiv"] is False
    assert all(isinstance(value, bool) for value in enabled_by_plugin.values())
    assert any(row["user_id"] == "user-999" for row in state)


@pytest.mark.asyncio
async def test_agent_collector_strategy_uses_only_enabled_sources(monkeypatch):
    from hedwig.engine.agent_collector import AgentCollector
    from hedwig.sources import settings as source_settings

    monkeypatch.setattr(
        source_settings,
        "filter_registered_sources",
        lambda: {
            "github_trending": object(),
            "youtube": object(),
        },
    )

    collector = AgentCollector(llm_client=None)
    strategy = await collector.generate_strategy()

    assert strategy["priority_sources"] == ["github_trending", "youtube"]
    assert strategy["source_configs"] == {
        "github_trending": {"limit": 30},
        "youtube": {"limit": 30},
    }
