"""
Discord webhook delivery for Hedwig signals.

Delivers to three channels:
  - #alerts: urgent signals
  - #daily-brief: daily summary
  - #weekly-brief: weekly deep analysis
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from hedwig.models import ScoredSignal

logger = logging.getLogger(__name__)


async def send_alert(signal: ScoredSignal, webhook_url: Optional[str] = None):
    """Send an individual alert signal to Discord."""
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_ALERTS", "")
    if not url:
        return

    relevance = signal.relevance_score
    color = 0x00FF00 if relevance >= 0.8 else 0xFFFF00 if relevance >= 0.5 else 0xFFFFFF

    embed = {
        "title": signal.raw.title[:256],
        "url": signal.raw.url,
        "color": color,
        "fields": [
            {"name": "관련성", "value": f"{relevance:.0%}", "inline": True},
            {"name": "소스", "value": signal.raw.platform.value, "inline": True},
            {"name": "왜 중요한가", "value": signal.why_relevant[:1024] or "—"},
            {"name": "Devil's Advocate", "value": signal.devils_advocate[:1024] or "—"},
        ],
        "footer": {"text": f"Hedwig | {signal.raw.author}"},
    }

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(url, json={"embeds": [embed]})
        except Exception as e:
            logger.error(f"Discord alert failed: {e}")


async def send_daily_briefing(text: str, webhook_url: Optional[str] = None):
    """Send daily briefing to Discord."""
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_DAILY", "")
    if not url:
        return

    # Discord has 2000 char limit per message; split if needed
    chunks = [text[i : i + 1900] for i in range(0, len(text), 1900)]
    async with httpx.AsyncClient(timeout=10) as client:
        for chunk in chunks:
            try:
                await client.post(url, json={"content": chunk})
            except Exception as e:
                logger.error(f"Discord daily briefing failed: {e}")


async def send_weekly_briefing(text: str, webhook_url: Optional[str] = None):
    """Send weekly briefing to Discord."""
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_WEEKLY", "")
    if not url:
        return

    chunks = [text[i : i + 1900] for i in range(0, len(text), 1900)]
    async with httpx.AsyncClient(timeout=10) as client:
        for chunk in chunks:
            try:
                await client.post(url, json={"content": chunk})
            except Exception as e:
                logger.error(f"Discord weekly briefing failed: {e}")
