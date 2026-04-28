"""AI lab tech blog source coverage."""
from __future__ import annotations


def test_ai_labs_registered():
    from hedwig.sources import get_registered_sources
    assert "ai_labs" in get_registered_sources()


def test_ai_labs_includes_required_feeds():
    """User explicitly asked for OpenAI, Anthropic, Google, TechCrunch."""
    from hedwig.sources.ai_labs import AI_LAB_FEEDS
    urls = [url for url, _ in AI_LAB_FEEDS]
    domains_required = ("openai.com", "anthropic.com", "blog.google",
                         "techcrunch.com")
    for d in domains_required:
        assert any(d in url for url in urls), f"missing {d}"


def test_ai_labs_metadata():
    from hedwig.sources.ai_labs import AILabsSource
    meta = AILabsSource.metadata()
    assert meta["plugin_id"] == "ai_labs"
    assert meta["fetch_method"] == "rss"


def test_ai_labs_count_at_least_eight():
    from hedwig.sources.ai_labs import AI_LAB_FEEDS
    assert len(AI_LAB_FEEDS) >= 8


def test_total_source_count_jumped_to_20():
    from hedwig.sources import get_registered_sources
    assert len(get_registered_sources()) == 20
