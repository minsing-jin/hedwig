from __future__ import annotations

import sys
import types

import pytest


def test_check_latest_version_detects_newer_github_release(monkeypatch):
    from hedwig.native import updater

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"tag_name": "v99.0.0"}

    def fake_get(url: str, *, headers: dict[str, str], timeout: float):
        assert url == updater.GITHUB_LATEST_RELEASE_URL
        assert headers["Accept"] == "application/vnd.github+json"
        assert timeout == updater.REQUEST_TIMEOUT_SECONDS
        return _FakeResponse()

    monkeypatch.setattr(updater, "resolve_current_version", lambda: "3.0.0")
    monkeypatch.setattr(updater.httpx, "get", fake_get)

    current_version, latest_version, is_update_available = updater.check_latest_version()

    assert current_version == "3.0.0"
    assert latest_version == "99.0.0"
    assert is_update_available is True


def test_run_native_checks_for_updates_without_pywebview_icon_kwarg(monkeypatch):
    from hedwig.native import app as native_app

    calls: dict[str, object] = {}

    class _FakeThread:
        def __init__(self, *, target, args, daemon):
            calls["thread_target"] = target
            calls["thread_args"] = args
            calls["thread_daemon"] = daemon

        def start(self):
            calls["thread_started"] = True

    def fake_create_window(*args, **kwargs):
        calls["window_args"] = args
        calls["window"] = kwargs
        return object()

    def fake_start(**kwargs):
        calls["start"] = kwargs

    fake_webview = types.SimpleNamespace(
        create_window=fake_create_window,
        start=fake_start,
    )

    class _FakeHTTPResponse:
        status_code = 200

    monkeypatch.setattr(native_app.threading, "Thread", _FakeThread)
    monkeypatch.setattr(native_app.httpx, "get", lambda *args, **kwargs: _FakeHTTPResponse())
    monkeypatch.setattr(native_app, "_apply_macos_app_icon", lambda icon_path: calls.setdefault("icon_path", icon_path))
    monkeypatch.setattr(
        native_app,
        "_start_update_check",
        lambda notify_update=None: calls.setdefault("update_notifier", notify_update),
    )
    monkeypatch.setitem(sys.modules, "webview", fake_webview)

    native_app.run_native(width=1024, height=640)

    assert calls["thread_target"] is native_app._run_server
    assert calls["thread_args"] == (native_app.DEFAULT_HOST, native_app.DEFAULT_PORT)
    assert calls["thread_daemon"] is True
    assert calls["thread_started"] is True
    assert calls["window_args"] == ()
    assert calls["window"]["width"] == 1024
    assert calls["window"]["height"] == 640
    assert calls["icon_path"] == native_app.NATIVE_ICON_PATH
    assert calls["update_notifier"] is None
    assert calls["start"]["debug"] is False
    assert "icon" not in calls["start"]
    assert native_app.get_native_icon_path() == native_app.NATIVE_ICON_PATH


def test_apply_macos_app_icon_uses_appkit(monkeypatch):
    from hedwig.native import app as native_app

    calls: dict[str, object] = {}

    class _FakeImage:
        def initWithContentsOfFile_(self, path: str):
            calls["image_path"] = path
            return "image-object"

    class _FakeNSImage:
        @staticmethod
        def alloc():
            return _FakeImage()

    class _FakeApplication:
        def setApplicationIconImage_(self, image: object):
            calls["image"] = image

    fake_application = _FakeApplication()
    fake_appkit = types.SimpleNamespace(
        NSImage=_FakeNSImage,
        NSApplication=types.SimpleNamespace(sharedApplication=lambda: fake_application),
    )

    monkeypatch.setattr(native_app.sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "AppKit", fake_appkit)

    native_app._apply_macos_app_icon(native_app.NATIVE_ICON_PATH)

    assert calls["image_path"] == str(native_app.NATIVE_ICON_PATH)
    assert calls["image"] == "image-object"


@pytest.mark.asyncio
async def test_dashboard_serves_native_icon_asset():
    from hedwig.dashboard.app import create_app
    from httpx import ASGITransport, AsyncClient

    app = create_app(saas_mode=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        setup_response = await client.get("/setup")
        asset_response = await client.get("/assets/hedwig-icon.svg")

    assert setup_response.status_code == 200
    assert '/assets/hedwig-icon.svg' in setup_response.text
    assert asset_response.status_code == 200
    assert "<svg" in asset_response.text
