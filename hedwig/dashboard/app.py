"""
Hedwig Dashboard — FastAPI web UI for setup, feedback, and monitoring.

Run with:
    python -m hedwig dashboard
    # or
    python -m hedwig.dashboard.app
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from hedwig.dashboard.db_setup import create_tables, get_schema_sql
from hedwig.dashboard.env_manager import EnvManager
from hedwig.dashboard.validator import test_all

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
SAAS_DASHBOARD_STATS_UNAVAILABLE_DETAIL = (
    "Dashboard stats are unavailable in SaaS mode until tenant-aware storage exists"
)
SAAS_SOURCE_SETTINGS_UNAVAILABLE_DETAIL = (
    "Source settings are unavailable in SaaS mode until tenant-aware configuration exists"
)


def create_app(saas_mode: bool = False) -> FastAPI:
    """Create the FastAPI app.

    Args:
        saas_mode: If True, enables multi-tenant routes (landing, auth, billing).
                   If False, single-user mode (original dashboard).
    """
    app = FastAPI(title="Hedwig Dashboard", version="3.0.0")
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

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
            "home.html",
            {
                "request": request,
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
            "setup.html",
            {
                "request": request,
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
        return TEMPLATES.TemplateResponse("onboarding.html", {"request": request})

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
            "signals.html", {"request": request, "signals": signals}
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
            from hedwig.saas.auth import require_auth

            await require_auth(request)
            raise HTTPException(
                status_code=503,
                detail=SAAS_DASHBOARD_STATS_UNAVAILABLE_DETAIL,
            )

        return JSONResponse(_load_dashboard_stats())

    @app.get("/health")
    async def health(request: Request):
        return JSONResponse(
            _load_health_status(started_at=getattr(request.app.state, "started_at", None))
        )

    @app.post("/feedback/{signal_id}/{vote}")
    async def submit_feedback(signal_id: str, vote: str):
        if vote not in ("up", "down"):
            return JSONResponse({"error": "Invalid vote"}, status_code=400)

        from hedwig.feedback import FeedbackCollector
        from hedwig.models import VoteType
        from hedwig.storage.supabase import save_feedback

        collector = FeedbackCollector()
        fb = collector.from_direct(
            signal_id=signal_id,
            vote=VoteType.UP if vote == "up" else VoteType.DOWN,
        )
        save_feedback(fb)

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
            "sources.html", {"request": request, "sources": sources}
        )

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_view(request: Request):
        if saas_mode:
            from hedwig.saas.auth import require_auth

            await require_auth(request)
            raise HTTPException(
                status_code=503,
                detail=SAAS_SOURCE_SETTINGS_UNAVAILABLE_DETAIL,
            )

        from hedwig.sources import get_registered_sources
        from hedwig.sources import settings as source_settings

        registry = get_registered_sources()
        enabled = source_settings.load_source_settings(registry=registry)
        sources = [
            {
                "id": pid,
                "meta": cls.metadata(),
                "enabled": enabled.get(pid, True),
            }
            for pid, cls in sorted(registry.items())
        ]
        return TEMPLATES.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "sources": sources,
                "config_path": str(source_settings.SOURCE_SETTINGS_PATH),
                "saved": request.query_params.get("saved") == "1",
            },
        )

    @app.post("/settings/save")
    async def settings_save(request: Request):
        if saas_mode:
            from hedwig.saas.auth import require_auth

            await require_auth(request)
            raise HTTPException(
                status_code=503,
                detail=SAAS_SOURCE_SETTINGS_UNAVAILABLE_DETAIL,
            )

        from hedwig.sources import get_registered_sources
        from hedwig.sources import settings as source_settings

        form = await request.form()
        selected = set(form.getlist("enabled_sources"))
        registry = get_registered_sources()
        enabled = {
            plugin_id: plugin_id in selected
            for plugin_id in registry
        }
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
            "criteria.html", {"request": request, "content": content}
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
        return TEMPLATES.TemplateResponse("landing.html", {"request": request})

    # ------- Auth pages -------

    @app.get("/signup", response_class=HTMLResponse)
    async def signup_page(request: Request):
        providers = saas_oauth.list_providers()
        return TEMPLATES.TemplateResponse(
            "signup.html",
            {"request": request, "oauth_providers": providers},
        )

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        providers = saas_oauth.list_providers()
        return TEMPLATES.TemplateResponse(
            "login.html",
            {"request": request, "oauth_providers": providers},
        )

    # ------- OAuth flow -------

    @app.get("/auth/callback")
    async def oauth_callback(request: Request):
        """Handle OAuth callback from Supabase. Token comes in URL fragment."""
        return TEMPLATES.TemplateResponse("oauth_callback.html", {"request": request})

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
            "onboarding_auto.html",
            {"request": request, "providers": saas_oauth.list_providers()},
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
        extra_links = [l.strip() for l in extra_links_raw.split("\n") if l.strip()]

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
        user = await saas_auth.require_auth(request)
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
            user = await saas_auth.get_current_user(request)
        except Exception:
            pass

        tokens_limit = TIER_TOKEN_QUOTAS[SubscriptionTier(tier)]
        signals_limit = 50 if tier == "free" else 999_999

        return TEMPLATES.TemplateResponse(
            "billing.html",
            {
                "request": request,
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
            "invite.html",
            {"request": request, "invite_link": invite_link},
        )

    # ------- Multilingual landing -------

    @app.get("/ko", response_class=HTMLResponse)
    async def landing_ko(request: Request):
        return TEMPLATES.TemplateResponse("landing_ko.html", {"request": request})

    @app.get("/zh", response_class=HTMLResponse)
    async def landing_zh(request: Request):
        return TEMPLATES.TemplateResponse("landing_zh.html", {"request": request})

    # ------- Legal pages -------

    @app.get("/terms", response_class=HTMLResponse)
    async def terms_page(request: Request):
        return TEMPLATES.TemplateResponse("terms.html", {"request": request})

    @app.get("/privacy", response_class=HTMLResponse)
    async def privacy_page(request: Request):
        return TEMPLATES.TemplateResponse("privacy.html", {"request": request})

    @app.get("/about", response_class=HTMLResponse)
    async def about_page(request: Request):
        return TEMPLATES.TemplateResponse("about.html", {"request": request})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_recent_signals(limit: int = 20) -> list[dict]:
    try:
        from hedwig.storage.supabase import get_recent_signals
        return get_recent_signals(days=3)[:limit]
    except Exception:
        return []


def _load_latest_signals(limit: int = 100) -> list[dict]:
    try:
        from hedwig.storage.supabase import get_latest_signals
        return get_latest_signals(limit=limit)
    except Exception:
        return []


def _search_signals(query: str, limit: int = 100) -> list[dict]:
    try:
        from hedwig.storage.supabase import search_signals
        return search_signals(query=query, limit=limit)
    except Exception:
        return []


def _load_dashboard_activity_stats() -> dict:
    try:
        from hedwig.storage.supabase import get_dashboard_activity_stats

        return get_dashboard_activity_stats()
    except Exception:
        return {
            "total_signals": 0,
            "upvote_ratio": 0.0,
            "top_5_sources": [],
            "days_active": 0,
        }


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


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


def _load_dashboard_stats() -> dict:
    stats = _load_dashboard_activity_stats()
    return {
        "total_signals": int(stats.get("total_signals", 0) or 0),
        "upvote_ratio": float(stats.get("upvote_ratio", 0.0) or 0.0),
        "evolution_cycles": _count_evolution_cycles(),
        "top_5_sources": list(stats.get("top_5_sources", []) or []),
        "days_active": int(stats.get("days_active", 0) or 0),
    }


def _serialize_signal_export(signal: dict) -> dict:
    try:
        from hedwig.storage.supabase import SIGNAL_EXPORT_FIELDS
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


def _load_health_status(started_at: datetime | None = None) -> dict:
    logs = _load_evolution_logs()
    started = _coerce_timestamp(started_at)
    uptime_seconds = 0
    if started is not None:
        uptime_seconds = max(int((_utcnow() - started).total_seconds()), 0)

    return {
        "last_daily_run": _latest_run_timestamp(logs, "daily"),
        "last_weekly_run": _latest_run_timestamp(logs, "weekly"),
        "evolution_cycle_count": len(logs),
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
