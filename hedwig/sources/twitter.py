from __future__ import annotations

from hedwig.models import Platform
from hedwig.sources.base import RSSSource, register_source

AI_RSS_FEEDS = [
    ("https://karpathy.github.io/feed.xml", "karpathy"),
    ("https://www.interconnects.ai/feed", "interconnects"),
    ("https://www.latent.space/feed", "latent.space"),
    ("https://simonwillison.net/atom/everything/", "simonwillison"),
    ("https://lilianweng.github.io/index.xml", "lilianweng"),
    ("https://newsletter.theaiedge.io/feed", "theaiedge"),
    ("https://buttondown.com/ainews/rss", "ainews"),
    ("https://jack-clark.net/feed/", "importai"),
    ("https://thegradient.pub/rss/", "thegradient"),
]


@register_source
class TwitterSource(RSSSource):
    """AI signals from blogs/newsletters that mirror X/Twitter discourse."""
    platform = Platform.TWITTER
    plugin_id = "twitter"
    display_name = "X / Twitter (RSS proxy)"
    feeds = AI_RSS_FEEDS
    entries_per_feed = 5
