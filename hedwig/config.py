from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CRITERIA_PATH = PROJECT_ROOT / "criteria.yaml"
ALGORITHM_PATH = PROJECT_ROOT / "algorithm.yaml"
EVOLUTION_LOG_PATH = PROJECT_ROOT / "evolution_log.jsonl"
ALGORITHM_LOG_PATH = PROJECT_ROOT / "algorithm_log.jsonl"
USER_MEMORY_PATH = PROJECT_ROOT / "user_memory.jsonl"


def load_criteria() -> dict:
    if not CRITERIA_PATH.exists():
        return {}
    with open(CRITERIA_PATH) as f:
        return yaml.safe_load(f) or {}


_ALGORITHM_VERSION_SEEDED = False


def load_algorithm_config() -> dict:
    """Load algorithm.yaml — user-owned recommendation algorithm definition.

    Peer to criteria.yaml. Defines the Hybrid Ensemble (retrieval + ranking)
    and Meta-Evolution settings. See docs/VISION_v3.md.

    Side effect: on first call with a non-empty algorithm.yaml, seed the
    ``algorithm_versions`` table with the baseline v1 so the Evolution
    timeline has an origin marker even before Meta-Evolution runs.
    """
    if not ALGORITHM_PATH.exists():
        return {}
    with open(ALGORITHM_PATH) as f:
        cfg = yaml.safe_load(f) or {}

    _seed_algorithm_version_once(cfg)
    return cfg


def _seed_algorithm_version_once(cfg: dict) -> None:
    global _ALGORITHM_VERSION_SEEDED
    if _ALGORITHM_VERSION_SEEDED or not cfg:
        return
    _ALGORITHM_VERSION_SEEDED = True
    try:
        from hedwig.storage import get_algorithm_history, save_algorithm_version
        if get_algorithm_history(limit=1):
            return
        save_algorithm_version(
            version=int(cfg.get("version", 1)),
            config=cfg,
            created_by="seed",
            origin=str(cfg.get("origin", "initial_default")),
        )
    except Exception:
        # Never let version-seeding failure block the pipeline
        pass


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
    """Check which truly-required keys are missing.

    Only OPENAI_API_KEY is strictly required — it powers the LLM scorer,
    briefer, and evolution engine, all of which are the core value.

    Supabase and delivery (Slack/Discord/SMTP) are *optional*: without them,
    the pipeline still collects, scores, stores locally (SQLite), and shows
    results in the dashboard. Their absence is surfaced via warnings in
    ``check_optional_keys``, not as a hard failure.
    """
    missing = []
    if mode in ("full", "score", "evolve", "daily"):
        if not OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
    return missing


def check_optional_keys(mode: str = "full") -> list[str]:
    """Return a list of optional capability gaps for user-facing warnings."""
    gaps: list[str] = []
    if mode in ("full", "daily"):
        if not _alert_delivery_configured():
            gaps.append("alert delivery (set SLACK_WEBHOOK_ALERTS / DISCORD_WEBHOOK_ALERTS / SMTP_*)")
        if not _daily_delivery_configured():
            gaps.append("daily-brief delivery (set SLACK_WEBHOOK_DAILY / DISCORD_WEBHOOK_DAILY / SMTP_*)")
    return gaps
