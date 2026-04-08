"""Hedwig source plugins — auto-register all builtin sources on import."""

# Import all builtin sources to trigger @register_source decorators
from hedwig.sources import (  # noqa: F401
    arxiv,
    bluesky,
    geeknews,
    hackernews,
    instagram,
    linkedin,
    newsletter,
    papers_with_code,
    polymarket,
    reddit,
    semantic_scholar,
    threads,
    tiktok,
    twitter,
    web_search,
    youtube,
)

from hedwig.sources.base import (  # noqa: F401
    CustomRSSSource,
    Source,
    create_source,
    get_registered_sources,
    get_source,
    register_source,
)
