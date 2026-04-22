from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Platform(str, Enum):
    """Supported signal source platforms."""
    HACKERNEWS = "hackernews"
    REDDIT = "reddit"
    GEEKNEWS = "geeknews"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    THREADS = "threads"
    YOUTUBE = "youtube"
    BLUESKY = "bluesky"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    POLYMARKET = "polymarket"
    ARXIV = "arxiv"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    PAPERS_WITH_CODE = "papers_with_code"
    WEB_SEARCH = "web_search"
    NEWSLETTER = "newsletter"
    PODCAST = "podcast"
    CUSTOM = "custom"


class UrgencyLevel(str, Enum):
    ALERT = "alert"
    DIGEST = "digest"
    SKIP = "skip"


class VoteType(str, Enum):
    UP = "up"
    DOWN = "down"


class EvolutionCycleType(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"


class SourcePluginType(str, Enum):
    BUILTIN = "builtin"
    CUSTOM = "custom"


class FetchMethod(str, Enum):
    API = "api"
    RSS = "rss"
    SCRAPE = "scrape"
    BROWSER = "browser"


# ---------------------------------------------------------------------------
# Core data models
# ---------------------------------------------------------------------------

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
    exploration_tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Feedback — boolean (upvote/downvote) + optional natural language
# ---------------------------------------------------------------------------

class Feedback(BaseModel):
    """User feedback on a delivered signal."""
    signal_id: str
    vote: VoteType
    natural_language: Optional[str] = None
    source_channel: str = ""  # "slack" or "discord"
    captured_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Criteria — versioned, auto-evolved
# ---------------------------------------------------------------------------

class CriteriaVersion(BaseModel):
    """A versioned snapshot of the user's filtering criteria."""
    version: int
    criteria: dict  # full criteria content
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = "system"  # "onboarding", "daily_evolution", "weekly_evolution", "user"
    diff_from_previous: Optional[str] = None
    fitness_score: Optional[float] = None  # upvote ratio at this version


# ---------------------------------------------------------------------------
# Evolution log — tracks every mutation
# ---------------------------------------------------------------------------

class EvolutionLog(BaseModel):
    """Record of a single evolution cycle (daily or weekly)."""
    cycle_type: EvolutionCycleType
    cycle_number: int
    criteria_version_before: int
    criteria_version_after: int
    mutations_applied: list[str] = Field(default_factory=list)
    fitness_before: Optional[float] = None
    fitness_after: Optional[float] = None
    kept: bool = True
    analysis_summary: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# User memory — long-horizon preference model
# ---------------------------------------------------------------------------

class UserMemory(BaseModel):
    """Persistent user preference snapshot (accumulated weekly)."""
    snapshot_week: str  # e.g. "2026-W15"
    confirmed_interests: list[str] = Field(default_factory=list)
    rejected_topics: list[str] = Field(default_factory=list)
    taste_trajectory: str = ""  # LLM-generated narrative of how preferences shifted
    context: dict = Field(default_factory=dict)  # role, projects, goals
    natural_language_feedback: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Source plugin config
# ---------------------------------------------------------------------------

class SourcePlugin(BaseModel):
    """Configuration for a signal source (builtin or user-added)."""
    plugin_id: str
    platform: Platform
    plugin_type: SourcePluginType = SourcePluginType.BUILTIN
    fetch_method: FetchMethod = FetchMethod.API
    display_name: str = ""
    endpoints: list[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)  # plugin-specific config
    reliability_score: float = 1.0  # auto-evolved, 0.0-1.0
    enabled: bool = True
    added_by: str = "system"  # "system" or "user"
    added_at: datetime = Field(default_factory=datetime.utcnow)
    last_useful_signal_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Briefing — extended with evolution report
# ---------------------------------------------------------------------------

class Briefing(BaseModel):
    """Aggregated output delivered to user."""
    briefing_type: str  # "alert", "daily", "weekly"
    signals: list[ScoredSignal] = Field(default_factory=list)
    summary_text: str = ""
    trend_patterns: list[str] = Field(default_factory=list)
    opportunity_hypotheses: list[str] = Field(default_factory=list)
    exploration_suggestions: list[str] = Field(default_factory=list)
    evolution_report: Optional[str] = None  # weekly only
    generated_at: datetime = Field(default_factory=datetime.utcnow)
