from __future__ import annotations

from hedwig.models import Platform
from hedwig.sources.base import RSSSource, register_source

THREADS_RSS_FEEDS = [
    ("https://www.bensbites.com/feed", "bensbites"),
    ("https://www.superhuman.ai/feed", "superhuman-ai"),
    ("https://techcrunch.com/category/artificial-intelligence/feed/", "techcrunch-ai"),
    ("https://the-decoder.com/feed/", "the-decoder"),
]


@register_source
class ThreadsSource(RSSSource):
    """AI signals from indie newsletters and tech press."""
    platform = Platform.THREADS
    plugin_id = "threads"
    display_name = "Threads (newsletters)"
    feeds = THREADS_RSS_FEEDS
    entries_per_feed = 5
