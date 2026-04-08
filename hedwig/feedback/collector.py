"""
Feedback collector — captures boolean votes + optional natural language.

Supports Slack and Discord as input channels.
Designed for the self-evolving recommendation loop:
  signal delivered → user votes up/down → feedback stored → evolution engine consumes
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from hedwig.models import Feedback, VoteType

logger = logging.getLogger(__name__)

# Slack emoji → vote mapping
UPVOTE_EMOJIS = {"thumbsup", "+1", "fire", "star", "heart", "rocket", "100", "eyes"}
DOWNVOTE_EMOJIS = {"thumbsdown", "-1", "no_good", "x", "wastebasket"}


class FeedbackCollector:
    """Collects and stores user feedback from Slack/Discord events."""

    def __init__(self, storage=None):
        self._storage = storage
        self._buffer: list[Feedback] = []

    def from_slack_reaction(self, emoji: str, signal_id: str) -> Feedback | None:
        """Convert a Slack emoji reaction to a Feedback object."""
        if emoji in UPVOTE_EMOJIS:
            vote = VoteType.UP
        elif emoji in DOWNVOTE_EMOJIS:
            vote = VoteType.DOWN
        else:
            return None

        fb = Feedback(
            signal_id=signal_id,
            vote=vote,
            source_channel="slack",
            captured_at=datetime.now(tz=timezone.utc),
        )
        self._buffer.append(fb)
        return fb

    def from_slack_message(self, signal_id: str, text: str) -> Feedback:
        """Convert a Slack thread reply to natural-language feedback."""
        fb = Feedback(
            signal_id=signal_id,
            vote=VoteType.UP,  # thread reply implies interest
            natural_language=text,
            source_channel="slack",
            captured_at=datetime.now(tz=timezone.utc),
        )
        self._buffer.append(fb)
        return fb

    def from_discord_reaction(self, emoji: str, signal_id: str) -> Feedback | None:
        """Convert a Discord reaction to Feedback."""
        if emoji in UPVOTE_EMOJIS or emoji in ("👍", "🔥", "⭐", "❤️", "🚀"):
            vote = VoteType.UP
        elif emoji in DOWNVOTE_EMOJIS or emoji in ("👎", "❌", "🗑️"):
            vote = VoteType.DOWN
        else:
            return None

        fb = Feedback(
            signal_id=signal_id,
            vote=vote,
            source_channel="discord",
            captured_at=datetime.now(tz=timezone.utc),
        )
        self._buffer.append(fb)
        return fb

    def from_direct(self, signal_id: str, vote: VoteType, text: str | None = None) -> Feedback:
        """Direct boolean feedback (for CLI, API, or future native app)."""
        fb = Feedback(
            signal_id=signal_id,
            vote=vote,
            natural_language=text,
            source_channel="direct",
            captured_at=datetime.now(tz=timezone.utc),
        )
        self._buffer.append(fb)
        return fb

    def get_buffer(self) -> list[Feedback]:
        return list(self._buffer)

    def clear_buffer(self):
        self._buffer.clear()

    async def flush(self) -> int:
        """Persist buffered feedback to storage and clear buffer."""
        if not self._buffer:
            return 0
        count = len(self._buffer)
        if self._storage:
            await self._storage.save_feedback_batch(self._buffer)
        logger.info(f"Flushed {count} feedback entries")
        self._buffer.clear()
        return count

    def compute_fitness(self, feedbacks: list[Feedback]) -> float:
        """Compute upvote ratio as fitness metric."""
        if not feedbacks:
            return 0.0
        ups = sum(1 for f in feedbacks if f.vote == VoteType.UP)
        return ups / len(feedbacks)
