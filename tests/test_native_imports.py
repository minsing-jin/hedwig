"""Integration tests for hedwig.native — verify all modules import and expose expected APIs."""
from __future__ import annotations

import importlib
import types


# ---------------------------------------------------------------------------
# Module import tests
# ---------------------------------------------------------------------------

def test_import_native_package():
    """hedwig.native package imports without error."""
    import hedwig.native
    assert isinstance(hedwig.native, types.ModuleType)


def test_import_native_app():
    """hedwig.native.app module imports without error."""
    import hedwig.native.app
    assert isinstance(hedwig.native.app, types.ModuleType)


def test_import_native_tray():
    """hedwig.native.tray module imports without error."""
    import hedwig.native.tray
    assert isinstance(hedwig.native.tray, types.ModuleType)


# ---------------------------------------------------------------------------
# Public API surface tests
# ---------------------------------------------------------------------------

def test_native_package_exports_run_native():
    """hedwig.native re-exports run_native from hedwig.native.app."""
    from hedwig.native import run_native
    assert callable(run_native)


def test_native_app_run_native_callable():
    """hedwig.native.app.run_native is a callable function."""
    from hedwig.native.app import run_native
    assert callable(run_native)


def test_native_app_run_server_callable():
    """hedwig.native.app._run_server helper is available."""
    from hedwig.native.app import _run_server
    assert callable(_run_server)


def test_native_tray_run_tray_callable():
    """hedwig.native.tray.run_tray is a callable function."""
    from hedwig.native.tray import run_tray
    assert callable(run_tray)


# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------

def test_native_app_defaults():
    """hedwig.native.app exposes sensible defaults for host/port."""
    from hedwig.native.app import DEFAULT_PORT, DEFAULT_HOST
    assert isinstance(DEFAULT_PORT, int)
    assert DEFAULT_PORT > 0
    assert isinstance(DEFAULT_HOST, str)
    assert DEFAULT_HOST  # non-empty


# ---------------------------------------------------------------------------
# Exhaustive module reload test
# ---------------------------------------------------------------------------

NATIVE_MODULES = [
    "hedwig.native",
    "hedwig.native.app",
    "hedwig.native.tray",
]


def test_all_native_modules_reimport():
    """Every module in hedwig/native can be freshly reloaded without error."""
    for mod_name in NATIVE_MODULES:
        mod = importlib.import_module(mod_name)
        reloaded = importlib.reload(mod)
        assert isinstance(reloaded, types.ModuleType), f"Reload failed for {mod_name}"
