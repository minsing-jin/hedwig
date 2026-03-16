from __future__ import annotations

import logging

import httpx

from hedwig.config import SLACK_WEBHOOK_ALERTS, SLACK_WEBHOOK_DAILY
from hedwig.models import ScoredSignal

logger = logging.getLogger(__name__)


def _format_signal_block(signal: ScoredSignal) -> dict:
    """Format a single signal as a Slack Block Kit message."""
    platform = signal.raw.platform.value.upper()
    score_bar = "🟢" if signal.relevance_score >= 0.7 else "🟡" if signal.relevance_score >= 0.4 else "⚪"

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{score_bar} *[{platform}]* <{signal.raw.url}|{signal.raw.title}>\n"
                    f"relevance: `{signal.relevance_score:.2f}` | urgency: `{signal.urgency.value}`"
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"💡 *왜 중요한가:* {signal.why_relevant}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"😈 *반대 관점:* {signal.devils_advocate}",
            },
        },
        {"type": "divider"},
    ]
    return {"blocks": blocks}


async def send_alert(signal: ScoredSignal) -> bool:
    """Send a single high-priority signal to #alerts channel."""
    payload = _format_signal_block(signal)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(SLACK_WEBHOOK_ALERTS, json=payload)
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")
        return False


async def send_daily_briefing(briefing_text: str) -> bool:
    """Send daily briefing to #daily-brief channel."""
    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "📋 Hedwig Daily Briefing"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": briefing_text[:3000]},
            },
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(SLACK_WEBHOOK_DAILY, json=payload)
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"Failed to send daily briefing: {e}")
        return False


async def send_weekly_briefing(briefing_text: str) -> bool:
    """Send weekly briefing to #daily-brief channel (same webhook, different format)."""
    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "📊 Hedwig Weekly Briefing"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": briefing_text[:3000]},
            },
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(SLACK_WEBHOOK_DAILY, json=payload)
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"Failed to send weekly briefing: {e}")
        return False
