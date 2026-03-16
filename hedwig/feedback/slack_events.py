"""
Slack Events listener for feedback collection.

This is a lightweight Flask/FastAPI app that receives Slack events
(emoji reactions + thread replies) and updates criteria accordingly.

Run separately from the cron job:
    python -m hedwig.feedback.slack_events

Requires: SLACK_BOT_TOKEN, a Slack app with Events API enabled,
and subscriptions to reaction_added + message events.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from hedwig.config import CRITERIA_PATH

logger = logging.getLogger(__name__)

# Emoji → sentiment mapping
POSITIVE_EMOJIS = {"thumbsup", "+1", "fire", "star", "heart", "rocket", "100"}
NEGATIVE_EMOJIS = {"thumbsdown", "-1", "no_good", "x"}


def process_reaction(emoji: str, signal_title: str) -> str:
    """Determine sentiment from emoji reaction."""
    if emoji in POSITIVE_EMOJIS:
        return "positive"
    elif emoji in NEGATIVE_EMOJIS:
        return "negative"
    return "neutral"


def update_criteria_from_feedback(feedbacks: list[dict]):
    """Update criteria.yaml based on accumulated feedback patterns.

    This is a simple heuristic: if many positive signals share a theme,
    strengthen that in care_about. If many negative, add to ignore.
    """
    criteria = yaml.safe_load(open(CRITERIA_PATH))

    positive_themes = [f["title"] for f in feedbacks if f.get("sentiment") == "positive"]
    negative_themes = [f["title"] for f in feedbacks if f.get("sentiment") == "negative"]

    if positive_themes:
        feedback_note = f"User liked signals about: {', '.join(positive_themes[:5])}"
        history = criteria.setdefault("feedback_history", [])
        history.append({"type": "positive", "note": feedback_note})
        # Keep last 50 feedback entries
        criteria["feedback_history"] = history[-50:]

    if negative_themes:
        feedback_note = f"User disliked signals about: {', '.join(negative_themes[:5])}"
        history = criteria.setdefault("feedback_history", [])
        history.append({"type": "negative", "note": feedback_note})
        criteria["feedback_history"] = history[-50:]

    with open(CRITERIA_PATH, "w") as f:
        yaml.dump(criteria, f, default_flow_style=False, allow_unicode=True)

    logger.info(f"Criteria updated with {len(positive_themes)} positive, {len(negative_themes)} negative feedback entries")
