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
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from hedwig.dashboard.db_setup import create_tables, get_schema_sql
from hedwig.dashboard.env_manager import EnvManager
from hedwig.dashboard.generative import GenerativeDashboard
from hedwig.dashboard.validator import test_all

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parents[1]
ASSETS_DIR = REPO_ROOT / "assets"
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))


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
        metadata = EnvManager.all_key_metadata()
        status = env_manager.get_status()
        return TEMPLATES.TemplateResponse(
            request,
            "setup.html",
            {
                "values": values,
                "metadata": metadata,
                "required_keys": EnvManager.REQUIRED_KEYS,
                "delivery_keys": EnvManager.DELIVERY_KEYS,
                "optional_keys": EnvManager.OPTIONAL_KEYS,
                "status": status,
            },
        )

    @app.post("/setup/save")
    async def setup_save(request: Request):
        form = await request.form()
        values = {k: v for k, v in form.items() if v}
        env_manager.save(values)
        return JSONResponse({"ok": True, "message": "Saved to .env"})

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
        from hedwig.storage import save_feedback

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
        save_feedback(fb, user_id=user_id)

        return JSONResponse({"ok": True, "vote": vote})

    # -----------------------------------------------------------------------
    # Pipeline control
    # -----------------------------------------------------------------------

    @app.post("/run/daily")
    async def run_daily():
        """Trigger a daily run in background."""
        subprocess.Popen(
            [sys.executable, "-m", "hedwig"],
            cwd=str(Path.cwd()),
        )
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
                "saved": request.query_params.get("saved") == "1",
                "saved_message": saved_message,
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
    # SaaS routes (landing, auth, billing) — only when saas_mode=True
    # -----------------------------------------------------------------------

    if saas_mode:
        _register_saas_routes(app)

    return app


def _register_saas_routes(app: FastAPI):
    """Register multi-tenant SaaS routes (landing, auth, billing, OAuth, auto-context)."""
    if not getattr(app.state, "saas_mode", False):
        raise RuntimeError("_register_saas_routes requires saas_mode=True")

    from hedwig.saas import auth as saas_auth
    from hedwig.saas import billing as saas_billing
    from hedwig.saas import oauth as saas_oauth
    from hedwig.saas.auto_context import AutoContextInference
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

    # ------- Auto-context onboarding -------

    @app.get("/onboarding/auto", response_class=HTMLResponse)
    async def auto_onboarding_page(request: Request):
        return TEMPLATES.TemplateResponse(
            request,
            "onboarding_auto.html",
            {"providers": saas_oauth.list_providers()},
        )

    @app.post("/onboarding/auto/infer")
    async def auto_inference(request: Request):
        """Run auto-context inference from SNS handles + bio."""
        from hedwig.saas.operator_keys import get_operator_openai_key

        form = await request.form()
        bio = form.get("bio", "")

        # Collect all SNS handles from form
        sns_handles = {}
        for key in form.keys():
            if key.startswith("sns_"):
                platform = key[4:]
                value = form[key].strip()
                if value:
                    sns_handles[platform] = value

        extra_links_raw = form.get("extra_links", "")
        extra_links = [link.strip() for link in extra_links_raw.split("\n") if link.strip()]

        # Use operator's OpenAI key
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

        # Save criteria for the user
        from hedwig.config import CRITERIA_PATH
        import yaml
        if result.get("criteria"):
            with open(CRITERIA_PATH, "w") as f:
                yaml.dump(result["criteria"], f, default_flow_style=False, allow_unicode=True)

        return JSONResponse(result)

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
