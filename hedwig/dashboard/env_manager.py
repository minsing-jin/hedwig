"""
Environment file manager — read/write/validate .env keys.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


class EnvManager:
    """Manage .env file for the dashboard setup wizard."""

    # Required for minimum operation
    REQUIRED_KEYS = {
        "OPENAI_API_KEY": {
            "label": "OpenAI API Key",
            "help": "LLM scoring, evolution, onboarding. Get from platform.openai.com",
            "required": True,
            "secret": True,
        },
        "SUPABASE_URL": {
            "label": "Supabase Project URL",
            "help": "Your Supabase project URL (https://xxx.supabase.co)",
            "required": True,
            "secret": False,
        },
        "SUPABASE_KEY": {
            "label": "Supabase Service Role Key",
            "help": "Service role key from Supabase → Settings → API",
            "required": True,
            "secret": True,
        },
    }

    # At least one delivery channel required
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
    }

    # Optional - expand source coverage
    OPTIONAL_KEYS = {
        "EXA_API_KEY": {
            "label": "Exa API Key (optional)",
            "help": "Semantic web search. 1000 free/month at exa.ai",
            "required": False,
            "secret": True,
        },
        "SCRAPECREATORS_API_KEY": {
            "label": "ScrapeCreators API Key (optional)",
            "help": "Enables TikTok + Instagram collection. scrapecreators.com",
            "required": False,
            "secret": True,
        },
    }

    def __init__(self, env_path: Optional[Path] = None):
        self.env_path = env_path or Path(".env")

    def load(self) -> dict[str, str]:
        """Load current .env values."""
        values: dict[str, str] = {}
        if not self.env_path.exists():
            return values
        for line in self.env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip()
        return values

    def save(self, values: dict[str, str]):
        """Write .env file, preserving comments from .env.example structure."""
        existing = self.load()
        existing.update({k: v for k, v in values.items() if v})

        lines = ["# Hedwig v2.1 environment configuration", ""]

        lines.append("# Required")
        for key in self.REQUIRED_KEYS:
            lines.append(f"{key}={existing.get(key, '')}")
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

        lines.append("# Optional")
        for key in self.OPTIONAL_KEYS:
            lines.append(f"{key}={existing.get(key, '')}")

        self.env_path.write_text("\n".join(lines) + "\n")

    def get_status(self) -> dict:
        """Return current configuration status."""
        values = self.load()

        required_ok = all(values.get(k) for k in self.REQUIRED_KEYS)
        slack_ok = bool(values.get("SLACK_WEBHOOK_ALERTS") and values.get("SLACK_WEBHOOK_DAILY"))
        discord_ok = bool(
            values.get("DISCORD_WEBHOOK_ALERTS")
            and values.get("DISCORD_WEBHOOK_DAILY")
        )
        delivery_ok = slack_ok or discord_ok

        return {
            "required_ok": required_ok,
            "delivery_ok": delivery_ok,
            "slack_configured": slack_ok,
            "discord_configured": discord_ok,
            "ready": required_ok and delivery_ok,
            "keys": values,
        }

    @classmethod
    def all_key_metadata(cls) -> dict:
        """Return metadata for all managed keys."""
        return {**cls.REQUIRED_KEYS, **cls.DELIVERY_KEYS, **cls.OPTIONAL_KEYS}
