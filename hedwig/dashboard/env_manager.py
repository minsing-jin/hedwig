"""
Environment file manager — read/write/validate .env keys.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


class EnvManager:
    """Manage .env file for the dashboard setup wizard."""

    DEFAULT_STORAGE_MODE = "sqlite"

    # Required for minimum local operation
    REQUIRED_KEYS = {
        "OPENAI_API_KEY": {
            "label": "OpenAI API Key",
            "help": "Required for LLM scoring, /chat, algorithm steering, and evolution. Get from platform.openai.com",
            "required": True,
            "secret": True,
        },
    }

    # Optional storage upgrade. Local SQLite is the default first-run mode.
    STORAGE_KEYS = {
        "HEDWIG_STORAGE": {
            "label": "Storage Mode",
            "help": "sqlite for local first-run mode, supabase for hosted/team mode",
            "required": False,
            "secret": False,
        },
        "SUPABASE_URL": {
            "label": "Supabase Project URL (advanced)",
            "help": "Your Supabase project URL (https://xxx.supabase.co)",
            "required": False,
            "secret": False,
        },
        "SUPABASE_KEY": {
            "label": "Supabase Service Role Key (advanced)",
            "help": "Service role key from Supabase → Settings → API",
            "required": False,
            "secret": True,
        },
    }

    # Optional external delivery channels; dashboard /feed is the local default.
    DELIVERY_KEYS = {
        "SLACK_WEBHOOK_ALERTS": {
            "label": "Slack Alerts Webhook",
            "help": "Slack incoming webhook URL for #alerts channel",
            "required": False,
            "secret": True,
            "group": "slack",
        },
        "SLACK_WEBHOOK_DAILY": {
            "label": "Slack Daily Brief Webhook",
            "help": "Slack incoming webhook URL for #daily-brief channel",
            "required": False,
            "secret": True,
            "group": "slack",
        },
        "DISCORD_WEBHOOK_ALERTS": {
            "label": "Discord Alerts Webhook",
            "help": "Discord webhook URL for alerts",
            "required": False,
            "secret": True,
            "group": "discord",
        },
        "DISCORD_WEBHOOK_DAILY": {
            "label": "Discord Daily Webhook",
            "help": "Discord webhook URL for daily briefs",
            "required": False,
            "secret": True,
            "group": "discord",
        },
        "DISCORD_WEBHOOK_WEEKLY": {
            "label": "Discord Weekly Webhook",
            "help": "Discord webhook URL for weekly briefs",
            "required": False,
            "secret": True,
            "group": "discord",
        },
        "SMTP_HOST": {
            "label": "SMTP Host",
            "help": "SMTP server hostname (for example smtp.gmail.com)",
            "required": False,
            "secret": False,
            "group": "smtp",
        },
        "SMTP_PORT": {
            "label": "SMTP Port",
            "help": "SMTP port. Hedwig defaults to 587 when left blank",
            "required": False,
            "secret": False,
            "group": "smtp",
        },
        "SMTP_USER": {
            "label": "SMTP Username",
            "help": "SMTP username for authenticated delivery",
            "required": False,
            "secret": False,
            "group": "smtp",
        },
        "SMTP_PASS": {
            "label": "SMTP Password",
            "help": "SMTP password or app password",
            "required": False,
            "secret": True,
            "group": "smtp",
        },
        "SMTP_FROM": {
            "label": "SMTP From Address",
            "help": "Sender email address for Hedwig alerts",
            "required": False,
            "secret": False,
            "group": "smtp",
        },
    }

    # Optional — expand source coverage / improve normalization
    OPTIONAL_KEYS = {
        "EXA_API_KEY": {
            "label": "Exa API Key (optional)",
            "help": "Semantic web search + on-demand live_search. 1000 free/month at exa.ai",
            "required": False,
            "secret": True,
        },
        "SCRAPECREATORS_API_KEY": {
            "label": "ScrapeCreators API Key (optional)",
            "help": "Enables TikTok + Instagram collection. scrapecreators.com",
            "required": False,
            "secret": True,
        },
        "JINA_API_KEY": {
            "label": "Jina Reader API Key (optional, recommended)",
            "help": "100× rate limit on URL→Markdown normalization. Free at jina.ai/reader",
            "required": False,
            "secret": True,
        },
        "HEDWIG_PODCAST_FEEDS": {
            "label": "Podcast RSS feeds (optional)",
            "help": "Comma-separated 'url|name' list. e.g. https://lexfridman.com/feed/podcast/|Lex",
            "required": False,
            "secret": False,
        },
        "HEDWIG_PODCAST_TRANSCRIBE": {
            "label": "Podcast transcription (0/1)",
            "help": "Set to 1 to auto-transcribe podcasts via OpenAI Whisper API (cost per minute). Requires OPENAI_API_KEY.",
            "required": False,
            "secret": False,
        },
        "HEDWIG_BSKY_HANDLES": {
            "label": "Bluesky handles to track (optional)",
            "help": "Comma-separated. e.g. karpathy.bsky.social,ylecun.bsky.social. Default: 5 AI builders.",
            "required": False,
            "secret": False,
        },
        "HEDWIG_PIPELINE": {
            "label": "Pipeline mode (single|ensemble)",
            "help": "ensemble=Hybrid (default), single=legacy LLM-only. Restart needed.",
            "required": False,
            "secret": False,
        },
        "HEDWIG_DISABLE_EMBEDDINGS": {
            "label": "Force-disable OpenAI embeddings (0/1)",
            "help": "Set to 1 to fall back to Jaccard token-overlap (no API cost).",
            "required": False,
            "secret": False,
        },
    }

    # Optional model/backend tuning. These remain advanced-only on /setup.
    MODEL_BACKEND_KEYS = {
        "OPENAI_MODEL_FAST": {
            "label": "Fast OpenAI model",
            "help": "Used for scoring, chat steering, QA, memory summaries, and lightweight evolution. Default: gpt-4o-mini.",
            "required": False,
            "secret": False,
        },
        "OPENAI_MODEL_DEEP": {
            "label": "Deep OpenAI model",
            "help": "Used for briefings and deeper synthesis. Default: gpt-4o.",
            "required": False,
            "secret": False,
        },
        "HEDWIG_PIPELINE": OPTIONAL_KEYS["HEDWIG_PIPELINE"],
        "HEDWIG_DISABLE_EMBEDDINGS": OPTIONAL_KEYS["HEDWIG_DISABLE_EMBEDDINGS"],
    }

    MODEL_BACKEND_DEFAULTS = {
        "OPENAI_MODEL_FAST": "gpt-4o-mini",
        "OPENAI_MODEL_DEEP": "gpt-4o",
        "HEDWIG_PIPELINE": "ensemble",
        "HEDWIG_DISABLE_EMBEDDINGS": "0",
    }

    def __init__(self, env_path: Optional[Path] = None):
        self.env_path = env_path or Path(".env")

    @classmethod
    def secret_keys(cls) -> set[str]:
        """Return managed environment keys whose values should not be displayed."""
        return {
            key
            for key, meta in cls.all_key_metadata().items()
            if meta.get("secret")
        }

    @classmethod
    def redact_secret_values(cls, values: dict[str, str]) -> dict[str, str]:
        """Return template-safe values with secrets omitted from rendered HTML."""
        redacted = dict(values)
        for key in cls.secret_keys():
            if key in redacted:
                redacted[key] = ""
        return redacted

    def _restrict_env_file_permissions(self):
        """Keep persisted local secrets readable/writable by the current user only."""
        if not self.env_path.exists():
            return
        try:
            self.env_path.chmod(0o600)
        except OSError:
            # Some platforms/filesystems do not support POSIX modes. Saving the
            # managed .env should still succeed; callers can still rely on UI
            # redaction for rendered secrets.
            pass

    def load(self) -> dict[str, str]:
        """Load current .env values."""
        values: dict[str, str] = {}
        if not self.env_path.exists():
            values["HEDWIG_STORAGE"] = self.DEFAULT_STORAGE_MODE
        else:
            for line in self.env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    values[key.strip()] = val.strip()
        if not values.get("HEDWIG_STORAGE"):
            values["HEDWIG_STORAGE"] = self.DEFAULT_STORAGE_MODE
        for key, default in self.MODEL_BACKEND_DEFAULTS.items():
            if not values.get(key):
                values[key] = default
        return values

    def save(self, values: dict[str, str], clear_keys: set[str] | None = None):
        """Write .env file, preserving comments from .env.example structure."""
        existing = self.load()
        for key in clear_keys or set():
            existing[key] = ""
        existing.update({k: v for k, v in values.items() if v})

        lines = ["# Hedwig v3.0 environment configuration", ""]

        lines.append("# Required for local mode")
        for key in self.REQUIRED_KEYS:
            lines.append(f"{key}={existing.get(key, '')}")
        lines.append("")

        lines.append("# Storage — local SQLite by default, Supabase optional")
        for key in self.STORAGE_KEYS:
            default = self.DEFAULT_STORAGE_MODE if key == "HEDWIG_STORAGE" else ""
            lines.append(f"{key}={existing.get(key, default)}")
        lines.append("")

        lines.append("# Delivery — Slack")
        for key, meta in self.DELIVERY_KEYS.items():
            if meta.get("group") == "slack":
                lines.append(f"{key}={existing.get(key, '')}")
        lines.append("")

        lines.append("# Delivery — Discord")
        for key, meta in self.DELIVERY_KEYS.items():
            if meta.get("group") == "discord":
                lines.append(f"{key}={existing.get(key, '')}")
        lines.append("")

        lines.append("# Delivery — SMTP")
        for key, meta in self.DELIVERY_KEYS.items():
            if meta.get("group") == "smtp":
                lines.append(f"{key}={existing.get(key, '')}")
        lines.append("")

        lines.append("# Model/backend — optional advanced controls")
        for key in self.MODEL_BACKEND_KEYS:
            lines.append(f"{key}={existing.get(key, '')}")
        lines.append("")

        lines.append("# Optional")
        for key in self.OPTIONAL_KEYS:
            if key in self.MODEL_BACKEND_KEYS:
                continue
            lines.append(f"{key}={existing.get(key, '')}")

        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        self._restrict_env_file_permissions()
        self.env_path.write_text("\n".join(lines) + "\n")
        self._restrict_env_file_permissions()

    def save_openai_local_setup(
        self,
        openai_key: str,
        values: dict[str, str] | None = None,
        model_backend_values: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Persist the minimum one-shot local setup through the managed .env path."""
        local_clear_keys = {"SUPABASE_URL", "SUPABASE_KEY"}
        payload = {
            key: value
            for key, value in dict(values or {}).items()
            if key not in local_clear_keys
        }
        payload["OPENAI_API_KEY"] = openai_key
        payload["HEDWIG_STORAGE"] = self.DEFAULT_STORAGE_MODE
        payload.update(model_backend_values or self.MODEL_BACKEND_DEFAULTS)
        self.save(payload, clear_keys=local_clear_keys)
        return payload

    def get_status(self) -> dict:
        """Return current configuration status."""
        values = self.load()

        # SQLite local mode only requires OPENAI_API_KEY.
        # Supabase mode requires URL+KEY as well.
        storage_mode = (
            values.get("HEDWIG_STORAGE", self.DEFAULT_STORAGE_MODE).strip().lower()
            or self.DEFAULT_STORAGE_MODE
        )
        supabase_required_keys = ("SUPABASE_URL", "SUPABASE_KEY")
        supabase_required = storage_mode == "supabase"
        missing_required_keys = []
        if not values.get("OPENAI_API_KEY"):
            missing_required_keys.append("OPENAI_API_KEY")
        if supabase_required:
            missing_required_keys.extend(
                key for key in supabase_required_keys if not values.get(key)
            )
        required_ok = not missing_required_keys
        slack_configured = bool(
            values.get("SLACK_WEBHOOK_ALERTS") or values.get("SLACK_WEBHOOK_DAILY")
        )
        discord_configured = bool(
            values.get("DISCORD_WEBHOOK_ALERTS")
            or values.get("DISCORD_WEBHOOK_DAILY")
            or values.get("DISCORD_WEBHOOK_WEEKLY")
        )
        smtp_configured = bool(values.get("SMTP_HOST") and values.get("SMTP_FROM"))
        alert_delivery_ok = bool(
            values.get("SLACK_WEBHOOK_ALERTS")
            or values.get("DISCORD_WEBHOOK_ALERTS")
            or smtp_configured
        )
        daily_delivery_ok = bool(
            values.get("SLACK_WEBHOOK_DAILY")
            or values.get("DISCORD_WEBHOOK_DAILY")
            or smtp_configured
        )
        # In SQLite local mode, delivery is optional — dashboard is the delivery
        if storage_mode in ("sqlite", "local"):
            delivery_ok = True
        else:
            delivery_ok = alert_delivery_ok and daily_delivery_ok

        return {
            "required_ok": required_ok,
            "delivery_ok": delivery_ok,
            "alert_delivery_ok": alert_delivery_ok,
            "daily_delivery_ok": daily_delivery_ok,
            "slack_configured": slack_configured,
            "discord_configured": discord_configured,
            "smtp_configured": smtp_configured,
            "ready": required_ok and delivery_ok,
            "keys": values,
            "storage_mode": storage_mode,
            "supabase_required": supabase_required,
            "supabase_required_keys": list(supabase_required_keys)
            if supabase_required
            else [],
            "missing_required_keys": missing_required_keys,
        }

    @classmethod
    def all_key_metadata(cls) -> dict:
        """Return metadata for all managed keys."""
        return {
            **cls.REQUIRED_KEYS,
            **cls.STORAGE_KEYS,
            **cls.DELIVERY_KEYS,
            **cls.OPTIONAL_KEYS,
            **cls.MODEL_BACKEND_KEYS,
        }
