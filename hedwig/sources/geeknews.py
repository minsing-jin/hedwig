from __future__ import annotations

from hedwig.models import Platform
from hedwig.sources.base import RSSSource, register_source

GEEKNEWS_RSS = "https://news.hada.io/rss/news"


@register_source
class GeekNewsSource(RSSSource):
    platform = Platform.GEEKNEWS
    plugin_id = "geeknews"
    display_name = "GeekNews (hada.io)"
    feeds = [(GEEKNEWS_RSS, "geeknews")]
    entries_per_feed = 30
