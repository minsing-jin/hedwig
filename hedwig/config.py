from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CRITERIA_PATH = PROJECT_ROOT / "criteria.yaml"


def load_criteria() -> dict:
    with open(CRITERIA_PATH) as f:
        return yaml.safe_load(f)


# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL_FAST = os.getenv("OPENAI_MODEL_FAST", "gpt-4o-mini")
OPENAI_MODEL_DEEP = os.getenv("OPENAI_MODEL_DEEP", "gpt-4o")

# Slack
SLACK_WEBHOOK_ALERTS = os.getenv("SLACK_WEBHOOK_ALERTS", "")
SLACK_WEBHOOK_DAILY = os.getenv("SLACK_WEBHOOK_DAILY", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# Reddit
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")


def check_required_keys(mode: str = "full") -> list[str]:
    """Check which required keys are missing. Returns list of missing key names."""
    missing = []
    if mode in ("full", "score"):
        if not OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
    if mode == "full":
        if not SLACK_WEBHOOK_ALERTS:
            missing.append("SLACK_WEBHOOK_ALERTS")
        if not SLACK_WEBHOOK_DAILY:
            missing.append("SLACK_WEBHOOK_DAILY")
        if not SUPABASE_URL:
            missing.append("SUPABASE_URL")
        if not SUPABASE_KEY:
            missing.append("SUPABASE_KEY")
    return missing
