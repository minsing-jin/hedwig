"""
Integration test — verify all hedwig.dashboard modules import successfully.

This test ensures every module in hedwig/dashboard/ can be imported without
errors, validating that dependencies are available and no circular imports
exist.
"""
from __future__ import annotations

import importlib
import os
import pkgutil
import stat
import types

import pytest


DASHBOARD_PACKAGE = "hedwig.dashboard"

# Explicitly list every module so the test fails loudly if one is removed or
# renamed without updating the suite.
EXPECTED_MODULES = [
    "hedwig.dashboard",
    "hedwig.dashboard.app",
    "hedwig.dashboard.db_setup",
    "hedwig.dashboard.demo_seed",
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
        """EnvManager.load() defaults first-run setup to local SQLite and safe models."""
        from hedwig.dashboard.env_manager import EnvManager

        mgr = EnvManager(env_path=tmp_path / ".env")
        assert mgr.load() == {
            "HEDWIG_STORAGE": "sqlite",
            **EnvManager.MODEL_BACKEND_DEFAULTS,
        }

    def test_env_manager_save_and_load(self, tmp_path):
        """EnvManager round-trips save/load correctly."""
        from hedwig.dashboard.env_manager import EnvManager

        mgr = EnvManager(env_path=tmp_path / ".env")
        mgr.save({"OPENAI_API_KEY": "sk-test123", "SUPABASE_URL": "https://x.supabase.co"})
        loaded = mgr.load()
        assert loaded["OPENAI_API_KEY"] == "sk-test123"
        assert loaded["SUPABASE_URL"] == "https://x.supabase.co"
        assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600

    def test_env_manager_save_tightens_existing_env_file_permissions(self, tmp_path):
        """Saving local secrets should restrict a pre-existing permissive .env."""
        from hedwig.dashboard.env_manager import EnvManager

        env_path = tmp_path / ".env"
        env_path.write_text("OPENAI_API_KEY=sk-old\n", encoding="utf-8")
        env_path.chmod(0o644)

        mgr = EnvManager(env_path=env_path)
        mgr.save({"OPENAI_API_KEY": "sk-new"})

        assert stat.S_IMODE(env_path.stat().st_mode) == 0o600

    def test_env_manager_save_openai_local_setup_uses_managed_env_file(self, tmp_path):
        """One-shot setup writes the OpenAI key through EnvManager's .env path."""
        from hedwig.dashboard.env_manager import EnvManager

        mgr = EnvManager(env_path=tmp_path / ".env")
        payload = mgr.save_openai_local_setup(
            "sk-local-setup",
            values={
                "SUPABASE_URL": "https://stale.supabase.co",
                "SUPABASE_KEY": "stale-key",
            },
        )

        loaded = mgr.load()
        assert payload["OPENAI_API_KEY"] == "sk-local-setup"
        assert payload["HEDWIG_STORAGE"] == "sqlite"
        assert loaded["OPENAI_API_KEY"] == "sk-local-setup"
        assert loaded["HEDWIG_STORAGE"] == "sqlite"
        assert loaded["SUPABASE_URL"] == ""
        assert loaded["SUPABASE_KEY"] == ""
        assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600

    def test_config_refresh_reads_persisted_openai_key_without_process_env(
        self, tmp_path, monkeypatch
    ):
        """First-feed runtime config can use setup's .env key without os.environ."""
        from hedwig import config as hedwig_config
        from hedwig.dashboard.env_manager import EnvManager

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(hedwig_config, "OPENAI_API_KEY", "")
        EnvManager(env_path=tmp_path / ".env").save_openai_local_setup(
            "sk-persisted-feed"
        )

        refreshed = hedwig_config.refresh_runtime_config(
            tmp_path / ".env",
            prefer_persisted=True,
        )

        assert refreshed["OPENAI_API_KEY"] == "sk-persisted-feed"
        assert hedwig_config.OPENAI_API_KEY == "sk-persisted-feed"
        assert os.getenv("OPENAI_API_KEY") is None
        assert hedwig_config.check_required_keys("daily") == []

    def test_env_manager_redacts_secret_values_for_templates(self, tmp_path):
        """Template display values should not expose saved API keys."""
        from hedwig.dashboard.env_manager import EnvManager

        mgr = EnvManager(env_path=tmp_path / ".env")
        mgr.save(
            {
                "OPENAI_API_KEY": "sk-local-setup",
                "HEDWIG_STORAGE": "sqlite",
                "OPENAI_MODEL_FAST": "gpt-4o-mini",
            }
        )

        display_values = EnvManager.redact_secret_values(mgr.load())

        assert display_values["OPENAI_API_KEY"] == ""
        assert display_values["HEDWIG_STORAGE"] == "sqlite"
        assert display_values["OPENAI_MODEL_FAST"] == "gpt-4o-mini"

    def test_setup_page_does_not_render_persisted_openai_key(
        self, tmp_path, monkeypatch
    ):
        """The one-shot setup page must not echo a saved API key into HTML."""
        from fastapi.testclient import TestClient

        from hedwig.dashboard.app import create_app
        from hedwig.dashboard.env_manager import EnvManager

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
        EnvManager(env_path=tmp_path / ".env").save_openai_local_setup(
            "sk-render-secret"
        )

        resp = TestClient(create_app()).get("/setup")

        assert resp.status_code == 200
        assert "sk-render-secret" not in resp.text
        assert 'id="OPENAI_API_KEY"' in resp.text
        assert 'data-secret="true"' in resp.text

    def test_env_manager_get_status_not_ready(self, tmp_path):
        """Status shows not ready when required keys are missing."""
        from hedwig.dashboard.env_manager import EnvManager

        mgr = EnvManager(env_path=tmp_path / ".env")
        status = mgr.get_status()
        assert status["ready"] is False
        assert status["required_ok"] is False

    def test_env_manager_get_status_local_sqlite_does_not_require_supabase(self, tmp_path):
        """OpenAI-only local SQLite setup is ready without Supabase variables."""
        from hedwig.dashboard.env_manager import EnvManager

        mgr = EnvManager(env_path=tmp_path / ".env")
        mgr.save({"OPENAI_API_KEY": "sk-local", "HEDWIG_STORAGE": "sqlite"})

        status = mgr.get_status()

        assert status["ready"] is True
        assert status["required_ok"] is True
        assert status["delivery_ok"] is True
        assert status["storage_mode"] == "sqlite"
        assert status["supabase_required"] is False
        assert status["supabase_required_keys"] == []
        assert status["missing_required_keys"] == []

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
