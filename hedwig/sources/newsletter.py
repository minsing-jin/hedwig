from __future__ import annotations

from hedwig.models import Platform
from hedwig.sources.base import RSSSource, register_source

AI_NEWSLETTER_FEEDS = [
    ("https://www.bensbites.com/feed", "bensbites"),
    ("https://www.latent.space/feed", "latent.space"),
    ("https://the-decoder.com/feed/", "the-decoder"),
    ("https://buttondown.com/ainews/rss", "ainews"),
    ("https://jack-clark.net/feed/", "importai"),
    ("https://newsletter.theaiedge.io/feed", "theaiedge"),
    ("https://www.superhuman.ai/feed", "superhuman-ai"),
    ("https://thegradient.pub/rss/", "thegradient"),
]


@register_source
class NewsletterSource(RSSSource):
    """AI newsletters aggregated via RSS."""
    platform = Platform.NEWSLETTER
    plugin_id = "newsletter"
    display_name = "AI Newsletters"
    feeds = AI_NEWSLETTER_FEEDS
    entries_per_feed = 5
