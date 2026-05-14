from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class AmbientSurface(str, Enum):
    """Post-ranking surfaces that can expose selected items ambiently."""
    CRITICAL = "critical"
    DAILY = "daily"
    WEEKLY = "weekly"
    PWA = "pwa"
    TRAY = "tray"
    NATIVE = "native"


class DeliveryTiming(str, Enum):
    NOW = "now"
    NEXT_DIGEST = "next_digest"
    WEEKLY_DIGEST = "weekly_digest"


class DeliveryChannel(str, Enum):
    DASHBOARD = "dashboard"
    EMAIL = "email"
    SLACK = "slack"
    DISCORD = "discord"
    PWA = "pwa"
    TRAY = "tray"
    NATIVE = "native"


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
    # Always timezone-aware UTC so downstream comparisons don't mix naive/aware.
    published_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
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
# Ambient delivery — post-ranking metadata, not ranking input/output
# ---------------------------------------------------------------------------

def _normalize_ambient_surface_value(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return {
        "native": "tray",
        "native_notification": "tray",
        "notification": "critical",
        "digest": "daily",
    }.get(normalized, normalized)


def _validate_hhmm(value: str) -> str:
    text = str(value or "").strip()
    parts = text.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError("time must use HH:MM format")
    hour, minute = (int(parts[0]), int(parts[1]))
    if hour > 23 or minute > 59:
        raise ValueError("time must use HH:MM format")
    return f"{hour:02d}:{minute:02d}"


VALID_WEEKLY_DIGEST_DAYS = {
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
}


class DeliveryPolicyTimingConfig(BaseModel):
    """Steerable timing defaults for post-ranking ambient delivery."""
    model_config = ConfigDict(extra="forbid")

    critical_timing: DeliveryTiming = DeliveryTiming.NOW
    daily_digest_time: str = "09:00"
    weekly_digest_day: str = "monday"
    weekly_digest_time: str = "09:00"
    timezone: str = "local"
    defer_to_quiet_hours: bool = True

    @field_validator("daily_digest_time", "weekly_digest_time")
    @classmethod
    def validate_digest_time(cls, value: str) -> str:
        return _validate_hhmm(value)

    @field_validator("weekly_digest_day")
    @classmethod
    def validate_weekly_digest_day(cls, value: str) -> str:
        day = str(value or "").strip().lower()
        if day not in VALID_WEEKLY_DIGEST_DAYS:
            raise ValueError("weekly_digest_day must be a weekday name")
        return day


class DeliveryPolicyRepeatConfig(BaseModel):
    """Bounded repeat policy for ambient surfaces."""
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    max_count: int = Field(default=2, ge=0, le=10)
    min_interval_minutes: int = Field(default=240, ge=0, le=10080)
    snooze_minutes: int = Field(default=60, ge=0, le=10080)


class DeliveryPolicyQuietHoursConfig(BaseModel):
    """Quiet-hours steering that gates delivery exposure, not ranking."""
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    start: str = "22:00"
    end: str = "07:00"
    timezone: str = "local"
    allow_critical_override: bool = True

    @field_validator("start", "end")
    @classmethod
    def validate_quiet_hour(cls, value: str) -> str:
        return _validate_hhmm(value)

    @model_validator(mode="after")
    def validate_quiet_hour_range(self) -> "DeliveryPolicyQuietHoursConfig":
        if self.enabled and self.start == self.end:
            raise ValueError("quiet_hours start and end must define a non-empty range")
        return self


class DeliveryPolicyUrgencyConfig(BaseModel):
    """Urgency routing thresholds consumed only after ranking is complete."""
    model_config = ConfigDict(extra="forbid")

    critical_urgencies: list[UrgencyLevel] = Field(default_factory=lambda: [UrgencyLevel.ALERT])
    critical_score_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    daily_score_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    exploration_surface: AmbientSurface = AmbientSurface.PWA

    @model_validator(mode="after")
    def enforce_threshold_order(self) -> "DeliveryPolicyUrgencyConfig":
        if self.critical_score_threshold < self.daily_score_threshold:
            raise ValueError("critical_score_threshold must be greater than or equal to daily_score_threshold")
        return self


class DeliveryPolicyConfig(BaseModel):
    """Versioned schema for steerable ambient delivery policy config."""
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    schema_version: str = "delivery_policy_config.v1"
    enabled: bool = True
    surfaces: list[AmbientSurface] = Field(
        default_factory=lambda: [
            AmbientSurface.CRITICAL,
            AmbientSurface.DAILY,
            AmbientSurface.WEEKLY,
            AmbientSurface.PWA,
            AmbientSurface.TRAY,
        ]
    )
    preferred_surfaces: list[AmbientSurface] = Field(default_factory=lambda: [AmbientSurface.DAILY])
    channels: list[DeliveryChannel] = Field(
        default_factory=lambda: [
            DeliveryChannel.DASHBOARD,
            DeliveryChannel.EMAIL,
            DeliveryChannel.SLACK,
            DeliveryChannel.DISCORD,
            DeliveryChannel.PWA,
            DeliveryChannel.TRAY,
        ]
    )
    default_channel: DeliveryChannel = DeliveryChannel.DASHBOARD
    timing: DeliveryPolicyTimingConfig = Field(default_factory=DeliveryPolicyTimingConfig)
    repeat: DeliveryPolicyRepeatConfig = Field(default_factory=DeliveryPolicyRepeatConfig)
    quiet_hours: DeliveryPolicyQuietHoursConfig = Field(default_factory=DeliveryPolicyQuietHoursConfig)
    urgency: DeliveryPolicyUrgencyConfig = Field(default_factory=DeliveryPolicyUrgencyConfig)
    policy_layer: str = "post_ranking_delivery"
    post_ranking_only: bool = True
    ranking_input: bool = False
    mutates_scores: bool = False
    mutates_rank_identity: bool = False

    @field_validator("surfaces", "preferred_surfaces", mode="before")
    @classmethod
    def normalize_surfaces(cls, value: object) -> list[str]:
        values = value if isinstance(value, list) else [value]
        normalized: list[str] = []
        for item in values:
            surface = _normalize_ambient_surface_value(item)
            if surface and surface not in normalized:
                normalized.append(surface)
        return normalized

    @model_validator(mode="after")
    def enforce_post_ranking_policy_boundary(self) -> "DeliveryPolicyConfig":
        if not self.post_ranking_only or self.ranking_input:
            raise ValueError("delivery policy config must remain post-ranking metadata")
        if self.mutates_scores or self.mutates_rank_identity:
            raise ValueError("delivery policy config cannot mutate ranking scores or rank identity")
        if self.default_channel not in self.channels:
            raise ValueError("default_channel must be included in channels")
        surface_values = {str(surface) for surface in self.surfaces}
        preferred_values = {str(surface) for surface in self.preferred_surfaces}
        if not preferred_values.issubset(surface_values):
            raise ValueError("preferred_surfaces must be enabled in surfaces")
        return self

class DeliveryRankingSnapshot(BaseModel):
    """Immutable score/rank values observed before delivery routing."""
    input_ensemble_rank: Optional[int] = None
    input_order: Optional[int] = None
    rank_identifiers: dict = Field(default_factory=dict)
    input_ensemble_score: float = 0.0
    input_final_score: float = 0.0
    immutable: bool = True


class DeliveryExplanationMetadata(BaseModel):
    """Display-only delivery explanation with no score-like authority."""
    model_config = ConfigDict(extra="forbid")

    text: str = ""
    display_only: bool = True
    ranking_input: bool = False
    score_like_authority: bool = False


class DeliveryDecisionMetadata(BaseModel):
    """Post-ranking delivery routing metadata for an already-ranked item."""
    signal_id: str = ""
    surface: AmbientSurface
    canonical_surface: str = ""
    eligible_surfaces: list[AmbientSurface] = Field(default_factory=list)
    preferred_surfaces: list[AmbientSurface] = Field(default_factory=list)
    surface_preference: dict = Field(default_factory=dict)
    channel: DeliveryChannel = DeliveryChannel.DASHBOARD
    timing: DeliveryTiming
    urgency: str = ""
    scheduling_priority: dict = Field(default_factory=dict)
    repeat: bool = True
    repeat_rule: dict = Field(default_factory=dict)
    ranking_snapshot: DeliveryRankingSnapshot = Field(default_factory=DeliveryRankingSnapshot)
    explanation: DeliveryExplanationMetadata = Field(default_factory=DeliveryExplanationMetadata)
    delivery_schedule: dict = Field(default_factory=dict)
    eligible_now: bool = True
    defer_reason: str = ""
    reason: str = "post-ranking delivery policy v1"
    emitted_event: dict = Field(default_factory=dict)
    decision_layer: str = "post_ranking_delivery"
    post_ranking: bool = True
    does_not_mutate_ensemble: bool = True
    ranking_input: bool = False
    ranking_output: bool = False


class AmbientPreLayerRankingSnapshot(BaseModel):
    """Immutable rank identity copied from the ranking layer for display."""
    ensemble_score: float = 0.0
    final_score: float = 0.0
    input_rank: Optional[int] = None
    input_order: Optional[int] = None
    rank_identifiers: dict = Field(default_factory=dict)
    immutable: bool = True


class AmbientDeliveryItem(BaseModel):
    """Small, surface-safe item shape consumed by ambient delivery clients."""
    id: str
    title: str = ""
    url: str = ""
    reason: str = ""
    platform: Optional[str] = None
    author: Optional[str] = None
    surface: AmbientSurface
    delivery_timing: DeliveryTiming
    delivery_channel: DeliveryChannel
    ensemble_score: float = 0.0
    final_score: float = 0.0
    pre_layer_ranking: AmbientPreLayerRankingSnapshot
    delivery_decision: DeliveryDecisionMetadata
    explanation: DeliveryExplanationMetadata = Field(default_factory=DeliveryExplanationMetadata)
    why_relevant: str = ""
    post_ranking_boundary: dict = Field(default_factory=lambda: {
        "layer": "ambient_delivery",
        "delivery_decisions_are_metadata": True,
        "mutates_scores": False,
        "mutates_rank_identity": False,
        "explanation_is_display_only": True,
    })

    @model_validator(mode="after")
    def enforce_display_only_explanation(self) -> "AmbientDeliveryItem":
        if (
            not self.explanation.display_only
            or self.explanation.ranking_input
            or self.explanation.score_like_authority
        ):
            raise ValueError("ambient explanations must remain display-only metadata")
        if self.delivery_decision.ranking_input or self.delivery_decision.ranking_output:
            raise ValueError("ambient delivery decisions cannot be ranking inputs or outputs")
        if not self.pre_layer_ranking.immutable:
            raise ValueError("ambient items require immutable pre-layer rank identity")
        return self


class AmbientDeliveryItemSet(BaseModel):
    """Versioned contract for small algorithm-selected ambient item batches."""
    schema_version: str = "ambient_delivery_item_set.v1"
    surface: AmbientSurface
    generated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    limit: int
    count: int
    items: list[AmbientDeliveryItem] = Field(default_factory=list)
    post_ranking_boundary: dict = Field(default_factory=lambda: {
        "layer": "ambient_delivery",
        "delivery_decisions_are_metadata": True,
        "mutates_scores": False,
        "mutates_rank_identity": False,
        "immutable_fields": ["ensemble_score", "final_score", "pre_layer_ranking"],
        "explanation_is_display_only": True,
    })

    @model_validator(mode="after")
    def enforce_small_bounded_item_set(self) -> "AmbientDeliveryItemSet":
        if self.limit < 1 or self.limit > 50:
            raise ValueError("ambient item-set limit must be between 1 and 50")
        if self.count != len(self.items):
            raise ValueError("ambient item-set count must match items length")
        if len(self.items) > self.limit:
            raise ValueError("ambient item-set cannot exceed its limit")
        return self


# ---------------------------------------------------------------------------
# Feedback — boolean (upvote/downvote) + optional natural language
# ---------------------------------------------------------------------------

class Feedback(BaseModel):
    """User feedback on a delivered signal."""
    signal_id: str
    vote: VoteType
    natural_language: Optional[str] = None
    source_channel: str = ""  # "slack" | "discord" | "email" | "dashboard" | "feed"
    delivered_signal_id: Optional[int] = None   # G6: cross-channel binding
    captured_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


# ---------------------------------------------------------------------------
# Criteria — versioned, auto-evolved
# ---------------------------------------------------------------------------

class Judgment(BaseModel):
    """First-class LLM judgment artifact (seed.yaml ontology, G1).

    Decouples LLM scoring from inline signal columns so each judgment can
    be traced to the criteria.version + interpretation_style.id that
    produced it. Enables cross-version fitness attribution.
    """
    signal_id: str
    score: float
    urgency: UrgencyLevel
    rationale: Optional[str] = None
    devil_advocate: Optional[str] = None
    opportunity_note: Optional[str] = None
    confidence: Optional[float] = None
    exploration_tags: list[str] = Field(default_factory=list)
    criteria_version: Optional[int] = None
    interpretation_style_id: Optional[str] = None


class InterpretationStyle(BaseModel):
    """First-class artifact controlling HOW signals are explained.

    Evolved weekly independently from criteria (seed.yaml ontology + AC 4).
    Each Judgment records which interpretation_style_id produced it so
    fitness attribution works across style versions.
    """
    id: str
    version: int
    tone: str = "mixed"        # technical | business | mixed
    depth: str = "deep"        # surface | deep
    jargon_level: str = "medium"  # low | medium | high
    prompt_template: str = ""
    parent_version: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


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
