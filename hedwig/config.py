from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CRITERIA_PATH = PROJECT_ROOT / "criteria.yaml"
EVOLUTION_LOG_PATH = PROJECT_ROOT / "evolution_log.jsonl"
USER_MEMORY_PATH = PROJECT_ROOT / "user_memory.jsonl"


def load_criteria() -> dict:
    if not CRITERIA_PATH.exists():
        return {}
    with open(CRITERIA_PATH) as f:
        return yaml.safe_load(f) or {}


# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL_FAST = os.getenv("OPENAI_MODEL_FAST", "gpt-4o-mini")
OPENAI_MODEL_DEEP = os.getenv("OPENAI_MODEL_DEEP", "gpt-4o")

# Slack
SLACK_WEBHOOK_ALERTS = os.getenv("SLACK_WEBHOOK_ALERTS", "")
SLACK_WEBHOOK_DAILY = os.getenv("SLACK_WEBHOOK_DAILY", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")

# Discord
DISCORD_WEBHOOK_ALERTS = os.getenv("DISCORD_WEBHOOK_ALERTS", "")
DISCORD_WEBHOOK_DAILY = os.getenv("DISCORD_WEBHOOK_DAILY", "")
DISCORD_WEBHOOK_WEEKLY = os.getenv("DISCORD_WEBHOOK_WEEKLY", "")

# SMTP
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = os.getenv("SMTP_PORT", "587")
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# Reddit
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")

# External APIs (optional)
EXA_API_KEY = os.getenv("EXA_API_KEY", "")
SCRAPECREATORS_API_KEY = os.getenv("SCRAPECREATORS_API_KEY", "")


def smtp_alerts_configured() -> bool:
    """SMTP is usable for alert delivery when host and sender are configured."""
    return bool(SMTP_HOST and SMTP_FROM)


def _alert_delivery_configured() -> bool:
    return bool(SLACK_WEBHOOK_ALERTS or DISCORD_WEBHOOK_ALERTS or smtp_alerts_configured())


def _daily_delivery_configured() -> bool:
    return bool(SLACK_WEBHOOK_DAILY or DISCORD_WEBHOOK_DAILY or smtp_alerts_configured())


def check_required_keys(mode: str = "full") -> list[str]:
    """Check which required keys are missing. Returns list of missing key names."""
    missing = []
    if mode in ("full", "score", "evolve", "daily"):
        if not OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
    if mode in ("full", "daily"):
        if not _alert_delivery_configured():
            missing.append("SLACK_WEBHOOK_ALERTS or DISCORD_WEBHOOK_ALERTS or SMTP_HOST/SMTP_FROM")
        if not _daily_delivery_configured():
            missing.append("SLACK_WEBHOOK_DAILY or DISCORD_WEBHOOK_DAILY or SMTP_HOST/SMTP_FROM")
        if not SUPABASE_URL:
            missing.append("SUPABASE_URL")
        if not SUPABASE_KEY:
            missing.append("SUPABASE_KEY")
    return missing
