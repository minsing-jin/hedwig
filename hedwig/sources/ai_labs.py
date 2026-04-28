"""AI lab tech blogs + TechCrunch — RSS aggregation.

Covers the official posts users explicitly asked for: OpenAI, Anthropic,
Google AI, plus DeepMind / Meta AI / Microsoft / Hugging Face / TechCrunch.

Note on xAI (Grok): https://x.ai/news is a JS-rendered SPA without a
public RSS feed at time of writing. Their announcements actually flow
through @grok / @xai on X — so the existing twitter source covers it
when those handles are tracked. If xAI adds RSS later, append it to
AI_LAB_FEEDS below.
"""
from __future__ import annotations

from hedwig.models import Platform
from hedwig.sources.base import RSSSource, register_source


AI_LAB_FEEDS = [
    # Frontier labs
    ("https://openai.com/news/rss.xml", "openai"),
    ("https://www.anthropic.com/news/rss", "anthropic"),
    ("https://blog.google/technology/ai/rss/", "google-ai"),
    ("https://blog.google/technology/research/rss/", "google-research"),
    ("https://deepmind.google/blog/rss.xml", "deepmind"),
    # Open-weight + tooling
    ("https://huggingface.co/blog/feed.xml", "huggingface"),
    ("https://ai.meta.com/blog/rss/", "meta-ai"),
    ("https://blogs.microsoft.com/ai/feed/", "microsoft-ai"),
    # Tech press
    ("https://techcrunch.com/category/artificial-intelligence/feed/", "techcrunch-ai"),
    ("https://www.theverge.com/ai-artificial-intelligence/rss/index.xml", "theverge-ai"),
    ("https://venturebeat.com/category/ai/feed/", "venturebeat-ai"),
    ("https://www.wired.com/feed/tag/ai/latest/rss", "wired-ai"),
]


@register_source
class AILabsSource(RSSSource):
    """Official AI lab blogs + TechCrunch / Verge / VB / Wired AI RSS."""
    platform = Platform.NEWSLETTER  # nearest existing enum; treated as press
    plugin_id = "ai_labs"
    display_name = "AI Labs + Tech Press"
    feeds = AI_LAB_FEEDS
    entries_per_feed = 4
    default_limit = 30
