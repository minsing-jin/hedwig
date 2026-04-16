"""
Integration test — verify all hedwig.dashboard modules import successfully.

This test ensures every module in hedwig/dashboard/ can be imported without
errors, validating that dependencies are available and no circular imports
exist.
"""
from __future__ import annotations

import importlib
import pkgutil
import types

import pytest


DASHBOARD_PACKAGE = "hedwig.dashboard"

# Explicitly list every module so the test fails loudly if one is removed or
# renamed without updating the suite.
EXPECTED_MODULES = [
    "hedwig.dashboard",
    "hedwig.dashboard.app",
    "hedwig.dashboard.db_setup",
    "hedwig.dashboard.env_manager",
    "hedwig.dashboard.generative",
    "hedwig.dashboard.validator",
]


class TestDashboardImports:
    """All hedwig.dashboard modules must import without error."""

    @pytest.mark.parametrize("module_name", EXPECTED_MODULES)
    def test_module_imports(self, module_name: str):
        """Each module should import successfully."""
        mod = importlib.import_module(module_name)
        assert isinstance(mod, types.ModuleType), f"{module_name} is not a module"

    def test_expected_modules_complete(self):
        """Ensure EXPECTED_MODULES covers every .py file in hedwig/dashboard/."""
        dashboard = importlib.import_module(DASHBOARD_PACKAGE)
        discovered: set[str] = {DASHBOARD_PACKAGE}

        for importer, modname, ispkg in pkgutil.walk_packages(
            path=dashboard.__path__,
            prefix=f"{DASHBOARD_PACKAGE}.",
        ):
            discovered.add(modname)

        expected_set = set(EXPECTED_MODULES)
        missing = discovered - expected_set
        assert not missing, (
            f"Modules discovered but not in EXPECTED_MODULES: {missing}. "
            "Add them to EXPECTED_MODULES so they are tested."
        )

    # ------------------------------------------------------------------
    # Smoke-test key exports from each module
    # ------------------------------------------------------------------

    def test_app_exports(self):
        """hedwig.dashboard.app exposes create_app and run."""
        from hedwig.dashboard.app import create_app, run

        assert callable(create_app)
        assert callable(run)

    def test_init_reexports(self):
        """hedwig.dashboard re-exports create_app and run from app."""
        from hedwig.dashboard import create_app, run

        assert callable(create_app)
        assert callable(run)

    def test_env_manager_exports(self):
        """hedwig.dashboard.env_manager exposes EnvManager class."""
        from hedwig.dashboard.env_manager import EnvManager

        assert hasattr(EnvManager, "REQUIRED_KEYS")
        assert hasattr(EnvManager, "DELIVERY_KEYS")
        assert hasattr(EnvManager, "OPTIONAL_KEYS")
        assert callable(EnvManager.all_key_metadata)

    def test_validator_exports(self):
        """hedwig.dashboard.validator exposes async test functions."""
        from hedwig.dashboard.validator import (
            test_all,
            test_discord_webhook,
            test_openai,
            test_slack_webhook,
            test_supabase,
        )

        import asyncio

        for fn in (test_openai, test_supabase, test_slack_webhook,
                    test_discord_webhook, test_all):
            assert callable(fn)
            assert asyncio.iscoroutinefunction(fn), f"{fn.__name__} should be async"

    def test_db_setup_exports(self):
        """hedwig.dashboard.db_setup exposes create_tables and get_schema_sql."""
        from hedwig.dashboard.db_setup import create_tables, get_schema_sql

        import asyncio

        assert asyncio.iscoroutinefunction(create_tables)
        assert callable(get_schema_sql)

    # ------------------------------------------------------------------
    # Functional smoke tests (no network, no real credentials)
    # ------------------------------------------------------------------

    def test_env_manager_load_missing_file(self, tmp_path):
        """EnvManager.load() returns {} when .env does not exist."""
        from hedwig.dashboard.env_manager import EnvManager

        mgr = EnvManager(env_path=tmp_path / ".env")
        assert mgr.load() == {}

    def test_env_manager_save_and_load(self, tmp_path):
        """EnvManager round-trips save/load correctly."""
        from hedwig.dashboard.env_manager import EnvManager

        mgr = EnvManager(env_path=tmp_path / ".env")
        mgr.save({"OPENAI_API_KEY": "sk-test123", "SUPABASE_URL": "https://x.supabase.co"})
        loaded = mgr.load()
        assert loaded["OPENAI_API_KEY"] == "sk-test123"
        assert loaded["SUPABASE_URL"] == "https://x.supabase.co"

    def test_env_manager_get_status_not_ready(self, tmp_path):
        """Status shows not ready when required keys are missing."""
        from hedwig.dashboard.env_manager import EnvManager

        mgr = EnvManager(env_path=tmp_path / ".env")
        status = mgr.get_status()
        assert status["ready"] is False
        assert status["required_ok"] is False

    def test_get_schema_sql_returns_string(self):
        """get_schema_sql() returns a non-empty SQL string."""
        from hedwig.dashboard.db_setup import get_schema_sql

        sql = get_schema_sql()
        assert isinstance(sql, str)
        assert len(sql) > 0

    def test_create_app_returns_fastapi(self):
        """create_app() returns a FastAPI instance."""
        from fastapi import FastAPI

        from hedwig.dashboard.app import create_app

        app = create_app(saas_mode=False)
        assert isinstance(app, FastAPI)

    def test_create_app_saas_mode(self):
        """create_app(saas_mode=True) returns a FastAPI with SaaS routes."""
        from fastapi import FastAPI

        from hedwig.dashboard.app import create_app

        app = create_app(saas_mode=True)
        assert isinstance(app, FastAPI)
        # SaaS mode should register additional routes
        route_paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/landing" in route_paths
        assert "/signup" in route_paths
        assert "/login" in route_paths
        assert "/auth/signup" in route_paths
        assert "/billing/checkout" in route_paths
