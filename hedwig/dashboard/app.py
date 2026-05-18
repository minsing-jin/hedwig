"""
Hedwig Dashboard — FastAPI web UI for setup, feedback, and monitoring.

Run with:
    python -m hedwig dashboard
    # or
    python -m hedwig.dashboard.app
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from hedwig.dashboard.db_setup import (
    create_tables,
    ensure_local_sqlite_schema,
    get_schema_sql,
)
from hedwig.dashboard.env_manager import EnvManager
from hedwig.dashboard.generative import GenerativeDashboard
from hedwig.dashboard.validator import test_all

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parents[1]
ASSETS_DIR = REPO_ROOT / "assets"
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_VALID_PIPELINES = {"single", "ensemble"}
_VALID_DISABLE_EMBEDDINGS = {"0", "1"}


def _model_backend_values(form) -> tuple[dict[str, str], dict[str, str]]:
    """Normalize and validate model/backend form values shared by setup/settings."""
    values: dict[str, str] = {}
    errors: dict[str, str] = {}
    for key in EnvManager.MODEL_BACKEND_KEYS:
        raw_value = str(form.get(key, "")).strip()
        if not raw_value:
            raw_value = EnvManager.MODEL_BACKEND_DEFAULTS.get(key, "")
        if key == "HEDWIG_PIPELINE":
            raw_value = raw_value.lower()
            if raw_value not in _VALID_PIPELINES:
                errors[key] = "Use single or ensemble."
                continue
        if (
            key == "HEDWIG_DISABLE_EMBEDDINGS"
            and raw_value not in _VALID_DISABLE_EMBEDDINGS
        ):
            errors[key] = "Use 0 or 1."
            continue
        values[key] = raw_value
    return values, errors


def _apply_model_backend_values(values: dict[str, str]) -> None:
    """Make saved model/backend settings visible to the current dashboard process."""
    if not values:
        return
    from hedwig import config as hedwig_config

    for key, value in values.items():
        os.environ[key] = value
        if hasattr(hedwig_config, key):
            setattr(hedwig_config, key, value)


def _openai_api_key_validation_error(openai_key: str) -> str | None:
    """Return a local validation error for setup keys without network calls."""
    if not openai_key:
        return "OPENAI_API_KEY is required before first-run setup can be enabled."
    if not openai_key.startswith("sk-"):
        return "OPENAI_API_KEY must start with sk-."
    return None


def _save_model_backend_settings(env_manager: EnvManager, form) -> dict:
    values, errors = _model_backend_values(form)
    if errors:
        return {"ok": False, "errors": errors, "values": values}
    env_manager.save(values)
    _apply_model_backend_values(values)
    return {"ok": True, "errors": {}, "values": values}


def _start_daily_collection_run(env: dict[str, str] | None = None) -> subprocess.Popen:
    """Start the existing daily collection command in the background."""
    return subprocess.Popen(
        [sys.executable, "-m", "hedwig"],
        cwd=str(Path.cwd()),
        env=env,
    )


def _refresh_config_from_managed_env(
    env_manager: EnvManager,
    *,
    prefer_persisted: bool = True,
) -> dict[str, str]:
    """Reload hedwig.config globals from the dashboard-managed .env."""
    from hedwig import config as hedwig_config

    return hedwig_config.refresh_runtime_config(
        env_manager.env_path,
        prefer_persisted=prefer_persisted,
    )


def create_app(saas_mode: bool = False) -> FastAPI:
    """Create the FastAPI app.

    Args:
        saas_mode: If True, enables multi-tenant routes (landing, auth, billing).
                   If False, single-user mode (original dashboard).
    """
    app = FastAPI(title="Hedwig Dashboard", version="3.0.0")
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    if ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

    env_manager = EnvManager(env_path=Path.cwd() / ".env")
    _refresh_config_from_managed_env(env_manager)
    app.state.saas_mode = saas_mode
    app.state.started_at = _utcnow()

    # -----------------------------------------------------------------------
    # Home / Status
    # -----------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        status = env_manager.get_status()
        if not status["ready"]:
            return RedirectResponse(url="/setup", status_code=303)

        # Load recent signals, feedback, evolution
        recent_signals = _load_recent_signals(limit=20)
        recent_evolution = _load_recent_evolution(limit=5)
        criteria = _load_criteria()
        source_count = _count_sources()

        return TEMPLATES.TemplateResponse(
            request,
            "home.html",
            {
                "status": status,
                "recent_signals": recent_signals,
                "recent_evolution": recent_evolution,
                "criteria": criteria,
                "source_count": source_count,
            },
        )

    # -----------------------------------------------------------------------
    # Setup wizard
    # -----------------------------------------------------------------------

    @app.get("/setup", response_class=HTMLResponse)
    async def setup_get(request: Request):
        values = env_manager.load()
        values.setdefault("HEDWIG_STORAGE", "sqlite")
        display_values = EnvManager.redact_secret_values(values)
        source_preset_context = _setup_source_preset_context()
        setup_defaults = _one_shot_setup_defaults()
        first_feed_config = _first_feed_app_config()
        metadata = EnvManager.all_key_metadata()
        status = env_manager.get_status()
        return TEMPLATES.TemplateResponse(
            request,
            "setup.html",
            {
                "values": display_values,
                "metadata": metadata,
                "required_keys": EnvManager.REQUIRED_KEYS,
                "storage_keys": EnvManager.STORAGE_KEYS,
                "delivery_keys": EnvManager.DELIVERY_KEYS,
                "optional_keys": EnvManager.OPTIONAL_KEYS,
                "model_backend_keys": EnvManager.MODEL_BACKEND_KEYS,
                "status": status,
                "setup_state": _one_shot_setup_state(env_manager),
                "setup_defaults": setup_defaults,
                "first_feed_config": first_feed_config,
                "setup_default_interest": setup_defaults["interest_text"],
                "source_presets": source_preset_context["presets"],
                "default_source_preset": source_preset_context["default_preset"],
                "setup_source_toggles": source_preset_context["source_toggles"],
                "setup_source_settings_path": source_preset_context[
                    "source_settings_path"
                ],
                "setup_option_location_map": _setup_option_location_map(),
            },
        )

    @app.post("/setup/save")
    async def setup_save(request: Request):
        form = await request.form()
        values = {k: v for k, v in form.items() if v}
        env_manager.save(values)
        return JSONResponse({"ok": True, "message": "Saved to .env"})

    @app.post("/setup/required/save")
    async def setup_required_save(request: Request):
        """Persist the minimum required onboarding inputs before first run."""
        form = await request.form()
        openai_key = str(form.get("OPENAI_API_KEY", "")).strip()
        openai_key_error = _openai_api_key_validation_error(openai_key)
        if openai_key_error:
            return JSONResponse(
                {
                    "ok": False,
                    "error": openai_key_error,
                    "state": _one_shot_setup_state(env_manager),
                },
                status_code=400,
            )

        setup_defaults = _one_shot_setup_defaults()
        env_manager.save_openai_local_setup(
            openai_key,
            model_backend_values=setup_defaults["model_backend"],
        )
        _refresh_config_from_managed_env(env_manager)

        # Reflect the saved local-first setup in this dashboard process too.
        from hedwig import config as hedwig_config

        os.environ["OPENAI_API_KEY"] = openai_key
        os.environ["HEDWIG_STORAGE"] = "sqlite"
        os.environ.pop("SUPABASE_URL", None)
        os.environ.pop("SUPABASE_KEY", None)
        hedwig_config.OPENAI_API_KEY = openai_key
        hedwig_config.SUPABASE_URL = ""
        hedwig_config.SUPABASE_KEY = ""
        _apply_model_backend_values(setup_defaults["model_backend"])

        state = _one_shot_setup_state(env_manager)
        return JSONResponse(
            {
                "ok": True,
                "message": "Required setup inputs saved. First collection is now enabled.",
                "saved_keys": ["HEDWIG_STORAGE", "OPENAI_API_KEY"],
                "state": state,
            }
        )

    @app.post("/setup/model-backend/save")
    async def setup_model_backend_save(request: Request):
        """Persist setup model/backend controls through the settings save behavior."""
        form = await request.form()
        result = _save_model_backend_settings(env_manager, form)
        if not result["ok"]:
            return JSONResponse(
                {
                    "ok": False,
                    "message": "Model/backend settings were not saved.",
                    "errors": result["errors"],
                },
                status_code=400,
            )
        return JSONResponse(
            {
                "ok": True,
                "message": "Model/backend settings were written to the local .env file.",
                "saved_keys": sorted(result["values"]),
            }
        )

    @app.post("/setup/test")
    async def setup_test(request: Request):
        form = await request.form()
        values = {k: v for k, v in form.items() if v}
        # Save first, then test what's saved
        env_manager.save(values)
        results = await test_all(env_manager.load())

        html_lines = ["<div class='test-results'>"]
        for key, (ok, msg) in results.items():
            icon = "✅" if ok else "❌"
            cls = "ok" if ok else "fail"
            html_lines.append(
                f"<div class='test-row {cls}'>{icon} <strong>{key}</strong>: {msg}</div>"
            )
        html_lines.append("</div>")
        return HTMLResponse("".join(html_lines))

    @app.post("/setup/create-tables")
    async def setup_create_tables():
        values = env_manager.load()
        url = values.get("SUPABASE_URL", "")
        key = values.get("SUPABASE_KEY", "")
        ok, msg = await create_tables(url, key)
        if ok:
            return HTMLResponse(
                "<div class='test-row ok'>✅ Supabase tables created</div>"
            )
        # Manual mode fallback
        sql = get_schema_sql()
        return HTMLResponse(
            f"""
            <div class='test-row fail'>
              ❌ Auto-creation unavailable. Please run this SQL manually in
              Supabase SQL Editor:
            </div>
            <details>
              <summary>Show SQL</summary>
              <pre style='max-height:400px;overflow:auto'>{sql}</pre>
            </details>
            """
        )

    @app.post("/setup/one-shot")
    async def setup_one_shot(request: Request):
        """Save local-first setup, generate criteria, initialize DB, and start first run."""
        form = await request.form()
        openai_key = str(form.get("OPENAI_API_KEY", "")).strip()
        openai_key_error = _openai_api_key_validation_error(openai_key)
        if openai_key_error:
            return JSONResponse(
                {
                    "ok": False,
                    "error": openai_key_error,
                    "state": _one_shot_setup_state(env_manager),
                },
                status_code=400,
            )

        from hedwig import config as hedwig_config
        from hedwig.quickstart import (
            generate_criteria_from_interest,
            normalize_interest,
            persist_generated_criteria,
            persist_initial_profile,
        )

        setup_defaults = _one_shot_setup_defaults()
        raw_interest = str(form.get("interest_text", "")).strip()
        interest = normalize_interest(raw_interest)
        criteria_state = {
            "interest_text": interest,
            "uses_default": raw_interest == "",
            "default_interest": setup_defaults["interest_text"],
        }
        non_env_fields = {"interest_text", "source_preset", "algorithm_bundle_file"}
        recognized_env_keys = set(EnvManager.all_key_metadata()) - set(
            EnvManager.MODEL_BACKEND_KEYS
        )
        values = {}
        for k, v in form.items():
            key = str(k)
            if key in non_env_fields or key not in recognized_env_keys:
                continue
            value = str(v).strip()
            if value:
                values[key] = value
        model_backend_values, model_backend_errors = _model_backend_values(form)
        if model_backend_errors:
            return JSONResponse(
                {
                    "ok": False,
                    "error": "Advanced model/backend settings were invalid.",
                    "errors": model_backend_errors,
                    "state": _one_shot_setup_state(env_manager),
                },
                status_code=400,
            )
        values["OPENAI_API_KEY"] = openai_key
        values["HEDWIG_STORAGE"] = setup_defaults["storage_mode"]
        values.update(model_backend_values)
        env_manager.save_openai_local_setup(
            openai_key,
            values=values,
            model_backend_values=model_backend_values,
        )
        _refresh_config_from_managed_env(env_manager)

        # Make the running dashboard process behave like the subprocess we spawn.
        os.environ["OPENAI_API_KEY"] = openai_key
        os.environ["HEDWIG_STORAGE"] = "sqlite"
        os.environ.pop("SUPABASE_URL", None)
        os.environ.pop("SUPABASE_KEY", None)
        hedwig_config.OPENAI_API_KEY = openai_key
        hedwig_config.SUPABASE_URL = ""
        hedwig_config.SUPABASE_KEY = ""
        _apply_model_backend_values(model_backend_values)

        criteria = generate_criteria_from_interest(interest)
        criteria_path = persist_generated_criteria(
            criteria,
            path=hedwig_config.CRITERIA_PATH,
        )
        os.environ["HEDWIG_CRITERIA_PATH"] = str(criteria_path)

        local_schema_state = ensure_local_sqlite_schema()
        if not local_schema_state["schema_ready"]:
            state = _one_shot_setup_state(env_manager)
            return JSONResponse(
                {
                    "ok": False,
                    "error": "Local SQLite schema could not be initialized.",
                    "first_run_started": False,
                    "local_schema_state": local_schema_state,
                    "state": state,
                    "redirect_to": None,
                },
                status_code=500,
            )
        profile_state = persist_initial_profile(
            criteria,
            interest,
            created_by="one_shot_setup",
        )

        from hedwig.sources import get_registered_sources
        from hedwig.sources import settings as source_settings

        registry = get_registered_sources()
        source_preset_id = source_settings.normalize_source_preset_id(
            str(form.get("source_preset", setup_defaults["source_preset"])).strip()
        )
        if source_preset_id == source_settings.DEFAULT_SOURCE_PRESET:
            source_settings_state = source_settings.initialize_source_settings_from_registry(
                registry=registry,
            )
            enabled_sources = source_settings_state["sources"]
        else:
            enabled_sources = source_settings.enabled_sources_for_preset(
                source_preset_id,
                registry=registry,
            )
            source_settings_state = {
                "created": True,
                "path": str(source_settings.SOURCE_SETTINGS_PATH),
                "sources": source_settings.save_source_settings(enabled_sources)[
                    "sources"
                ],
            }
        enabled_source_ids = [
            plugin_id
            for plugin_id in sorted(registry)
            if enabled_sources.get(plugin_id, True)
        ]
        collection_run_id: int | str | None = None
        try:
            from hedwig.storage import local as local_storage

            collection_run_id = local_storage.start_collection_run(
                "daily",
                status="queued",
                metadata={
                    "source": "setup_one_shot",
                    "storage_mode": "sqlite",
                    "criteria_path": str(criteria_path),
                    "source_preset": source_preset_id,
                    "enabled_source_count": len(enabled_source_ids),
                },
            )
        except Exception:
            collection_run_id = None

        run_env = dict(os.environ)
        run_env["OPENAI_API_KEY"] = openai_key
        run_env["HEDWIG_STORAGE"] = "sqlite"
        run_env["HEDWIG_CRITERIA_PATH"] = str(criteria_path)
        if collection_run_id:
            run_env["HEDWIG_COLLECTION_RUN_ID"] = str(collection_run_id)
        run_env.pop("SUPABASE_URL", None)
        run_env.pop("SUPABASE_KEY", None)
        try:
            process = _start_daily_collection_run(env=run_env)
            if collection_run_id:
                try:
                    from hedwig.storage import local as local_storage

                    local_storage.update_collection_run(
                        collection_run_id,
                        status="running",
                        metadata={"pid": process.pid},
                    )
                except Exception:
                    pass
        except Exception as exc:
            if collection_run_id:
                try:
                    from hedwig.storage import local as local_storage

                    local_storage.finish_collection_run(
                        collection_run_id,
                        status="failed",
                        error=exc,
                    )
                except Exception:
                    pass
            state = _one_shot_setup_state(env_manager)
            return JSONResponse(
                {
                    "ok": False,
                    "error": f"First feed run could not start: {exc}",
                    "first_run_started": False,
                    "state": state,
                    "redirect_to": None,
                },
                status_code=500,
            )

        state = _one_shot_setup_state(env_manager)
        redirect_to = _setup_feed_redirect_target(state)
        return JSONResponse(
            {
                "ok": True,
                "message": "Local setup saved. First feed run started.",
                "interest": interest,
                "criteria_path": str(criteria_path),
                "criteria_state": criteria_state,
                "first_run_started": True,
                "pid": process.pid,
                "collection_run_id": collection_run_id,
                "local_schema_state": local_schema_state,
                "profile_state": profile_state,
                "source_preset_state": {
                    "preset_id": source_preset_id,
                    "enabled_count": len(enabled_source_ids),
                    "enabled_source_ids": enabled_source_ids,
                    "source_settings_created": source_settings_state["created"],
                    "source_settings_path": source_settings_state["path"],
                },
                "setup_defaults": setup_defaults,
                "first_feed_config": _first_feed_app_config(),
                "state": state,
                "redirect_to": redirect_to,
                "redirect_immediately": _setup_feed_redirect_immediately(state),
            }
        )

    @app.get("/setup/one-shot/status")
    async def setup_one_shot_status():
        state = _one_shot_setup_state(env_manager)
        return JSONResponse(_setup_state_api_payload(state))

    @app.get("/setup/collection-progress")
    async def setup_collection_progress():
        """Polling endpoint for the one-shot setup/feed collection workflow."""
        state = _one_shot_setup_state(env_manager)
        return JSONResponse(
            _collection_progress_api_payload(
                state,
                endpoint="/setup/collection-progress",
            )
        )

    @app.get("/setup/state")
    async def setup_state():
        """Return the first-run setup model used by /setup polling clients."""
        state = _one_shot_setup_state(env_manager)
        return JSONResponse(_setup_state_api_payload(state))

    @app.post("/setup/source-settings/save")
    async def setup_source_settings_save(request: Request):
        """Persist visible setup source toggles without requiring setup completion."""
        from hedwig.sources import get_registered_sources
        from hedwig.sources import settings as source_settings

        form = await request.form()
        selected = set(form.getlist("enabled_sources"))
        registry = get_registered_sources()
        enabled = {
            plugin_id: plugin_id in selected
            for plugin_id in registry
        }
        payload = source_settings.save_source_settings(enabled)
        enabled_source_ids = [
            plugin_id
            for plugin_id in sorted(registry)
            if payload["sources"].get(plugin_id, True)
        ]
        return JSONResponse(
            {
                "ok": True,
                "message": "Source toggles saved locally.",
                "enabled_source_ids": enabled_source_ids,
                "enabled_count": len(enabled_source_ids),
                "registered_source_count": len(registry),
                "source_settings_path": str(source_settings.SOURCE_SETTINGS_PATH),
            }
        )

    # -----------------------------------------------------------------------
    # Onboarding (Socratic interview)
    # -----------------------------------------------------------------------

    _onboarding_session: dict = {}

    @app.get("/onboarding", response_class=HTMLResponse)
    async def onboarding_get(request: Request):
        return TEMPLATES.TemplateResponse(request, "onboarding.html")

    @app.post("/onboarding/start")
    async def onboarding_start():
        from hedwig.config import CRITERIA_PATH, OPENAI_API_KEY
        from hedwig.onboarding import SocraticInterviewer

        llm = None
        if OPENAI_API_KEY:
            try:
                from openai import AsyncOpenAI
                llm = AsyncOpenAI(api_key=OPENAI_API_KEY)
            except Exception:
                pass

        interviewer = SocraticInterviewer(llm_client=llm, criteria_path=CRITERIA_PATH)
        first = (
            interviewer.start_recalibrate()
            if CRITERIA_PATH.exists()
            else interviewer.start_initial()
        )
        _onboarding_session["interviewer"] = interviewer
        return JSONResponse({"message": first, "complete": False})

    @app.post("/onboarding/respond")
    async def onboarding_respond(request: Request):
        form = await request.form()
        user_input = form.get("message", "")
        interviewer = _onboarding_session.get("interviewer")
        if not interviewer:
            return JSONResponse({"error": "No active session"}, status_code=400)

        response = await interviewer.respond(user_input)
        return JSONResponse(
            {
                "message": response,
                "complete": interviewer.is_complete,
            }
        )

    # -----------------------------------------------------------------------
    # Signals & feedback
    # -----------------------------------------------------------------------

    @app.get("/signals", response_class=HTMLResponse)
    async def signals_view(request: Request):
        signals = _load_recent_signals(limit=50)
        return TEMPLATES.TemplateResponse(
            request, "signals.html", {"signals": signals}
        )

    @app.get("/signals/export")
    async def signals_export(request: Request):
        if saas_mode:
            from hedwig.saas.auth import require_auth

            await require_auth(request)

        signals = [
            _serialize_signal_export(signal)
            for signal in _load_latest_signals(limit=100)
        ]
        return Response(
            content=json.dumps(signals, default=str),
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="signals-export.json"',
            },
        )

    @app.get("/signals/search")
    async def signals_search(request: Request, q: str):
        if saas_mode:
            from hedwig.saas.auth import require_auth

            await require_auth(request)

        signals = [
            _serialize_signal_export(signal)
            for signal in _search_signals(query=q.strip(), limit=100)
        ]
        return JSONResponse(signals)

    @app.get("/dashboard/stats")
    async def dashboard_stats(request: Request):
        if saas_mode:
            from hedwig.saas.auth import require_auth, require_user_id

            user = await require_auth(request)
            return JSONResponse(_load_dashboard_stats(user_id=require_user_id(user)))

        return JSONResponse(_load_dashboard_stats())

    @app.get("/dashboard/generative", response_class=HTMLResponse)
    async def dashboard_generative(request: Request):
        layout_spec = GenerativeDashboard().build_layout(
            user_criteria=_load_criteria(),
            recent_signals=_load_recent_signals(limit=30),
            dashboard_stats=_load_dashboard_stats(),
        )
        return TEMPLATES.TemplateResponse(
            request,
            "generative.html",
            {
                "layout_spec": layout_spec,
            },
        )

    @app.get("/health")
    async def health(request: Request):
        return JSONResponse(
            _load_health_status(started_at=getattr(request.app.state, "started_at", None))
        )

    # -----------------------------------------------------------------------
    # On-Demand Q&A (4-tier temporal lattice: on-demand layer)
    # Semi-explicit feedback: accept/reject events feed back into evolution.
    # -----------------------------------------------------------------------

    @app.post("/ask")
    async def ask(request: Request):
        from hedwig.qa.router import answer
        from hedwig.qa.feedback import record_qa_event

        payload = {}
        try:
            payload = await request.json()
        except Exception:
            form = await request.form()
            payload = dict(form)
        question = str(payload.get("question", "")).strip()
        if not question:
            return JSONResponse({"error": "question required"}, status_code=400)

        top_k = int(payload.get("top_k", 8) or 8)
        result = await answer(question, top_k=top_k)
        # Log the raw question as a low-weight 'semi' signal
        record_qa_event("qa_ask", payload={"question": question}, weight=0.3)
        return JSONResponse(result)

    @app.post("/qa/feedback")
    async def qa_feedback(request: Request):
        from hedwig.qa.feedback import record_qa_event

        try:
            body = await request.json()
        except Exception:
            form = await request.form()
            body = dict(form)
        kind = str(body.get("kind", "")).strip()
        question = str(body.get("question", "")).strip()
        if kind not in {"qa_accept", "qa_reject", "qa_more_like", "qa_less_like", "qa_live_search"}:
            return JSONResponse({"error": f"invalid kind {kind}"}, status_code=400)
        weight = 2.0 if kind == "qa_accept" else 1.5 if kind == "qa_reject" else 1.0
        ok = record_qa_event(kind, payload={"question": question}, weight=weight)
        return JSONResponse({"ok": bool(ok)})

    # -----------------------------------------------------------------------
    # Natural-language criteria editor (Triple-input explicit channel)
    # -----------------------------------------------------------------------

    @app.post("/criteria/propose")
    async def criteria_propose(request: Request):
        from hedwig.onboarding.nl_editor import propose_edit

        try:
            body = await request.json()
        except Exception:
            form = await request.form()
            body = dict(form)
        intent = str(body.get("intent", "")).strip()
        if not intent:
            return JSONResponse({"ok": False, "error": "intent required"}, status_code=400)
        result = await propose_edit(intent)
        return JSONResponse(result)

    @app.post("/criteria/apply")
    async def criteria_apply(request: Request):
        from hedwig.onboarding.nl_editor import confirm_edit

        try:
            body = await request.json()
        except Exception:
            form = await request.form()
            body = dict(form)
        changes = body.get("changes") or []
        intent = str(body.get("intent", "")).strip()
        if not isinstance(changes, list):
            return JSONResponse({"ok": False, "error": "changes must be list"}, status_code=400)
        result = confirm_edit(changes, intent=intent)
        status_code = 200 if result.get("ok") else 500
        return JSONResponse(result, status_code=status_code)

    # --- Natural-language editor for algorithm.yaml (HOW to recommend) -----

    @app.post("/algorithm/propose")
    async def algorithm_propose(request: Request):
        from hedwig.onboarding.nl_algo_editor import propose_edit

        try:
            body = await request.json()
        except Exception:
            form = await request.form()
            body = dict(form)
        intent = str(body.get("intent", "")).strip()
        if not intent:
            return JSONResponse({"ok": False, "error": "intent required"}, status_code=400)
        result = await propose_edit(intent)
        return JSONResponse(_jsonable(result))

    @app.post("/algorithm/apply")
    async def algorithm_apply(request: Request):
        from hedwig.onboarding.nl_algo_editor import confirm_edit

        try:
            body = await request.json()
        except Exception:
            form = await request.form()
            body = dict(form)
        changes = body.get("changes") or []
        intent = str(body.get("intent", "")).strip()
        if not isinstance(changes, list):
            return JSONResponse({"ok": False, "error": "changes must be list"}, status_code=400)
        result = confirm_edit(changes, intent=intent)
        status_code = 200 if result.get("ok") else 500
        return JSONResponse(result, status_code=status_code)

    # -----------------------------------------------------------------------
    # Phase 2 — Instrumentation: Why trace, Evolution timeline, Sandbox
    # -----------------------------------------------------------------------

    @app.get("/signals/{signal_id}/trace")
    async def signal_trace(signal_id: str):
        from hedwig.engine.trace import trace_signal

        signal = None
        for candidate in _load_recent_signals(limit=500):
            if str(candidate.get("id")) == str(signal_id):
                signal = candidate
                break
        if not signal:
            return JSONResponse({"error": "signal not found"}, status_code=404)
        return JSONResponse(trace_signal(signal))

    @app.get("/evolution/timeline")
    async def evolution_timeline(request: Request):
        from hedwig.evolution.timeline import build_timeline

        days = int(request.query_params.get("days", 30))
        limit = int(request.query_params.get("limit", 100))
        return JSONResponse({"events": build_timeline(days=days, limit=limit)})

    @app.get("/evolution", response_class=HTMLResponse)
    async def evolution_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "evolution.html")

    @app.get("/sandbox", response_class=HTMLResponse)
    async def sandbox_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "sandbox.html")

    @app.get("/meta", response_class=HTMLResponse)
    async def meta_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "meta.html")

    # -----------------------------------------------------------------------
    # Phase 7 — Feed (SNS-style infinite scroll) + behavior beacon
    # -----------------------------------------------------------------------

    # ChatGPT-style chat — single entry point ("정보 홍수에서 한 화면" pillar)
    @app.get("/chat", response_class=HTMLResponse)
    async def chat_page(request: Request):
        from hedwig.chat.router import new_conversation_id
        return TEMPLATES.TemplateResponse(
            request, "chat.html",
            {"conversation_id": new_conversation_id()},
        )

    @app.get("/chat/conversations")
    async def chat_conversations():
        from hedwig.storage import list_conversations
        return JSONResponse({"conversations": list_conversations(limit=50)})

    @app.get("/chat/conversations/{conv_id}/messages")
    async def chat_messages_endpoint(conv_id: str):
        from hedwig.storage import get_chat_messages
        return JSONResponse({"messages": get_chat_messages(conv_id, limit=200)})

    @app.delete("/chat/conversations/{conv_id}")
    async def chat_conversation_delete(conv_id: str):
        from hedwig.storage import delete_conversation
        return JSONResponse({"ok": delete_conversation(conv_id)})

    @app.post("/chat/message")
    async def chat_message(request: Request):
        from hedwig.chat.router import handle_user_message, new_conversation_id

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "expected JSON body"}, status_code=400)

        message = str(body.get("message", "")).strip()
        if not message:
            return JSONResponse({"error": "message required"}, status_code=400)
        conv_id = str(body.get("conversation_id") or "").strip() or new_conversation_id()
        result = await handle_user_message(conv_id, message)
        return JSONResponse(result)

    @app.get("/feed", response_class=HTMLResponse)
    async def feed_page(request: Request):
        from hedwig.feeds import list_feeds

        _apply_managed_local_feed_runtime(env_manager)
        first_feed_config = _first_feed_app_config()
        allowed_modes = set(first_feed_config["available_modes"])
        requested_mode = str(
            request.query_params.get("mode")
            or first_feed_config["default_mode"]
        )
        feed_mode = (
            requested_mode
            if requested_mode in allowed_modes
            else first_feed_config["default_mode"]
        )
        current_stream = str(
            request.query_params.get("stream")
            or first_feed_config["default_stream"]
        )
        initial_feed_items = _load_initial_feed_page_items()
        source_readiness = _feed_source_readiness()
        return TEMPLATES.TemplateResponse(
            request, "feed.html",
            {
                "feed_mode": feed_mode,
                "feed_mode_class": feed_mode.replace("_", "-"),
                "current_stream": current_stream,
                "feeds_list": list_feeds(),
                "first_feed_config": first_feed_config,
                "initial_feed_items": initial_feed_items,
                "source_readiness": source_readiness,
            },
        )

    @app.get("/feed/list")
    async def feed_list_endpoint():
        from hedwig.feeds import list_feeds
        return JSONResponse({"feeds": list_feeds()})

    @app.get("/feed/collection-progress")
    async def feed_collection_progress():
        """Polling endpoint for feed clients watching first collection progress."""
        _apply_managed_local_feed_runtime(env_manager)
        state = _one_shot_setup_state(env_manager)
        return JSONResponse(
            _collection_progress_api_payload(
                state,
                endpoint="/feed/collection-progress",
            )
        )

    @app.get("/feed/api")
    async def feed_api(request: Request):
        """Cursor-paginated feed JSON.

        Query params:
            stream: feed id (default 'default')
            cursor: opaque base64 token (omit for first page)
            limit:  page size (default 30, max 100)
        """
        import base64

        _apply_managed_local_feed_runtime(env_manager)
        from hedwig.personal_algorithm import route_items_after_ranking
        from hedwig.storage import get_latest_collection_progress, get_recent_signals
        stream = request.query_params.get("stream", "default")
        try:
            limit = max(1, min(100, int(request.query_params.get("limit", 30))))
        except ValueError:
            limit = 30

        # Pull a generous superset and slice; SQLite is fast enough for v1
        all_rows = get_recent_signals(days=14) or []

        cursor = request.query_params.get("cursor", "")
        start_idx = 0
        if cursor:
            try:
                token = base64.urlsafe_b64decode(cursor.encode()).decode()
                last_id, _last_collected = token.split("|", 1)
                for i, r in enumerate(all_rows):
                    if str(r.get("id")) == last_id:
                        start_idx = i + 1
                        break
            except Exception:
                start_idx = 0

        page = all_rows[start_idx : start_idx + limit]
        next_cursor = ""
        has_more = (start_idx + limit) < len(all_rows)
        if page and has_more:
            last = page[-1]
            tok = f"{last.get('id')}|{last.get('collected_at') or ''}"
            next_cursor = base64.urlsafe_b64encode(tok.encode()).decode()

        items = [
            _ranked_feed_item_from_signal_row(r, input_order=start_idx + offset)
            for offset, r in enumerate(page)
        ]
        items = route_items_after_ranking(items)
        setup_readiness = _feed_api_setup_readiness(
            env_manager,
            readable_item_count=len(all_rows),
        )
        return JSONResponse({
            "items": items,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "stream": stream,
            "collection_progress": get_latest_collection_progress("daily"),
            "setup_readiness": setup_readiness,
        })

    @app.post("/events/beacon")
    async def events_beacon(request: Request):
        """Batch endpoint for /feed JS beacon — implicit-passive feedback."""
        from hedwig.delivery.ambient import (
            interpret_ambient_delivery_event,
            is_ambient_delivery_event,
        )
        from hedwig.personal_algorithm import interpret_behavior_event
        from hedwig.storage import (
            save_behavior_events_batch,
            save_behavior_rewards_batch,
            save_evolution_signal,
        )

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "expected JSON body"}, status_code=400)

        events = body.get("events") or []
        if not isinstance(events, list):
            return JSONResponse({"error": "events must be a list"}, status_code=400)

        saved = save_behavior_events_batch(events)
        reward_candidate_events = [
            ev for ev in events
            if not is_ambient_delivery_event(ev)
        ]
        delivery_reward_candidate_events = [
            ev for ev in events
            if is_ambient_delivery_event(ev)
        ]
        feed_rewards = [rw for ev in reward_candidate_events if (rw := interpret_behavior_event(ev))]
        delivery_rewards = [
            rw for ev in delivery_reward_candidate_events
            if (rw := interpret_ambient_delivery_event(ev))
        ]
        rewards = feed_rewards + delivery_rewards
        saved_rewards = save_behavior_rewards_batch(rewards) if rewards else 0

        # Promote dwell/skip/share events into the unified evolution_signal
        # stream (channel='implicit', kind='behavior_<type>') so the existing
        # evolution loop sees them without new wiring.
        for ev in reward_candidate_events:
            etype = ev.get("event_type")
            if etype in ("dwell", "skip", "share", "save", "open", "not_interested", "swipe_left", "swipe_right", "swipe_next"):
                weight = {
                    "dwell": 0.2,
                    "skip": 0.1,
                    "swipe_right": 0.1,
                    "swipe_next": 0.05,
                    "share": 0.8,
                    "save": 1.0,
                    "open": 0.8,
                    "not_interested": 1.0,
                    "swipe_left": 0.8,
                }.get(etype, 0.2)
                try:
                    save_evolution_signal(
                        channel="implicit",
                        kind=f"behavior_{etype}",
                        payload={
                            "signal_id": ev.get("signal_id"),
                            "dwell_ms": ev.get("dwell_ms"),
                            "feed_id": ev.get("feed_id"),
                            "feed_mode": ev.get("feed_mode") or ev.get("mode"),
                        },
                        weight=weight,
                    )
                except Exception:
                    pass
        return JSONResponse({
            "ok": True,
            "saved": saved,
            "rewards": saved_rewards,
            "feed_rewards": len(feed_rewards),
            "delivery_rewards": len(delivery_rewards),
        })

    @app.get("/feed/metrics")
    async def feed_metrics_endpoint():
        from hedwig.storage import get_usage_metrics_by_mode
        return JSONResponse({"modes": get_usage_metrics_by_mode()})

    @app.get("/ambient/surfaces")
    async def ambient_surfaces_endpoint():
        from hedwig.delivery.ambient import ambient_surface_entry_points
        return JSONResponse({"surfaces": ambient_surface_entry_points()})

    @app.get("/ambient/{surface}", response_class=HTMLResponse)
    async def ambient_surface_page(request: Request, surface: str):
        from hedwig.delivery.ambient import select_ambient_items

        try:
            limit = int(request.query_params.get("limit", 0) or 0) or None
        except ValueError:
            limit = None
        client_context = {
            key: request.query_params.get(key)
            for key in (
                "display_mode",
                "display",
                "installed",
                "is_installed",
                "standalone",
                "unsupported_browser",
                "supports_service_worker",
                "supports_manifest",
                "native_available",
                "supports_native",
                "native_bridge_available",
                "notification_permission",
                "native_notification_permission",
                "enforce_delivery_schedule",
                "scheduler",
                "now",
                "current_datetime",
                "schedule_at",
                "current_time",
                "local_time",
                "weekday",
            )
            if key in request.query_params
        }
        try:
            from hedwig.storage import get_behavior_events
            client_context["ambient_delivery_events"] = get_behavior_events(
                event_types=["delivered", "snoozed"],
                limit=500,
            )
        except Exception:
            client_context["ambient_delivery_events"] = []

        try:
            selected = select_ambient_items(
                _load_ranked_feed_items(days=14),
                surface,
                limit=limit,
                client_context=client_context,
            )
        except ValueError:
            return TEMPLATES.TemplateResponse(
                request,
                "ambient_surface.html",
                {"surface": surface, "payload": None, "items": [], "error": f"Unknown ambient surface: {surface}"},
                status_code=404,
            )
        return TEMPLATES.TemplateResponse(
            request,
            "ambient_surface.html",
            {"surface": selected["surface"], "payload": selected, "items": selected["items"], "error": None},
        )

    @app.get("/ambient/{surface}/api")
    async def ambient_surface_items_endpoint(request: Request, surface: str):
        from hedwig.delivery.ambient import record_ambient_delivery_events, select_ambient_items

        try:
            limit = int(request.query_params.get("limit", 0) or 0) or None
        except ValueError:
            limit = None
        client_context = {
            key: request.query_params.get(key)
            for key in (
                "display_mode",
                "display",
                "installed",
                "is_installed",
                "standalone",
                "unsupported_browser",
                "supports_service_worker",
                "supports_manifest",
                "native_available",
                "supports_native",
                "native_bridge_available",
                "notification_permission",
                "native_notification_permission",
                "enforce_delivery_schedule",
                "scheduler",
                "now",
                "current_datetime",
                "schedule_at",
                "current_time",
                "local_time",
                "weekday",
            )
            if key in request.query_params
        }
        try:
            from hedwig.storage import get_behavior_events
            client_context["ambient_delivery_events"] = get_behavior_events(
                event_types=["delivered", "snoozed"],
                limit=500,
            )
        except Exception:
            client_context["ambient_delivery_events"] = []

        try:
            selected = select_ambient_items(
                _load_ranked_feed_items(days=14),
                surface,
                limit=limit,
                client_context=client_context,
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        record_ambient_delivery_events(selected, event_type="delivered", device="server_api")
        return JSONResponse(selected)

    @app.get("/policy/personal-algorithm")
    async def personal_algorithm_policy_endpoint():
        from hedwig.personal_algorithm import get_personal_algorithm_policy
        return JSONResponse(_jsonable(get_personal_algorithm_policy()))

    @app.post("/policy/natural-language")
    async def personal_algorithm_nl_endpoint(request: Request):
        from hedwig.onboarding.nl_algo_editor import confirm_edit, propose_local_policy_edit
        from hedwig.personal_algorithm import classify_policy_edit, shadow_test_policy_edit

        try:
            body = await request.json()
        except Exception:
            form = await request.form()
            body = dict(form)
        intent = str(body.get("intent", "")).strip()
        if not intent:
            return JSONResponse({"ok": False, "error": "intent required"}, status_code=400)
        proposed = propose_local_policy_edit(intent)
        changes = proposed.get("changes") or []
        classification = classify_policy_edit(changes, intent)
        proposed["classification"] = classification
        proposed["risk_class"] = classification["risk_class"]
        if classification["risk_class"] == "future_ranking_experimental" and body.get("apply"):
            return JSONResponse(_jsonable(confirm_edit(changes, intent=intent)))
        if classification["risk_class"] == "risky_post_ranking" and not body.get("shadow_approved"):
            proposed["shadow"] = shadow_test_policy_edit(changes, intent)
            proposed["requires_shadow_test"] = True
            return JSONResponse(_jsonable(proposed))
        if body.get("apply"):
            return JSONResponse(_jsonable(confirm_edit(changes, intent=intent, shadow_approved=bool(body.get("shadow_approved")))))
        return JSONResponse(_jsonable(proposed))

    @app.post("/policy/rollback")
    async def personal_algorithm_rollback_endpoint(request: Request):
        from hedwig.onboarding.nl_algo_editor import restore_algorithm_version

        try:
            body = await request.json()
        except Exception:
            form = await request.form()
            body = dict(form)
        try:
            version = int(body.get("version"))
        except Exception:
            return JSONResponse({"ok": False, "error": "version required"}, status_code=400)
        result = restore_algorithm_version(version)
        return JSONResponse(_jsonable(result), status_code=200 if result.get("ok") else 404)

    @app.get("/status", response_class=HTMLResponse)
    async def status_page(request: Request):
        from hedwig.qa.exit_conditions import (
            compute_algorithm_training_status,
            compute_exit_progress,
            compute_retrain_history,
            compute_source_health,
        )
        return TEMPLATES.TemplateResponse(
            request, "status.html",
            {
                "conditions": compute_exit_progress(),
                "source_health": compute_source_health(days=1),
                "retrain_history": compute_retrain_history(),
                "algorithm_training": compute_algorithm_training_status(),
            },
        )

    # -----------------------------------------------------------------------
    # Phase 7 S5 — /profile single page
    # -----------------------------------------------------------------------

    @app.get("/profile", response_class=HTMLResponse)
    async def profile_page(request: Request):
        from hedwig.config import load_algorithm_config, load_criteria
        from hedwig.evolution.timeline import build_timeline
        from hedwig.qa.personality import compute_feed_personality
        from hedwig.storage import get_active_interpretation_style
        import yaml as _yaml
        criteria = load_criteria() or {}
        algorithm = load_algorithm_config() or {}
        style = get_active_interpretation_style() or {}
        personality = compute_feed_personality(days=7)
        recent_evolution = build_timeline(days=14, limit=10)
        criteria_yaml = _yaml.safe_dump(criteria, allow_unicode=True, sort_keys=False)
        return TEMPLATES.TemplateResponse(
            request, "profile.html",
            {
                "criteria": criteria,
                "criteria_yaml": criteria_yaml,
                "algorithm": algorithm,
                "style": style,
                "personality": personality,
                "recent_evolution": recent_evolution,
                "source_count": _count_sources(),
            },
        )

    # -----------------------------------------------------------------------
    # Phase 7 S6 — Algorithm export/import bundle
    # -----------------------------------------------------------------------

    @app.get("/algorithm/export")
    async def algorithm_export_endpoint():
        from hedwig.onboarding.bundle import export_bundle
        blob, filename = export_bundle()
        return Response(
            content=blob,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/algorithm/import/dry-run")
    async def algorithm_import_dry_run(request: Request):
        from hedwig.onboarding.bundle import dry_run_import
        body = await request.body()
        return JSONResponse(_jsonable(dry_run_import(body)))

    @app.post("/algorithm/import")
    async def algorithm_import_endpoint(request: Request):
        from hedwig.onboarding.bundle import confirm_import
        body = await request.body()
        return JSONResponse(_jsonable(confirm_import(body)))

    # -----------------------------------------------------------------------
    # Admin — data reset (keeps YAML configs)
    # -----------------------------------------------------------------------

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "admin.html")

    @app.post("/admin/reset")
    async def admin_reset(request: Request):
        from hedwig.admin import reset_data
        try:
            body = await request.json()
        except Exception:
            body = {}
        scope = str(body.get("scope") or "all")
        result = reset_data(scope=scope)
        return JSONResponse(result)

    @app.get("/sovereignty", response_class=HTMLResponse)
    async def sovereignty_page(request: Request):
        from hedwig.sovereignty import load_sovereignty
        spec = load_sovereignty()
        domains = {k: v for k, v in spec.items() if k in ("criteria", "algorithm", "memory")}
        export = spec.get("export_contract", {}) or {}
        return TEMPLATES.TemplateResponse(
            request, "sovereignty.html",
            {
                "domains": domains,
                "export_files": export.get("files", []),
                "export_guarantee": export.get("guarantee", ""),
            },
        )

    @app.get("/brief", response_class=HTMLResponse)
    async def brief_page(request: Request):
        from hedwig.storage import get_briefings
        cycle = request.query_params.get("cycle")
        if cycle in ("daily", "weekly", "critical"):
            rows = get_briefings(cycle_type=cycle, limit=30)
            active = cycle
        else:
            rows = get_briefings(limit=30)
            active = "all"
        return TEMPLATES.TemplateResponse(
            request, "brief.html",
            {"briefings": rows, "cycle": active},
        )

    # -----------------------------------------------------------------------
    # Demo — concept walkthrough with seed data
    # -----------------------------------------------------------------------

    @app.get("/demo", response_class=HTMLResponse)
    async def demo_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "demo.html")

    @app.post("/demo/seed")
    async def demo_seed_endpoint():
        from hedwig.dashboard.demo_seed import seed_demo
        return JSONResponse(seed_demo(reset=True))

    @app.post("/demo/reset")
    async def demo_reset_endpoint():
        from hedwig.dashboard.demo_seed import reset_demo
        return JSONResponse(reset_demo())

    @app.post("/meta/cycle")
    async def meta_cycle_endpoint(request: Request):
        from hedwig.evolution.meta import run_meta_cycle

        try:
            body = await request.json()
        except Exception:
            form = await request.form()
            body = dict(form)

        n = int(body.get("n_candidates", 3))
        force = bool(body.get("force", False))
        strategies = body.get("strategies")
        result = run_meta_cycle(
            n_candidates=n,
            strategies=strategies if isinstance(strategies, list) else None,
            force=force,
        )
        return JSONResponse(_jsonable(result))

    @app.post("/sandbox/simulate")
    async def sandbox_simulate(request: Request):
        from hedwig.config import load_algorithm_config
        from hedwig.evolution.sandbox import make_candidate, run_sandbox

        try:
            body = await request.json()
        except Exception:
            form = await request.form()
            body = dict(form)

        baseline = load_algorithm_config()
        perturbations = body.get("perturbations") or {}
        injected = body.get("injected_events") or []
        candidate = make_candidate(baseline, perturbations)
        result = run_sandbox(candidate, baseline, injected_events=injected)
        result["candidate_config"] = _jsonable(candidate)
        return JSONResponse(result)

    @app.post("/feedback/{signal_id}/{vote}")
    async def submit_feedback(request: Request, signal_id: str, vote: str):
        if vote not in ("up", "down"):
            return JSONResponse({"error": "Invalid vote"}, status_code=400)

        from hedwig.feedback import FeedbackCollector
        from hedwig.models import VoteType
        # Dynamic import — survives code-edit reloads without restarting uvicorn.
        from hedwig import storage as _storage

        user_id: str | None = None
        if saas_mode:
            from hedwig.saas.auth import require_auth, require_user_id

            user = await require_auth(request)
            user_id = require_user_id(user)

        collector = FeedbackCollector()
        fb = collector.from_direct(
            signal_id=signal_id,
            vote=VoteType.UP if vote == "up" else VoteType.DOWN,
        )
        # Defensive: if user_id is None, call without the kwarg so any
        # backend whose signature isn't user_id-aware still works.
        try:
            if user_id is not None:
                _storage.save_feedback(fb, user_id=user_id)
            else:
                _storage.save_feedback(fb)
        except TypeError:
            # Last-ditch — backend has neither signature; call positional only.
            _storage.save_feedback(fb)

        return JSONResponse({"ok": True, "vote": vote})

    # -----------------------------------------------------------------------
    # Pipeline control
    # -----------------------------------------------------------------------

    @app.post("/run/daily")
    async def run_daily():
        """Trigger a daily run in background."""
        _start_daily_collection_run()
        return JSONResponse({"ok": True, "message": "Daily run started"})

    @app.post("/run/dry")
    async def run_dry():
        subprocess.Popen(
            [sys.executable, "-m", "hedwig", "--dry-run"],
            cwd=str(Path.cwd()),
        )
        return JSONResponse({"ok": True, "message": "Dry run started"})

    @app.post("/run/weekly")
    async def run_weekly():
        subprocess.Popen(
            [sys.executable, "-m", "hedwig", "--weekly"],
            cwd=str(Path.cwd()),
        )
        return JSONResponse({"ok": True, "message": "Weekly run started"})

    @app.post("/run/critical")
    async def run_critical():
        from hedwig.engine.critical import run_critical_cycle

        async def _deliver(signal):
            from hedwig.config import (
                SLACK_WEBHOOK_ALERTS,
                DISCORD_WEBHOOK_ALERTS,
                smtp_alerts_configured,
            )
            if SLACK_WEBHOOK_ALERTS:
                try:
                    from hedwig.delivery.slack import send_alert
                    await send_alert(signal)
                except Exception as e:
                    logger.warning("slack alert failed: %s", e)
            if DISCORD_WEBHOOK_ALERTS:
                try:
                    from hedwig.delivery.discord import send_alert
                    await send_alert(signal)
                except Exception as e:
                    logger.warning("discord alert failed: %s", e)
            if smtp_alerts_configured():
                try:
                    from hedwig.delivery.email import send_alert
                    await send_alert(signal)
                except Exception as e:
                    logger.warning("email alert failed: %s", e)

        result = await run_critical_cycle(deliver=_deliver)
        return JSONResponse({"ok": True, **result})

    # -----------------------------------------------------------------------
    # Sources view
    # -----------------------------------------------------------------------

    @app.get("/sources", response_class=HTMLResponse)
    async def sources_view(request: Request):
        from hedwig.sources import get_registered_sources
        registry = get_registered_sources()
        sources = [
            {"id": pid, "meta": cls.metadata()} for pid, cls in sorted(registry.items())
        ]
        return TEMPLATES.TemplateResponse(
            request, "sources.html", {"sources": sources}
        )

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_view(request: Request):
        if saas_mode:
            from hedwig.saas.auth import require_auth, require_user_id
            from hedwig.storage import load_user_source_settings

            user = await require_auth(request)
            user_id = require_user_id(user)
        else:
            user_id = None

        from hedwig.sources import get_registered_sources
        from hedwig.sources import settings as source_settings

        registry = get_registered_sources()
        if saas_mode:
            enabled = load_user_source_settings(user_id=user_id, registry=registry)
            settings_destination = "Saved to your SaaS account via Supabase."
            saved_message = "Source plugin settings were saved to your SaaS account."
        else:
            enabled = source_settings.load_source_settings(registry=registry)
            settings_destination = (
                f"Saved locally to {source_settings.SOURCE_SETTINGS_PATH}."
            )
            saved_message = (
                "Source plugin settings were written to the local config file."
            )

        sources = [
            {
                "id": pid,
                "meta": cls.metadata(),
                "enabled": enabled.get(pid, True),
            }
            for pid, cls in sorted(registry.items())
        ]
        return TEMPLATES.TemplateResponse(
            request,
            "settings.html",
            {
                "sources": sources,
                "settings_destination": settings_destination,
                "saved": request.query_params.get("saved") in {"1", "model-backend"},
                "saved_message": (
                    "Model/backend settings were written to the local .env file."
                    if request.query_params.get("saved") == "model-backend"
                    else saved_message
                ),
                "values": EnvManager.redact_secret_values(env_manager.load()),
                "model_backend_keys": EnvManager.MODEL_BACKEND_KEYS,
            },
        )

    @app.post("/settings/save")
    async def settings_save(request: Request):
        from hedwig.sources import get_registered_sources
        from hedwig.sources import settings as source_settings

        form = await request.form()
        selected = set(form.getlist("enabled_sources"))
        registry = get_registered_sources()
        enabled = {
            plugin_id: plugin_id in selected
            for plugin_id in registry
        }

        if saas_mode:
            from hedwig.saas.auth import require_auth, require_user_id
            from hedwig.storage import save_user_source_settings

            user = await require_auth(request)
            user_id = require_user_id(user)
            if not save_user_source_settings(user_id=user_id, enabled=enabled):
                raise HTTPException(
                    status_code=503,
                    detail="Failed to save source settings",
                )
        else:
            source_settings.save_source_settings(enabled)

        return RedirectResponse(url="/settings?saved=1", status_code=303)

    @app.post("/settings/model-backend/save")
    async def settings_model_backend_save(request: Request):
        """Persist advanced model/backend controls through the existing settings UI."""
        if saas_mode:
            from hedwig.saas.auth import require_auth

            await require_auth(request)

        form = await request.form()
        result = _save_model_backend_settings(env_manager, form)
        if not result["ok"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Invalid model/backend settings",
                    "errors": result["errors"],
                },
            )
        return RedirectResponse(url="/settings?saved=model-backend", status_code=303)

    # -----------------------------------------------------------------------
    # Criteria editor
    # -----------------------------------------------------------------------

    @app.get("/criteria", response_class=HTMLResponse)
    async def criteria_view(request: Request):
        from hedwig.config import CRITERIA_PATH
        content = ""
        if CRITERIA_PATH.exists():
            content = CRITERIA_PATH.read_text()
        return TEMPLATES.TemplateResponse(
            request, "criteria.html", {"content": content}
        )

    @app.post("/criteria/save")
    async def criteria_save(content: str = Form(...)):
        from hedwig.config import CRITERIA_PATH
        CRITERIA_PATH.write_text(content)
        return JSONResponse({"ok": True})

    # -----------------------------------------------------------------------
    # Optional auto-context onboarding is linked from setup in local and SaaS
    # modes; auth, billing, and landing routes remain SaaS-only.
    # -----------------------------------------------------------------------

    _register_auto_onboarding_routes(app)

    if saas_mode:
        _register_saas_routes(app)

    return app


def _register_auto_onboarding_routes(app: FastAPI):
    """Register the optional auto-context onboarding surface for setup links."""

    @app.get("/onboarding/auto", response_class=HTMLResponse)
    async def auto_onboarding_page(request: Request):
        providers = []
        try:
            from hedwig.saas import oauth as saas_oauth

            providers = saas_oauth.list_providers()
        except Exception:
            providers = []
        return TEMPLATES.TemplateResponse(
            request,
            "onboarding_auto.html",
            {"providers": providers},
        )

    @app.post("/onboarding/auto/infer")
    async def auto_inference(request: Request):
        """Run auto-context inference from SNS handles + bio."""
        from hedwig.saas.auto_context import AutoContextInference
        from hedwig.saas.operator_keys import get_operator_openai_key

        form = await request.form()
        bio = form.get("bio", "")

        # Collect all SNS handles from form.
        sns_handles = {}
        for key in form.keys():
            if key.startswith("sns_"):
                platform = key[4:]
                value = form[key].strip()
                if value:
                    sns_handles[platform] = value

        extra_links_raw = form.get("extra_links", "")
        extra_links = [
            link.strip() for link in extra_links_raw.split("\n") if link.strip()
        ]

        try:
            from openai import AsyncOpenAI

            llm = AsyncOpenAI(api_key=get_operator_openai_key())
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

        engine = AutoContextInference(llm_client=llm)
        result = await engine.infer(
            bio=bio,
            sns_handles=sns_handles,
            extra_links=extra_links,
        )

        from hedwig.config import CRITERIA_PATH
        import yaml

        if result.get("criteria"):
            with open(CRITERIA_PATH, "w") as f:
                yaml.dump(
                    result["criteria"],
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                )

        return JSONResponse(result)


def _register_saas_routes(app: FastAPI):
    """Register multi-tenant SaaS routes (landing, auth, billing, OAuth, auto-context)."""
    if not getattr(app.state, "saas_mode", False):
        raise RuntimeError("_register_saas_routes requires saas_mode=True")

    from hedwig.saas import auth as saas_auth
    from hedwig.saas import billing as saas_billing
    from hedwig.saas import oauth as saas_oauth
    from hedwig.saas.models import SubscriptionTier

    # ------- Landing -------

    @app.get("/landing", response_class=HTMLResponse)
    async def landing(request: Request):
        return TEMPLATES.TemplateResponse(request, "landing.html")

    # ------- Auth pages -------

    @app.get("/signup", response_class=HTMLResponse)
    async def signup_page(request: Request):
        providers = saas_oauth.list_providers()
        return TEMPLATES.TemplateResponse(
            request,
            "signup.html",
            {"oauth_providers": providers},
        )

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        providers = saas_oauth.list_providers()
        return TEMPLATES.TemplateResponse(
            request,
            "login.html",
            {"oauth_providers": providers},
        )

    # ------- OAuth flow -------

    @app.get("/auth/callback")
    async def oauth_callback(request: Request):
        """Handle OAuth callback from Supabase. Token comes in URL fragment."""
        return TEMPLATES.TemplateResponse(request, "oauth_callback.html")

    @app.get("/auth/oauth/{provider}")
    async def oauth_redirect(provider: str, request: Request):
        """Redirect user to Supabase OAuth flow for the chosen provider."""
        base_url = str(request.base_url).rstrip("/")
        redirect_to = f"{base_url}/auth/callback"
        oauth_url = saas_oauth.build_oauth_url(provider, redirect_to)
        if not oauth_url:
            return JSONResponse({"error": f"Provider {provider} not supported"}, status_code=400)
        return RedirectResponse(url=oauth_url, status_code=303)

    @app.post("/auth/oauth/save-token")
    async def oauth_save_token(request: Request):
        """Save OAuth access token from frontend (after URL fragment parsing)."""
        form = await request.form()
        token = form.get("access_token", "")
        if not token:
            return JSONResponse({"error": "No token"}, status_code=400)
        response = JSONResponse({"ok": True, "next": "/onboarding/auto"})
        response.set_cookie(
            "hedwig_access_token",
            token,
            httponly=True,
            secure=False,
            samesite="lax",
        )
        return response

    # ------- Auth API -------

    @app.post("/auth/signup")
    async def auth_signup(request: Request):
        form = await request.form()
        email = form.get("email", "")
        password = form.get("password", "")
        try:
            result = await saas_auth.sign_up(email, password)
            response = JSONResponse({"ok": True, "user": result.get("user", {})})
            if result.get("access_token"):
                response.set_cookie(
                    "hedwig_access_token",
                    result["access_token"],
                    httponly=True,
                    secure=False,
                    samesite="lax",
                )
            return response
        except saas_auth.AuthError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    @app.post("/auth/login")
    async def auth_login(request: Request):
        form = await request.form()
        email = form.get("email", "")
        password = form.get("password", "")
        try:
            result = await saas_auth.sign_in(email, password)
            response = JSONResponse({"ok": True, "user": result.get("user", {})})
            if result.get("access_token"):
                response.set_cookie(
                    "hedwig_access_token",
                    result["access_token"],
                    httponly=True,
                    secure=False,
                    samesite="lax",
                )
            return response
        except saas_auth.AuthError as e:
            return JSONResponse({"error": str(e)}, status_code=401)

    @app.post("/auth/logout")
    async def auth_logout(request: Request):
        token = request.cookies.get("hedwig_access_token", "")
        if token:
            await saas_auth.sign_out(token)
        response = JSONResponse({"ok": True})
        response.delete_cookie("hedwig_access_token")
        return response

    @app.get("/auth/me")
    async def auth_me(request: Request):
        user = await saas_auth.get_current_user(request)
        if not user:
            return JSONResponse({"authenticated": False}, status_code=401)
        return JSONResponse({"authenticated": True, "user": user})

    # ------- Billing -------

    @app.post("/billing/checkout")
    async def billing_checkout(request: Request):
        user = await saas_auth.require_auth(request)
        form = await request.form()
        tier_str = form.get("tier", "pro")
        try:
            tier = SubscriptionTier(tier_str)
            base_url = str(request.base_url).rstrip("/")
            session = await saas_billing.create_checkout_session(
                user_id=user["id"],
                user_email=user["email"],
                tier=tier,
                success_url=f"{base_url}/?upgraded=true",
                cancel_url=f"{base_url}/billing/cancel",
            )
            return JSONResponse({"url": session.get("url")})
        except (ValueError, saas_billing.BillingError) as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    @app.post("/billing/webhook")
    async def billing_webhook(request: Request):
        # TODO: verify signature with STRIPE_WEBHOOK_SECRET
        event = await request.json()
        result = await saas_billing.handle_webhook(event)
        if result:
            # Ralph loop handles DB updates based on webhook results
            logger.info(f"Webhook: {result}")
        return JSONResponse({"received": True})

    @app.get("/billing/portal")
    async def billing_portal(request: Request):
        await saas_auth.require_auth(request)
        # TODO: look up stripe_customer_id from subscriptions table
        return JSONResponse({"ok": True, "message": "Portal route placeholder"})

    # ------- Billing dashboard page -------

    @app.get("/billing", response_class=HTMLResponse)
    async def billing_page(request: Request):
        from hedwig.saas.operator_keys import TIER_TOKEN_QUOTAS

        tier = "free"
        tokens_used = 0
        signals_collected = 0
        sources_active = _count_sources()

        try:
            await saas_auth.get_current_user(request)
        except Exception:
            pass

        tokens_limit = TIER_TOKEN_QUOTAS[SubscriptionTier(tier)]
        signals_limit = 50 if tier == "free" else 999_999

        return TEMPLATES.TemplateResponse(
            request,
            "billing.html",
            {
                "tier": tier,
                "status": "active",
                "tokens_used": tokens_used,
                "tokens_limit": tokens_limit,
                "tokens_percent": round(tokens_used / tokens_limit * 100, 1) if tokens_limit else 0,
                "signals_collected": signals_collected,
                "signals_limit": signals_limit,
                "signals_percent": round(signals_collected / signals_limit * 100, 1) if signals_limit < 999_999 else 0,
                "sources_active": sources_active,
                "sources_limit": 5 if tier == "free" else 999,
            },
        )

    # ------- Referral / invite system -------

    @app.get("/invite", response_class=HTMLResponse)
    async def invite_page(request: Request):
        user = None
        try:
            user = await saas_auth.get_current_user(request)
        except Exception:
            pass
        user_id = user.get("id", "anonymous") if user else "anonymous"
        base_url = str(request.base_url).rstrip("/")
        invite_link = f"{base_url}/signup?ref={user_id[:8]}"
        return TEMPLATES.TemplateResponse(
            request,
            "invite.html",
            {"invite_link": invite_link},
        )

    # ------- Multilingual landing -------

    @app.get("/ko", response_class=HTMLResponse)
    async def landing_ko(request: Request):
        return TEMPLATES.TemplateResponse(request, "landing_ko.html")

    @app.get("/zh", response_class=HTMLResponse)
    async def landing_zh(request: Request):
        return TEMPLATES.TemplateResponse(request, "landing_zh.html")

    # ------- Legal pages -------

    @app.get("/terms", response_class=HTMLResponse)
    async def terms_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "terms.html")

    @app.get("/privacy", response_class=HTMLResponse)
    async def privacy_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "privacy.html")

    @app.get("/about", response_class=HTMLResponse)
    async def about_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "about.html")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_recent_signals(limit: int = 20) -> list[dict]:
    try:
        from hedwig.storage import get_recent_signals
        return get_recent_signals(days=3)[:limit]
    except Exception:
        return []


def _load_ranked_feed_items(days: int = 14) -> list[dict]:
    try:
        from hedwig.storage import get_recent_signals
        rows = get_recent_signals(days=days) or []
    except Exception:
        rows = []

    items = []
    for offset, r in enumerate(rows):
        items.append(_ranked_feed_item_from_signal_row(r, input_order=offset))
    return items


def _apply_managed_local_feed_runtime(env_manager: EnvManager) -> None:
    """Honor the dashboard-managed local setup before feed storage reads.

    The storage dispatcher reads process environment variables. A completed
    one-shot setup is persisted in the managed .env, so feed requests should
    use that local SQLite selection even if the dashboard process was started
    with stale Supabase-oriented variables.
    """
    if not env_manager.env_path.exists():
        return

    values = env_manager.load()
    storage_mode = (values.get("HEDWIG_STORAGE") or "sqlite").strip().lower()
    if storage_mode not in {"sqlite", "local"}:
        return

    os.environ["HEDWIG_STORAGE"] = "sqlite"
    if not values.get("SUPABASE_URL"):
        os.environ.pop("SUPABASE_URL", None)
    if not values.get("SUPABASE_KEY"):
        os.environ.pop("SUPABASE_KEY", None)


def _load_initial_feed_page_items(limit: int = 30) -> list[dict]:
    """Load the first local feed page for no-extra-config server rendering."""
    try:
        from hedwig.personal_algorithm import route_items_after_ranking

        return route_items_after_ranking(_load_ranked_feed_items(days=14)[:limit])
    except Exception:
        return []


def _coalesce_score(row: dict, *fields: str) -> float:
    for field in fields:
        value = row.get(field)
        if value is not None:
            return float(value)
    return 0.0


def _ranked_feed_item_from_signal_row(row: dict, input_order: int) -> dict:
    """Adapt stored ranking output into the post-ranking item contract.

    Ambient surfaces and the manual feed share this adapter so delivery stays
    downstream of ranking instead of inventing a separate ordering path.
    """
    import json

    extra = row.get("extra") or {}
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except Exception:
            extra = {}
    if not isinstance(extra, dict):
        extra = {}
    ensemble_score = _coalesce_score(row, "ensemble_score", "relevance_score")
    final_score = _coalesce_score(row, "final_score", "relevance_score", "ensemble_score")
    input_rank = row.get("ensemble_rank") or row.get("rank") or row.get("rank_position") or input_order + 1
    content = str(row.get("content") or "")
    transcript = str(extra.get("transcript") or "")
    item = {
        "id": row.get("id"),
        "title": row.get("title"),
        "url": row.get("url"),
        "content_excerpt": content[:220],
        "thumbnail_url": extra.get("thumbnail_url") or extra.get("thumbnail"),
        "transcript_excerpt": transcript[:220],
        "platform": row.get("platform"),
        "score": row.get("relevance_score") if row.get("relevance_score") is not None else final_score,
        "ensemble_score": ensemble_score,
        "final_score": final_score,
        "ensemble_rank": input_rank,
        "urgency": row.get("urgency"),
        "why_relevant": row.get("why_relevant"),
        "devils_advocate": row.get("devils_advocate"),
        "author": row.get("author"),
        "feed_position": input_order,
        "pre_layer_ranking": {
            "ensemble_score": ensemble_score,
            "final_score": final_score,
            "input_rank": input_rank,
            "input_order": input_order,
            "rank_identifiers": {
                "id": row.get("id"),
                "ensemble_rank": input_rank,
                "feed_position": input_order,
            },
            "immutable": True,
        },
    }
    return item


def _load_latest_signals(limit: int = 100) -> list[dict]:
    try:
        from hedwig.storage import get_latest_signals
        return get_latest_signals(limit=limit)
    except Exception:
        return []


def _search_signals(query: str, limit: int = 100) -> list[dict]:
    try:
        from hedwig.storage import search_signals
        return search_signals(query=query, limit=limit)
    except Exception:
        return []


def _load_dashboard_activity_stats(user_id: str | None = None) -> dict:
    try:
        from hedwig.storage import get_dashboard_activity_stats

        if user_id is None:
            return get_dashboard_activity_stats()
        return get_dashboard_activity_stats(user_id=user_id)
    except Exception:
        return {
            "total_signals": 0,
            "upvote_ratio": 0.0,
            "top_5_sources": [],
            "days_active": 0,
        }


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _setup_source_preset_context() -> dict:
    """Return setup source presets derived from registry/source_settings."""
    from hedwig.sources import get_registered_sources
    from hedwig.sources import settings as source_settings

    registry = get_registered_sources()
    enabled = source_settings.load_source_settings(registry=registry)
    presets = source_settings.get_source_presets(registry=registry)
    source_toggles = [
        {
            "id": plugin_id,
            "meta": source_cls.metadata(),
            "enabled": enabled.get(plugin_id, True),
        }
        for plugin_id, source_cls in sorted(registry.items())
    ]
    return {
        "presets": presets,
        "default_preset": source_settings.DEFAULT_SOURCE_PRESET,
        "source_toggles": source_toggles,
        "source_settings_path": str(source_settings.SOURCE_SETTINGS_PATH),
    }


def _one_shot_setup_defaults() -> dict:
    """Return the safe non-key defaults used by key-only one-shot setup."""
    from hedwig.quickstart import DEFAULT_INTEREST
    from hedwig.sources import settings as source_settings

    return {
        "storage_mode": EnvManager.DEFAULT_STORAGE_MODE,
        "interest_text": DEFAULT_INTEREST,
        "source_preset": source_settings.DEFAULT_SOURCE_PRESET,
        "delivery_target": "/feed",
        "delivery_required": False,
        "source_selection_required": False,
        "model_backend": dict(EnvManager.MODEL_BACKEND_DEFAULTS),
    }


def _first_feed_app_config() -> dict:
    """Seed app defaults needed by setup handoff and the first /feed render."""
    from hedwig.feeds import load_feeds
    from hedwig.personal_algorithm import DEFAULT_PERSONAL_ALGORITHM

    setup_defaults = _one_shot_setup_defaults()
    feeds_config = load_feeds() or {}
    configured_feeds = [
        feed
        for feed in feeds_config.get("feeds", [])
        if isinstance(feed, dict) and str(feed.get("id", "")).strip()
    ]
    feed_ids = [str(feed["id"]) for feed in configured_feeds]
    default_stream = str(feeds_config.get("default_feed") or "default").strip()
    if default_stream not in feed_ids:
        default_stream = feed_ids[0] if feed_ids else "default"

    feed_policy = DEFAULT_PERSONAL_ALGORITHM.get("feed") or {}
    valid_modes = {"grid", "detail_swipe", "dense_reader"}
    available_modes = [
        str(mode)
        for mode in feed_policy.get("available_modes", [])
        if str(mode) in valid_modes
    ]
    if not available_modes:
        available_modes = ["grid", "detail_swipe", "dense_reader"]
    default_mode = str(feed_policy.get("default_mode") or "grid")
    if default_mode not in available_modes:
        default_mode = "grid" if "grid" in available_modes else available_modes[0]

    return {
        "schema_version": "hedwig.first_feed_config.v1",
        "route": "/feed",
        "api_route": "/feed/api",
        "list_route": "/feed/list",
        "event_route": "/events/beacon",
        "default_stream": default_stream,
        "available_streams": feed_ids or [default_stream],
        "default_mode": default_mode,
        "available_modes": available_modes,
        "storage_mode": setup_defaults["storage_mode"],
        "delivery_target": setup_defaults["delivery_target"],
        "delivery_required": setup_defaults["delivery_required"],
        "source_preset": setup_defaults["source_preset"],
        "source_selection_required": setup_defaults["source_selection_required"],
        "interest_text": setup_defaults["interest_text"],
        "empty_state_recovery_target": "/setup",
        "source_recovery_target": "/settings",
        "post_setup_nav_targets": ["/chat", "/profile", "/status"],
    }


def _setup_option_location_map() -> list[dict[str, object]]:
    """Inventory existing setup/onboarding options and their /setup homes."""

    def labels(keys: dict[str, dict[str, object]]) -> list[str]:
        return [f"{key} - {meta['label']}" for key, meta in keys.items()]

    source_api_keys = {
        key: meta
        for key, meta in EnvManager.OPTIONAL_KEYS.items()
        if key not in EnvManager.MODEL_BACKEND_KEYS
    }
    delivery_options = labels(EnvManager.DELIVERY_KEYS) + [
        "Dashboard /feed - default delivery target",
        "Ambient and brief surfaces - optional after first feed",
    ]

    return [
        {
            "id": "required-local",
            "layer": "Essential",
            "title": "Required local setup",
            "href": "#setup-essential",
            "location": "Step 1: OpenAI key + local SQLite",
            "options": labels(EnvManager.REQUIRED_KEYS)
            + ["HEDWIG_STORAGE=sqlite - local SQLite default"],
        },
        {
            "id": "criteria-onboarding",
            "layer": "Optional steering",
            "title": "Criteria and onboarding",
            "href": "#setup-criteria",
            "location": "Step 2 plus Step 5 steering links",
            "options": [
                "interest_text - optional one-line interest seed",
                "Default AI-builder criteria - AI agents, LLM tooling, and research papers",
                "Socratic onboarding - /onboarding",
                "Auto onboarding - /onboarding/auto",
                "Natural-language steering - /chat and /criteria",
            ],
        },
        {
            "id": "source-defaults",
            "layer": "Sources",
            "title": "Source defaults and source toggles",
            "href": "#setup-sources",
            "location": "Step 3: automatic sources with collapsed overrides",
            "options": [
                "Registry default preset - derived from registry/source_settings",
                "Source toggles - same-page optional source enablement",
                "Source catalog - /sources",
                "Detailed source settings - /settings",
            ],
        },
        {
            "id": "advanced-storage",
            "layer": "Advanced",
            "title": "Storage backend",
            "href": "#setup-supabase-storage",
            "location": "Advanced: Storage backend and Supabase setup",
            "options": labels(EnvManager.STORAGE_KEYS),
        },
        {
            "id": "advanced-delivery",
            "layer": "Advanced",
            "title": "Delivery channels",
            "href": "#setup-delivery-configuration",
            "location": "Advanced: delivery channels",
            "options": delivery_options,
        },
        {
            "id": "advanced-source-api-keys",
            "layer": "Advanced",
            "title": "Source/API keys",
            "href": "#setup-source-api-keys",
            "location": "Advanced: source/API keys",
            "options": labels(source_api_keys),
        },
        {
            "id": "advanced-model-backend",
            "layer": "Advanced",
            "title": "Model/backend settings",
            "href": "#setup-model-backend-settings",
            "location": "Advanced: model/backend settings",
            "options": labels(EnvManager.MODEL_BACKEND_KEYS),
        },
        {
            "id": "advanced-profile-ownership",
            "layer": "Advanced",
            "title": "Profile, export/import, and ownership",
            "href": "#setup-profile",
            "location": "Advanced: profile and export/import sections",
            "options": [
                "Profile polish - /profile",
                "Algorithm export - /algorithm/export",
                "Algorithm import dry-run - /algorithm/import/dry-run",
                "Algorithm import confirm - /algorithm/import",
                "Sovereignty boundaries - /sovereignty",
            ],
        },
        {
            "id": "advanced-monitoring-tools",
            "layer": "Advanced",
            "title": "Monitoring and algorithm tools",
            "href": "#setup-status",
            "location": "Advanced links plus existing dashboard pages",
            "options": [
                "Runtime health and source status - /status",
                "Signals and feed recovery - /signals and /feed",
                "Evolution timeline - /evolution",
                "Meta tools - /meta",
                "Sandbox experiments - /sandbox",
                "General settings - /settings",
            ],
        },
    ]


def _feed_source_readiness() -> dict:
    """Return non-blocking source readiness context for the manual feed UI."""
    try:
        from hedwig.sources import get_registered_sources
        from hedwig.sources import settings as source_settings

        registry = get_registered_sources()
        enabled = source_settings.load_source_settings(registry=registry)
        enabled_source_ids = [
            plugin_id
            for plugin_id in sorted(registry)
            if enabled.get(plugin_id, True)
        ]
        return {
            "default_sources_available": bool(enabled_source_ids),
            "enabled_source_count": len(enabled_source_ids),
            "registered_source_count": len(registry),
            "enabled_source_preview": enabled_source_ids[:6],
            "settings_path": str(source_settings.SOURCE_SETTINGS_PATH),
        }
    except Exception:
        return {
            "default_sources_available": False,
            "enabled_source_count": 0,
            "registered_source_count": 0,
            "enabled_source_preview": [],
            "settings_path": "",
        }


def _setup_completion_state_path() -> Path:
    value = os.getenv("HEDWIG_SETUP_STATE_PATH", "").strip()
    if value:
        return Path(value).expanduser()
    return Path.cwd() / ".hedwig" / "setup_state.json"


def _load_setup_completion_state() -> dict:
    path = _setup_completion_state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _setup_criteria_path() -> Path:
    """Return the criteria path relevant to the current setup run."""
    try:
        from hedwig import config as hedwig_config

        return hedwig_config.CRITERIA_PATH
    except Exception:
        return Path.cwd() / "criteria.yaml"


def _setup_criteria_exists(path: Path) -> bool:
    """Detect whether setup has a local criteria config to rely on.

    The repository ships a default criteria.yaml. In isolated local setup
    contexts, do not treat that package default as the user's generated local
    config unless the dashboard is actually running from the repository root or
    the criteria path has been explicitly overridden.
    """
    if not path.exists():
        return False

    try:
        is_repo_default = path.resolve() == (REPO_ROOT / "criteria.yaml").resolve()
        cwd_is_repo = Path.cwd().resolve() == REPO_ROOT.resolve()
    except OSError:
        is_repo_default = False
        cwd_is_repo = False
    return bool(
        os.getenv("HEDWIG_CRITERIA_PATH") or not is_repo_default or cwd_is_repo
    )


def _persist_setup_completion_state(state: dict) -> dict:
    """Persist the first successful local one-shot completion marker."""
    path = _setup_completion_state_path()
    existing = _load_setup_completion_state()
    completed_at = existing.get("completed_at") or _utcnow().isoformat()
    delivery_configuration_deferred = bool(
        state.get("delivery_configuration_deferred")
    )
    delivery_configuration_deferred_at = ""
    if delivery_configuration_deferred:
        delivery_configuration_deferred_at = (
            existing.get("delivery_configuration_deferred_at") or completed_at
        )
    payload = {
        "schema_version": "hedwig.setup_state.v1",
        "completed": True,
        "completed_at": completed_at,
        "last_seen_at": _utcnow().isoformat(),
        "storage_mode": state["storage_mode"],
        "db_path": state["db_path"],
        "criteria_exists": state["criteria_exists"],
        "feed_items": state["feed_items"],
        "completion_action": state["completion_action"],
        "redirect_target": state["redirect_target"],
        "delivery_channels_configured": state["delivery_channels_configured"],
        "delivery_configuration_status": state["delivery_configuration_status"],
        "delivery_configuration_deferred": delivery_configuration_deferred,
        "delivery_configuration_deferred_at": delivery_configuration_deferred_at,
        "delivery_configuration_resume_target": state[
            "delivery_configuration_resume_target"
        ],
        "deferred_delivery_channels": state["deferred_delivery_channels"],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except Exception:
        payload["persist_error"] = True
        return payload
    payload["path"] = str(path)
    return payload


def _setup_feed_redirect_target(state: dict) -> str | None:
    """Return /feed only after setup is complete enough to leave /setup."""
    feed_items = int(state.get("feed_items") or 0)
    if (
        not state.get("setup_navigation_locked")
        and (
            state.get("setup_completed")
            or state.get("setup_complete")
            or state.get("first_collection_completed")
        )
        and state.get("feed_items_available")
        and state.get("first_feed_data_verified")
        and feed_items > 0
    ):
        return "/feed"
    return None


def _setup_feed_redirect_immediately(state: dict) -> bool:
    """Auto-handoff only after setup is fully complete, not partial readiness."""
    return bool(_setup_feed_redirect_target(state) == "/feed" and state.get("setup_completed"))


def _feed_navigation_readiness_model(
    *,
    openai_configured: bool,
    storage_mode: str,
    local_config_exists: bool,
    local_database_ready: bool,
    feed_items_available: bool,
    first_feed_data_verified: bool,
    first_collection_completed: bool,
    collection_failed: bool,
) -> dict:
    """Define the exact criteria that unlock setup's /feed handoff."""
    criteria = [
        {
            "id": "openai_local_mode",
            "label": "OPENAI_API_KEY saved and local SQLite active",
            "satisfied": bool(openai_configured and storage_mode == "sqlite"),
            "detail": "The minimum setup path is OpenAI-only local mode.",
        },
        {
            "id": "criteria_profile",
            "label": "Generated criteria profile is present",
            "satisfied": bool(local_config_exists),
            "detail": "Blank interests still generate the default AI-builder criteria.",
        },
        {
            "id": "local_sqlite_ready",
            "label": "Local SQLite database and schema are ready",
            "satisfied": bool(local_database_ready),
            "detail": "The first feed reads from the local SQLite signals table.",
        },
        {
            "id": "verified_feed_item",
            "label": "At least one verified feed item is readable",
            "satisfied": bool(feed_items_available and first_feed_data_verified),
            "detail": "The item must include the core fields required by /feed.",
        },
        {
            "id": "first_collection_completed",
            "label": "Tracked first collection has completed",
            "satisfied": bool(first_collection_completed),
            "detail": "Readable rows can appear early, but setup handoff waits for completion.",
        },
        {
            "id": "first_collection_not_failed",
            "label": "First collection did not fail",
            "satisfied": not collection_failed,
            "detail": "Failures keep recovery on /setup instead of redirecting away.",
        },
    ]
    blocking_ids = [
        criterion["id"] for criterion in criteria if not criterion["satisfied"]
    ]
    return {
        "schema_version": "hedwig.feed_navigation_readiness.v1",
        "criteria": criteria,
        "ready": not blocking_ids,
        "blocked": bool(blocking_ids),
        "blocking_criteria_ids": blocking_ids,
        "available_after_setup_complete": not blocking_ids,
        "redirect_target_when_ready": "/feed",
    }


def _setup_requirement(
    *,
    requirement_id: str,
    label: str,
    configured: bool,
    required_for_completion: bool,
    target: str,
    status: str | None = None,
    detail: str = "",
) -> dict:
    """Build one JSON-ready setup requirement record."""
    if status is None:
        if configured:
            status = "satisfied"
        elif required_for_completion:
            status = "blocking"
        else:
            status = "optional"
    return {
        "id": requirement_id,
        "label": label,
        "status": status,
        "configured": configured,
        "required_for_completion": required_for_completion,
        "blocking": bool(required_for_completion and not configured),
        "non_blocking": not required_for_completion,
        "target": target,
        "detail": detail,
    }


def _setup_state_readiness_model(state: dict) -> dict:
    """Summarize partial readiness without implying setup is complete."""
    feed_navigation_ready = bool(state.get("feed_navigation_ready"))
    feed_navigation_available = bool(state.get("feed_navigation_available"))
    return {
        "minimum_required_inputs_saved": bool(state.get("local_ready")),
        "openai_ready": bool(state.get("openai_configured")),
        "local_mode_ready": bool(state.get("local_ready")),
        "criteria_ready": bool(state.get("criteria_exists")),
        "local_database_ready": bool(state.get("local_database_ready")),
        "first_feed_ready": feed_navigation_ready,
        "feed_data_usable": feed_navigation_ready,
        "first_feed_usable_before_collection_complete": bool(
            state.get("first_feed_usable_before_collection_complete")
        ),
        "feed_navigation_available": feed_navigation_available,
        "feed_navigation_blocked": bool(state.get("feed_navigation_blocked")),
        "feed_navigation_blocking_criteria_ids": state.get(
            "feed_navigation_blocking_criteria_ids", []
        ),
        "collection_incomplete": bool(state.get("collection_process_incomplete")),
        "first_collection_completed": bool(state.get("first_collection_completed")),
        "can_start_first_run": bool(
            state.get("openai_configured") and state.get("storage_mode") == "sqlite"
        ),
        "can_open_feed": feed_navigation_ready,
        "first_run_status": state.get("first_run_status", "not_started"),
        "progress_percent": int(state.get("progress_percent") or 0),
    }


def _setup_state_requirements_model(state: dict) -> dict:
    """Classify first-run blockers separately from advanced, non-blocking options."""
    requirements = [
        _setup_requirement(
            requirement_id="openai_api_key",
            label="OPENAI_API_KEY configured",
            configured=bool(state.get("openai_configured")),
            required_for_completion=True,
            target="#setup-essential",
            detail="Required for local scoring, criteria generation, and /chat.",
        ),
        _setup_requirement(
            requirement_id="local_sqlite_storage",
            label="Local SQLite storage selected",
            configured=state.get("storage_mode") == "sqlite",
            required_for_completion=True,
            target="#setup-essential",
            detail="The one-shot setup path writes HEDWIG_STORAGE=sqlite.",
        ),
        _setup_requirement(
            requirement_id="criteria_profile",
            label="Criteria profile generated",
            configured=bool(state.get("criteria_exists")),
            required_for_completion=True,
            target="#setup-criteria",
            detail="Blank interests use the default AI-builder criteria.",
        ),
        _setup_requirement(
            requirement_id="local_sqlite_schema",
            label="Local SQLite schema ready",
            configured=bool(state.get("local_database_ready")),
            required_for_completion=True,
            target="#setup-progress",
            detail="Created automatically before the first feed run.",
        ),
        _setup_requirement(
            requirement_id="first_feed_items",
            label="First feed items available",
            configured=bool(state.get("feed_navigation_ready")),
            required_for_completion=True,
            target="#setup-completion",
            detail="Setup remains on /setup until /feed has readable items.",
        ),
        _setup_requirement(
            requirement_id="first_collection_completed",
            label="First collection completed",
            configured=bool(
                not state.get("feed_navigation_ready")
                or state.get("first_collection_completed")
            ),
            required_for_completion=True,
            target="#setup-progress",
            detail=(
                "Readable feed rows can be opened early, but setup completion "
                "waits for the tracked first collection to finish."
            ),
        ),
        _setup_requirement(
            requirement_id="source_defaults",
            label="Default source set selected",
            configured=True,
            required_for_completion=False,
            target="#setup-sources",
            status="default_ready",
            detail="Uses the existing registry/source_settings defaults.",
        ),
        _setup_requirement(
            requirement_id="supabase_storage",
            label="Supabase storage configured",
            configured=state.get("storage_mode") == "supabase",
            required_for_completion=False,
            target="#setup-supabase-storage",
            status="advanced_optional",
            detail="Hosted/team storage is optional for first-run local setup.",
        ),
        _setup_requirement(
            requirement_id="delivery_channels",
            label="External delivery channels configured",
            configured=bool(state.get("delivery_channels_configured")),
            required_for_completion=False,
            target="#setup-delivery-configuration",
            status=state.get("delivery_configuration_status", "deferred"),
            detail="Dashboard /feed is the default delivery target.",
        ),
        _setup_requirement(
            requirement_id="source_api_keys",
            label="Advanced source API keys configured",
            configured=False,
            required_for_completion=False,
            target="#setup-source-api-keys",
            status="advanced_optional",
            detail="Optional keys can improve source coverage after setup.",
        ),
        _setup_requirement(
            requirement_id="profile_export_import",
            label="Profile polish and export/import reviewed",
            configured=False,
            required_for_completion=False,
            target="#setup-profile",
            status="advanced_optional",
            detail="Ownership and portability tools remain reachable after setup.",
        ),
        _setup_requirement(
            requirement_id="model_backend_settings",
            label="Model/backend settings reviewed",
            configured=True,
            required_for_completion=False,
            target="#setup-model-backend-settings",
            status="default_ready",
            detail="Default OpenAI model/backend settings are applied automatically.",
        ),
    ]
    blocking = [
        requirement for requirement in requirements if requirement["blocking"]
    ]
    non_blocking = [
        requirement
        for requirement in requirements
        if requirement["non_blocking"]
    ]
    return {
        "requirements": requirements,
        "blocking_setup_requirements": blocking,
        "non_blocking_setup_requirements": non_blocking,
        "blocking_requirement_ids": [
            requirement["id"] for requirement in blocking
        ],
        "non_blocking_requirement_ids": [
            requirement["id"] for requirement in non_blocking
        ],
    }


def _setup_status_from_state(state: dict, blocking_requirements: list[dict]) -> str:
    if state.get("setup_completed"):
        return "complete"
    if not state.get("openai_configured") or state.get("storage_mode") != "sqlite":
        return "blocked"
    if blocking_requirements:
        return "partial_ready"
    if state.get("feed_navigation_ready"):
        return "complete"
    return "ready"


def _setup_state_api_payload(state: dict) -> dict:
    """Return the public setup-state API payload shared by setup status routes."""
    redirect_to = _setup_feed_redirect_target(state)
    readiness = _setup_state_readiness_model(state)
    requirements_model = _setup_state_requirements_model(state)
    blocking_requirements = requirements_model["blocking_setup_requirements"]
    setup_status = _setup_status_from_state(state, blocking_requirements)
    return {
        "ok": True,
        "schema_version": "hedwig.setup_state_api.v1",
        "setup_status": setup_status,
        "setup_complete": bool(state.get("setup_completed")),
        "setup_completion_blocked": bool(blocking_requirements),
        "partial_readiness": readiness,
        "requirements": requirements_model["requirements"],
        "blocking_setup_requirements": blocking_requirements,
        "non_blocking_setup_requirements": requirements_model[
            "non_blocking_setup_requirements"
        ],
        "blocking_requirement_ids": requirements_model["blocking_requirement_ids"],
        "non_blocking_requirement_ids": requirements_model[
            "non_blocking_requirement_ids"
        ],
        "collection_progress": _collection_progress_model(state),
        "state": state,
        "first_feed_config": _first_feed_app_config(),
        "redirect_to": redirect_to,
        "redirect_immediately": _setup_feed_redirect_immediately(state),
    }


def _collection_progress_model(state: dict) -> dict:
    """Normalize setup/feed progress into a direct polling-friendly model."""
    progress = state.get("collection_progress") or {}
    counts = state.get("collection_progress_counts") or progress.get("counts") or {}
    errors = state.get("collection_progress_errors") or progress.get("errors") or []
    status = str(
        state.get("collection_progress_status")
        or progress.get("status")
        or state.get("first_run_status")
        or "not_started"
    )
    terminal_statuses = {"completed", "failed", "no_items"}
    feed_items = int(state.get("feed_items") or 0)
    feed_items_available = bool(state.get("feed_items_available") and feed_items > 0)
    setup_complete = bool(state.get("setup_complete") or state.get("setup_completed"))
    collection_process_incomplete = bool(state.get("collection_process_incomplete"))
    return {
        "schema_version": "hedwig.collection_progress.v1",
        "run_id": progress.get("id"),
        "run_type": progress.get("run_type") or "daily",
        "status": status,
        "first_run_status": state.get("first_run_status", "not_started"),
        "first_run_active": bool(state.get("first_run_active")),
        "setup_complete": setup_complete,
        "feed_items_available": feed_items_available,
        "feed_items": feed_items,
        "feed_data_usable": bool(state.get("feed_navigation_ready")),
        "collection_process_incomplete": collection_process_incomplete,
        "first_feed_usable_before_collection_complete": bool(
            state.get("first_feed_usable_before_collection_complete")
        ),
        "progress_percent": int(state.get("progress_percent") or 0),
        "counts": {
            "posts_collected": int(counts.get("posts_collected") or 0),
            "posts_filtered": int(counts.get("posts_filtered") or 0),
            "signals_scored": int(counts.get("signals_scored") or 0),
            "signals_saved": int(counts.get("signals_saved") or 0),
            "alerts_count": int(counts.get("alerts_count") or 0),
            "digest_count": int(counts.get("digest_count") or 0),
            "skipped_count": int(counts.get("skipped_count") or 0),
        },
        "errors": errors if isinstance(errors, list) else [],
        "metadata": progress.get("metadata")
        if isinstance(progress.get("metadata"), dict)
        else {},
        "started_at": progress.get("started_at") or "",
        "last_updated_at": (
            state.get("collection_progress_last_updated_at")
            or progress.get("last_updated_at")
            or ""
        ),
        "completed_at": progress.get("completed_at") or "",
        "is_active": bool(state.get("first_run_active")),
        "is_terminal": bool(
            status in terminal_statuses
            or setup_complete
            or (feed_items_available and not collection_process_incomplete)
        ),
        "completion_action": state.get("completion_action", "/feed"),
        "redirect_target": _setup_feed_redirect_target(state),
    }


def _collection_progress_api_payload(state: dict, *, endpoint: str) -> dict:
    progress = _collection_progress_model(state)
    redirect_to = _setup_feed_redirect_target(state)
    return {
        "ok": True,
        "schema_version": "hedwig.collection_progress_api.v1",
        "polling": {
            "endpoint": endpoint,
            "interval_ms": 2500,
            "method": "GET",
        },
        "collection_progress": progress,
        "setup_status": state.get("setup_status", "unknown"),
        "setup_complete": bool(state.get("setup_complete")),
        "partial_readiness": _setup_state_readiness_model(state),
        "feed_items_available": bool(progress["feed_items_available"]),
        "state": state,
        "redirect_to": redirect_to,
        "redirect_immediately": _setup_feed_redirect_immediately(state),
    }


def _feed_api_setup_readiness(
    env_manager: EnvManager,
    *,
    readable_item_count: int,
) -> dict:
    """Expose feed API readability without requiring setup completion."""
    try:
        state = _one_shot_setup_state(env_manager, persist_completion=False)
    except Exception as exc:
        return {
            "setup_complete": False,
            "setup_status": "unknown",
            "setup_completion_blocked": True,
            "partial_readiness": {
                "first_feed_ready": readable_item_count > 0,
                "can_open_feed": readable_item_count > 0,
            },
            "feed_items_available": readable_item_count > 0,
            "readable_feed_items": readable_item_count,
            "can_read_feed_data": readable_item_count > 0,
            "requires_setup_complete": False,
            "feed_navigation_available": False,
            "feed_navigation_readiness": {},
            "feed_navigation_blocking_criteria_ids": [],
            "blocking_requirement_ids": [],
            "completion_action": "/feed",
            "error": str(exc),
        }

    partial_readiness = _setup_state_readiness_model(state)
    feed_items_available = bool(
        readable_item_count > 0 or state.get("feed_items_available")
    )
    return {
        "setup_complete": bool(state.get("setup_completed")),
        "setup_status": state.get("setup_status", "unknown"),
        "setup_completion_blocked": bool(state.get("setup_completion_blocked")),
        "partial_readiness": partial_readiness,
        "feed_items_available": feed_items_available,
        "readable_feed_items": readable_item_count,
        "can_read_feed_data": feed_items_available,
        "requires_setup_complete": False,
        "first_feed_usable_before_collection_complete": bool(
            state.get("first_feed_usable_before_collection_complete")
        ),
        "feed_navigation_available": bool(state.get("feed_navigation_available")),
        "feed_navigation_readiness": state.get("feed_navigation_readiness", {}),
        "feed_navigation_blocking_criteria_ids": state.get(
            "feed_navigation_blocking_criteria_ids", []
        ),
        "collection_process_incomplete": bool(
            state.get("collection_process_incomplete")
        ),
        "blocking_requirement_ids": state.get("blocking_requirement_ids", []),
        "completion_action": state.get("completion_action", "/feed"),
    }


def _one_shot_setup_state(
    env_manager: EnvManager,
    *,
    persist_completion: bool = True,
) -> dict:
    """Return non-blocking first-run status for the /setup entry point."""
    values = env_manager.load()
    env_file_exists = env_manager.env_path.exists()
    storage_mode = (values.get("HEDWIG_STORAGE") or "sqlite").strip().lower()
    if storage_mode == "local":
        storage_mode = "sqlite"

    criteria_path = _setup_criteria_path()
    criteria_exists = _setup_criteria_exists(criteria_path)

    db_path = ""
    db_file_exists = False
    db_exists = False
    db_schema_ready = False
    db_read_error = ""
    feed_items = 0
    first_feed_item: dict[str, object] | None = None
    first_feed_data_verified = False
    collection_progress: dict[str, object] = {}
    if storage_mode == "sqlite":
        try:
            from hedwig.storage import local as local_storage

            local_db_path = local_storage._db_path()
            db_path = str(local_db_path)
            db_file_exists = local_db_path.exists()
            db_exists = db_file_exists
            if db_file_exists:
                with sqlite3.connect(str(local_db_path)) as conn:
                    table = conn.execute(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type = 'table' AND name = 'signals'
                        """
                    ).fetchone()
                    db_schema_ready = bool(table)
                    if db_schema_ready:
                        row = conn.execute("SELECT COUNT(*) FROM signals").fetchone()
                        feed_items = int(row[0] or 0) if row else 0
                        columns = {
                            str(column[1])
                            for column in conn.execute(
                                "PRAGMA table_info(signals)"
                            ).fetchall()
                        }
                        optional_columns = [
                            column if column in columns else f"NULL AS {column}"
                            for column in (
                                "url",
                                "content",
                                "author",
                                "relevance_score",
                                "urgency",
                                "why_relevant",
                                "collected_at",
                            )
                        ]
                        order_columns = [
                            f"{column} DESC"
                            for column in ("collected_at", "relevance_score")
                            if column in columns
                        ]
                        order_columns.append("id DESC")
                        sample = conn.execute(
                            f"""
                            SELECT id, platform, external_id, title,
                                   {", ".join(optional_columns)}
                            FROM signals
                            ORDER BY {", ".join(order_columns)}
                            LIMIT 1
                            """
                        ).fetchone()
                        if sample:
                            first_feed_item = {
                                "id": sample[0],
                                "platform": sample[1],
                                "external_id": sample[2],
                                "title": sample[3],
                                "url": sample[4],
                                "content": sample[5],
                                "author": sample[6],
                                "relevance_score": sample[7],
                                "urgency": sample[8],
                                "why_relevant": sample[9],
                                "collected_at": sample[10],
                            }
                            first_feed_data_verified = bool(
                                first_feed_item["id"]
                                and first_feed_item["platform"]
                                and first_feed_item["external_id"]
                                and first_feed_item["title"]
                            )
                    progress_table = conn.execute(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type = 'table' AND name = 'collection_runs'
                        """
                    ).fetchone()
                    if progress_table:
                        progress_sample = conn.execute(
                            """
                            SELECT id, run_type, status, posts_collected,
                                   posts_filtered, signals_scored, signals_saved,
                                   alerts_count, digest_count, skipped_count,
                                   errors, metadata, started_at, last_updated_at,
                                   completed_at
                            FROM collection_runs
                            ORDER BY last_updated_at DESC, id DESC
                            LIMIT 1
                            """
                        ).fetchone()
                        if progress_sample:
                            try:
                                progress_errors = json.loads(
                                    progress_sample[10] or "[]"
                                )
                            except Exception:
                                progress_errors = []
                            try:
                                progress_metadata = json.loads(
                                    progress_sample[11] or "{}"
                                )
                            except Exception:
                                progress_metadata = {}
                            collection_progress = {
                                "id": progress_sample[0],
                                "run_type": progress_sample[1],
                                "status": progress_sample[2],
                                "counts": {
                                    "posts_collected": int(progress_sample[3] or 0),
                                    "posts_filtered": int(progress_sample[4] or 0),
                                    "signals_scored": int(progress_sample[5] or 0),
                                    "signals_saved": int(progress_sample[6] or 0),
                                    "alerts_count": int(progress_sample[7] or 0),
                                    "digest_count": int(progress_sample[8] or 0),
                                    "skipped_count": int(progress_sample[9] or 0),
                                },
                                "errors": progress_errors
                                if isinstance(progress_errors, list)
                                else [],
                                "metadata": progress_metadata
                                if isinstance(progress_metadata, dict)
                                else {},
                                "started_at": progress_sample[12],
                                "last_updated_at": progress_sample[13],
                                "completed_at": progress_sample[14],
                            }
        except Exception as exc:
            db_read_error = str(exc)
            feed_items = 0
            first_feed_item = None
            first_feed_data_verified = False

    openai_configured = bool(values.get("OPENAI_API_KEY"))
    local_ready = bool(openai_configured and storage_mode == "sqlite")
    delivery_channels_configured = bool(
        values.get("SLACK_WEBHOOK_ALERTS")
        or values.get("SLACK_WEBHOOK_DAILY")
        or values.get("DISCORD_WEBHOOK_ALERTS")
        or values.get("DISCORD_WEBHOOK_DAILY")
        or values.get("DISCORD_WEBHOOK_WEEKLY")
        or (values.get("SMTP_HOST") and values.get("SMTP_FROM"))
    )
    delivery_configuration_deferred = not delivery_channels_configured
    delivery_configuration_resume_target = "/setup#setup-delivery-configuration"
    deferred_delivery_channels = (
        ["slack", "discord", "smtp"] if delivery_configuration_deferred else []
    )
    local_config_exists = bool(env_file_exists and criteria_exists)
    local_database_ready = bool(db_exists and db_schema_ready)
    missing_local_state = []
    if not env_file_exists:
        missing_local_state.append(".env")
    if not openai_configured:
        missing_local_state.append("OPENAI_API_KEY")
    if not criteria_exists:
        missing_local_state.append("criteria.yaml")
    if storage_mode == "sqlite":
        if not db_exists:
            missing_local_state.append("sqlite database")
        elif not db_schema_ready:
            missing_local_state.append("sqlite signals table")
    if not feed_items:
        missing_local_state.append("feed items")
    feed_items_available = feed_items > 0
    feed_navigation_ready = bool(feed_items_available and first_feed_data_verified)
    if feed_items_available and not first_feed_data_verified:
        missing_local_state.append("verified feed item")

    collection_status = str(collection_progress.get("status") or "")
    collection_errors = collection_progress.get("errors") or []
    minimum_ready = bool(local_ready and criteria_exists and local_database_ready)
    collection_running = collection_status in {
        "queued",
        "running",
        "collected",
        "filtered",
        "scored",
        "routed",
        "saved",
    }
    collection_failed = collection_status == "failed"
    collection_no_items = bool(
        collection_status == "no_items"
        or (collection_status == "completed" and minimum_ready and feed_items == 0)
    )
    collection_terminal_attention = bool(collection_failed or collection_no_items)
    collection_counts = collection_progress.get("counts", {})
    collection_terminal_statuses = {"completed", "failed", "no_items"}
    collection_process_started = bool(collection_progress)
    tracked_feed_rows_saved = bool(
        int(collection_counts.get("signals_saved") or 0) > 0
        or collection_status == "saved"
    )
    collection_process_complete = bool(
        not collection_process_started
        or collection_status in collection_terminal_statuses
        or (feed_navigation_ready and not tracked_feed_rows_saved)
    )
    first_collection_completed = bool(
        not collection_process_started
        or collection_status == "completed"
        or (feed_navigation_ready and not tracked_feed_rows_saved)
    )

    first_run_status = "ready" if feed_navigation_ready else "not_started"
    if feed_navigation_ready and not first_collection_completed:
        first_run_status = "feed_ready_collection_finishing"
    if collection_failed:
        first_run_status = "failed"
    elif collection_no_items:
        first_run_status = "no_items"
    elif local_ready and db_schema_ready and feed_items == 0:
        first_run_status = "waiting_for_feed_items"
    elif feed_items_available and not first_feed_data_verified:
        first_run_status = "waiting_for_verified_feed_item"
    elif local_ready and criteria_exists and not local_database_ready:
        first_run_status = "ready_to_run"
    first_run_active = bool(
        minimum_ready
        and not collection_terminal_attention
        and (
            (feed_items == 0 and (collection_running or not collection_progress))
            or (
                feed_items > 0
                and collection_running
                and not collection_process_complete
            )
        )
    )
    progress_percent = 20
    if feed_navigation_ready and not first_collection_completed:
        progress_percent = 95
    elif feed_navigation_ready:
        progress_percent = 100
    elif feed_items_available:
        progress_percent = 90
    elif collection_failed:
        has_progress_counts = any(int(value or 0) > 0 for value in collection_counts.values())
        progress_percent = 90 if has_progress_counts else 0
    elif collection_no_items:
        progress_percent = 90
    elif collection_status == "scored":
        progress_percent = 85
    elif collection_status == "filtered":
        progress_percent = 75
    elif collection_status == "collected":
        progress_percent = 70
    elif first_run_active:
        progress_percent = 80
    elif local_ready and criteria_exists:
        progress_percent = 60
    elif local_ready:
        progress_percent = 40

    feed_navigation_readiness = _feed_navigation_readiness_model(
        openai_configured=openai_configured,
        storage_mode=storage_mode,
        local_config_exists=local_config_exists,
        local_database_ready=local_database_ready,
        feed_items_available=feed_items_available,
        first_feed_data_verified=first_feed_data_verified,
        first_collection_completed=first_collection_completed,
        collection_failed=collection_failed,
    )
    setup_completion_valid = bool(feed_navigation_readiness["ready"])
    setup_navigation_locked = bool(first_run_active and not setup_completion_valid)
    state = {
        "storage_mode": storage_mode,
        "openai_configured": openai_configured,
        "local_ready": local_ready,
        "env_file_exists": env_file_exists,
        "env_path": str(env_manager.env_path),
        "local_config_exists": local_config_exists,
        "delivery_channels_configured": delivery_channels_configured,
        "delivery_optional": True,
        "delivery_required_for_completion": False,
        "delivery_configuration_status": (
            "configured" if delivery_channels_configured else "deferred"
        ),
        "delivery_configuration_deferred": delivery_configuration_deferred,
        "delivery_configuration_resume_target": delivery_configuration_resume_target,
        "deferred_delivery_channels": deferred_delivery_channels,
        "criteria_exists": criteria_exists,
        "criteria_path": str(criteria_path),
        "db_path": db_path,
        "db_file_exists": db_file_exists,
        "db_exists": db_exists,
        "db_schema_ready": db_schema_ready,
        "db_read_error": db_read_error,
        "local_database_ready": local_database_ready,
        "feed_items": feed_items,
        "feed_items_available": feed_items_available,
        "first_feed_data_verified": first_feed_data_verified,
        "first_feed_item": first_feed_item,
        "feed_navigation_ready": feed_navigation_ready,
        "feed_navigation_available": setup_completion_valid,
        "feed_navigation_readiness": feed_navigation_readiness,
        "feed_navigation_criteria": feed_navigation_readiness["criteria"],
        "feed_navigation_blocking_criteria_ids": feed_navigation_readiness[
            "blocking_criteria_ids"
        ],
        "feed_navigation_blocked": feed_navigation_readiness["blocked"],
        "feed_data_usable": feed_navigation_ready,
        "collection_process_started": collection_process_started,
        "collection_process_complete": collection_process_complete,
        "collection_process_incomplete": not collection_process_complete,
        "first_collection_completed": first_collection_completed,
        "first_feed_usable_before_collection_complete": bool(
            feed_navigation_ready and not collection_process_complete
        ),
        "first_feed_config": _first_feed_app_config(),
        "missing_local_state": missing_local_state,
        "first_run_status": first_run_status,
        "collection_progress": collection_progress,
        "collection_progress_status": collection_status,
        "collection_progress_counts": collection_counts,
        "collection_progress_errors": collection_errors
        if isinstance(collection_errors, list)
        else [],
        "collection_progress_last_updated_at": collection_progress.get(
            "last_updated_at", ""
        ),
        "collection_progress_started_at": collection_progress.get("started_at", ""),
        "first_run_active": first_run_active,
        "collection_failed": collection_failed,
        "collection_no_items": collection_no_items,
        "collection_terminal_attention": collection_terminal_attention,
        "collection_slow_progress": bool(
            first_run_active and not setup_completion_valid
        ),
        "setup_navigation_locked": setup_navigation_locked,
        "completion_navigation_disabled": setup_navigation_locked,
        "navigation_lock_reason": (
            "first_collection_in_progress" if setup_navigation_locked else ""
        ),
        "navigation_lock_target": "/setup#setup-progress",
        "minimum_ready": minimum_ready,
        "progress_percent": progress_percent,
        "completion_action": "/feed",
        "redirect_target": "/feed"
        if feed_navigation_ready and not setup_navigation_locked
        else None,
    }
    persisted_completion = _load_setup_completion_state()
    if setup_completion_valid and persist_completion:
        persisted_completion = _persist_setup_completion_state(state)

    persisted_setup_completed = bool(persisted_completion.get("completed"))
    setup_completed = bool(setup_completion_valid and persisted_setup_completed)
    setup_completion_stale = bool(
        persisted_setup_completed and not setup_completion_valid
    )
    state.update(
        {
            "setup_completed": setup_completed,
            "persisted_setup_completed": persisted_setup_completed,
            "setup_completion_stale": setup_completion_stale,
            "setup_completed_at": persisted_completion.get("completed_at", ""),
            "setup_completion_persisted": setup_completed
            and not persisted_completion.get("persist_error", False),
            "setup_state_path": persisted_completion.get(
                "path", str(_setup_completion_state_path())
            )
            if persisted_setup_completed
            else str(_setup_completion_state_path()),
            "persisted_feed_items": int(persisted_completion.get("feed_items") or 0)
            if persisted_setup_completed
            else 0,
            "delivery_configuration_deferred_at": persisted_completion.get(
                "delivery_configuration_deferred_at", ""
            )
            if persisted_setup_completed
            else "",
        }
    )
    readiness = _setup_state_readiness_model(state)
    requirements_model = _setup_state_requirements_model(state)
    blocking_requirements = requirements_model["blocking_setup_requirements"]
    state.update(
        {
            "setup_status": _setup_status_from_state(state, blocking_requirements),
            "setup_complete": setup_completed,
            "setup_completion_blocked": bool(blocking_requirements),
            "partial_readiness": readiness,
            "requirements": requirements_model["requirements"],
            "blocking_setup_requirements": blocking_requirements,
            "non_blocking_setup_requirements": requirements_model[
                "non_blocking_setup_requirements"
            ],
            "blocking_requirement_ids": requirements_model[
                "blocking_requirement_ids"
            ],
            "non_blocking_requirement_ids": requirements_model[
                "non_blocking_requirement_ids"
            ],
        }
    )
    return state


def _jsonable(obj):
    """Deep-convert a Python value into something JSONResponse can serialize.

    Handles datetime/date values from yaml.safe_load (the `updated_at` key in
    algorithm.yaml resolves to a date, which JSON cannot encode directly).
    """
    from datetime import date, datetime as _dt

    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (date, _dt)):
        return obj.isoformat()
    return obj


def _coerce_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    text = str(value).strip()
    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _load_evolution_logs() -> list[dict]:
    from hedwig.config import EVOLUTION_LOG_PATH

    if not EVOLUTION_LOG_PATH.exists():
        return []

    logs = []
    for line in EVOLUTION_LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            logs.append(payload)
    return logs


def _count_evolution_cycles() -> int:
    return len(_load_evolution_logs())


def _load_dashboard_stats(user_id: str | None = None) -> dict:
    if user_id is None:
        stats = _load_dashboard_activity_stats()
    else:
        stats = _load_dashboard_activity_stats(user_id=user_id)
    return {
        "total_signals": int(stats.get("total_signals", 0) or 0),
        "upvote_ratio": float(stats.get("upvote_ratio", 0.0) or 0.0),
        "evolution_cycles": _count_evolution_cycles(),
        "top_5_sources": list(stats.get("top_5_sources", []) or []),
        "days_active": int(stats.get("days_active", 0) or 0),
    }


def _serialize_signal_export(signal: dict) -> dict:
    try:
        from hedwig.storage import SIGNAL_EXPORT_FIELDS
    except Exception:
        SIGNAL_EXPORT_FIELDS = (
            "id",
            "platform",
            "title",
            "url",
            "content",
            "author",
            "relevance_score",
            "urgency",
            "published_at",
            "collected_at",
        )

    return {field: signal.get(field) for field in SIGNAL_EXPORT_FIELDS}


def _load_recent_evolution(limit: int = 5) -> list[dict]:
    return list(reversed(_load_evolution_logs()))[:limit]


def _load_criteria() -> dict:
    from hedwig.config import load_criteria
    try:
        return load_criteria()
    except Exception:
        return {}


def _count_sources() -> int:
    try:
        from hedwig.sources import get_registered_sources
        return len(get_registered_sources())
    except Exception:
        return 0


def _latest_run_timestamp(logs: list[dict], cycle_type: str) -> str | None:
    latest: datetime | None = None
    for log in logs:
        if str(log.get("cycle_type", "")).lower() != cycle_type:
            continue
        timestamp = _coerce_timestamp(log.get("timestamp"))
        if timestamp is None:
            continue
        if latest is None or timestamp > latest:
            latest = timestamp
    return latest.isoformat() if latest else None


def _empty_run_stats() -> dict[str, object]:
    return {
        "consecutive_daily_runs": 0,
        "total_daily_cycles": 0,
        "total_weekly_cycles": 0,
        "last_daily_at": None,
        "last_weekly_at": None,
    }


def _summarize_run_rows(rows: list[dict]) -> dict[str, object]:
    stats = _empty_run_stats()
    daily_times: list[datetime] = []
    weekly_times: list[datetime] = []

    for row in rows:
        cycle_type = str(row.get("cycle_type") or "").strip().lower()
        run_at = _coerce_timestamp(row.get("run_at"))
        if run_at is None:
            continue
        if cycle_type == "daily":
            daily_times.append(run_at)
        elif cycle_type == "weekly":
            weekly_times.append(run_at)

    if daily_times:
        stats["total_daily_cycles"] = len(daily_times)
        stats["last_daily_at"] = max(daily_times).isoformat()

        streak = 0
        expected_day = None
        for run_day in sorted({run_at.date() for run_at in daily_times}, reverse=True):
            if expected_day is None or run_day == expected_day:
                streak += 1
                expected_day = run_day - timedelta(days=1)
                continue
            break
        stats["consecutive_daily_runs"] = streak

    if weekly_times:
        stats["total_weekly_cycles"] = len(weekly_times)
        stats["last_weekly_at"] = max(weekly_times).isoformat()

    return stats


def _legacy_run_stats() -> dict[str, object]:
    logs = _load_evolution_logs()
    return _summarize_run_rows(
        [
            {
                "cycle_type": log.get("cycle_type"),
                "run_at": log.get("timestamp"),
            }
            for log in logs
        ]
    )


def _load_run_stats() -> dict[str, object]:
    stats = _legacy_run_stats()
    try:
        from hedwig.storage import get_run_stats

        storage_stats = get_run_stats() or {}
    except Exception:
        return stats

    merged = dict(stats)
    for key in ("consecutive_daily_runs", "total_daily_cycles", "total_weekly_cycles"):
        merged[key] = int(storage_stats.get(key, merged[key]) or 0)
    for key in ("last_daily_at", "last_weekly_at"):
        if storage_stats.get(key):
            merged[key] = storage_stats[key]
    return merged


def _load_health_status(started_at: datetime | None = None) -> dict:
    run_stats = _load_run_stats()
    started = _coerce_timestamp(started_at)
    uptime_seconds = 0
    if started is not None:
        uptime_seconds = max(int((_utcnow() - started).total_seconds()), 0)

    return {
        **run_stats,
        "last_daily_run": run_stats["last_daily_at"],
        "last_weekly_run": run_stats["last_weekly_at"],
        "evolution_cycle_count": (
            int(run_stats["total_daily_cycles"]) + int(run_stats["total_weekly_cycles"])
        ),
        "source_count": _count_sources(),
        "uptime_seconds": uptime_seconds,
    }


def run(host: str = "127.0.0.1", port: int = 8765, saas: bool = False):
    """Run the dashboard web server."""
    import uvicorn

    mode = "SaaS" if saas else "Single-user"
    print(f"\n🦉 Hedwig Dashboard ({mode}) running at http://{host}:{port}\n")
    uvicorn.run(create_app(saas_mode=saas), host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
