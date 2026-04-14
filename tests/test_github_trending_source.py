from hedwig.models import Platform, RawPost
from hedwig.sources import get_registered_sources, get_source
from hedwig.sources.github_trending import GitHubTrendingSource


def test_github_trending_registers_with_expected_metadata():
    registry = get_registered_sources()

    assert "github_trending" in registry
    assert get_source("github_trending") is GitHubTrendingSource
    assert GitHubTrendingSource.metadata() == {
        "plugin_id": "github_trending",
        "platform": "custom",
        "display_name": "GitHub Trending",
        "plugin_type": "builtin",
        "fetch_method": "scrape",
        "default_limit": 50,
    }


def test_github_trending_is_ai_related_for_ai_repo():
    source = GitHubTrendingSource()
    post = RawPost(
        platform=Platform.CUSTOM,
        external_id="openai/agents-sdk",
        title="openai/agents-sdk",
        url="https://github.com/openai/agents-sdk",
        content="LLM agent framework for RAG, embeddings, and inference workflows",
    )

    assert source._is_ai_related(post) is True


def test_github_trending_is_not_ai_related_for_non_ai_repo():
    source = GitHubTrendingSource()
    post = RawPost(
        platform=Platform.CUSTOM,
        external_id="sharkdp/fd",
        title="sharkdp/fd",
        url="https://github.com/sharkdp/fd",
        content="A fast and user-friendly command-line tool to find files",
    )

    assert source._is_ai_related(post) is False
