from __future__ import annotations

from hedwig.models import Platform
from hedwig.sources.base import RSSSource, register_source

LINKEDIN_RSS_FEEDS = [
    ("https://blog.google/technology/ai/rss/", "google-ai"),
    ("https://openai.com/blog/rss.xml", "openai-blog"),
    ("https://ai.meta.com/blog/rss/", "meta-ai"),
    ("https://www.deeplearning.ai/blog/feed/", "deeplearning.ai"),
    ("https://huggingface.co/blog/feed.xml", "huggingface"),
]


@register_source
class LinkedInSource(RSSSource):
    """AI signals from corporate blogs commonly shared on LinkedIn."""
    platform = Platform.LINKEDIN
    plugin_id = "linkedin"
    display_name = "LinkedIn (corporate blogs)"
    feeds = LINKEDIN_RSS_FEEDS
    entries_per_feed = 5
