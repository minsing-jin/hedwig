from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Platform(str, Enum):
    HACKERNEWS = "hackernews"
    REDDIT = "reddit"
    GEEKNEWS = "geeknews"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    THREADS = "threads"


class UrgencyLevel(str, Enum):
    ALERT = "alert"
    DIGEST = "digest"
    SKIP = "skip"


class RawPost(BaseModel):
    """Raw post collected from a platform before scoring."""
    platform: Platform
    external_id: str
    title: str
    url: str
    content: str = ""
    author: str = ""
    score: int = 0
    comments_count: int = 0
    published_at: datetime = Field(default_factory=datetime.utcnow)
    extra: dict = Field(default_factory=dict)


class ScoredSignal(BaseModel):
    """A signal after LLM scoring."""
    raw: RawPost
    relevance_score: float = 0.0
    urgency: UrgencyLevel = UrgencyLevel.SKIP
    why_relevant: str = ""
    devils_advocate: str = ""
    opportunity_note: str = ""


class Feedback(BaseModel):
    """User feedback from Slack."""
    signal_id: str
    reaction_type: str  # "emoji" or "thread"
    content: str
    sentiment: str = ""  # "positive", "negative", "neutral"
    captured_at: datetime = Field(default_factory=datetime.utcnow)
